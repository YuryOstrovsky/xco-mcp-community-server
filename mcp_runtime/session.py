# mcp_runtime/session.py

from typing import Dict
from copy import deepcopy
from mcp_runtime.tracing import new_correlation_id


class MCPSession:
    def __init__(self, session_id: str):
        self.session_id = session_id

        # ---- Phase 2.8 tracing ----
        self.correlation_id = new_correlation_id()

        # ---- Persisted resolved context ----
        self._context: Dict = {}

    def get_context(self) -> Dict:
        return deepcopy(self._context)

    def update_context(self, new_context: Dict):
        """
        Persist only resolved, validated context.
        """
        self._context = deepcopy(new_context)

    def clear(self):
        self._context = {}

    def update_context(self, ctx: dict):
        print(">>> SESSION.update_context CALLED")
        print(">>> ctx =", ctx)
        self._context = ctx

    def get_context(self):
        print(">>> SESSION.get_context CALLED")
        print(">>> stored ctx =", getattr(self, "_context", None))
        return getattr(self, "_context", {})
