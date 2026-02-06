import os
import json
from dotenv import load_dotenv

# --------------------------------------------------
# Logging setup (MUST be first)
# --------------------------------------------------
from mcp_runtime.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("mcp.server")
invoke_logger = get_logger("mcp.invoke")

# --------------------------------------------------
# Env
# --------------------------------------------------
load_dotenv()

# --------------------------------------------------
# MCP imports
# --------------------------------------------------
from mcp_runtime.registry import MCPRegistry
from mcp_runtime.policy import enforce_policy
from mcp_runtime.errors import ToolNotFound
from mcp_runtime.transport import XCOTransport
from mcp_runtime.auth import AuthManager
from mcp_runtime.context_injection import ContextInjector
from mcp_runtime.context_validator import ContextValidator

from mcp_runtime.session import MCPSession
from mcp_runtime.context_merge import merge_context
from mcp_runtime.tracing import new_request_id, new_correlation_id
from mcp_runtime.mutation_registry import MutationRegistry
from mcp_runtime.mutation_ledger import MutationLedger


# ==================================================
# MCP SERVER
# ==================================================
class MCPServer:
    def __init__(self, auto_mode=False):
        from mcp_runtime.context_resolver import ContextResolver

        self.registry = MCPRegistry().load()
        self.auto_mode = auto_mode
        self.mutations = MutationRegistry()
        self.mutation_ledger = MutationLedger()

        # ---- Phase 2.x context components ----
        self.context_validator = ContextValidator()
        self.context_injector = ContextInjector()

        # ---- Auth manager ----
        self.auth = AuthManager()

        # ---- Transport ----
        self.transport = XCOTransport(
            host=os.environ["XCO_HOST"],
            auth=self.auth,
            verify_tls=os.environ.get("XCO_VERIFY_TLS", "false").lower() == "true",
            timeout=int(os.environ.get("XCO_TIMEOUT_SECONDS", "20")),
        )

        # ---- Context resolver ----
        self.context_resolver = ContextResolver(self.transport)

        logger.info(
            "MCPServer initialized auto_mode=%s tools=%d",
            self.auto_mode,
            len(self.registry.list_tools()),
        )

    def list_tools(self):
        return self.registry.list_tools()

    # --------------------------------------------------
    # INVOKE
    # --------------------------------------------------
    def invoke(
        self,
        tool_name: str,
        inputs: dict,
        context: dict | None = None,
        session: MCPSession | None = None,
    ):
        request_id = new_request_id()
        correlation_id = (
            session.correlation_id
            if session and hasattr(session, "correlation_id")
            else new_correlation_id()
        )

        invoke_logger.info(
            "invoke start tool=%s request_id=%s correlation_id=%s context=%s",
            tool_name,
            request_id,
            correlation_id,
            context,
        )


        try:
            tool = self.registry.get(tool_name)
            if not tool:
                raise ToolNotFound(tool_name)

            enforce_policy(tool, auto_mode=self.auto_mode)

            invoke_logger.info(
                "policy decision tool=%s risk=%s mode=%s allowed=%s",
                tool_name,
                tool["policy"]["risk"],
                "auto" if self.auto_mode else "manual",
                True,
            )


            session_ctx = session.get_context() if session else {}

            merged_incoming = self.context_validator.merge({}, session_ctx)
            merged_incoming = self.context_validator.merge(
                merged_incoming,
                context or {},
            )

            resolved_context: dict = {}

            if merged_incoming:
                # -------------------------
                # Fabric (SAFE FALLBACK)
                # -------------------------
                if "fabric" in merged_incoming:
                    val = merged_incoming["fabric"]
                    if isinstance(val, dict) and "id" in val:
                        resolved_context["fabric"] = val
                    else:
                        try:
                            resolved = self.context_resolver.resolve_fabric(val)
                            resolved_context["fabric"] = (
                                resolved
                                if resolved
                                else {"name": str(val).upper()}
                            )
                        except Exception:
                            resolved_context["fabric"] = {
                                "name": str(val).upper()
                            }

                # -------------------------
                # Tenant
                # -------------------------
                if "tenant" in merged_incoming:
                    val = merged_incoming["tenant"]
                    if isinstance(val, dict) and "id" in val:
                        resolved_context["tenant"] = val
                    else:
                        resolved_context["tenant"] = (
                            self.context_resolver.resolve_tenant(val)
                        )

                # -------------------------
                # Device (SAFE FALLBACK)
                # -------------------------
                if "device" in merged_incoming:
                    val = merged_incoming["device"]
                    if isinstance(val, dict) and "id" in val:
                        resolved_context["device"] = val
                    else:
                        try:
                            resolved = self.context_resolver.resolve_device(
                                val,
                                fabric_ctx=resolved_context.get("fabric"),
                                tenant_ctx=resolved_context.get("tenant"),
                            )
                            resolved_context["device"] = (
                                resolved
                                if resolved
                                else {"name": str(val)}
                            )
                        except Exception:
                            resolved_context["device"] = {"name": str(val)}

                # ---- Auto-derive fabric from device ----
                if "device" in resolved_context and "fabric" not in resolved_context:
                    dev = resolved_context["device"]
                    if dev.get("fabric_id") and dev.get("fabric_name"):
                        resolved_context["fabric"] = {
                            "id": dev["fabric_id"],
                            "name": dev["fabric_name"],
                        }

            # ---- Validate resolved context ----
            self.context_validator.validate(resolved_context)

            # ==================================================
            # 🔑 TOOL-DRIVEN CONTEXT → INPUT INJECTION (THE FIX)
            # ==================================================
            capabilities = tool.get("capabilities", {})
            fabric_param = capabilities.get("fabric_param")

            if fabric_param and "fabric" in resolved_context:
                fabric_ctx = resolved_context["fabric"]

                # Only inject if caller didn't already specify it
                if fabric_param not in inputs:
                    if fabric_param == "fabric-name" and "name" in fabric_ctx:
                        inputs["fabric-name"] = fabric_ctx["name"]
                    elif fabric_param == "fabric-id" and "id" in fabric_ctx:
                        inputs["fabric-id"] = fabric_ctx["id"]

            endpoint = tool["endpoint"]

            response = self.transport.request(
                method=tool["method"],
                port=endpoint.get("port"),
                path=endpoint["path"],
                params=inputs,
                context=resolved_context,
            )

            # ---- Persist context ONLY on success ----
            if session:
                session.update_context(resolved_context)

            invoke_logger.info(
                "invoke success tool=%s status=%s url=%s correlation_id=%s",
                tool_name,
                response["status"],
                response["url"],
                correlation_id,
            )


            return {
                "tool": tool_name,
                "status": response["status"],
                "payload": response["payload"],
                "context": resolved_context,
                "meta": {
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "risk": tool["policy"]["risk"],
                    "effective_port": response["effective_port"],
                    "url": response["url"],
                    "params": response.get("params", {}),
                },
                "explain": {
                    "context": {
                        "input_context": context or {},
                        "session_context": session_ctx if session else {},
                        "resolved_context": resolved_context,
                    },
                    "validation": {"status": "passed"},
                    "policy": {
                        "risk": tool["policy"]["risk"],
                        "mode": "auto" if self.auto_mode else "manual",
                    },
                },
            }

        except Exception as e:
            invoke_logger.exception(
                "invoke failed tool=%s request_id=%s correlation_id=%s error=%s",
                tool_name,
                request_id,
                correlation_id,
                str(e),
            )

            raise


# ==================================================
# SERVER FACTORY
# ==================================================
def create_server():
    return MCPServer(auto_mode=False)


# ==================================================
# MAIN
# ==================================================
if __name__ == "__main__":
    mcp = create_server()
    logger.info("MCP Server started")
    for t in mcp.list_tools():
        logger.info("registered tool=%s", t["name"])
