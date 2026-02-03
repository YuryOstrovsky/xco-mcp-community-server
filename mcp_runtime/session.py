# mcp_runtime/session.py

from typing import Dict, Optional
from copy import deepcopy

class MCPSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
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

