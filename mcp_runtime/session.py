# mcp_runtime/session.py

from typing import Dict
from copy import deepcopy
from mcp_runtime.tracing import new_correlation_id


class MCPSession:
    """
    Session object carrying:
    - resolved context (Phase 2.x)
    - correlation id (Phase 2.8)
    - optional agent/caller identity
    """

    def __init__(self, session_id: str, agent=None):
        self.session_id = session_id

        # ---- Phase 2.8 tracing ----
        self.correlation_id = new_correlation_id()

        # ---- optional agent/caller identity ----
        self.agent = agent  # optional caller/agent label; may be None

        # ---- Persisted resolved context ----
        self._context: Dict = {}

    # --------------------------------------------------
    # Context handling
    # --------------------------------------------------

    def get_context(self) -> Dict:
        return deepcopy(self._context)

    def update_context(self, ctx: Dict):
        """
        Persist only resolved, validated context.
        """
        self._context = deepcopy(ctx)

    def clear(self):
        self._context = {}

    # --------------------------------------------------
    # Agent helpers (optional, but useful)
    # --------------------------------------------------

    def set_agent(self, agent):
        self.agent = agent

    def get_agent(self):
        return self.agent
