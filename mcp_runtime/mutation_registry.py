# mcp_runtime/mutation_registry.py

from typing import Dict


class MutationRegistryError(ValueError):
    pass


class MutationRegistry:
    """
    Phase 6.1:
    Registry of mutation-capable MCP tools.
    """

    def __init__(self):
        self._tools: Dict[str, Dict] = {}

    def register(
        self,
        tool: str,
        *,
        rollback_tool: str,
        description: str = "",
    ):
        if tool in self._tools:
            raise MutationRegistryError(
                f"Mutation tool already registered: {tool}"
            )

        self._tools[tool] = {
            "tool": tool,
            "rollback_tool": rollback_tool,
            "description": description,
        }

    def is_mutating(self, tool: str) -> bool:
        return tool in self._tools

    def get(self, tool: str) -> Dict:
        if tool not in self._tools:
            raise MutationRegistryError(
                f"Unknown mutation tool: {tool}"
            )
        return self._tools[tool]

