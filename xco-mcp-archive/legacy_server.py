# Archived pre-MCP runtime experiment — do not use
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from xco.client import XCOClient


load_dotenv()

mcp = FastMCP(
    "XCO MCP Server",
    json_response=True
)



def _get_env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None or v == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return v

def _read_only_enabled() -> bool:
    return os.getenv("XCO_READ_ONLY", "1").strip() in ("1", "true", "True", "yes", "YES")


@mcp.tool()
def xco_discovery_system_status() -> dict:
    """
    Tier 1: Discovery
    Returns basic XCO system and version information.
    Read-only, no side effects.
    """
    client = XCOClient()

    # This endpoint is safe and non-mutating
    # If your XCO version differs, we can adjust path
    data = client.get("/system")

    return {
        "ok": True,
        "tier": "discovery",
        "object": "system",
        "data": {
            "version": data.get("version"),
            "build": data.get("build"),
            "uptime": data.get("uptime"),
            "hostname": data.get("hostname"),
        },
        "read_only_enforced": client.read_only,
    }



if __name__ == "__main__":
    # Streamable HTTP transport exposes /mcp on port 8000 by default.
     mcp.run(transport="stdio")


