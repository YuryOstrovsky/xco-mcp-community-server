# tools/notification/last_failed_delivery_or_errors.py

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
import re


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


def _coerce_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _norm(v: Any) -> str:
    return str(v).strip() if v is not None else ""


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


def _exec_time(ex: Dict[str, Any]) -> Optional[datetime]:
    dt = _parse_time(ex.get("start_time"))
    return dt if dt is not None else _parse_time(ex.get("end_time"))


def _normalize_status(raw: Any) -> str:
    """
    Normalize backend status strings into a stable token.
    Examples:
      "Completed(2.87ms)" -> "completed"
      "FAILED" -> "failed"
      "Succeeded (ok)" -> "succeeded"
    """
    s = _norm(raw).lower()
    if not s:
        return "unknown"
    # strip timing suffix like "(2.873133ms)" or "(ok)"
    s = re.sub(r"\s*\(.*\)\s*$", "", s).strip()
    # collapse spaces/underscores
    s = re.sub(r"[\s_]+", " ", s).strip()
    return s


def _status_str(ex: Dict[str, Any]) -> str:
    return _normalize_status(ex.get("status"))


def _is_success_status(status: str) -> bool:
    """
    Success-ish states across customer deployments.
    """
    s = _normalize_status(status)
    if s in ("succeeded", "success", "successful", "completed", "complete", "ok", "done", "passed", "finished"):
        return True
    # accept common prefixes
    for p in ("succeeded", "success", "completed", "complete", "finished", "passed"):
        if s.startswith(p):
            return True
    return False


def _is_running_or_pending(status: str) -> bool:
    s = _normalize_status(status)
    return s in ("running", "in progress", "in-progress", "pending", "queued", "started") or s.startswith("running")


def _looks_failed(status: str) -> bool:
    """
    Failure-ish detector used only for fallback mode (status=all).
    We DO NOT want to classify 'running' or 'pending' as failures.
    """
    s = _normalize_status(status)
    if _is_success_status(s):
        return False
    if _is_running_or_pending(s):
        return False
    # strong failure terms
    if any(tok in s for tok in ("fail", "error", "exception", "timeout", "denied", "unauthorized", "forbidden", "aborted")):
        return True
    # if it's neither success nor running/pending nor unknown, treat as suspicious/non-success
    return s not in ("unknown", "")


def _matches_query(ex: Dict[str, Any], q: str) -> bool:
    if not q:
        return True
    q = q.lower().strip()
    if not q:
        return True
    hay = " ".join(
        [
            _norm(ex.get("command")),
            _norm(ex.get("parameters")),
            _norm(ex.get("status")),
            _norm(ex.get("user_name")),
        ]
    ).lower()
    return q in hay


def _pick_most_recent(execs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    best = None
    best_ts = None
    for ex in execs:
        dt = _exec_time(ex)
        if dt is None:
            continue
        if best is None or dt > best_ts:
            best = ex
            best_ts = dt
    return best


def _trim_execution(ex: Dict[str, Any]) -> Dict[str, Any]:
    dt = _exec_time(ex)
    params = ex.get("parameters")
    # normalize the common "null" string into JSON null
    if isinstance(params, str) and params.strip().lower() == "null":
        params = None

    return {
        "id": ex.get("id"),
        "command": ex.get("command"),
        "parameters": params,
        "status": ex.get("status"),
        "status_norm": _status_str(ex),
        "user_name": ex.get("user_name"),
        "start_time": ex.get("start_time"),
        "end_time": ex.get("end_time"),
        "timestamp": (dt.isoformat() if isinstance(dt, datetime) else None),
    }


# ---------------------------
# Transport adapter (GET)
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
    3) Else fallback to direct known endpoint path for notification executions.
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
        if tool_name == "notification_get_executions":
            return _transport_get(transport, "/v1/notification/executions", tool_inputs)

    return {"status": 500, "payload": None, "error": f"Tool not registered / callable: {tool_name}"}


# ---------------------------
# Tier-2 tool
# ---------------------------

