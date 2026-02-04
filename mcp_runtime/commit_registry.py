# mcp_runtime/commit_registry.py

import uuid
import time


class CommitRegistry:
    """
    Phase 5.3:
    Stores pending confirmed intents awaiting execution
    """

    def __init__(self):
        self._pending = {}

    def create(self, *, intent: str, agent: str, risk: str, plan=None):
        token = uuid.uuid4().hex

        self._pending[token] = {
            "intent": intent,
            "agent": agent,
            "risk": risk,
            "plan": plan,          # may be None (Phase 5.3)
            "created_at": time.time(),
        }

        return token

    def pop(self, token: str):
        return self._pending.pop(token, None)

