# mcp_runtime/planner.py

from typing import Dict, List
from mcp_runtime.workflow_schema import validate_workflow_schema, WorkflowSchemaError
from mcp_runtime.intent_normalizer import (
    IntentNormalizer,
    IntentNormalizationError,
)
from mcp_runtime.tool_capabilities import (
    ToolCapabilityResolver,
    ToolCapabilityError,
)


class PlannerError(Exception):
    pass


class MCPPlanner:
    """
    Phase 4.x:
    Deterministic intent → workflow planner
    """

    def __init__(self, registry):
        self.registry = registry
        self.normalizer = IntentNormalizer()
        self.cap_resolver = ToolCapabilityResolver(registry)

    def plan(self, intent: str) -> Dict:
        """
        Translate intent string into workflow schema.
        Supports multi-clause intent separated by 'then'.
        """

        if not intent or not intent.strip():
            raise PlannerError("Empty intent")

        clauses = [
            c.strip()
            for c in intent.lower().split(" then ")
            if c.strip()
        ]

        steps: List[Dict] = []
        explain_steps = []

        for clause in clauses:
            try:
                normalized = self.normalizer.normalize(clause)
            except IntentNormalizationError as e:
                raise PlannerError(str(e))

            action = normalized["action"]
            obj = normalized["object"]
            scope = normalized["scope"]

            # =====================================================
            # Rule 1: show switches in fabric <fabric>
            # =====================================================
            if action == "show" and obj == "switches" and "fabric" in scope:
                try:
                    tool_name = self.cap_resolver.find_tool(
                        action=action,
                        object_=obj,
                        scope_keys=["fabric"],
                    )
                    capability_explain = self.cap_resolver.explain_match(
                        action=action,
                        object_=obj,
                        scope_keys=["fabric"],
                    )
                except ToolCapabilityError as e:
                    raise PlannerError(str(e))

                steps.append({
                    "tool": tool_name,
                    "context": {
                        "fabric": scope["fabric"],
                    },
                })

                explain_steps.append({
                    "clause": clause,
                    "tool": tool_name,
                    "capability_evaluation": capability_explain,
                })
                continue

            # =====================================================
            # Rule 2: show device <device>
            # =====================================================
            if action == "show" and obj == "device" and "device" in scope:
                try:
                    tool_name = self.cap_resolver.find_tool(
                        action=action,
                        object_="switches",
                        scope_keys=["device"],
                    )
                    capability_explain = self.cap_resolver.explain_match(
                        action=action,
                        object_="switches",
                        scope_keys=["device"],
                    )
                except ToolCapabilityError as e:
                    raise PlannerError(str(e))

                steps.append({
                    "tool": tool_name,
                    "context": {
                        "device": scope["device"],
                    },
                })

                explain_steps.append({
                    "clause": clause,
                    "tool": tool_name,
                    "capability_evaluation": capability_explain,
                })
                continue

            # =====================================================
            # Fallback
            # =====================================================
            raise PlannerError(f"Unable to plan intent clause: '{clause}'")

        workflow = {
            "version": "1.0",
            "steps": steps,
        }

        try:
            validate_workflow_schema(workflow)
        except WorkflowSchemaError as e:
            raise PlannerError(str(e))

        return {
            "workflow": workflow,
            "explain": {
                "intent": intent,
                "steps": explain_steps,
            },
        }