def notification_get_last_failed_delivery_or_errors(
    inputs: Dict[str, Any],
    *,
    registry=None,
    transport=None,
    http_client=None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Tier-2: Recent notification pipeline failures.

    Composite:
      - Tier-1 notification_get_executions (status=failed by default)
      - local time window filtering + optional keyword filtering
      - optional fallback to status=all and detect failure-ish statuses locally

    Returns:
      - last_failed (single most recent)
      - recent_failed (up to max_items)
      - summary + next actions
    """

    window_hours = _coerce_int(inputs.get("window_hours", 168), 168)
    window_hours = max(1, min(window_hours, 2160))  # up to 90 days

    limit = _coerce_int(inputs.get("limit", 200), 200)
    limit = max(1, min(limit, 5000))

    status = _norm(inputs.get("status", "failed")).lower() or "failed"
    if status not in ("failed", "succeeded", "all"):
        return {
            "status": 400,
            "error": "invalid status",
            "payload": {
                "error": "Invalid 'status' (must be: failed | succeeded | all)",
                "status": status,
                "expected": ["failed", "succeeded", "all"],
            },
        }

    query = _norm(inputs.get("query", ""))

    max_items = _coerce_int(inputs.get("max_items", 10), 10)
    max_items = max(1, min(max_items, 200))

    include_raw = bool(inputs.get("include_raw", False))
    fallback_detect_non_success = bool(inputs.get("fallback_detect_non_success", True))

    input_echo = {
        "window_hours": window_hours,
        "limit": limit,
        "status": status,
        "query": (query if query else None),
        "max_items": max_items,
        "fallback_detect_non_success": fallback_detect_non_success,
        "include_raw": include_raw,
    }

    raw: Dict[str, Any] = {}
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)

    # 1) Primary Tier-1 fetch
    tier1_primary = _call_tier1(
        "notification_get_executions",
        {"limit": limit, "status": status},
        registry=registry,
        transport=transport,
    )
    if include_raw:
        raw["notification_get_executions"] = tier1_primary

    primary_status = int(tier1_primary.get("status") or 500)
    if primary_status != 200:
        return {
            "status": 502,
            "error": "tier1 notification_get_executions failed",
            "payload": {
                "input_echo": input_echo,
                "tier1_status": primary_status,
                "warnings": [
                    "Tier-1 notification_get_executions returned non-200; cannot determine notification pipeline failures."
                ],
                "next_actions": [
                    {"action": "retry", "hint": "Retry with a smaller limit (e.g., 50) or check auth/connectivity."},
                    {"action": "debug", "hint": "Invoke Tier-1 notification_get_executions directly to inspect status/payload."},
                ],
                **({"tier1_raw": raw} if include_raw else {}),
            },
        }

    primary_items = [x for x in _as_list(tier1_primary.get("payload")) if isinstance(x, dict)]

    def _filter_window_and_query(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for ex in items:
            dt = _exec_time(ex)
            if dt is None:
                continue
            if dt < cutoff:
                continue
            if not _matches_query(ex, query):
                continue
            out.append(ex)
        return out

    in_window = _filter_window_and_query(primary_items)

    # 2) Fallback: if status=failed returned nothing meaningful, try status=all and detect failures locally
    used_fallback = False
    effective_items = primary_items

    if not in_window and status == "failed" and fallback_detect_non_success:
        tier1_all = _call_tier1(
            "notification_get_executions",
            {"limit": limit, "status": "all"},
            registry=registry,
            transport=transport,
        )
        if include_raw:
            raw["notification_get_executions:fallback_all"] = tier1_all

        if int(tier1_all.get("status") or 500) == 200:
            all_items = [x for x in _as_list(tier1_all.get("payload")) if isinstance(x, dict)]
            all_items = _filter_window_and_query(all_items)
            # Only keep true failure-ish statuses (avoid Completed(...), Running, etc.)
            all_items = [ex for ex in all_items if _looks_failed(ex.get("status"))]

            in_window = all_items
            used_fallback = True
            effective_items = [x for x in _as_list(tier1_all.get("payload")) if isinstance(x, dict)]

    # Sort by time desc
    in_window.sort(key=lambda ex: (_exec_time(ex) or datetime.fromtimestamp(0, tz=timezone.utc)), reverse=True)

    last_failed = _pick_most_recent(in_window) if in_window else None

    summary = {
        "executions_total_fetched_primary": len(primary_items),
        "executions_total_fetched_effective": len(effective_items),
        "executions_in_window": len(in_window),
        "returned_recent_failed": min(len(in_window), max_items),
        "last_failed_found": (last_failed is not None),
        "tier1_mode_used": ("fallback_failure_detect" if used_fallback else f"status={status}"),
    }

    warnings: List[str] = []
    next_actions: List[Dict[str, str]] = []

    if last_failed is None:
        warnings.append("No failed notification executions found in the requested window.")
        next_actions.append({"action": "retry", "hint": "Increase window_hours (e.g., 720 for 30 days)."})
        next_actions.append({"action": "retry", "hint": "Increase limit (e.g., 500) to look further back."})
        next_actions.append({"action": "retry", "hint": "Try query='error' or query='timeout' to scan for pipeline issues."})

    payload = {
        "input_echo": input_echo,
        "summary": summary,
        "last_failed": (_trim_execution(last_failed) if isinstance(last_failed, dict) else None),
        "recent_failed": [_trim_execution(x) for x in in_window[:max_items]],
        "warnings": warnings,
        "next_actions": next_actions,
        **({"tier1_raw": raw} if include_raw else {}),
    }

    return {"status": 200, "payload": payload}

