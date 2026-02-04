# mcp_runtime/session.py

from typing import Dict, Optional
from copy import deepcopy
from mcp_runtime.tracing import new_correlation_id


class MCPSession:
    """
    Session object carrying:
    - resolved context (Phase 2.x)
    - correlation id (Phase 2.8)
    - agent identity (Phase 5.6)
    """

    def __init__(self, session_id: str, agent=None):
        self.session_id = session_id

        # ---- Phase 2.8 tracing ----
        self.correlation_id = new_correlation_id()

        # ---- Phase 5.6 agent identity ----
        self.agent = agent  # may be None (defaults handled by executor)

        # ---- Persisted resolved context ----
        self._context: Dict = {}

    # --------------------------------------------------
    # Context handling (with debug)
    # --------------------------------------------------

    def get_context(self) -> Dict:
        print(">>> SESSION.get_context CALLED")
        print(">>> stored ctx =", self._context)
        return deepcopy(self._context)

    def update_context(self, ctx: Dict):
        """
        Persist only resolved, validated context.
        """
        print(">>> SESSION.update_context CALLED")
        print(">>> ctx =", ctx)
        self._context = deepcopy(ctx)

    def clear(self):
        print(">>> SESSION.clear CALLED")
        self._context = {}

    # --------------------------------------------------
    # Agent helpers (optional, but useful)
    # --------------------------------------------------

    def set_agent(self, agent):
        self.agent = agent

    def get_agent(self):
        return self.agent
