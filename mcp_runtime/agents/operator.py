from mcp_runtime.agents.base import MCPAgent


class OperatorAgent(MCPAgent):
    """
    Phase 5.1:
    Operator agent — may request changes but requires confirmation.
    """

    name = "operator"
    allow_mutation = True
    auto_mode_allowed = False

    def classify_intent(self, intent: str) -> dict:
        """
        For now: everything not clearly read-only is treated as CHANGE.
        (We refine this in Phase 5.2.)
        """
        return {
            "type": "change",
            "risk": "CONFIRM_REQUIRED",
        }

