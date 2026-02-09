import json
from pathlib import Path

from mcp_runtime.tier1_tools import TIER1_TOOL_NAMES
from tools.system.diagnostics import system_get_last_execution_diagnostic
from tools.fabric.overview import fabric_get_fabric_overview
from tools.fabric.health_summary import fabric_get_fabric_health_summary
from tools.fabric.health_timeline import fabric_get_fabric_health_timeline
from tools.fabric.validation_report import fabric_get_fabric_validation_report
from tools.fabric.errors_summary import fabric_get_fabric_errors_summary
from tools.fabric.execution_last_failed import fabric_get_fabric_execution_last_failed
from tools.fabric.execution_recent import fabric_get_fabric_execution_recent
from tools.fabric.efa_command_list import fabric_get_fabric_efa_command_list
#from tools.inventory.fabric_switches_summary import inventory_get_fabric_switches_summary












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

        
        self.handlers["fabric_get_fabric_health_summary"] = (
            fabric_get_fabric_health_summary
        )

        self.handlers["fabric_get_fabric_health_timeline"] = (
            fabric_get_fabric_health_timeline
        )

        self.handlers["fabric_get_fabric_validation_report"] = (
            fabric_get_fabric_validation_report
        )

        self.handlers["fabric_get_fabric_errors_summary"] = (
            fabric_get_fabric_errors_summary
        )

        self.handlers["fabric_get_fabric_execution_last_failed"] = (
            fabric_get_fabric_execution_last_failed
        )

        self.handlers["fabric_get_fabric_execution_recent"] = (
            fabric_get_fabric_execution_recent
        )

        self.handlers["fabric_get_fabric_efa_command_list"] = (
            fabric_get_fabric_efa_command_list
        )

 #       self.handlers["inventory_get_fabric_switches_summary"] = (
 #           inventory_get_fabric_switches_summary
 #       )



        




        


        


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
