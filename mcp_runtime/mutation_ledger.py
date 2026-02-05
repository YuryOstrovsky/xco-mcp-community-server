# mcp_runtime/mutation_ledger.py

from typing import List, Dict
from uuid import uuid4
from datetime import datetime


class MutationLedger:
    """
    Phase 6.5:
    Append-only mutation audit log.
    """

    def __init__(self):
        self._entries: List[Dict] = []

    def record(
        self,
        *,
        tool: str,
        agent: str,
        session_id: str | None,
        rollback_tool: str | None,
        status: str,
    ) -> Dict:
        entry = {
            "id": uuid4().hex,
            "tool": tool,
            "agent": agent,
            "session_id": session_id,
            "rollback_tool": rollback_tool,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._entries.append(entry)
        return entry

    def list(self) -> List[Dict]:
        return list(self._entries)

