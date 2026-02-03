# mcp_runtime/tool_capabilities.py

from typing import Dict, Optional


class ToolCapabilityError(Exception):
    pass


class ToolCapabilityResolver:
    """
    Phase 4.2:
    Resolve MCP tools by declared capabilities.
    """

    def __init__(self, registry):
        self.registry = registry

    def find_tool(
        self,
        action: str,
        object_: str,
        scope_keys: Optional[list] = None,
    ) -> str:
        """
        Find a tool matching requested capability.
        """

        for name, tool in self.registry.tools.items():
            caps = tool.get("capabilities")
            if not caps:
                continue

            if caps.get("action") != action:
                continue

            if caps.get("object") != object_:
                continue

            if scope_keys:
                tool_scopes = caps.get("scope", [])
                if not all(s in tool_scopes for s in scope_keys):
                    continue

            return name

        raise ToolCapabilityError(
            f"No tool found for action={action}, object={object_}, scope={scope_keys}"
        )

