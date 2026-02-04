# mcp_runtime/intent_executor.py

from mcp_runtime.planner import MCPPlanner, PlannerError
from mcp_runtime.workflow import MCPWorkflowRunner
from mcp_runtime.agents.observer import ObserverAgent
from mcp_runtime.safety.envelope import SafetyEnvelope, SafetyEnvelopeError


MUTATE_KEYWORDS = {"tag", "delete", "remove", "add", "set", "rename"}


class MCPIntentExecutor:
    """
    Phase 5.2:
    Intent → Safety → Plan → Execute
    """

    def __init__(self, mcp_server):
        self.mcp = mcp_server
        self.planner = MCPPlanner(mcp_server.registry)
        self.runner = MCPWorkflowRunner(mcp_server)

    def execute(self, intent: str, session=None):

        intent_lc = intent.lower()

        # --------------------------------------------------
        # Agent + intent classification
        # --------------------------------------------------
        agent = ObserverAgent()
        intent_meta = agent.classify_intent(intent)

        # --------------------------------------------------
        # 🔴 SAFETY PRE-CLASSIFICATION FIX 🔴
        # Catch mutation verbs even if planner doesn't know them
        # --------------------------------------------------
        if any(k in intent_lc for k in MUTATE_KEYWORDS):
            if intent_meta["risk"] == "SAFE_READ":
                # Upgrade risk BEFORE envelope
                intent_meta["risk"] = (
                    "RISKY_MUTATE" if "delete" in intent_lc else "SAFE_MUTATE"
                )

        # --------------------------------------------------
        # Safety envelope (must short-circuit)
        # --------------------------------------------------
        envelope = SafetyEnvelope(agent)
        decision = envelope.enforce(intent_meta)

        if decision == "CONFIRM_REQUIRED":
            return {
                "confirmation_required": True,
                "intent": intent,
                "risk": intent_meta["risk"],
                "agent": agent.name,
                "message": "This action requires confirmation before execution",
            }

        # --------------------------------------------------
        # Planning
        # --------------------------------------------------
        try:
            plan = self.planner.plan(intent)
        except PlannerError:
            # Planner errors are valid ONLY after safety
            raise

        # Clarification path
        if plan.get("clarification_required"):
            return plan

        workflow = plan["workflow"]

        # --------------------------------------------------
        # Execution
        # --------------------------------------------------
        execution = self.runner.run(
            workflow["steps"],
            session=session,
        )

        return {
            "intent": intent,
            "workflow": workflow,
            "execution": execution,
            "explain": plan.get("explain"),
        }
