# tools/fabric/health_timeline.py

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta


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


def _truncate_list(items: List[Any], max_items: int) -> Tuple[List[Any], bool]:
    if max_items <= 0:
        return [], bool(items)
    if len(items) <= max_items:
        return items, False
    return items[:max_items], True


def _parse_time(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts:
        return None
    # event histories use "2023-03-07T19:41:47Z"
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        # Ensure tz-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_window(inputs: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime], str]:
    """
    Returns (since_dt, until_dt, window_note).
    - If since/until provided -> use them (best effort parse)
    - Else use window_hours (default 168h)
    """
    since_raw = inputs.get("since")
    until_raw = inputs.get("until")
    window_hours = _coerce_int(inputs.get("window_hours", 168), 168)

    since_dt = _parse_time(since_raw) if since_raw else None
    until_dt = _parse_time(until_raw) if until_raw else None

    if since_dt is None and until_dt is None:
        until_dt = _now_utc()
        since_dt = until_dt - timedelta(hours=max(1, window_hours))
        return since_dt, until_dt, f"window_hours={max(1, window_hours)} (default window applied)"

    note = "since/until provided"
    return since_dt, until_dt, note


def _in_window(dt: Optional[datetime], since_dt: Optional[datetime], until_dt: Optional[datetime]) -> bool:
    if dt is None:
        return False
    if since_dt is not None and dt < since_dt:
        return False
    if until_dt is not None and dt > until_dt:
        return False
    return True


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
    # 1) Preferred: registry invoke-style APIs
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

        # 2) Try registry tool catalog to get endpoint info
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

    # 3) Last-resort hardcoded paths (kept tight to only what we need)
    if transport is not None:
        if tool_name == "fabric_get_fabrics_health":
            return _transport_get(transport, "/v1/fabric/fabrics-health", tool_inputs)
        if tool_name in ("fabric_get_fabric_health", "fabric_get_health"):
            return _transport_get(transport, "/v1/fabric/fabric-health", tool_inputs)
        if tool_name == "fabric_get_event_history_list":
            return _transport_get(transport, "/v1/fabric/eventhistories", tool_inputs)
        if tool_name == "fabric_get_execution_list":
            return _transport_get(transport, "/v1/fabric/executions", tool_inputs)
        if tool_name == "fabric_get_execution":
            return _transport_get(transport, "/v1/fabric/execution", tool_inputs)

    return {"status": 500, "payload": None, "error": f"Tool not registered / callable: {tool_name}"}


# ---------------------------
# Normalizers
# ---------------------------

def _normalize_global_fabric_row(row: Dict[str, Any]) -> Dict[str, Any]:
    fname = _pick_first(row, ["fabric-name", "fabric_name", "name", "fabric"])
    fhealth = _pick_first(row, ["fabric-health", "fabric_health", "health"])
    topo = _safe_get(row, "fabric-level-physical-topology-health", "health", default=None)

    out = {
        "fabric": fname,
        "fabric_health": fhealth,
        "topology_health": topo,
    }

    for k in ("fabric-id", "fabric-type", "fabric-stage", "fabric-status"):
        if k in row:
            out[k] = row.get(k)

    return out


def _extract_service_health(payload: Any) -> Optional[Dict[str, Any]]:
    if isinstance(payload, dict):
        if "Service" in payload or "MessageBus" in payload:
            return payload
        for k in ("health", "payload", "service_health", "status"):
            v = payload.get(k)
            if isinstance(v, dict) and ("Service" in v or "MessageBus" in v):
                return v
    return None


def _normalize_event_items(payload: Any) -> List[Dict[str, Any]]:
    items = _as_list(payload)
    out: List[Dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict):
            out.append(it)
    return out


def _normalize_execution_items(payload: Any) -> List[Dict[str, Any]]:
    items = _as_list(payload)
    out: List[Dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict):
            out.append(it)
    return out


def _event_matches_fabric(ev: Dict[str, Any], fabric_name: str) -> bool:
    mo = ev.get("message_object")
    if mo == fabric_name:
        return True
    # fallback heuristic: message contains "Fabric <name>"
    msg = ev.get("message")
    if isinstance(msg, str) and fabric_name:
        if f"Fabric {fabric_name}" in msg:
            return True
    return False


def _make_event_compact(ev: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "date": ev.get("date"),
        "event": ev.get("event"),
        "service": ev.get("service"),
        "message_type": ev.get("message_type"),
        "message_object": ev.get("message_object"),
        "message": ev.get("message"),
        "execution_uuid": ev.get("execution_uuid"),
    }


def _summarize_execution_bucket(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a compact "what happened" summary per execution_uuid.
    """
    stages: List[str] = []
    for ev in events:
        msg = ev.get("message")
        if not isinstance(msg, str):
            continue
        if "Validation succeeded" in msg and "validation" not in stages:
            stages.append("validation")
        if "Allocation succeeded" in msg and "allocation" not in stages:
            stages.append("allocation")
        if "Configuration on devices succeeded" in msg and "configuration" not in stages:
            stages.append("configuration")
        if "failed" in msg.lower() and "failure" not in stages:
            stages.append("failure")

    if not stages:
        stages = ["events"]

    return {"stages": stages}


def _exec_mentions_fabric(ex: Dict[str, Any], fabric_name: str) -> bool:
    cmd = ex.get("command")
    if not isinstance(cmd, str) or not fabric_name:
        return False
    # best-effort heuristics; your current commands often show "--name " without a value
    if f"--name {fabric_name}" in cmd:
        return True
    if f"Fabric {fabric_name}" in cmd:
        return True
    # very loose fallback: if name appears anywhere
    if fabric_name in cmd:
        return True
    return False


def _best_effort_match_execution(
    ex_items: List[Dict[str, Any]],
    fabric_name: str,
    bucket_start: Optional[datetime],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    If exact id match isn't possible, pick the closest execution in time that "mentions" the fabric.
    """
    if bucket_start is None:
        return None, None

    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for ex in ex_items:
        if not isinstance(ex, dict):
            continue
        if not _exec_mentions_fabric(ex, fabric_name):
            continue
        ex_start = _parse_time(ex.get("start_time"))
        if ex_start is None:
            continue
        delta = abs((ex_start - bucket_start).total_seconds())
        candidates.append((delta, ex))

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: x[0])
    best_delta, best = candidates[0]

    # Only accept if reasonably close (1 hour)
    if best_delta <= 3600:
        return best, f"time_proximity<=3600s (delta={int(best_delta)}s)"
    return None, None


# ---------------------------
# Main tool
# ---------------------------

def fabric_get_fabric_health_timeline(
    inputs: Dict[str, Any],
    *,
    registry=None,
    transport=None,
    http_client=None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Tier-2: Fabric health timeline (composite)

    Important behaviors (based on your environment):
      - eventhistories does NOT reliably filter by fabric name -> we filter locally
      - eventhistories may return {} for device_ip filters -> treat as empty list
      - executions endpoint may not support name filtering -> fetch system-wide list, filter locally when possible
      - execution_uuid from events does NOT necessarily match executions.id -> join is BEST-EFFORT
    """

    transport = transport or http_client

    name = inputs.get("name") or inputs.get("fabric_name")
    if not name:
        return {"status": 400, "payload": {"error": "inputs.name is required"}, "error": "missing name"}

    device_ip = inputs.get("device_ip")

    include_global = bool(inputs.get("include_global", True))
    include_service_health = bool(inputs.get("include_service_health", True))
    include_health_headline = bool(inputs.get("include_health_headline", True))
    include_executions = bool(inputs.get("include_executions", True))
    include_exec_details = bool(inputs.get("include_exec_details", False))
    include_raw = bool(inputs.get("include_raw", False))

    limit_events = _coerce_int(inputs.get("limit_events", 200), 200)
    max_events = _coerce_int(inputs.get("max_events", 200), 200)  # after filtering
    max_timeline_items = _coerce_int(inputs.get("max_timeline_items", 50), 50)

    exec_limit = _coerce_int(inputs.get("exec_limit", 100), 100)
    exec_status = inputs.get("exec_status", "all")
    max_exec_details = _coerce_int(inputs.get("max_exec_details", 10), 10)

    since_dt, until_dt, window_note = _coerce_window(inputs)

    filter_obj: Dict[str, Any] = {
        "name": name,
        "device_ip": device_ip if device_ip else None,
        "include_global": include_global,
        "include_service_health": include_service_health,
        "include_health_headline": include_health_headline,
        "include_executions": include_executions,
        "include_exec_details": include_exec_details,
        "since": since_dt.isoformat() if since_dt else None,
        "until": until_dt.isoformat() if until_dt else None,
        "window_note": window_note,
        "limit_events": limit_events,
        "max_events": max_events,
        "max_timeline_items": max_timeline_items,
        "exec_limit": exec_limit,
        "exec_status": exec_status,
        "max_exec_details": max_exec_details,
        "include_raw": include_raw,
    }

    out: Dict[str, Any] = {"filter": filter_obj}

    # ---------------------------
    # Global fabrics list (validate name)
    # ---------------------------
    fabrics_normed: List[Dict[str, Any]] = []
    match_row: Optional[Dict[str, Any]] = None

    if include_global:
        g_res = _call_tier1(
            "fabric_get_fabrics_health",
            {},
            registry=registry,
            transport=transport,
        )
        g_status = _coerce_int(g_res.get("status", 0), 0)
        g_payload = g_res.get("payload")

        if g_status == 200 and g_payload is not None:
            items = _as_list(g_payload)
            for it in items:
                if isinstance(it, dict):
                    row = _normalize_global_fabric_row(it)
                    fabrics_normed.append(row)
                    if row.get("fabric") == name:
                        match_row = row

            out["global_context"] = {
                "status": 200,
                "count": len(fabrics_normed),
                "fabrics": fabrics_normed,
            }
        else:
            out["global_context"] = {
                "status": g_status,
                "count": 0,
                "fabrics": [],
                "error": g_res.get("error") or "Failed to fetch fabrics health",
            }

    # If we have global list and name not found -> 404 (regression test style like tool #2)
    if include_global and fabrics_normed and match_row is None:
        out["error"] = f"Fabric '{name}' not found in fabrics health list"
        out["next_actions"] = [
            {
                "reason": "Use global mode of fabric_get_fabric_health_summary to see valid fabric names.",
                "tool": "fabric_get_fabric_health_summary",
                "inputs": {},
            }
        ]
        return {"status": 404, "payload": out, "error": "fabric not found"}

    # ---------------------------
    # Service health
    # ---------------------------
    if include_service_health:
        s_res = _call_tier1(
            "fabric_get_health",
            {},
            registry=registry,
            transport=transport,
        )
        s_status = _coerce_int(s_res.get("status", 0), 0)
        svc = _extract_service_health(s_res.get("payload"))
        if s_status == 200 and svc is not None:
            out["service_health"] = svc
        else:
            out["service_health"] = svc or {}
            out["service_health_status"] = s_status
            if s_res.get("error"):
                out["service_health_error"] = s_res.get("error")

    # ---------------------------
    # Current health headline (optional)
    # ---------------------------
    if include_health_headline:
        h_res = _call_tier1(
            "fabric_get_fabric_health",
            {"name": name},
            registry=registry,
            transport=transport,
        )
        h_status = _coerce_int(h_res.get("status", 0), 0)
        h_payload = h_res.get("payload")

        if h_status == 200 and isinstance(h_payload, dict):
            out["headline"] = {
                "fabric_health": _pick_first(h_payload, ["fabric-health", "fabric_health"]),
                "topology_health": _safe_get(h_payload, "fabric-level-physical-topology-health", "health", default=None),
            }
        elif match_row is not None:
            out["headline"] = {
                "fabric_health": match_row.get("fabric_health"),
                "topology_health": match_row.get("topology_health"),
            }
            out["headline_status"] = h_status
        else:
            out["headline"] = {"fabric_health": None, "topology_health": None}
            out["headline_status"] = h_status

        if include_raw:
            out["health_raw"] = h_payload

    # ---------------------------
    # Event histories (fetch globally, filter locally)
    # ---------------------------
    ev_inputs: Dict[str, Any] = {"limit": limit_events}
    if device_ip:
        ev_inputs["device_ip"] = device_ip

    ev_res = _call_tier1(
        "fabric_get_event_history_list",
        ev_inputs,
        registry=registry,
        transport=transport,
    )
    ev_status = _coerce_int(ev_res.get("status", 0), 0)
    ev_payload = ev_res.get("payload")

    ev_items = _normalize_event_items(ev_payload)

    filtered_events: List[Dict[str, Any]] = []
    for ev in ev_items:
        if not _event_matches_fabric(ev, name):
            continue
        ev_dt = _parse_time(ev.get("date"))
        if since_dt or until_dt:
            if not _in_window(ev_dt, since_dt, until_dt):
                continue
        filtered_events.append(ev)

    # sort ascending by date
    filtered_events.sort(key=lambda e: _parse_time(e.get("date")) or datetime.min.replace(tzinfo=timezone.utc))

    # truncate and compact
    filtered_compact = [_make_event_compact(e) for e in filtered_events]
    filtered_compact, ev_trunc = _truncate_list(filtered_compact, max_events)

    out["events"] = {
        "status": ev_status,
        "count": len(filtered_compact),
        "items": filtered_compact,
        "truncated": ev_trunc,
        "note": "Event histories are fetched globally and filtered locally by message_object==fabric name (and optional time window).",
    }

    if include_raw:
        out["events_raw"] = ev_payload

    # ---------------------------
    # Executions list (optional)
    # ---------------------------
    exec_items_all: List[Dict[str, Any]] = []
    exec_items_window: List[Dict[str, Any]] = []
    exec_map_by_id: Dict[str, Dict[str, Any]] = {}

    if include_executions:
        # IMPORTANT: Do not pass name here (you proved it can 404 in your environment)
        ex_res = _call_tier1(
            "fabric_get_execution_list",
            {"limit": exec_limit, "status": exec_status},
            registry=registry,
            transport=transport,
        )
        ex_status = _coerce_int(ex_res.get("status", 0), 0)
        ex_payload = ex_res.get("payload")

        exec_items_all = _normalize_execution_items(ex_payload)

        # window filter
        for ex in exec_items_all:
            ex_start_dt = _parse_time(ex.get("start_time"))
            if since_dt or until_dt:
                if not _in_window(ex_start_dt, since_dt, until_dt):
                    continue
            exec_items_window.append(ex)

        # map by id
        for it in exec_items_window:
            ex_id = it.get("id")
            if isinstance(ex_id, str) and ex_id:
                exec_map_by_id[ex_id] = it

        out["executions"] = {
            "status": ex_status,
            "count": len(exec_items_window),
            "items": exec_items_window if include_raw else [],
            "note": "Executions are fetched system-wide and filtered locally by time window; fabric correlation is best-effort via id match or heuristics.",
        }

        if include_raw:
            out["executions_raw"] = ex_payload

    # ---------------------------
    # Timeline grouped by execution_uuid
    # ---------------------------
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for ev in filtered_events:
        ex_uuid = ev.get("execution_uuid")
        if not isinstance(ex_uuid, str) or not ex_uuid:
            continue
        buckets.setdefault(ex_uuid, []).append(ev)

    timeline_items: List[Dict[str, Any]] = []
    for ex_uuid, evs in buckets.items():
        evs_sorted = sorted(evs, key=lambda e: _parse_time(e.get("date")) or datetime.min.replace(tzinfo=timezone.utc))
        bucket_start = _parse_time(evs_sorted[0].get("date")) if evs_sorted else None
        bucket_end = _parse_time(evs_sorted[-1].get("date")) if evs_sorted else None

        summary = _summarize_execution_bucket(evs_sorted)

        item: Dict[str, Any] = {
            "execution_uuid": ex_uuid,
            "start_time": evs_sorted[0].get("date") if evs_sorted else None,
            "end_time": evs_sorted[-1].get("date") if evs_sorted else None,
            "event_count": len(evs_sorted),
            "summary": summary,
            "events": [_make_event_compact(e) for e in evs_sorted],
            "execution": None,
            "execution_match": None,
        }

        # 1) Exact match attempt: execution_uuid == executions.id
        ex_rec = exec_map_by_id.get(ex_uuid)
        if isinstance(ex_rec, dict):
            item["execution"] = {
                "id": ex_rec.get("id"),
                "command": ex_rec.get("command"),
                "status": ex_rec.get("status"),
                "start_time": ex_rec.get("start_time"),
                "end_time": ex_rec.get("end_time"),
                "user_name": ex_rec.get("user_name"),
            }
            item["execution_match"] = "exact_id_match"
        else:
            # 2) Best-effort match: time proximity + command mentions fabric
            best, why = _best_effort_match_execution(exec_items_window, name, bucket_start)
            if isinstance(best, dict):
                item["execution"] = {
                    "id": best.get("id"),
                    "command": best.get("command"),
                    "status": best.get("status"),
                    "start_time": best.get("start_time"),
                    "end_time": best.get("end_time"),
                    "user_name": best.get("user_name"),
                }
                item["execution_match"] = why

        timeline_items.append(item)

    # newest-first by bucket start time
    timeline_items.sort(key=lambda x: _parse_time(x.get("start_time")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    timeline_items, tl_trunc = _truncate_list(timeline_items, max_timeline_items)

    out["timeline"] = {
        "count": len(timeline_items),
        "items": timeline_items,
        "truncated": tl_trunc,
    }

    # ---------------------------
    # Execution detail enrichment (optional)
    # ---------------------------
    if include_exec_details and transport is not None and timeline_items:
        details: List[Dict[str, Any]] = []
        to_fetch = [t.get("execution_uuid") for t in timeline_items if isinstance(t.get("execution_uuid"), str)]
        to_fetch, _ = _truncate_list(to_fetch, max_exec_details)

        for ex_id in to_fetch:
            d_res = _call_tier1(
                "fabric_get_execution",
                {"id": ex_id},
                registry=registry,
                transport=transport,
            )
            d_status = _coerce_int(d_res.get("status", 0), 0)
            d_payload = d_res.get("payload")

            details.append(
                {
                    "id": ex_id,
                    "status": d_status,
                    "payload": d_payload,
                }
            )

        out["execution_details"] = {
            "count": len(details),
            "items": details,
            "note": "Execution detail is best-effort; some deployments may not support /v1/fabric/execution.",
        }

    # ---------------------------
    # Next actions
    # ---------------------------
    next_actions: List[Dict[str, Any]] = []

    if out.get("headline", {}).get("fabric_health") == "Red":
        next_actions.append(
            {
                "reason": "Fabric health is Red. Use health summary + include_errors for quicker hints.",
                "tool": "fabric_get_fabric_health_summary",
                "inputs": {"name": name, "include_errors": True},
            }
        )

    next_actions.extend(
        [
            {
                "reason": "See current fabric events (often explains why health changed).",
                "tool": "fabric_get_event_history_list",
                "inputs": {"name": name},
            },
            {
                "reason": "If unhealthy devices exist, fetch topology to correlate where issues are located.",
                "tool": "fabric_get_physical_topology",
                "inputs": {"name": name},
            },
            {
                "reason": "If config state is Red/refreshed, inspect config show output.",
                "tool": "fabric_get_config_show",
                "inputs": {"name": name},
            },
        ]
    )

    out["next_actions"] = next_actions

    return {"status": 200, "payload": out}

