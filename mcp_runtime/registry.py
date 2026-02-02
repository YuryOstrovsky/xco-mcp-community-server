import json
from pathlib import Path
from mcp_runtime.tier1_tools import TIER1_TOOL_NAMES

TOOLS_FILE = Path("generated/mcp_tools.json")


class MCPRegistry:
    def __init__(self):
        self.tools = {}

    def load(self):
        """
        Load MCP tools from generated/mcp_tools.json
        and restrict registry to Tier-1 tools only.
        """
        data = json.loads(TOOLS_FILE.read_text())

        for tool in data:
            name = tool.get("name")
            if name in TIER1_TOOL_NAMES:
                self.tools[name] = tool

        return self

    def list_tools(self):
        """
        Return full tool definitions for all registered tools.
        """
        return list(self.tools.values())

    def get(self, name: str):
        """
        Return a single tool definition by name.
        """
        return self.tools.get(name)
