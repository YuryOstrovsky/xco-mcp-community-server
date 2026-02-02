# mcp_runtime/context.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class MCPContext:
    fabric_name: Optional[str] = None
    fabric_id: Optional[int] = None

    tenant_name: Optional[str] = None
    tenant_id: Optional[int] = None

    resolved: bool = False

