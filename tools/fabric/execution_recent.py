# tools/fabric/execution_recent.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ---------------------------
# Small helpers
# ---------------------------

def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _is_dict(x: Any) -> bool:
    return isinstance(x, dict)


def _is_list(x: Any) -> bool:
    return isinstance(x, list)


def _truncate(items: List[Any], max_items: int) -> Tuple[List[Any], bool]:
    if max_items is None:
        return items, False
    try:
        max_items = int(max_items)
    except Exception:
        max_items = 0

    if max_items <= 0:
        return [], (len(items) > 0)

    if len(items) <= max_items:
        return items, False
    return items[:max_items], True


def _safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        if k not in cur:
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _normalize_items(payload: Any) -> List[Any]:
    """
    XCO payload shapes vary:
      - {"items":[...]}
      - {"payload":{"items":[...]}}
      - already a list
    """
    if _is_list(payload):
        return payload
    if _is_dict(payload):
        if _is_list(payload.get("items")):
            return payload.get("items")  # type: ignore[return-value]
        nested = payload.get("payload")
        if _is_dict(nested) and _is_list(nested.get("items")):
            return nested.get("items")  # type: ignore[return-value]
    return []


# ---------------------------
# Transport + Tier-1 calling
# ---------------------------

def _transport_get(transport: Any, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort adapter for whatever transport object the runtime passes.
    """
    if transport is None:
        return {"status": 500, "payload": None, "error": "No transport"}

    # try common method names
    for meth_name in ("get", "request", "send", "call"):
        fn = getattr(transport, meth_name, None)
        if not callable(fn):
            continue
        try:
            # Some transports want (method, path, params)
            if meth_name in ("request", "send", "call"):
                res = fn("GET", path, params=params)
            else:
                res = fn(path, params=params)
            if isinstance(res, dict) and "status" in res:
                return res
            # normalize tuple-like (status, payload)
            if isinstance(res, tuple) and len(res) == 2:
                return {"status": res[0], "payload": res[1]}
        except Exception as e:
            return {"status": 500, "payload": None, "error": str(e)}

    return {"status": 500, "payload": None, "error": "Transport has no supported GET method"}


def _call_tier1(
    tool_name: str,
    tool_inputs: Dict[str, Any],
    *,
    registry: Any = None,
    transport: Any = None,
) -> Dict[str, Any]:
    """
    Call Tier-1 tools in the most reliable way available:
    1) If registry exposes invoke/call/run methods, try those.
    2) Else if registry exposes tool catalog + transport exists, call endpoint via transport.
    3) Else last-resort hardcoded GET paths for small set we need.
    """
    # 1) Preferred: registry invoke-style APIs
    if registry is not None:
        for meth in ("invoke_tool", "invoke", "call", "run"):
            fn = getattr(registry, meth, None)
            if callable(fn):
                try:
                    return fn(tool_name, tool_inputs)
                except TypeError:
                    # some registries use (name, inputs=...)
                    try:
                        return fn(tool_name, inputs=tool_inputs)
                    except Exception:
                        pass
                except Exception:
                    pass

        # 2) Try registry tool catalog to get endpoint info
        tool_def = None
        for meth in ("get_tool_definition", "get_tool", "tool_def", "tool_definition"):
            fn = getattr(registry, meth, None)
            if callable(fn):
                try:
                    tool_def = fn(tool_name)
                    break
                except Exception:
                    pass

        if tool_def is None:
            for attr in ("tools", "tool_defs", "catalog"):
                maybe = getattr(registry, attr, None)
                if isinstance(maybe, dict) and tool_name in maybe:
                    tool_def = maybe.get(tool_name)
                    break

        if isinstance(tool_def, dict) and transport is not None:
            endpoint = tool_def.get("endpoint", {}) or {}
            method = (tool_def.get("method") or "GET").upper()
            path = endpoint.get("path")
            if method == "GET" and isinstance(path, str) and path.startswith("/"):
                return _transport_get(transport, path, tool_inputs)

    # 3) Last-resort hardcoded paths (kept tight)
    if transport is not None:
        if tool_name == "fabric_get_fabrics":
            return _transport_get(transport, "/v1/fabric/fabrics", {})
        if tool_name == "fabric_get_execution_list":
            return _transport_get(transport, "/v1/fabric/executions", tool_inputs)
        if tool_name == "fabric_get_execution_get":
            return _transport_get(transport, "/v1/fabric/execution", tool_inputs)

    return {"status": 500, "payload": None, "error": f"Tool not registered / callable: {tool_name}"}


# ---------------------------
# Correlation + summarization
# ---------------------------

def _find_fabric_row(fabrics_payload: Any, name: str) -> Optional[Dict[str, Any]]:
    items = _normalize_items(fabrics_payload)
    for it in items:
        if isinstance(it, dict) and str(it.get("fabric-name") or it.get("fabric_name") or "").lower() == name.lower():
            return it
    return None


def _candidate_strings(obj: Any) -> List[str]:
    """
    Collect short-ish string candidates from dict values for heuristic matching.
    """
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and len(v) <= 500:
                out.append(v)
            elif isinstance(v, (int, float)):
                out.append(str(v))
            elif isinstance(v, dict):
                # peek one level deep
                for _, vv in v.items():
                    if isinstance(vv, str) and len(vv) <= 500:
                        out.append(vv)
    return out


def _execution_id(ex: Dict[str, Any]) -> Optional[str]:
    for k in ("id", "execution_uuid", "uuid", "execution-id", "executionId"):
        v = ex.get(k)
        if v is not None and str(v).strip() != "":
            return str(v)
    return None


def _execution_status(ex: Dict[str, Any]) -> str:
    for k in ("status", "execution-status", "execution_status", "state"):
        v = ex.get(k)
        if v is not None:
            return str(v)
    return "unknown"


def _execution_time(ex: Dict[str, Any]) -> Optional[str]:
    for k in ("start-time", "start_time", "startTime", "timestamp", "time", "created_at", "createdAt"):
        v = ex.get(k)
        if v is not None:
            return str(v)
    return None


def _matches_fabric(ex: Dict[str, Any], fabric_name: str, fabric_id: Optional[Any]) -> bool:
    """
    Best-effort fabric correlation.
    Returns True if execution record clearly references fabric_name or fabric_id.
    """
    # direct keys first
    for k in ("fabric-name", "fabric_name", "fabric", "fabricName"):
        if str(ex.get(k) or "").lower() == fabric_name.lower():
            return True

    if fabric_id is not None:
        for k in ("fabric-id", "fabric_id", "fabricId"):
            if str(ex.get(k) or "") == str(fabric_id):
                return True

    # heuristic: search string fields for fabric name or id
    hay = " | ".join(s.lower() for s in _candidate_strings(ex))
    if fabric_name.lower() in hay:
        return True
    if fabric_id is not None and str(fabric_id).lower() in hay:
        return True

    return False


def _count_by_status(items: List[Dict[str, Any]]) -> Dict[str, int]:
    m: Dict[str, int] = {}
    for ex in items:
        s = _execution_status(ex).lower()
        m[s] = m.get(s, 0) + 1
    return dict(sorted(m.items(), key=lambda kv: (-kv[1], kv[0])))


# ---------------------------
# Tier-2 Tool
# ---------------------------

def fabric_get_fabric_execution_recent(
    inputs: Dict[str, Any],
    *,
    registry: Any = None,
    transport: Any = None,
    http_client: Any = None,  # unused (kept for signature compatibility)
    **kwargs,
) -> Dict[str, Any]:
    """
    Tier-2: Recent executions for a fabric, correlated best-effort to fabric name/id.
    Tier-1 tools used:
      - fabric_get_fabrics (validate + get fabric-id)
      - fabric_get_execution_list (recent executions, optionally filtered by status)
      - fabric_get_execution_get (optional detail for first N matched executions)
    """
    name = (
        inputs.get("name")
        or inputs.get("fabric_name")
        or inputs.get("fabric-name")
    )
    if not name or not str(name).strip():
        return {
            "status": 400,
            "payload": {
                "error": "Missing required input: name",
                "next_actions": [
                    {
                        "reason": "Provide a fabric name.",
                        "tool": "fabric_get_fabric_execution_recent",
                        "inputs": {"name": "<FABRIC_NAME>"},
                    }
                ],
            },
            "error": "missing name",
        }

    limit = _as_int(inputs.get("limit", 50), 50)
    status = str(inputs.get("status", "all")).lower()
    max_items = _as_int(inputs.get("max_items", 10), 10)
    include_detail = bool(inputs.get("include_detail", False))
    detail_limit = _as_int(inputs.get("detail_limit", 3), 3)
    include_raw = bool(inputs.get("include_raw", False))

    filt = {
        "name": str(name),
        "limit": limit,
        "status": status,
        "max_items": max_items,
        "include_detail": include_detail,
        "detail_limit": detail_limit,
        "include_raw": include_raw,
    }

    # Validate fabric exists
    fabrics_res = _call_tier1("fabric_get_fabrics", {}, registry=registry, transport=transport)
    fabrics_status = _as_int(fabrics_res.get("status"), 500)
    fabrics_payload = fabrics_res.get("payload")

    row = _find_fabric_row(fabrics_payload, str(name)) if fabrics_status == 200 else None
    if row is None:
        known_count = 0
        if fabrics_status == 200:
            known_count = len(_normalize_items(fabrics_payload))

        return {
            "status": 404,
            "payload": {
                "filter": filt,
                "error": f"Fabric '{name}' not found",
                "known_fabrics_count": known_count,
                "next_actions": [
                    {
                        "reason": "List valid fabrics (or use overview to discover names).",
                        "tool": "fabric_get_fabric_overview",
                        "inputs": {"include_health": True, "include_errors": True},
                    }
                ],
            },
            "error": "fabric not found",
        }

    fabric_id = row.get("fabric-id")

    # Fetch executions
    exec_inputs: Dict[str, Any] = {"limit": limit, "status": status}
    exec_res = _call_tier1("fabric_get_execution_list", exec_inputs, registry=registry, transport=transport)
    exec_status = _as_int(exec_res.get("status"), 500)
    exec_payload = exec_res.get("payload")

    exec_items_raw = _normalize_items(exec_payload)
    exec_items: List[Dict[str, Any]] = [x for x in exec_items_raw if isinstance(x, dict)]

    matched: List[Dict[str, Any]] = [ex for ex in exec_items if _matches_fabric(ex, str(name), fabric_id)]
    matched_trunc, matched_truncated = _truncate(matched, max_items)

    # Optional details
    detail_map: Dict[str, Any] = {}
    detail_signal = None
    if include_detail and matched_trunc:
        want = min(detail_limit, len(matched_trunc))
        fetched = 0
        for ex in matched_trunc:
            if fetched >= want:
                break
            ex_id = _execution_id(ex)
            if not ex_id:
                continue
            dres = _call_tier1("fabric_get_execution_get", {"id": ex_id}, registry=registry, transport=transport)
            detail_map[ex_id] = {
                "status": _as_int(dres.get("status"), 500),
                "payload": dres.get("payload"),
            }
            fetched += 1

        detail_signal = {
            "requested": want,
            "fetched": fetched,
        }

    # Build a compact list output
    def compact(ex: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": _execution_id(ex),
            "status": _execution_status(ex),
            "time": _execution_time(ex),
            "headline": ex.get("headline") or ex.get("message") or ex.get("command") or ex.get("description"),
        }

    matched_compact = [compact(ex) for ex in matched_trunc]

    # Verdict logic
    verdict = "PASS"
    note = None
    if exec_status != 200:
        verdict = "WARN"
        note = f"Execution list call returned status={exec_status}."
    else:
        if len(exec_items) == 0:
            verdict = "PASS"
            note = "No executions returned by backend."
        elif len(matched) == 0:
            verdict = "WARN"
            note = (
                f"Executions exist (count={len(exec_items)}) but none could be correlated to fabric '{name}' "
                "(matching depends on execution metadata/command fields; treat as inconclusive)."
            )
        else:
            verdict = "PASS"

    # Recommendations + next actions
    recommendations: List[str] = []
    next_actions: List[Dict[str, Any]] = []

    if verdict == "WARN" and note:
        recommendations.append(note)

    # If health is degraded, timeline is always useful
    next_actions.append(
        {
            "reason": "Inspect timeline/events for context.",
            "tool": "fabric_get_fabric_health_timeline",
            "inputs": {"name": str(name), "include_exec_details": False},
        }
    )

    if verdict == "WARN" and len(exec_items) > 0 and len(matched) == 0:
        next_actions.append(
            {
                "reason": "Inspect raw execution list (may show fabric in command/message fields).",
                "tool": "fabric_get_execution_list",
                "inputs": {"limit": limit, "status": status},
            }
        )

    if include_detail and matched_trunc and detail_map:
        recommendations.append("Execution detail included for the most recent matched executions.")

    out: Dict[str, Any] = {
        "status": 200,
        "payload": {
            "filter": filt,
            "summary": {
                "fabric": str(name),
                "verdict": verdict,
                "execution_list_status": exec_status,
                "total_returned": len(exec_items) if exec_status == 200 else None,
                "matched_count": len(matched) if exec_status == 200 else None,
                "matched_returned": len(matched_trunc) if exec_status == 200 else None,
                "matched_truncated": matched_truncated if exec_status == 200 else None,
                "status_counts": _count_by_status(matched) if exec_status == 200 else {},
                "note": note,
            },
            "signals": {
                "fabric_summary_row": {
                    "fabric-name": row.get("fabric-name"),
                    "fabric-id": row.get("fabric-id"),
                    "fabric-health": row.get("fabric-health"),
                    "fabric-status": row.get("fabric-status"),
                    "fabric-type": row.get("fabric-type"),
                    "fabric-stage": row.get("fabric-stage"),
                },
                "execution_list": {
                    "status": exec_status,
                    "returned": len(exec_items) if exec_status == 200 else None,
                    "matched": len(matched) if exec_status == 200 else None,
                },
                "recent_executions": {
                    "items": matched_compact,
                    "truncated": matched_truncated,
                },
                "execution_detail": detail_signal,
            },
            "recommendations": recommendations,
            "next_actions": next_actions,
        },
    }

    if include_detail and detail_map:
        out["payload"]["signals"]["execution_details"] = detail_map

    if include_raw:
        raw: Dict[str, Any] = {
            "fabric_get_fabrics": {"status": fabrics_status, "payload": fabrics_payload},
            "fabric_get_execution_list": {"status": exec_status, "payload": exec_payload},
        }
        if include_detail and detail_map:
            raw["fabric_get_execution_get"] = detail_map
        out["payload"]["raw"] = raw

    return out

