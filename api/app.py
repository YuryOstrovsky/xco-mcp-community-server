# api/app.py

import concurrent.futures
from datetime import datetime, timezone
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time


from fastapi import FastAPI, HTTPException, Header, Response
from pydantic import BaseModel
from typing import Optional, Dict, Any

from mcp_runtime.server import MCPServer
from mcp_runtime.session_store import SessionStore
from mcp_runtime.errors import ToolNotFound
from mcp_runtime.policy import PolicyViolation
from api.docs_routes import router as docs_router


# -------------------------------------------------
# App & MCP initialization
# -------------------------------------------------

app = FastAPI(title="XCO MCP Server")

app.include_router(docs_router)
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
    # Fix #3: validate tool name against registry before invoking
    if req.tool not in mcp.registry.tools:
        raise HTTPException(status_code=404, detail=f"Tool '{req.tool}' not found")

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

    # Fix #4: map specific exceptions to correct HTTP codes
    except ToolNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PolicyViolation as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
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

# Fix #9: per-check timeout so /ready cannot hang indefinitely
_READY_TIMEOUT = 10  # seconds

@app.get("/ready")
def readiness_check(response: Response):
    """
    Readiness probe:
    - registry loaded
    - auth token available
    - XCO reachable (bounded by _READY_TIMEOUT)
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
    # Fix #9: wrap in a thread with timeout so it cannot hang indefinitely
    # ----------------------------------
    def _xco_probe():
        return mcp.transport.request(
            method="GET",
            path="/v1/fabric/fabrics",
            params={},
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_xco_probe)
            res = future.result(timeout=_READY_TIMEOUT)

        if res["status"] == 200:
            checks["xco"] = True
        else:
            errors.append(f"xco_status_{res['status']}")
    except concurrent.futures.TimeoutError:
        errors.append(f"xco_timeout_after_{_READY_TIMEOUT}s")
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
