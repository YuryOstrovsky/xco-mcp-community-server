# mcp_runtime/planner.py

from typing import Dict, List

from mcp_runtime.workflow_schema import (
    validate_workflow_schema,
    WorkflowSchemaError,
)
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


class PlannerClarification(Exception):
    """
    Raised when intent is valid but underspecified.
    """

    def __init__(self, message: str, questions: list):
        super().__init__(message)
        self.questions = questions


class MCPPlanner:
    """
    Phase 4.x:
    Deterministic intent → workflow planner
    With ambiguity detection & clarification (Phase 4.6)
    """

    def __init__(self, registry):
        self.registry = registry
        self.normalizer = IntentNormalizer()
        self.cap_resolver = ToolCapabilityResolver(registry)

    # -------------------------------------------------
    # Helper: clarification question builder
    # -------------------------------------------------
    def _require_scope(self, clause: str, missing: list) -> Dict:
        return {
            "clause": clause,
            "missing": missing,
            "question": (
                f"Please specify {', '.join(missing)} "
                f"for: '{clause}'"
            ),
        }

    # -------------------------------------------------
    # Main planner entrypoint
    # -------------------------------------------------
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

        try:
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
                if action == "show" and obj == "switches":

                    if "fabric" not in scope:
                        raise PlannerClarification(
                            "Missing required scope",
                            [self._require_scope(clause, ["fabric"])],
                        )

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
                if action == "show" and obj == "device":

                    if "device" not in scope:
                        raise PlannerClarification(
                            "Missing required scope",
                            [self._require_scope(clause, ["device"])],
                        )

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

        except PlannerClarification as c:
            return {
                "clarification_required": True,
                "questions": c.questions,
                "explain": {
                    "intent": intent,
                    "reason": str(c),
                },
            }

        # -------------------------------------------------
        # Final workflow validation
        # -------------------------------------------------
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
