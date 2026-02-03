# mcp_runtime/server.py

import os
import os
from dotenv import load_dotenv

load_dotenv()   

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

        # ---- Phase 2.x context components ----
        self.context_validator = ContextValidator()
        self.context_injector = ContextInjector()

        # ---- Auth manager (token lifecycle owner) ----
        self.auth = AuthManager()

        # ---- Transport (auth-aware) ----
        self.transport = XCOTransport(
            host=os.environ["XCO_HOST"],
            auth=self.auth,
            verify_tls=os.environ.get("XCO_VERIFY_TLS", "false").lower() == "true",
            timeout=int(os.environ.get("XCO_TIMEOUT_SECONDS", "20")),
        )

        # ---- Context resolver (Phase 2.1+) ----
        self.context_resolver = ContextResolver(self.transport)

    def list_tools(self):
        return self.registry.list_tools()

    def invoke(self, tool_name: str, inputs: dict, context: dict | None = None):
        """
        Phase 2.6:
        - Accept context either as strings (needs resolve) OR dicts (already resolved)
        - Merge deterministically
        - Validate AFTER resolution/merge, BEFORE transport
        """

        tool = self.registry.get(tool_name)
        if not tool:
            raise ToolNotFound(tool_name)

        # ---- Policy enforcement ----
        enforce_policy(tool, auto_mode=self.auto_mode)

        # ---- Start with empty resolved_context ----
        resolved_context: dict = {}

        # ---- Phase 2.6 merge: bring in incoming context first ----
        # This ensures dict contexts from previous calls are preserved.
        merged_incoming = self.context_validator.merge({}, context or {})

        # ---- Resolve strings into canonical dict objects ----
        # NOTE: if caller passed a dict with id, we keep it as-is.
        if merged_incoming:
            # ---- Fabric ----
            if "fabric" in merged_incoming:
                val = merged_incoming["fabric"]
                if isinstance(val, dict) and "id" in val:
                    resolved_context["fabric"] = val
                else:
                    resolved_context["fabric"] = self.context_resolver.resolve_fabric(val)

            # ---- Tenant ----
            if "tenant" in merged_incoming:
                val = merged_incoming["tenant"]
                if isinstance(val, dict) and "id" in val:
                    resolved_context["tenant"] = val
                else:
                    resolved_context["tenant"] = self.context_resolver.resolve_tenant(val)

            # ---- Device ----
            if "device" in merged_incoming:
                val = merged_incoming["device"]
                if isinstance(val, dict) and "id" in val:
                    resolved_context["device"] = val
                else:
                    resolved_context["device"] = self.context_resolver.resolve_device(
                        val,
                        fabric_ctx=resolved_context.get("fabric"),
                        tenant_ctx=resolved_context.get("tenant"),
                    )

            # ---- If device exists and fabric was NOT explicitly provided, auto-derive fabric ----
            if "device" in resolved_context and "fabric" not in resolved_context:
                dev = resolved_context["device"]
                if dev.get("fabric_id") is not None and dev.get("fabric_name") is not None:
                    resolved_context["fabric"] = {
                        "id": dev["fabric_id"],
                        "name": dev["fabric_name"],
                    }

        # ---- Phase 2.6 validation: validate AFTER resolution ----
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
