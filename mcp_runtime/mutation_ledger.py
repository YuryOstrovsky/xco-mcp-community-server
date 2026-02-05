# mcp_runtime/mutation_ledger.py

from typing import Dict, List, Optional
from uuid import uuid4
from datetime import datetime


class MutationLedger:
    """
    Phase 6.6.1
    - Append-only mutation ledger
    - Adds mutation_id and lineage fields
    - NO execution semantics here
    """

    def __init__(self):
        self._entries: List[Dict] = []

    def record(
        self,
        *,
        tool: str,
        agent: str,
        session_id: Optional[str],
        status: str,
        rollback_tool: Optional[str] = None,
        parent_mutation_id: Optional[str] = None,
        reverts_mutation_id: Optional[str] = None,
    ) -> Dict:
        """
        Record a mutation or rollback intent/execution.

        This is APPEND-ONLY.
        """

        entry = {
            "mutation_id": f"mut-{uuid4().hex[:8]}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tool": tool,
            "status": status,
            "agent": agent,
            "session_id": session_id,
            "rollback_tool": rollback_tool,
            # Phase 6.6 lineage fields
            "parent_mutation_id": parent_mutation_id,
            "reverts_mutation_id": reverts_mutation_id,
        }

        self._entries.append(entry)
        return entry

    def list(self) -> List[Dict]:
        """
        Return all ledger entries (append-only).
        """
        return list(self._entries)

