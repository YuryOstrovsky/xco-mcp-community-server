# mcp_runtime/workflow_schema.py

from typing import Dict


class WorkflowSchemaError(ValueError):
    pass


def validate_workflow_schema(workflow: Dict):
    if not isinstance(workflow, dict):
        raise WorkflowSchemaError("Workflow must be a dict")

    if workflow.get("version") != "1.0":
        raise WorkflowSchemaError("Unsupported or missing workflow version")

    steps = workflow.get("steps")
    if not isinstance(steps, list) or not steps:
        raise WorkflowSchemaError("Workflow must contain a non-empty 'steps' list")

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise WorkflowSchemaError(f"Step {idx} must be a dict")

        if "tool" not in step:
            raise WorkflowSchemaError(f"Step {idx} missing 'tool'")

        if "inputs" in step and not isinstance(step["inputs"], dict):
            raise WorkflowSchemaError(f"Step {idx} 'inputs' must be a dict")

        if "context" in step and not isinstance(step["context"], dict):
            raise WorkflowSchemaError(f"Step {idx} 'context' must be a dict")

        if "when" in step:
            when = step["when"]
            if not isinstance(when, dict):
                raise WorkflowSchemaError(f"Step {idx} 'when' must be a dict")
            if "path" not in when or "equals" not in when:
                raise WorkflowSchemaError(
                    f"Step {idx} 'when' requires 'path' and 'equals'"
                )

        # --------------------------------------------------
        # Phase 6.0 — step mode
        # --------------------------------------------------
        mode = step.get("mode", "read")
        if mode not in ("read", "mutate"):
            raise WorkflowSchemaError(
                f"Step {idx} invalid mode '{mode}' (must be read|mutate)"
            )

        # --------------------------------------------------
        # Phase 6.0 — rollback REQUIRED for mutate
        # --------------------------------------------------
        if mode == "mutate":
            if "rollback" not in step:
                raise WorkflowSchemaError(
                    f"Step {idx} is mutate but missing rollback"
                )

        # --------------------------------------------------
        # Rollback structure (strategy NOT required yet)
        # --------------------------------------------------
        if "rollback" in step:
            rollback = step["rollback"]
            if not isinstance(rollback, dict):
                raise WorkflowSchemaError(f"Step {idx} rollback must be a dict")

            if "tool" not in rollback:
                raise WorkflowSchemaError(
                    f"Step {idx} rollback missing 'tool'"
                )
