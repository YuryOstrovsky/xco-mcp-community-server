# mcp_runtime/planner.py

from typing import Dict
from mcp_runtime.workflow_schema import validate_workflow_schema, WorkflowSchemaError
from mcp_runtime.intent_normalizer import IntentNormalizer, IntentNormalizationError
from mcp_runtime.tool_capabilities import ToolCapabilityResolver, ToolCapabilityError




class PlannerError(Exception):
    pass


class MCPPlanner:
    """
    Phase 4.0:
    Deterministic intent → workflow planner
    """

    def __init__(self, registry):
        self.registry = registry
        self.normalizer = IntentNormalizer()
        self.cap_resolver = ToolCapabilityResolver(registry)

    def plan(self, intent: str) -> Dict:
        """
        Translate intent string into workflow schema.
        """

        try:
            normalized = self.normalizer.normalize(intent)
        except IntentNormalizationError as e:
            raise PlannerError(str(e))

        canonical = normalized["canonical"]


        # ---- Simple deterministic rules (Phase 4.x) ----

        if canonical.startswith("show switches in fabric"):
            fabric = normalized["scope"]["fabric"]

            try:
                tool_name = self.cap_resolver.find_tool(
                    action=normalized["action"],
                    object_=normalized["object"],
                    scope_keys=list(normalized["scope"].keys()),
                )
            except ToolCapabilityError as e:
                raise PlannerError(str(e))
            
            capability_explain = self.cap_resolver.explain_match(
            action=normalized["action"],
            object_=normalized["object"],
            scope_keys=list(normalized["scope"].keys()),
        )



            workflow = {
                "version": "1.0",
                "steps": [
                    {
                        "tool": tool_name,
                        "context": {
                            "fabric": fabric
                        },
                    }
                ],
            }


            try:
                validate_workflow_schema(workflow)
            except WorkflowSchemaError as e:
                raise PlannerError(str(e))

            return {
                "workflow": workflow,
                "explain": {
                    "intent": intent,
                    "canonical_intent": canonical,
                    "normalized": normalized,
                    "matched_pattern": "show switches in fabric <fabric>",
                    "capabilities_required": {
                        "action": normalized["action"],
                        "object": normalized["object"],
                        "scope": list(normalized["scope"].keys()),
                    },
                    "tool_selected": tool_name,
                    "capability_evaluation": capability_explain,
                    "reasoning": (
                        f"Selected tool '{tool_name}' because it matched "
                        f"action={normalized['action']}, "
                        f"object={normalized['object']}, "
                        f"scope={list(normalized['scope'].keys())}"
                    ),
                },
            }


        # ---- Fallback ----
        raise PlannerError(f"Unable to plan intent: '{intent}'")

