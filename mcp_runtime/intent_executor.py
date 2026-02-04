# mcp_runtime/intent_executor.py

from mcp_runtime.planner import MCPPlanner, PlannerError
from mcp_runtime.workflow import MCPWorkflowRunner
from mcp_runtime.agents.observer import ObserverAgent
from mcp_runtime.safety.envelope import SafetyEnvelope, SafetyEnvelopeError
from mcp_runtime.commit_registry import CommitRegistry


MUTATE_KEYWORDS = {"tag", "delete", "remove", "add", "set", "rename"}


class MCPIntentExecutor:
    """
    Phase 5.3:
    Intent → Safety → (Confirm?) → Plan → Execute
    """

    def __init__(self, mcp_server):
        self.mcp = mcp_server
        self.planner = MCPPlanner(mcp_server.registry)
        self.runner = MCPWorkflowRunner(mcp_server)
        self.commits = CommitRegistry()

    def execute(self, intent: str, session=None):

        intent_lc = intent.lower()

        # --------------------------------------------------
        # Agent + intent classification
        # --------------------------------------------------
        agent = ObserverAgent()
        intent_meta = agent.classify_intent(intent)

        # --------------------------------------------------
        # Safety pre-upgrade for unknown mutation verbs
        # --------------------------------------------------
        if any(k in intent_lc for k in MUTATE_KEYWORDS):
            if intent_meta["risk"] == "SAFE_READ":
                intent_meta["risk"] = (
                    "RISKY_MUTATE" if "delete" in intent_lc else "SAFE_MUTATE"
                )

        # --------------------------------------------------
        # Safety envelope (may DENY or REQUIRE confirmation)
        # --------------------------------------------------
        envelope = SafetyEnvelope(agent)
        decision = envelope.enforce(intent_meta)

        # --------------------------------------------------
        # 🔴 CONFIRMATION SHORT-CIRCUIT (NO PLANNING HERE)
        # --------------------------------------------------
        if decision == "CONFIRM_REQUIRED":
            token = self.commits.create(
                intent=intent,
                agent=agent.name,
                risk=intent_meta["risk"],
                plan=None,
            )

            return {
                "confirmation_required": True,
                "commit_token": token,
                "intent": intent,
                "risk": intent_meta["risk"],
                "agent": agent.name,
                "message": "Confirmation required to proceed",
            }

        # --------------------------------------------------
        # Planning (SAFE_READ only)
        # --------------------------------------------------
        try:
            plan = self.planner.plan(intent)
        except PlannerError:
            raise

        # Clarification path
        if plan.get("clarification_required"):
            return plan

        # --------------------------------------------------
        # Execution
        # --------------------------------------------------
        workflow = plan["workflow"]

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

    def confirm(self, commit_token: str, session=None):
        """
        Phase 5.3:
        Confirm intent execution.
        NOTE: Mutation planning/execution is deferred to later phases.
        """

        record = self.commits.pop(commit_token)
        if not record:
            raise ValueError("Invalid or expired commit token")

        return {
            "confirmed": True,
            "intent": record["intent"],
            "risk": record["risk"],
            "agent": record["agent"],
            "message": "Intent confirmed. Execution will be handled by mutation planner.",
        }

