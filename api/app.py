# api/app.py

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Dict, Any

from mcp_runtime.server import MCPServer
from mcp_runtime.session_store import SessionStore

# -------------------------------------------------
# App & MCP initialization
# -------------------------------------------------

app = FastAPI(title="XCO MCP Server")

mcp = MCPServer(auto_mode=False)
session_store = SessionStore()

# -------------------------------------------------
# Models
# -------------------------------------------------

class InvokeRequest(BaseModel):
    tool: str
    inputs: Dict[str, Any] = {}
    context: Optional[Dict[str, Any]] = None


# -------------------------------------------------
# Endpoints
# -------------------------------------------------

@app.post("/invoke")
def invoke_tool(
    req: InvokeRequest,
    x_mcp_session: Optional[str] = Header(default=None),
):
    """
    Invoke an MCP tool with optional session support.

    - Session is carried via X-MCP-Session header
    - If missing, a new session is created
    """
    try:
        # Get or create MCP session
        session = session_store.get_or_create(x_mcp_session)

        result = mcp.invoke(
            tool_name=req.tool,
            inputs=req.inputs,
            context=req.context,
            session=session,
        )

        return {
            "session_id": session.session_id,
            "result": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools")
def list_tools():
    return mcp.list_tools()
