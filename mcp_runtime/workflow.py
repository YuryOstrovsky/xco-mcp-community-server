# mcp_runtime/workflow.py

from typing import List, Dict, Any
from uuid import uuid4

from mcp_runtime.workflow_schema import validate_workflow_schema


def _get_by_path(data: Dict, path: str):
    """
    Safely resolve dot-paths like: context.fabric.name
    """
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


class MCPWorkflowRunner:
    """
    Phase 3.4 → 6.0:
    - Sequential execution of MCP tools
    - Conditional execution (when)
    - Fail-fast semantics
    - Rollback scaffolding (NOT executed yet)
    - Workflow schema validation
    - Explicit mutation blocking (Phase 6.0)
    """

    def __init__(self, mcp_server):
        self.mcp = mcp_server

    def run(
        self,
        steps: List[Dict[str, Any]],
        session=None,
    ) -> Dict[str, Any]:

        # --------------------------------------------------
        # Phase 6.0 — Schema validation (single entry point)
        # --------------------------------------------------
        validate_workflow_schema(
            {
                "version": "1.0",
                "steps": steps,
            },
            mutation_registry=self.mcp.mutations,
        )


        # --------------------------------------------------
        # Phase 6.0 — Block mutation execution
        # --------------------------------------------------
        for idx, step in enumerate(steps):
            if step.get("mode", "read") == "mutate":
                raise RuntimeError(
                    "Mutation execution is blocked in Phase 6.0"
                )

        workflow_id = f"wf-{uuid4().hex[:8]}"

        results = []
        current_context: Dict[str, Any] = {}
        rollback_plan = []

        # --------------------------------------------------
        # Execute steps sequentially
        # --------------------------------------------------
        for idx, step in enumerate(steps):
            tool = step.get("tool")
            inputs = step.get("inputs", {})
            step_context = step.get("context", {})
            rollback = step.get("rollback")
            condition = step.get("when")

            # ---- Conditional execution ----
            if condition:
                value = _get_by_path(
                    {"context": current_context},
                    condition["path"]
                )
                if value != condition.get("equals"):
                    results.append({
                        "step": idx,
                        "tool": tool,
                        "skipped": True,
                        "reason": {
                            "path": condition["path"],
                            "expected": condition.get("equals"),
                            "actual": value,
                        },
                    })
                    continue

            try:
                r = self.mcp.invoke(
                    tool_name=tool,
                    inputs=inputs,
                    context=step_context,
                    session=session,
                )

                # Update rolling context
                current_context = r["context"]

                results.append({
                    "step": idx,
                    "tool": tool,
                    "status": r["status"],
                    "context": r["context"],
                    "meta": r["meta"],
                    "explain": r.get("explain"),
                })

                # Rollback is recorded, not executed
                if rollback:
                    rollback_plan.append({
                        "step": idx,
                        "rollback": rollback,
                    })

            except Exception as e:
                return {
                    "workflow_id": workflow_id,
                    "steps": results,
                    "failed_step": idx,
                    "error": {
                        "type": type(e).__name__,
                        "message": str(e),
                    },
                    "final_context": current_context,
                    "rollback_plan": rollback_plan,
                    "meta": {
                        "correlation_id": (
                            session.correlation_id if session else None
                        ),
                    },
                }

        # --------------------------------------------------
        # Successful completion
        # --------------------------------------------------
        return {
            "workflow_id": workflow_id,
            "steps": results,
            "final_context": current_context,
            "meta": {
                "correlation_id": (
                    session.correlation_id if session else None
                ),
            },
        }
