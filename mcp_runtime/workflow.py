from typing import List, Dict, Any
from uuid import uuid4
from copy import deepcopy

from mcp_runtime.workflow_schema import validate_workflow_schema
from mcp_runtime.safety.envelope import SafetyEnvelope, SafetyEnvelopeError


def _get_by_path(data: Dict, path: str):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


class MCPWorkflowRunner:
    """
    Phase 6.5:
    - Agent-aware mutation execution
    - Runtime safety enforcement
    - Auto-mode gating
    - Rollback-safe execution
    - Mutation ledger recording
    """

    def __init__(self, mcp_server):
        self.mcp = mcp_server

    def run(
        self,
        steps: List[Dict[str, Any]],
        session=None,
    ) -> Dict[str, Any]:

        # ----------------------------
        # Schema validation
        # ----------------------------
        validate_workflow_schema(
            {"version": "1.0", "steps": steps},
            mutation_registry=self.mcp.mutations,
        )

        workflow_id = f"wf-{uuid4().hex[:8]}"

        results: List[Dict] = []
        mutations: List[Dict] = []
        rollback_stack: List[Dict] = []
        rollback_results: List[Dict] = []

        current_context: Dict[str, Any] = {}
        safe_context = deepcopy(current_context)

        agent = getattr(session, "agent", None)
        session_id = getattr(session, "session_id", None)

        # ----------------------------
        # Execute steps
        # ----------------------------
        for idx, step in enumerate(steps):
            tool = step["tool"]
            mode = step.get("mode", "read")
            inputs = step.get("inputs", {})
            step_context = step.get("context", {})
            rollback = step.get("rollback")
            condition = step.get("when")

            # ----------------------------
            # Conditional execution
            # ----------------------------
            if condition:
                value = _get_by_path(
                    {"context": current_context},
                    condition["path"],
                )
                if value != condition["equals"]:
                    results.append({
                        "step": idx,
                        "tool": tool,
                        "skipped": True,
                    })
                    continue

            # ----------------------------
            # 🔒 Mutation policy gate
            # ----------------------------
            if mode == "mutate":
                if not agent:
                    raise RuntimeError("Mutation requires an agent")

                if not agent.allow_mutation:
                    raise SafetyEnvelopeError(
                        f"Agent '{agent.name}' is not allowed to mutate"
                    )

                if self.mcp.auto_mode and not agent.auto_mode_allowed:
                    raise SafetyEnvelopeError(
                        f"Agent '{agent.name}' is not allowed in auto mode"
                    )

                envelope = SafetyEnvelope(agent)
                envelope.enforce({"risk": "SAFE_MUTATE"})

                # Capture safe context ONCE (before first mutation)
                if not rollback_stack:
                    safe_context = deepcopy(current_context)

                # 🔑 FIX: register rollback intent EARLY
                if rollback:
                    rollback_stack.append(rollback)

                # Record mutation intent (attempted)
                entry = self.mcp.mutation_ledger.record(
                    tool=tool,
                    agent=agent.name,
                    session_id=session_id,
                    rollback_tool=rollback.get("tool") if rollback else None,
                    status="attempted",
                )
                mutations.append(entry)

            # ----------------------------
            # Tool execution
            # ----------------------------
            try:
                r = self.mcp.invoke(
                    tool_name=tool,
                    inputs=inputs,
                    context=step_context,
                    session=session,
                )

                current_context = r["context"]

                results.append({
                    "step": idx,
                    "tool": tool,
                    "mode": mode,
                    "status": r["status"],
                })

                # Mark successful mutation
                if mode == "mutate":
                    entry["status"] = "executed"

            except Exception as e:
                # ----------------------------
                # 🔁 Rollback (LIFO)
                # ----------------------------
                for rb in reversed(rollback_stack):
                    rb_tool = rb["tool"]
                    try:
                        self.mcp.invoke(
                            tool_name=rb_tool,
                            inputs=rb.get("inputs", {}),
                            context=safe_context,
                            session=session,
                        )

                        self.mcp.mutation_ledger.record(
                            tool=rb_tool,
                            agent=agent.name if agent else "system",
                            session_id=session_id,
                            rollback_tool=None,
                            status="rollback",
                        )

                        rollback_results.append({
                            "tool": rb_tool,
                            "status": "rollback",
                        })


                    except Exception as re:
                        rollback_results.append({
                            "tool": rb_tool,
                            "status": "rollback_failed",
                            "error": str(re),
                        })

                return {
                    "workflow_id": workflow_id,
                    "steps": results,
                    "mutations": mutations,
                    "failed_step": idx,
                    "error": str(e),
                    "rollback_executed": True,
                    "rollback_results": rollback_results,
                    "final_context": safe_context,
                }

        # ----------------------------
        # Successful completion
        # ----------------------------
        return {
            "workflow_id": workflow_id,
            "steps": results,
            "mutations": mutations,
            "final_context": current_context,
        }
