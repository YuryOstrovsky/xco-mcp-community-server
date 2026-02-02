# mcp_runtime/server.py

import os

from mcp_runtime.registry import MCPRegistry
from mcp_runtime.policy import enforce_policy
from mcp_runtime.errors import ToolNotFound
from mcp_runtime.transport import XCOTransport
from mcp_runtime.auth import AuthManager
from mcp_runtime.context_injection import ContextInjector
from mcp_runtime.context_validator import ContextValidator


class MCPServer:
    def __init__(self, auto_mode=False):
        from mcp_runtime.context_resolver import ContextResolver

        self.registry = MCPRegistry().load()
        self.auto_mode = auto_mode

        # ---- Auth manager (token lifecycle owner) ----
        self.auth = AuthManager()

        # ---- Transport (auth-aware) ----
        self.transport = XCOTransport(
            host=os.environ["XCO_HOST"],
            auth=self.auth,
            verify_tls=os.environ.get("XCO_VERIFY_TLS", "false").lower() == "true",
            timeout=int(os.environ.get("XCO_TIMEOUT_SECONDS", "20")),
        )

        # ---- Context plumbing ----
        self.context_resolver = ContextResolver(self.transport)
        self.context_injector = ContextInjector()
        self.context_validator = ContextValidator()

    def list_tools(self):
        return self.registry.list_tools()

    def invoke(self, tool_name: str, inputs: dict, context: dict | None = None):
        tool = self.registry.get(tool_name)
        if not tool:
            raise ToolNotFound(tool_name)

        # ---- Policy enforcement ----
        enforce_policy(tool, auto_mode=self.auto_mode)

        resolved_context: dict = {}

        if context:
            # ---- Fabric ----
            if "fabric" in context:
                val = context["fabric"]
                if isinstance(val, dict) and "id" in val:
                    resolved_context["fabric"] = val
                else:
                    resolved_context["fabric"] = self.context_resolver.resolve_fabric(val)

            # ---- Tenant ----
            if "tenant" in context:
                val = context["tenant"]
                if isinstance(val, dict) and "id" in val:
                    resolved_context["tenant"] = val
                else:
                    resolved_context["tenant"] = self.context_resolver.resolve_tenant(val)

            # ---- Device ----
            if "device" in context:
                val = context["device"]
                if isinstance(val, dict) and "id" in val:
                    resolved_context["device"] = val
                else:
                    resolved_context["device"] = self.context_resolver.resolve_device(
                        val,
                        fabric_ctx=resolved_context.get("fabric"),
                        tenant_ctx=resolved_context.get("tenant"),
                    )

        # ---- Context validation (Phase 2.5) ----
        self.context_validator.validate(resolved_context)

        endpoint = tool["endpoint"]

        response = self.transport.request(
            method=tool["method"],
            port=endpoint.get("port"),
            path=endpoint["path"],
            params=inputs,
            context=resolved_context,
        )

        return {
            "tool": tool_name,
            "status": response["status"],
            "payload": response["payload"],
            "context": resolved_context,
            "meta": {
                "risk": tool["policy"]["risk"],
                "effective_port": response["effective_port"],
                "url": response["url"],
                "params": response.get("params", {}),
            },
        }
