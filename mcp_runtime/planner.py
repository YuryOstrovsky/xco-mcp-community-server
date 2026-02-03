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

    # ---------------------------------------------------------
    # Phase 4.6 — initial planning (already working)
    # ---------------------------------------------------------
    def plan(self, intent: str) -> Dict:
        if not intent or not intent.strip():
            raise PlannerError("Empty intent")

        clauses = [
            c.strip()
            for c in intent.lower().split(" then ")
            if c.strip()
        ]

        steps: List[Dict] = []
        explain_steps = []
        questions = []

        for clause in clauses:
            try:
                normalized = self.normalizer.normalize(clause)
            except IntentNormalizationError:
                # Ambiguous clause → clarification
                if clause.startswith("show switches"):
                    questions.append({
                        "clause": clause,
                        "missing": ["fabric"],
                    })
                    continue

                if clause.startswith("show device"):
                    questions.append({
                        "clause": clause,
                        "missing": ["device"],
                    })
                    continue

                raise PlannerError(f"Unrecognized intent: '{clause}'")

            action = normalized["action"]
            obj = normalized["object"]
            scope = normalized["scope"]

            # ---- Rule: show switches in fabric <fabric> ----
            if action == "show" and obj == "switches":
                if "fabric" not in scope:
                    questions.append({
                        "clause": clause,
                        "missing": ["fabric"],
                    })
                    continue

                try:
                    tool = self.cap_resolver.find_tool(
                        action="show",
                        object_="switches",
                        scope_keys=["fabric"],
                    )
                except ToolCapabilityError as e:
                    raise PlannerError(str(e))

                steps.append({
                    "tool": tool,
                    "context": {"fabric": scope["fabric"]},
                })

                explain_steps.append({
                    "clause": clause,
                    "tool": tool,
                })
                continue

            # ---- Rule: show device <device> ----
            if action == "show" and obj == "device":
                if "device" not in scope:
                    questions.append({
                        "clause": clause,
                        "missing": ["device"],
                    })
                    continue

                try:
                    tool = self.cap_resolver.find_tool(
                        action="show",
                        object_="switches",
                        scope_keys=["device"],
                    )
                except ToolCapabilityError as e:
                    raise PlannerError(str(e))

                steps.append({
                    "tool": tool,
                    "context": {"device": scope["device"]},
                })

                explain_steps.append({
                    "clause": clause,
                    "tool": tool,
                })
                continue

            raise PlannerError(f"Unable to plan clause: '{clause}'")

        if questions:
            return {
                "clarification_required": True,
                "questions": questions,
                "partial_workflow": {
                    "version": "1.0",
                    "steps": steps,
                },
            }

        workflow = {
            "version": "1.0",
            "steps": steps,
        }

        validate_workflow_schema(workflow)

        return {
            "workflow": workflow,
            "explain": {
                "intent": intent,
                "steps": explain_steps,
            },
        }

    # ---------------------------------------------------------
    # Phase 4.7 — clarification resolution (NEW)
    # ---------------------------------------------------------
    def resolve_clarification(
        self,
        previous_plan: Dict,
        answers: Dict,
    ) -> Dict:
        """
        Apply user-provided answers and resume planning.
        """

        if not previous_plan.get("clarification_required"):
            raise PlannerError("No clarification required")

        questions = previous_plan["questions"]
        steps = previous_plan.get("partial_workflow", {}).get("steps", [])

        for q in questions:
            clause = q["clause"]
            missing = q["missing"]

            for key in missing:
                if key not in answers:
                    raise PlannerError(f"Missing clarification answer for '{key}'")

                value = answers[key].lower()

                # Re-inject resolved step
                if clause.startswith("show switches"):
                    tool = self.cap_resolver.find_tool(
                        action="show",
                        object_="switches",
                        scope_keys=["fabric"],
                    )
                    steps.append({
                        "tool": tool,
                        "context": {"fabric": value},
                    })

                elif clause.startswith("show device"):
                    tool = self.cap_resolver.find_tool(
                        action="show",
                        object_="switches",
                        scope_keys=["device"],
                    )
                    steps.append({
                        "tool": tool,
                        "context": {"device": value},
                    })

        workflow = {
            "version": "1.0",
            "steps": steps,
        }

        validate_workflow_schema(workflow)

        return {
            "workflow": workflow,
            "clarification_resolved": True,
        }
