#!/usr/bin/env python3
"""
Phase 1.2.2 — Endpoint Capability Classification

Input:
  generated/resolved_endpoints.json  (from resolve_endpoints.py)

Output:
  generated/mcp_capabilities.json

What it does:
  - Creates a deterministic, rule-based "capability" layer on top of resolved endpoints
  - Assigns:
      mcp_action, category, requires_confirmation, allowed_in_auto_mode, tags, etc.
  - Keeps ALL endpoints (GET/POST/PUT/DELETE), but restricts auto mode for mutations.

Run:
  python tools/classify_endpoints.py

Optional env:
  MCP_AUTO_ALLOW_READ_ONLY=true|false  (default true)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List


IN_PATH = Path("generated/resolved_endpoints.json")
OUT_PATH = Path("generated/mcp_capabilities.json")

AUTO_ALLOW_READ_ONLY = os.getenv("MCP_AUTO_ALLOW_READ_ONLY", "true").lower() in ("1", "true", "yes", "y")

# Keywords that imply a higher-risk or disruptive action.
# If found in URL/summary/description/operationId, we force confirmation and disallow auto mode.
DANGEROUS_KEYWORDS = {
    "delete", "remove", "destroy", "wipe", "purge",
    "reset", "reboot", "restart",
    "execute", "run", "trigger",
    "upgrade", "firmware", "flash",
    "password", "secret", "token", "credential",
    "reconcile", "sync", "apply", "commit",
    "disable", "enable",
    "shutdown", "poweroff",
    "factory", "format",
}

# Lower-risk but still mutation-ish words. Helps tagging.
MUTATION_HINTS = {
    "create", "post", "update", "put", "patch", "set", "edit", "assign",
    "add", "insert", "import", "export", "provision", "configure",
}

# Common read-ish keywords
READ_HINTS = {
    "get", "list", "show", "describe", "query", "search", "health", "status", "validate",
}

def _safe_lower(s: Any) -> str:
    return str(s or "").lower()

def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "action"

def _category_from_url(url: str) -> str:
    """
    Example:
      /v1/system/feature -> system
      /v1/fabric/fabrics -> fabric
      /v1/monitor/service/enable -> monitor
    """
    parts = [p for p in url.split("/") if p]
    if not parts:
        return "misc"
    # Expect ["v1", "<category>", ...]
    if parts[0] in ("v1", "v2") and len(parts) >= 2:
        return parts[1]
    # Fallback: first segment
    return parts[0]

def _danger_score(endpoint: Dict[str, Any]) -> Dict[str, Any]:
    url = _safe_lower(endpoint.get("url"))
    summary = _safe_lower(endpoint.get("summary"))
    desc = _safe_lower(endpoint.get("description"))
    opid = _safe_lower(endpoint.get("operationId"))

    haystack = " ".join([url, summary, desc, opid])

    hit = sorted([k for k in DANGEROUS_KEYWORDS if k in haystack])
    hint_mut = sorted([k for k in MUTATION_HINTS if k in haystack])
    hint_read = sorted([k for k in READ_HINTS if k in haystack])

    return {
        "dangerous_hits": hit,
        "mutation_hints": hint_mut,
        "read_hints": hint_read,
    }

def _build_mcp_action(endpoint: Dict[str, Any], category: str) -> str:
    """
    Build a stable action name. Prefer operationId if present, else fall back to method+url.
    """
    opid = endpoint.get("operationId") or ""
    method = _safe_lower(endpoint.get("method"))
    url = endpoint.get("url") or ""

    if opid:
        base = _slugify(opid)
        return f"{category}_{base}"
    # fallback: use last path segment(s)
    parts = [p for p in url.split("/") if p and p not in ("v1", "v2")]
    tail = "_".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else "root")
    tail = _slugify(tail)
    return f"{category}_{method}_{tail}"

def _human_readable(endpoint: Dict[str, Any]) -> str:
    summary = (endpoint.get("summary") or "").strip()
    if summary:
        return summary
    # fallback: method + url
    method = (endpoint.get("method") or "").upper()
    url = (endpoint.get("url") or "").strip()
    return f"{method} {url}".strip()

def classify(endpoints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for ep in endpoints:
        method = (ep.get("method") or "GET").upper()
        risk = ep.get("risk") or ("SAFE_READ" if method == "GET" else "MUTATION")

        url = ep.get("url") or ""
        category = _category_from_url(url)
        score = _danger_score(ep)

        # Base rules
        is_mutation = (risk == "MUTATION") or (method in ("POST", "PUT", "PATCH", "DELETE"))
        is_read = not is_mutation

        requires_confirmation = False
        allowed_in_auto_mode = False

        # Determine confirmation + auto rules
        if is_read:
            requires_confirmation = False
            allowed_in_auto_mode = AUTO_ALLOW_READ_ONLY
        else:
            # Mutations always require confirmation by default
            requires_confirmation = True
            allowed_in_auto_mode = False

        # Escalate if any dangerous keywords present (even for GET)
        if score["dangerous_hits"]:
            requires_confirmation = True
            allowed_in_auto_mode = False

        # Tags for UI/grouping/debug
        tags = []
        if is_read:
            tags.append("read")
        if is_mutation:
            tags.append("mutation")
        tags.extend(score["dangerous_hits"])
        # Deduplicate, keep stable
        tags = sorted(set(tags))

        mcp_action = _build_mcp_action(ep, category)

        cap = {
            "id": ep.get("id"),
            "service": ep.get("service"),
            "category": category,
            "method": method,
            "host": ep.get("host"),
            "port": ep.get("port"),
            "url": url,
            "auth": ep.get("auth"),
            "risk": risk,
            "requires_confirmation": requires_confirmation,
            "allowed_in_auto_mode": allowed_in_auto_mode,
            "mcp_action": mcp_action,
            "human_readable": _human_readable(ep),
            "operationId": ep.get("operationId"),
            "summary": ep.get("summary"),
            "description": ep.get("description"),
            "params": ep.get("params") or {"path": [], "query": [], "body": None},
            "tags": tags,
            "analysis": {
                "dangerous_hits": score["dangerous_hits"],
                "mutation_hints": score["mutation_hints"],
                "read_hints": score["read_hints"],
            },
        }
        out.append(cap)

    return out

def main() -> int:
    if not IN_PATH.exists():
        raise SystemExit(f"ERROR: Missing input file: {IN_PATH} (run tools/resolve_endpoints.py first)")

    endpoints = json.loads(IN_PATH.read_text(encoding="utf-8"))
    if not isinstance(endpoints, list):
        raise SystemExit("ERROR: resolved_endpoints.json must be a JSON array")

    caps = classify(endpoints)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(caps, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print small stats for you
    total = len(caps)
    auto_allowed = sum(1 for c in caps if c["allowed_in_auto_mode"])
    confirm = sum(1 for c in caps if c["requires_confirmation"])
    reads = sum(1 for c in caps if "read" in c.get("tags", []))
    muts = sum(1 for c in caps if "mutation" in c.get("tags", []))
    danger = sum(1 for c in caps if c["analysis"]["dangerous_hits"])

    print(f"Wrote {OUT_PATH}")
    print(f"Total: {total}")
    print(f"Read-tagged: {reads} | Mutation-tagged: {muts}")
    print(f"Allowed in auto mode: {auto_allowed}")
    print(f"Requires confirmation: {confirm}")
    print(f"Has dangerous keyword hits: {danger}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())

