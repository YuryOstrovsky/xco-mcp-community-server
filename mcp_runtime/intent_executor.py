# mcp_runtime/intent_executor.py

from mcp_runtime.planner import MCPPlanner, PlannerError
from mcp_runtime.workflow import MCPWorkflowRunner


class MCPIntentExecutor:
    """
    Phase 4.9:
    Execute user intent end-to-end:
      intent → plan → (clarify?) → execute workflow
    """

    def __init__(self, mcp_server):
        self.mcp = mcp_server
        self.planner = MCPPlanner(mcp_server.registry)
        self.runner = MCPWorkflowRunner(mcp_server)

    def execute(self, intent: str, session=None):
        """
        Execute intent.
        Returns either:
          - clarification request
          - execution result
        """

        # ---- Phase 1: planning ----
        try:
            plan = self.planner.plan(intent)
        except PlannerError as e:
            return {
                "error": str(e),
                "intent": intent,
            }

        # ---- Phase 2: clarification passthrough ----
        if plan.get("clarification_required"):
            return plan

        workflow = plan["workflow"]

        # ---- Phase 3: execution ----
        execution = self.runner.run(
            workflow["steps"],
            session=session,
        )

        # 🔑 DO NOT recompute or override final_context
        # It already comes from the session inside the runner

        return {
            "intent": intent,
            "workflow": workflow,
            "execution": execution,
            "explain": plan.get("explain"),
        }
