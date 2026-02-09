# tools/fabric/execution_last_failed.py

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone


# ---------------------------
# Small safe helpers
# ---------------------------

def _safe_get(d: Any, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _as_list(payload: Any) -> List[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return items
        nested = payload.get("payload")
        if isinstance(nested, dict):
            items2 = nested.get("items")
            if isinstance(items2, list):
                return items2
    return []


def _pick_first(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _coerce_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _parse_time(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _snippet(s: Any, n: int = 160) -> Optional[str]:
    if not isinstance(s, str):
        return None
    s2 = " ".join(s.split())
    return s2 if len(s2) <= n else (s2[: n - 3] + "...")


# ---------------------------
# Transport adapter
# ---------------------------

def _transport_get(transport: Any, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort adapter for whatever transport object the runtime passes.
    Expected return: {"status": int, "payload": Any, ...}
    """
    for meth_name in ("request", "send", "call"):
        fn = getattr(transport, meth_name, None)
        if not callable(fn):
            continue
        try:
            res = fn(method="GET", path=path, params=params)
            if isinstance(res, dict) and "status" in res:
                return res
        except TypeError:
            pass
        except Exception as e:
            return {"status": 500, "payload": None, "error": f"transport.{meth_name} failed: {e}"}

    fn = getattr(transport, "get", None)
    if callable(fn):
        try:
            res = fn(path, params=params)
            if isinstance(res, dict) and "status" in res:
                return res
        except Exception as e:
            return {"status": 500, "payload": None, "error": f"transport.get failed: {e}"}

    return {"status": 500, "payload": None, "error": "No compatible GET method found on transport"}


# ---------------------------
# Tier-1 calling helper
# ---------------------------

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
    3) Else (last resort) call known fabric endpoints directly via transport.
    """
    if registry is not None:
        for meth in ("invoke_tool", "invoke", "call", "run", "invoke_tier1"):
            fn = getattr(registry, meth, None)
            if callable(fn):
                try:
                    res = fn(tool_name, tool_inputs)
                    if isinstance(res, dict) and "status" in res:
                        return res
                except TypeError:
                    pass
                except Exception as e:
                    return {"status": 500, "payload": None, "error": f"registry.{meth} failed: {e}"}

        tool_def = None
        get_tool = getattr(registry, "get_tool", None)
        if callable(get_tool):
            try:
                tool_def = get_tool(tool_name)
            except Exception:
                tool_def = None

        if tool_def is None:
            tools_dict = getattr(registry, "tools", None)
            if isinstance(tools_dict, dict):
                tool_def = tools_dict.get(tool_name)

        if tool_def and transport is not None and isinstance(tool_def, dict):
            endpoint = tool_def.get("endpoint", {}) or {}
            path = endpoint.get("path")
            method = (tool_def.get("method") or "GET").upper()
            if method == "GET" and isinstance(path, str) and path.startswith("/"):
                return _transport_get(transport, path, tool_inputs)

    if transport is not None:
        if tool_name == "fabric_get_fabrics":
            return _transport_get(transport, "/v1/fabric/fabrics", tool_inputs)
        if tool_name == "fabric_get_execution_list":
            return _transport_get(transport, "/v1/fabric/executions", tool_inputs)
        if tool_name in ("fabric_get_execution_get", "fabric_get_execution"):
            return _transport_get(transport, "/v1/fabric/execution", tool_inputs)

    return {"status": 500, "payload": None, "error": f"Tool not registered / callable: {tool_name}"}


# ---------------------------
# Execution matching logic
# ---------------------------

def _exec_status(ex: Dict[str, Any]) -> Optional[str]:
    st = _pick_first(ex, ["status", "result", "state", "execution_status"])
    return st if isinstance(st, str) else None


def _exec_id(ex: Dict[str, Any]) -> Optional[str]:
    v = _pick_first(ex, ["id", "execution_id", "executionId", "execution_uuid", "uuid"])
    return str(v) if v is not None else None


def _exec_time(ex: Dict[str, Any]) -> Optional[datetime]:
    dt = _parse_time(ex.get("start_time"))
    return dt if dt is not None else _parse_time(ex.get("end_time"))


def _find_fabric_id_in_execution(ex: Dict[str, Any]) -> Optional[int]:
    """
    Best-effort pull of fabric id from execution item if present.
    We try common variants and nested dicts.
    """
    candidates = [
        "fabric-id", "fabric_id", "fabricId",
        "entity-id", "entity_id", "entityId",
        "target-id", "target_id", "targetId",
    ]
    for k in candidates:
        v = ex.get(k)
        if v is None:
            continue
        try:
            return int(v)
        except Exception:
            pass

    # sometimes nested under "context"/"params"/"inputs"
    for nest_key in ("context", "params", "inputs", "payload"):
        nest = ex.get(nest_key)
        if isinstance(nest, dict):
            for k in candidates + ["fabric"]:
                v = nest.get(k)
                if v is None:
                    continue
                try:
                    return int(v)
                except Exception:
                    pass

    return None


def _exec_mentions_fabric(ex: Dict[str, Any], fabric_name: str, fabric_id: Optional[int]) -> Tuple[bool, Optional[str]]:
    """
    Returns (matched, reason).
    Tries direct fields, fabric id fields, and command heuristics.
    """
    if not fabric_name:
        return False, None

    direct_name = _pick_first(ex, ["fabric-name", "fabric_name", "fabric", "name"])
    if isinstance(direct_name, str) and direct_name == fabric_name:
        return True, "direct_name_field"

    ex_fid = _find_fabric_id_in_execution(ex)
    if fabric_id is not None and ex_fid is not None and ex_fid == fabric_id:
        return True, "direct_fabric_id_field"

    cmd = ex.get("command")
    if isinstance(cmd, str) and cmd:
        if f"--name {fabric_name}" in cmd:
            return True, "command(--name)"
        if f"--fabric-name {fabric_name}" in cmd:
            return True, "command(--fabric-name)"
        if f"fabric-name {fabric_name}" in cmd:
            return True, "command(fabric-name)"
        if f"Fabric {fabric_name}" in cmd:
            return True, "command(Fabric <name>)"
        if fabric_id is not None and (f"--fabric-id {fabric_id}" in cmd or f"fabric-id {fabric_id}" in cmd):
            return True, "command(fabric-id)"
        if fabric_name in cmd:
            return True, "command(name_anywhere)"

    return False, None


def _sort_most_recent(ex_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def keyfn(ex: Dict[str, Any]):
        dt = _exec_time(ex)
        ts = dt.timestamp() if isinstance(dt, datetime) else -1.0
        exid = _exec_id(ex)
        try:
            exidn = int(exid) if exid is not None else 0
        except Exception:
            exidn = 0
        return (ts, exidn)

    return sorted(ex_items, key=keyfn, reverse=True)


def _compact_execution(ex: Dict[str, Any], matched_by: Optional[str]) -> Dict[str, Any]:
    return {
        "id": _exec_id(ex),
        "status": _exec_status(ex),
        "start_time": ex.get("start_time"),
        "end_time": ex.get("end_time"),
        "command": _snippet(ex.get("command")),
        "matched_by": matched_by,
    }


def _extract_failure_hint(detail_payload: Any) -> Optional[str]:
    if not isinstance(detail_payload, dict):
        return None

    for k in ("error", "message", "failure_reason", "reason", "detail", "details"):
        v = detail_payload.get(k)
        if isinstance(v, str) and v.strip():
            return _snippet(v, 220)

    nested = detail_payload.get("payload")
    if isinstance(nested, dict):
        for k in ("error", "message", "failure_reason", "reason", "detail", "details"):
            v = nested.get(k)
            if isinstance(v, str) and v.strip():
                return _snippet(v, 220)

    return None


# ---------------------------
# Main tool
# ---------------------------

def fabric_get_fabric_execution_last_failed(
    inputs: Dict[str, Any],
    *,
    registry=None,
    transport=None,
    http_client=None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Tier-2: Most recent FAILED execution correlated to a fabric (best-effort).

    Honest behavior:
      - If there are failed executions but none can be correlated to this fabric, verdict=WARN (inconclusive),
        NOT PASS.
    """

    name = inputs.get("name") or inputs.get("fabric_name") or inputs.get("fabric-name")
    if not isinstance(name, str) or not name.strip():
        return {
            "status": 400,
            "error": "missing required input: name",
            "payload": {
                "error": "Missing required input: name",
                "expected_inputs": {"name": "Fabric name (string)"},
                "next_actions": [
                    {
                        "reason": "Discover valid fabric names.",
                        "tool": "fabric_get_fabric_overview",
                        "inputs": {"include_health": True, "include_errors": True},
                    }
                ],
            },
        }
    name = name.strip()

    limit = _coerce_int(inputs.get("limit", 50), 50)
    limit = max(1, min(limit, 500))
    include_detail = bool(inputs.get("include_detail", True))
    include_raw = bool(inputs.get("include_raw", False))

    filt = {
        "name": name,
        "limit": limit,
        "include_detail": include_detail,
        "include_raw": include_raw,
        "status_filter": "failed",
    }

    raw: Dict[str, Any] = {}

    # 1) Validate fabric exists
    fabrics_res = _call_tier1("fabric_get_fabrics", {}, registry=registry, transport=transport)
    if include_raw:
        raw["fabric_get_fabrics"] = fabrics_res

    fabrics_payload = fabrics_res.get("payload")
    fabrics_items = _as_list(fabrics_payload)

    row = None
    for r in fabrics_items:
        if isinstance(r, dict) and r.get("fabric-name") == name:
            row = r
            break

    if row is None:
        known_count = len([x for x in fabrics_items if isinstance(x, dict)])
        return {
            "status": 404,
            "error": "fabric not found",
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
                **({"raw": raw} if include_raw else {}),
            },
        }

    fabric_id = None
    try:
        fabric_id = int(row.get("fabric-id")) if row.get("fabric-id") is not None else None
    except Exception:
        fabric_id = None

    # 2) Pull failed executions list
    exec_list_res = _call_tier1(
        "fabric_get_execution_list",
        {"limit": limit, "status": "failed"},
        registry=registry,
        transport=transport,
    )
    if include_raw:
        raw["fabric_get_execution_list"] = exec_list_res

    exec_list_status = int(exec_list_res.get("status") or 500)
    exec_list_payload = exec_list_res.get("payload")
    exec_items_all = [x for x in _as_list(exec_list_payload) if isinstance(x, dict)]
    failed_total = len(exec_items_all)

    if exec_list_status != 200:
        payload = {
            "filter": filt,
            "summary": {
                "fabric": name,
                "verdict": "WARN",
                "last_failed_found": None,
                "note": "Could not retrieve executions list (non-200).",
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
                "execution_list": {"status": exec_list_status, "count": failed_total},
            },
            "recommendations": [
                "Execution list could not be retrieved. Verify fabric service health and permissions."
            ],
            "next_actions": [
                {
                    "reason": "Try viewing overall fabric timeline (may still show failures via events).",
                    "tool": "fabric_get_fabric_health_timeline",
                    "inputs": {"name": name, "include_exec_details": False},
                }
            ],
        }
        if include_raw:
            payload["raw"] = raw
        return {"status": 200, "payload": payload}

    # 3) Filter by fabric name/id (best-effort)
    matches: List[Tuple[Dict[str, Any], str]] = []
    for ex in exec_items_all:
        ok, why = _exec_mentions_fabric(ex, name, fabric_id)
        if ok and why:
            matches.append((ex, why))

    matched_by_map: Dict[str, str] = {}
    for ex, why in matches:
        exid = _exec_id(ex) or str(id(ex))
        matched_by_map[exid] = why

    matches_sorted = _sort_most_recent([m[0] for m in matches])
    last_failed = matches_sorted[0] if matches_sorted else None
    matched_by = matched_by_map.get(_exec_id(last_failed) or "", None) if isinstance(last_failed, dict) else None

    # If there are failed executions but we couldn't correlate any to this fabric -> WARN (inconclusive)
    if last_failed is None:
        verdict = "PASS" if failed_total == 0 else "WARN"
        note = (
            f"No failed executions exist in the returned window (limit={limit})."
            if failed_total == 0
            else f"Failed executions exist (count={failed_total}) but none could be correlated to fabric '{name}' "
                 f"(matching depends on execution metadata/command fields; treat as inconclusive)."
        )

        payload = {
            "filter": filt,
            "summary": {
                "fabric": name,
                "verdict": verdict,
                "last_failed_found": False,
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
                    "status": exec_list_status,
                    "failed_total_returned": failed_total,
                    "matched_failed_count": len(matches_sorted),
                },
            },
            "recommendations": (
                ["No failed executions were found."]
                if failed_total == 0
                else [
                    "Failed executions exist but could not be mapped to this fabric from available metadata. "
                    "Inspect execution list and timeline/events for clues."
                ]
            ),
            "next_actions": [
                {
                    "reason": "Inspect timeline/events for context.",
                    "tool": "fabric_get_fabric_health_timeline",
                    "inputs": {"name": name, "include_exec_details": False},
                },
                {
                    "reason": "Inspect the raw failed executions list (may show fabric info in command/message fields).",
                    "tool": "fabric_get_execution_list",
                    "inputs": {"limit": limit, "status": "failed"},
                },
            ],
        }
        if include_raw:
            # keep raw key consistency
            raw.setdefault("fabric_get_execution_get", None)
            payload["raw"] = raw
        return {"status": 200, "payload": payload}

    # 4) Optional detail
    detail_res = None
    detail_status = None
    detail_payload = None
    failure_hint = None

    ex_id = _exec_id(last_failed)
    if include_detail and ex_id:
        detail_res = _call_tier1(
            "fabric_get_execution_get",
            {"id": ex_id},
            registry=registry,
            transport=transport,
        )
        if not (isinstance(detail_res, dict) and "status" in detail_res):
            detail_res = _call_tier1(
                "fabric_get_execution",
                {"id": ex_id},
                registry=registry,
                transport=transport,
            )

        if isinstance(detail_res, dict):
            detail_status = int(detail_res.get("status") or 500)
            detail_payload = detail_res.get("payload")
            failure_hint = _extract_failure_hint(detail_payload)

    if include_raw:
        raw["fabric_get_execution_get"] = detail_res

    verdict = "FAIL"

    next_actions: List[Dict[str, Any]] = [
        {
            "reason": "See health timeline + nearby executions/events around the failure.",
            "tool": "fabric_get_fabric_health_timeline",
            "inputs": {"name": name, "include_exec_details": False},
        }
    ]

    if ex_id:
        next_actions.append(
            {
                "reason": "Fetch full execution detail for this failed execution.",
                "tool": "fabric_get_execution_get",
                "inputs": {"id": ex_id},
            }
        )

    ex_uuid = _pick_first(last_failed, ["execution_uuid", "uuid"])
    if isinstance(ex_uuid, str) and ex_uuid.strip():
        next_actions.append(
            {
                "reason": "Inspect event history for this execution UUID (often contains root cause messages).",
                "tool": "fabric_get_event_history_list",
                "inputs": {"execution_uuid": ex_uuid},
            }
        )

    payload: Dict[str, Any] = {
        "filter": filt,
        "summary": {
            "fabric": name,
            "verdict": verdict,
            "fabric_health": row.get("fabric-health"),
            "last_failed_found": True,
            "last_failed": _compact_execution(last_failed, matched_by),
            "failure_hint": failure_hint,
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
                "status": exec_list_status,
                "failed_total_returned": failed_total,
                "matched_failed_count": len(matches_sorted),
            },
            "execution_detail": (
                {
                    "status": detail_status,
                    "note": None if detail_status == 200 else "Execution detail lookup did not return 200.",
                }
                if include_detail
                else None
            ),
        },
        "recommendations": [
            "A recent failed execution was detected for this fabric. Review timeline/events and execution detail for root cause."
        ],
        "next_actions": next_actions,
    }

    if include_raw:
        payload["raw"] = raw

    return {"status": 200, "payload": payload}

