# tools/fabric/efa_command_list.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json
import re


# ---------------------------
# Small utilities
# ---------------------------

def _as_int(v: Any, default: int) -> int:
    try:
        iv = int(v)
        return iv
    except Exception:
        return default


def _safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        if k not in cur:
            return default
        cur = cur[k]
    return default if cur is None else cur


def _truncate(items: List[Any], max_items: int) -> Tuple[List[Any], bool]:
    if max_items <= 0:
        return [], True
    if len(items) <= max_items:
        return items, False
    return items[:max_items], True


# ---------------------------
# Transport / Tier-1 calling helpers
# ---------------------------

def _transport_get(transport: Any, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort adapter for whatever transport object the runtime passes.
    Returns: {"status": int, "payload": Any, "error": Optional[str]}
    """
    for meth_name in ("request", "send", "call"):
        fn = getattr(transport, meth_name, None)
        if not callable(fn):
            continue
        try:
            res = fn("GET", path, params=params)
            if isinstance(res, dict) and "status" in res:
                return res
        except Exception as e:
            return {"status": 500, "payload": None, "error": f"transport.{meth_name} failed: {e}"}

    return {"status": 500, "payload": None, "error": "No supported transport method found."}


def _call_tier1(
    tool_name: str,
    tool_inputs: Dict[str, Any],
    *,
    registry: Any,
    transport: Any = None,
) -> Dict[str, Any]:
    """
    Call Tier-1 tools in the most reliable way available.

    1) If registry exposes invoke/call/run methods, try those.
    2) Else if registry exposes tool catalog + transport exists, call endpoint via transport.
    3) Else last-resort hardcoded GET paths (kept tight).
    """
    # 1) Preferred: registry invoke-style APIs
    for meth_name in ("invoke", "call", "run"):
        fn = getattr(registry, meth_name, None)
        if callable(fn):
            try:
                res = fn(tool_name, tool_inputs)
                if isinstance(res, dict) and "status" in res:
                    return res
            except Exception as e:
                return {"status": 500, "payload": None, "error": f"registry.{meth_name} failed: {e}"}

    # 2) Use tool catalog -> transport request
    tool_def = None
    for meth_name in ("get_tool_def", "tool_def", "get_tool", "lookup_tool"):
        fn = getattr(registry, meth_name, None)
        if callable(fn):
            try:
                tool_def = fn(tool_name)
            except Exception:
                tool_def = None
            break

    if isinstance(tool_def, dict) and transport is not None:
        endpoint = tool_def.get("endpoint", {}) or {}
        method = str(tool_def.get("method", "GET")).upper()
        path = endpoint.get("path")
        if method == "GET" and isinstance(path, str) and path.startswith("/"):
            return _transport_get(transport, path, tool_inputs)

    # 3) Last-resort hardcoded paths (kept tight)
    if transport is not None:
        if tool_name == "fabric_get_running_config":
            return _transport_get(transport, "/v1/fabric/runningConfig", tool_inputs)
        if tool_name == "fabric_get_fabrics":
            return _transport_get(transport, "/v1/fabric/fabrics", tool_inputs)

    return {"status": 500, "payload": None, "error": f"Tool not registered / callable: {tool_name}"}


# ---------------------------
# Payload normalization
# ---------------------------

def _extract_lines(payload: Any) -> Tuple[List[str], Optional[str]]:
    """
    Normalize 'running config' payload into a list of textual lines/commands.

    Handles common shapes:
      - list[str]
      - dict with keys: items/lines/payload/nested payloads
      - str with JSON content or multiline content
    """
    note = None

    def _flatten(x: Any) -> List[str]:
        if x is None:
            return []
        if isinstance(x, list):
            out: List[str] = []
            for it in x:
                out.extend(_flatten(it))
            return out
        if isinstance(x, dict):
            # common fields
            for k in ("lines", "items", "commands", "cmds"):
                v = x.get(k)
                if v is not None:
                    return _flatten(v)
            nested = x.get("payload")
            if nested is not None:
                return _flatten(nested)
            # fallback: stringify dict as one line
            return [json.dumps(x, ensure_ascii=False)]
        if isinstance(x, str):
            s = x.strip()
            if not s:
                return []
            # Try JSON decode if looks like JSON
            if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                try:
                    parsed = json.loads(s)
                    return _flatten(parsed)
                except Exception:
                    pass
            # Split multiline string
            if "\n" in s:
                return [ln.rstrip("\r") for ln in s.splitlines() if ln.strip()]
            return [s]
        # numbers/bools/others
        return [str(x)]

    lines = _flatten(payload)

    # Clean up escaped quotes (so regex matching is easier)
    cleaned: List[str] = []
    for ln in lines:
        if not isinstance(ln, str):
            ln = str(ln)
        ln2 = ln.replace('\\"', '"').replace("\\'", "'")
        cleaned.append(ln2)

    # If we had to stringify dicts, be honest
    if isinstance(payload, dict) and not any(k in payload for k in ("lines", "items", "commands", "cmds", "payload")):
        note = "Payload shape unexpected; dict was JSON-stringified."

    return cleaned, note


def _match_fabric_commands(lines: List[str], fabric_name: str) -> List[str]:
    """
    Best-effort filter for EFA commands related to a specific fabric.
    Strategy: prefer '--name <fabric>' patterns but also allow '"<fabric>"' appears near 'fabric ' commands.
    """
    name = fabric_name.strip()
    if not name:
        return []

    # --name DC / --name "DC" / --name 'DC'
    re_name = re.compile(rf"--name\s+(['\"])?{re.escape(name)}\1(\s|$)")
    # Some EFA lines may contain: efa fabric ... "DC" without --name (rare, but allow)
    re_fabric_ctx = re.compile(rf"\bfabric\b.*\b{re.escape(name)}\b", re.IGNORECASE)

    out: List[str] = []
    for ln in lines:
        if re_name.search(ln) or re_fabric_ctx.search(ln):
            out.append(ln)
    return out


# ---------------------------
# Tier-2 tool
# ---------------------------

def fabric_get_fabric_efa_command_list(
    inputs: Dict[str, Any],
    *,
    registry: Any = None,
    transport: Any = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    Tier-2 composite:
    - Validates fabric exists (fabric_get_fabrics)
    - Pulls XCO's runningConfig script (fabric_get_running_config)
    - Extracts and filters EFA commands for the requested fabric name
    """

    name = (
        inputs.get("name")
        or inputs.get("fabric_name")
        or inputs.get("fabric-name")
        or inputs.get("fabric")
    )
    name = str(name).strip() if name is not None else ""

    include_raw = bool(inputs.get("include_raw", False))
    include_full_text = bool(inputs.get("include_full_text", False))
    max_items = _as_int(inputs.get("max_items", 200), 200)

    if not name:
        return {
            "status": 400,
            "error": "missing required input: name",
            "payload": {
                "error": "Missing required input 'name'.",
                "next_actions": [
                    {
                        "reason": "Discover valid fabrics first.",
                        "tool": "fabric_get_fabric_overview",
                        "inputs": {"include_health": True, "include_errors": True},
                    }
                ],
            },
        }

    # --- Validate fabric exists
    fabrics_res = _call_tier1("fabric_get_fabrics", {}, registry=registry, transport=transport)
    fabrics_status = int(fabrics_res.get("status") or 500)
    fabrics_payload = fabrics_res.get("payload")

    if fabrics_status != 200 or not isinstance(fabrics_payload, dict):
        return {
            "status": 502,
            "error": "failed to fetch fabrics list",
            "payload": {
                "filter": {"name": name, "max_items": max_items, "include_raw": False},
                "error": "Could not validate fabric name (fabric_get_fabrics failed).",
                "signals": {
                    "fabrics": {"status": fabrics_status, "error": fabrics_res.get("error")},
                },
            },
        }

    items = fabrics_payload.get("items")
    if not isinstance(items, list):
        # some deployments nest payload
        nested = fabrics_payload.get("payload")
        if isinstance(nested, dict) and isinstance(nested.get("items"), list):
            items = nested.get("items")
        else:
            items = []

    fabric_row = None
    for it in items:
        if isinstance(it, dict) and str(it.get("fabric-name", "")).strip() == name:
            fabric_row = it
            break

    if fabric_row is None:
        return {
            "status": 404,
            "error": "fabric not found",
            "payload": {
                "filter": {"name": name, "max_items": max_items, "include_raw": False},
                "error": f"Fabric '{name}' not found",
                "known_fabrics_count": len(items),
                "next_actions": [
                    {
                        "reason": "List valid fabrics (or use overview to discover names).",
                        "tool": "fabric_get_fabric_overview",
                        "inputs": {"include_health": True, "include_errors": True},
                    }
                ],
            },
        }

    # --- Fetch runningConfig (global EFA script)
    run_res = _call_tier1("fabric_get_running_config", {}, registry=registry, transport=transport)
    run_status = int(run_res.get("status") or 500)
    run_payload = run_res.get("payload")

    lines_all: List[str] = []
    parse_note = None
    if run_status == 200:
        lines_all, parse_note = _extract_lines(run_payload)

    matched = _match_fabric_commands(lines_all, name) if run_status == 200 else []

    matched_trunc, matched_truncated = _truncate(matched, max_items)

    # Verdict:
    # - PASS only if runningConfig fetched and we found at least one correlated command
    # - WARN if runningConfig fetched but correlation found none (inconclusive)
    # - WARN if runningConfig fetch failed
    if run_status != 200:
        verdict = "WARN"
        note = "Could not fetch running config script (fabric_get_running_config failed)."
    else:
        if len(matched) > 0:
            verdict = "PASS"
            note = None
        else:
            verdict = "WARN"
            note = "Running config script returned, but no EFA commands could be correlated to this fabric name (treat as inconclusive)."

    recommendations: List[str] = []
    if parse_note:
        recommendations.append(parse_note)
    if note:
        recommendations.append(note)

    next_actions: List[Dict[str, Any]] = [
        {
            "reason": "Inspect timeline/events for context (config/health changes, executions).",
            "tool": "fabric_get_fabric_health_timeline",
            "inputs": {"name": name, "include_exec_details": False},
        },
        {
            "reason": "See recent executions related to this fabric (helps interpret script output).",
            "tool": "fabric_get_fabric_execution_recent",
            "inputs": {"name": name},
        },
    ]

    out: Dict[str, Any] = {
        "filter": {
            "name": name,
            "max_items": max_items,
            "include_full_text": include_full_text,
            "include_raw": False,
        },
        "summary": {
            "fabric": name,
            "verdict": verdict,
            "running_config_status": run_status,
            "total_lines_extracted": len(lines_all) if run_status == 200 else None,
            "matched_count": len(matched) if run_status == 200 else None,
            "matched_returned": len(matched_trunc) if run_status == 200 else None,
            "matched_truncated": matched_truncated if run_status == 200 else None,
            "note": (recommendations[0] if recommendations else None),
        },
        "signals": {
            "fabric_summary_row": {
                "fabric-name": fabric_row.get("fabric-name"),
                "fabric-id": fabric_row.get("fabric-id"),
                "fabric-health": fabric_row.get("fabric-health"),
                "fabric-status": fabric_row.get("fabric-status"),
                "fabric-type": fabric_row.get("fabric-type"),
                "fabric-stage": fabric_row.get("fabric-stage"),
            },
            "efa_commands": {
                "status": run_status,
                "count": len(matched_trunc) if run_status == 200 else 0,
                "items": matched_trunc if run_status == 200 else [],
                "truncated": matched_truncated if run_status == 200 else False,
            },
        },
        "recommendations": recommendations,
        "next_actions": next_actions,
    }

    if include_full_text and run_status == 200:
        # Provide the *entire* extracted script text (still normalized)
        out["signals"]["full_script_text"] = "\n".join(lines_all)

    if include_raw:
        out["filter"]["include_raw"] = True
        out["raw"] = {
            "fabric_get_fabrics": fabrics_res,
            "fabric_get_running_config": run_res,
        }

    return {"status": 200 if run_status in (200, 404) else 200, "payload": out}

