#!/usr/bin/env python3
"""
Phase 1.3 — MCP Tool Manifest Generator

Input:
  generated/mcp_capabilities.json

Output:
  generated/mcp_tools.json

Purpose:
  Convert policy-classified XCO endpoints into MCP-ready tool definitions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


IN_PATH = Path("generated/mcp_capabilities.json")
OUT_PATH = Path("generated/mcp_tools.json")


def _param_name(p: Any) -> str | None:
    """
    Params sometimes come as:
      - "name" (string)
      - {"name": "foo", ...} (dict)
    Return a usable param name or None.
    """
    if isinstance(p, str):
        return p.strip() or None
    if isinstance(p, dict):
        for k in ("name", "param", "key", "id"):
            v = p.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def build_input_schema(params: Dict[str, Any]) -> Dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    # Path params (usually required)
    for p in params.get("path", []) or []:
        name = _param_name(p)
        if not name:
            continue
        schema["properties"][name] = {"type": "string"}
        if name not in schema["required"]:
            schema["required"].append(name)

    # Query params (optional unless you later choose to mark required ones)
    for q in params.get("query", []) or []:
        name = _param_name(q)
        if not name:
            continue
        schema["properties"][name] = {"type": "string"}

    # Body (if present)
    if params.get("body"):
        schema["properties"]["body"] = {
            "type": "object",
            "description": "Request body payload"
        }

    return schema


def generate_tools(caps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tools = []

    for cap in caps:
        tool = {
            "name": cap["mcp_action"],
            "description": cap["human_readable"],
            "category": cap["category"],
            "method": cap["method"],
            "endpoint": {
                "host": cap["host"],
                "port": cap["port"],
                "path": cap["url"],
            },
            "auth": cap["auth"],
            "input_schema": build_input_schema(cap.get("params", {})),
            "policy": {
                "risk": cap["risk"],
                "allowed_in_auto_mode": cap["allowed_in_auto_mode"],
                "requires_confirmation": cap["requires_confirmation"],
            },
            "tags": cap.get("tags", []),
        }

        tools.append(tool)

    return tools


def main() -> int:
    if not IN_PATH.exists():
        raise SystemExit("ERROR: mcp_capabilities.json not found")

    caps = json.loads(IN_PATH.read_text(encoding="utf-8"))

    tools = generate_tools(caps)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(tools, indent=2, ensure_ascii=False), encoding="utf-8")

    auto_allowed = sum(1 for t in tools if t["policy"]["allowed_in_auto_mode"])
    print(f"Wrote {OUT_PATH}")
    print(f"Total MCP tools: {len(tools)}")
    print(f"Auto-mode allowed: {auto_allowed}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

