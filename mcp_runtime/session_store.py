# mcp_runtime/session_store.py

from mcp_runtime.session import MCPSession
import uuid

class SessionStore:
    def __init__(self):
        self._sessions = {}

    def get_or_create(self, session_id: str | None):
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        # create new session
        new_id = session_id or str(uuid.uuid4())
        session = MCPSession(session_id=new_id)
        self._sessions[new_id] = session
        return session

    def get(self, session_id: str):
        return self._sessions.get(session_id)

