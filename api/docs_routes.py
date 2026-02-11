# api/docs_routes.py
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

# This file is api/docs_routes.py -> repo root is parent of /api
REPO_ROOT = Path(__file__).resolve().parent.parent

TOOL_CATALOG = REPO_ROOT / "docs" / "TOOL_CATALOG.md"
MCP_OPENAPI = REPO_ROOT / "openapi" / "mcp-server" / "openapi_mcp_invoke.yaml"


@router.get("/docs/tools", response_class=PlainTextResponse)
def docs_tools():
    if not TOOL_CATALOG.exists():
        return PlainTextResponse(f"Missing file: {TOOL_CATALOG}", status_code=404)
    return PlainTextResponse(TOOL_CATALOG.read_text(encoding="utf-8"))


@router.get("/openapi/mcp-invoke.yaml", response_class=PlainTextResponse)
def openapi_mcp_invoke():
    # PlainTextResponse makes the browser display it instead of downloading
    if not MCP_OPENAPI.exists():
        return PlainTextResponse(f"Missing file: {MCP_OPENAPI}", status_code=404)
    return PlainTextResponse(MCP_OPENAPI.read_text(encoding="utf-8"))

