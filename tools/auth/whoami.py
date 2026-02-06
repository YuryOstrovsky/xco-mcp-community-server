from typing import Dict, Any

from mcp_runtime.tools import tool
from mcp_runtime.context import ExecutionContext
from xco.client import XCOClient


@tool(
    name="xco.auth.whoami",
    description="Return the authenticated XCO user context, tenant scope, and RBAC roles."
)
def xco_auth_whoami(ctx: ExecutionContext) -> Dict[str, Any]:
    """
    Read-only tool.
    Returns the effective authentication and authorization context
    for the current MCP execution against XCO.
    """

    client = XCOClient.from_env()

    # ---- Trace: start ----
    ctx.trace.info("Resolving authenticated XCO user context")

    # Call Auth / RBAC context endpoint
    # (Exact path encapsulated in client)
    me = client.get_current_user()

    # Normalize output (defensive: fields may vary by role)
    result = {
        "user": me.get("username") or me.get("user") or "unknown",
        "user_type": me.get("userType") or me.get("type") or "unknown",
        "tenant": me.get("tenant") or None,
        "roles": me.get("roles") or [],
        "permissions": me.get("permissions") or [],
        "raw": me  # preserved for trace/debug
    }

    # ---- Explanation contract ----
    ctx.explain(
        action="Query authenticated user context",
        system="ExtremeCloud Orchestrator",
        safety="Read-only authentication context lookup",
        result_summary={
            "user": result["user"],
            "user_type": result["user_type"],
            "tenant": result["tenant"],
            "roles_count": len(result["roles"])
        }
    )

    return result

