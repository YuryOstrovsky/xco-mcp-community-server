# mcp_runtime/workflow.py

from typing import List, Dict, Any
from uuid import uuid4
from copy import deepcopy

from mcp_runtime.workflow_schema import validate_workflow_schema


def _get_by_path(data: Dict, path: str):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


class MCPWorkflowRunner:
    """
    Phase 6.3.4:
    - Deterministic rollback
    - LIFO rollback order
    - Rollback context isolation
    """

    def __init__(self, mcp_server):
        self.mcp = mcp_server

    def run(
        self,
        steps: List[Dict[str, Any]],
        session=None,
    ) -> Dict[str, Any]:

        validate_workflow_schema(
            {
                "version": "1.0",
                "steps": steps,
            },
            mutation_registry=self.mcp.mutations,
        )

        workflow_id = f"wf-{uuid4().hex[:8]}"

        results = []
        current_context: Dict[str, Any] = {}

        # --------------------------------------------------
        # Phase 6.3.4 — capture safe context BEFORE mutation
        # --------------------------------------------------
        safe_context = None
        for step in steps:
            if step.get("mode") == "mutate":
                safe_context = deepcopy(current_context)
                break

        # --------------------------------------------------
        # Build rollback stack from definition
        # --------------------------------------------------
        rollback_stack = [
            step["rollback"]
            for step in steps
            if step.get("mode") == "mutate" and "rollback" in step
        ]

        # --------------------------------------------------
        # Execute workflow
        # --------------------------------------------------
        for idx, step in enumerate(steps):
            tool = step["tool"]
            mode = step.get("mode", "read")
            inputs = step.get("inputs", {})
            step_context = step.get("context", {})
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
                        "reason": condition,
                    })
                    continue

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
                    "context": r["context"],
                })

            except Exception as e:
                rollback_results = []

                # --------------------------------------------------
                # 🔁 Rollback using SAFE CONTEXT
                # --------------------------------------------------
                for rb in reversed(rollback_stack):
                    try:
                        rb_result = self.mcp.invoke(
                            tool_name=rb["tool"],
                            inputs=rb.get("inputs", {}),
                            context=safe_context or {},
                            session=session,
                        )
                        rollback_results.append({
                            "tool": rb["tool"],
                            "status": rb_result["status"],
                        })
                    except Exception as re:
                        rollback_results.append({
                            "tool": rb["tool"],
                            "error": str(re),
                        })

                return {
                    "workflow_id": workflow_id,
                    "steps": results,
                    "failed_step": idx,
                    "error": {
                        "type": type(e).__name__,
                        "message": str(e),
                    },
                    "rollback_executed": True,
                    "rollback_results": rollback_results,
                    "final_context": current_context,
                }

        return {
            "workflow_id": workflow_id,
            "steps": results,
            "final_context": current_context,
        }
