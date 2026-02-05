# mcp_runtime/workflow.py

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
    Phase 6.4:
    - Agent-aware mutation execution
    - Runtime safety enforcement
    - Auto-mode gating
    - Rollback-safe execution
    """

    def __init__(self, mcp_server):
        self.mcp = mcp_server

    def run(
        self,
        steps: List[Dict[str, Any]],
        session=None,
    ) -> Dict[str, Any]:

        validate_workflow_schema(
            {"version": "1.0", "steps": steps},
            mutation_registry=self.mcp.mutations,
        )

        workflow_id = f"wf-{uuid4().hex[:8]}"
        results = []
        rollback_stack = []
        rollback_results = []

        current_context: Dict[str, Any] = {}
        safe_context = deepcopy(current_context)

        agent = getattr(session, "agent", None)

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
                value = _get_by_path({"context": current_context}, condition["path"])
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

                # Re-enforce safety envelope
                envelope = SafetyEnvelope(agent)
                envelope.enforce({"risk": "SAFE_MUTATE"})

                # Capture safe context ONCE (before first mutation)
                if not rollback_stack:
                    safe_context = deepcopy(current_context)

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

                if rollback:
                    rollback_stack.append(rollback)

            except Exception as e:
                # ----------------------------
                # 🔁 Rollback (LIFO)
                # ----------------------------
                for rb in reversed(rollback_stack):
                    rb_tool = rb["tool"]
                    try:
                        rb_result = self.mcp.invoke(
                            tool_name=rb_tool,
                            inputs=rb.get("inputs", {}),
                            context=safe_context,
                            session=session,
                        )
                        rollback_results.append({
                            "tool": rb_tool,
                            "status": rb_result["status"],
                        })
                    except Exception as re:
                        rollback_results.append({
                            "tool": rb_tool,
                            "error": str(re),
                        })

                return {
                    "workflow_id": workflow_id,
                    "steps": results,
                    "failed_step": idx,
                    "error": str(e),
                    "rollback_executed": True,
                    "rollback_results": rollback_results,
                    "final_context": safe_context,
                }

        return {
            "workflow_id": workflow_id,
            "steps": results,
            "final_context": current_context,
        }
