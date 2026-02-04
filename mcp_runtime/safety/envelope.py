# mcp_runtime/safety/envelope.py


class SafetyEnvelopeError(Exception):
    pass


class SafetyEnvelope:
    """
    Phase 5.x:
    Enforces agent-level safety constraints BEFORE planning/execution.

    Outcomes:
    - allow execution
    - require confirmation
    - reject intent
    """

    def __init__(self, agent):
        self.agent = agent

    def enforce(self, intent_meta: dict):
        """
        Validate intent against agent permissions.

        Returns:
          - None                → execution allowed
          - "CONFIRM_REQUIRED"  → must confirm before execution

        Raises:
          - SafetyEnvelopeError → intent is not allowed
        """

        risk = intent_meta.get("risk")

        # -----------------------------
        # SAFE READ-ONLY INTENTS
        # -----------------------------
        if risk == "SAFE_READ":
            return None

        # -----------------------------
        # CHANGE / MUTATION INTENTS
        # -----------------------------
        if risk == "CONFIRM_REQUIRED":
            if not self.agent.allow_mutation:
                raise SafetyEnvelopeError(
                    f"Agent '{self.agent.name}' is not allowed to perform mutations"
                )

            # Operator is allowed to request, but must confirm
            return "CONFIRM_REQUIRED"

        # -----------------------------
        # UNKNOWN / FUTURE RISKS
        # -----------------------------
        raise SafetyEnvelopeError(
            f"Unhandled intent risk '{risk}' for agent '{self.agent.name}'"
        )

