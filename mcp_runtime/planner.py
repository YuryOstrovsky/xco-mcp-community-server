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
                    "matched_pattern": "show switches in fabric <fabric>",
                    "reasoning": f"Mapped intent to inventory_getswitches with fabric={fabric}",
                },
            }

        # ---- Fallback ----
        raise PlannerError(f"Unable to plan intent: '{intent}'")

