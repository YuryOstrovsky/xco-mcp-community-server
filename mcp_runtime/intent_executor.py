# mcp_runtime/intent_executor.py

from mcp_runtime.planner import MCPPlanner, PlannerError
from mcp_runtime.workflow import MCPWorkflowRunner
from mcp_runtime.agents.observer import ObserverAgent
from mcp_runtime.safety.envelope import SafetyEnvelope, SafetyEnvelopeError


class MCPIntentExecutor:
    """
    Phase 4.9 / 5.x:
    End-to-end intent → safety → plan → execute
    """

    def __init__(self, mcp_server):
        self.mcp = mcp_server
        self.planner = MCPPlanner(mcp_server.registry)
        self.runner = MCPWorkflowRunner(mcp_server)

    def execute(self, intent: str, session=None):
        """
        Execute an intent string.

        Returns one of:
        - clarification_required response
        - executed workflow result
        - SafetyEnvelopeError
        """

        # --------------------------------------------------
        # Phase 5.0 — Agent identity & intent classification
        # --------------------------------------------------
        agent = ObserverAgent()
        intent_meta = agent.classify_intent(intent)

        # --------------------------------------------------
        # Phase 5.1 — Safety envelope enforcement
        # --------------------------------------------------
        envelope = SafetyEnvelope(agent)
        envelope_result = envelope.enforce(intent_meta)

        # NOTE:
        # - None → allowed
        # - "CONFIRM_REQUIRED" → handled in Phase 5.2+
        # For now we allow execution to continue

        # --------------------------------------------------
        # Phase 4.x — Planning
        # --------------------------------------------------
        try:
            plan = self.planner.plan(intent)
        except PlannerError as e:
            raise e

        # --------------------------------------------------
        # Clarification passthrough (NO execution)
        # --------------------------------------------------
        if plan.get("clarification_required"):
            return plan

        workflow = plan["workflow"]

        # --------------------------------------------------
        # Phase 3.x — Workflow execution
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
