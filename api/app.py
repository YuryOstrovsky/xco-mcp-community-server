# api/app.py

from datetime import datetime, timezone
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time




from fastapi import FastAPI, HTTPException, Header, Response
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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "xco-mcp",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0",
    }

@app.get("/metrics")
def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

@app.get("/ready")
def readiness_check(response: Response):
    """
    Readiness probe:
    - registry loaded
    - auth token available
    - XCO reachable
    """

    checks = {
        "registry": False,
        "auth": False,
        "xco": False,
    }

    errors = []

    # ----------------------------------
    # 1) Registry check
    # ----------------------------------
    try:
        tools = mcp.list_tools()
        if tools and isinstance(tools, list):
            checks["registry"] = True
        else:
            errors.append("registry_empty")
    except Exception as e:
        errors.append(f"registry_error: {e}")

    # ----------------------------------
    # 2) Auth check (token fetch)
    # ----------------------------------
    try:
        token = mcp.auth.get_token()
        if token:
            checks["auth"] = True
        else:
            errors.append("auth_token_empty")
    except Exception as e:
        errors.append(f"auth_error: {e}")

    # ----------------------------------
    # 3) XCO connectivity check
    # ----------------------------------
    try:
        # Very lightweight call (no fabric context)
        res = mcp.transport.request(
            method="GET",
            path="/v1/fabric/fabrics",
            params={},
        )

        if res["status"] == 200:
            checks["xco"] = True
        else:
            errors.append(f"xco_status_{res['status']}")
    except Exception as e:
        errors.append(f"xco_error: {e}")

    # ----------------------------------
    # Final decision
    # ----------------------------------
    if all(checks.values()):
        return {
            "status": "ready",
            "checks": checks,
        }

    response.status_code = 503
    return {
        "status": "not_ready",
        "checks": checks,
        "errors": errors,
    }
