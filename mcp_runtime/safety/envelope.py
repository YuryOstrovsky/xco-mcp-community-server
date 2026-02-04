# mcp_runtime/safety/envelope.py

class SafetyEnvelopeError(Exception):
    pass


class SafetyEnvelope:
    """
    Phase 5.2:
    Enforces agent-level safety constraints BEFORE planning/execution.
    """

    def __init__(self, agent):
        self.agent = agent

    def enforce(self, intent_meta: dict):
        """
        Returns:
        - "ALLOW"
        - "CONFIRM_REQUIRED"
        Raises:
        - SafetyEnvelopeError for denied actions
        """

        risk = intent_meta.get("risk")

        # ---------------------------
        # SAFE READ → always allowed
        # ---------------------------
        if risk == "SAFE_READ":
            return "ALLOW"

        # ---------------------------
        # SAFE MUTATE → confirmation
        # ---------------------------
        if risk == "SAFE_MUTATE":
            if not self.agent.allow_mutation:
                return "CONFIRM_REQUIRED"
            return "ALLOW"

        # ---------------------------
        # RISKY MUTATE → hard deny
        # ---------------------------
        if risk == "RISKY_MUTATE":
            raise SafetyEnvelopeError(
                f"Agent '{self.agent.name}' is not allowed to perform risky actions"
            )

        # ---------------------------
        # Unknown risk → deny
        # ---------------------------
        raise SafetyEnvelopeError(f"Unknown risk level: {risk}")

