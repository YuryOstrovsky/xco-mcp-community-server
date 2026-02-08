import json
from pathlib import Path

from mcp_runtime.tier1_tools import TIER1_TOOL_NAMES
from tools.system.diagnostics import system_get_last_execution_diagnostic
from tools.fabric.overview import fabric_get_fabric_overview
from tools.fabric.health_summary import fabric_get_fabric_health_summary


TOOLS_FILE = Path("generated/mcp_tools.json")


class MCPRegistry:
    def __init__(self):
        # tool_name -> tool definition (JSON)
        self.tools = {}

        # tool_name -> execution handler (Python callable)
        self.handlers = {}

    def load(self):
        """
        Load MCP tools from generated/mcp_tools.json
        """
        data = json.loads(TOOLS_FILE.read_text())

        for tool in data:
            name = tool.get("name")

            # ---------------------------------------
            # 🚫 Skip disabled tools (doc-only)
            # ---------------------------------------
            if tool.get("policy", {}).get("disabled") is True:
                continue

            self.tools[name] = tool

            # Tier-1 tools use generic HTTP executor
            if name in TIER1_TOOL_NAMES:
                self.handlers[name] = None  # handled by Tier-1 executor


        # ---- Tier-2 registrations (EXPLICIT) ----
        self.handlers["system_get_last_execution_diagnostic"] = (
            system_get_last_execution_diagnostic
        )

        self.handlers["fabric_get_fabric_overview"] = (
            fabric_get_fabric_overview
        )

        # ---- Tier-2 registrations (EXPLICIT) ----
        self.handlers["fabric_get_fabric_health_summary"] = (
            fabric_get_fabric_health_summary
        )


        return self

    def list_tools(self):
        return list(self.tools.values())

    def get(self, name: str):
        return self.tools.get(name)

    def get_handler(self, name: str):
        """
        Return execution handler if this is a Tier-2 tool.
        """
        return self.handlers.get(name)
