# tools/notification/recent_events_filtered.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


SEV_RANK = {
    "unknown": 0,
    "info": 1,
    "minor": 1,
    "warning": 2,
    "warn": 2,
    "major": 3,
    "critical": 4,
    "crit": 4,
}

NORM_SEV_ALIASES = {
    "information": "info",
    "informational": "info",
    "warn": "warning",
    "sev1": "critical",
    "sev2": "major",
    "sev3": "warning",
    "sev4": "info",
}

STATUS_ALIASES = {
    "success": "succeeded",
    "succeed": "succeeded",
    "succeeded": "succeeded",
    "ok": "succeeded",
    "passed": "succeeded",
    "fail": "failed",
    "failed": "failed",
    "error": "failed",
    "errors": "failed",
    "running": "running",
    "in_progress": "running",
    "in progress": "running",
    "pending": "pending",
}


def _as_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def _as_int(v: Any, default: int) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


def _norm_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _norm_sev(v: Any) -> str:
    if v is None:
        return "unknown"
    s = str(v).strip().lower()
    s = NORM_SEV_ALIASES.get(s, s)
    if s in SEV_RANK:
        return s
    for k in ("critical", "major", "warning", "info"):
        if k in s:
            return k
    return "unknown"


def _norm_status(v: Any) -> str:
    if v is None:
        return "unknown"
    s = str(v).strip().lower()
    return STATUS_ALIASES.get(s, s)


def _sev_ok(sev: str, min_sev: Optional[str]) -> bool:
    if not min_sev:
        return True
    a = SEV_RANK.get(_norm_sev(sev), 0)
    b = SEV_RANK.get(_norm_sev(min_sev), 0)
    return a >= b


def _walk(obj: Any):
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _extract_records(payload: Any) -> List[dict]:
    for node in _walk(payload):
        if isinstance(node, list) and any(isinstance(x, dict) for x in node):
            return [x for x in node if isinstance(x, dict)]
    return []


def _score_event_list(lst: List[dict]) -> int:
    if not lst:
        return 0
    keys = set()
    for r in lst[:10]:
        keys |= set(r.keys())
    wanted = {
        "severity", "Severity", "level", "Level",
        "type", "Type", "eventType", "event_type",
        "resource", "Resource",
        "message", "Message", "detail", "Detail", "description", "Description",
        "timestamp", "Timestamp", "time", "TimeCreated", "created", "createdAt",
    }
    score = 0
    for k in wanted:
        if k in keys:
            score += 2
    if any(k in keys for k in ("timestamp", "Timestamp", "time", "created", "createdAt", "TimeCreated")):
        score += 3
    return score


def _find_event_records(payload: Any) -> List[dict]:
    best: Tuple[int, List[dict]] = (0, [])
    for node in _walk(payload):
        if isinstance(node, list) and node and all(isinstance(x, dict) for x in node):
            sc = _score_event_list(node)
            if sc > best[0]:
                best = (sc, node)
    return best[1] if best[0] > 0 else []


def _parse_ts_any(v: Any) -> int:
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        n = int(v)
        return n if n > 10_000_000_000 else n * 1000
    s = str(v).strip()
    if not s:
        return 0
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except Exception:
            pass
    return 0


def _pick(d: dict, *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _best_message_from_detail(detail_payload: Any) -> Optional[str]:
    for node in _walk(detail_payload):
        if isinstance(node, dict):
            for k in (
                "message", "Message",
                "detail", "Detail",
                "description", "Description",
                "error", "Error",
                "errorMessage", "error_message",
                "reason", "Reason",
            ):
                v = node.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return None


def _best_resource_from_detail(detail_payload: Any) -> Optional[str]:
    """
    Extract a meaningful "resource" for UI filtering.
    Preference order:
      1) Any explicit /App/... string
      2) Any URL/path that contains /App/...
      3) Any obvious endpoint/path/url string
    """
    # 1) explicit resource fields
    for node in _walk(detail_payload):
        if isinstance(node, dict):
            for k in ("resource", "Resource", "scope", "Scope", "target", "Target"):
                v = node.get(k)
                if isinstance(v, str) and v.strip():
                    if "/App/" in v:
                        return v.strip()

    # 2) endpoint/path/url keys
    for node in _walk(detail_payload):
        if isinstance(node, dict):
            for k in ("path", "Path", "url", "URL", "endpoint", "Endpoint", "requestPath", "request_path"):
                v = node.get(k)
                if isinstance(v, str) and v.strip():
                    vv = v.strip()
                    if "/App/" in vv:
                        return vv
                    # still useful even without /App/
                    if vv.startswith("/") or vv.startswith("http"):
                        return vv

    # 3) raw string scan for /App/
    for node in _walk(detail_payload):
        if isinstance(node, str) and "/App/" in node:
            return node.strip()

    return None


def _normalize_event(
    *,
    src: str,
    execution_id: Optional[str],
    execution_status: Optional[str],
    rec: dict,
) -> dict:
    ts = _pick(rec, "timestamp", "Timestamp", "time", "TimeCreated", "created", "createdAt")
    sev = _pick(rec, "severity", "Severity", "level", "Level")
    typ = _pick(rec, "type", "Type", "eventType", "event_type")
    res = _pick(rec, "resource", "Resource")
    msg = _pick(rec, "message", "Message", "detail", "Detail", "description", "Description")

    sev_norm = _norm_sev(sev)
    if sev_norm == "unknown" and execution_status:
        st = _norm_status(execution_status)
        if st == "failed":
            sev_norm = "critical"
        elif st == "succeeded":
            sev_norm = "info"
        else:
            sev_norm = "info"

    if not typ:
        typ = "execution_event"

    if not msg:
        msg = f"{src} execution {execution_id or '?'} status={execution_status or 'unknown'}"

    return {
        "timestamp": ts,
        "timestamp_ms": _parse_ts_any(ts),
        "severity": sev_norm,
        "type": str(typ),
        "resource": str(res) if res is not None else None,
        "message": str(msg),
        "source": {
            "service": src,
            "execution_id": execution_id,
            "execution_status": execution_status,
        },
        "is_synthetic": False,
    }


def _synthetic_from_execution(src: str, ex: dict, detail_payload: Any = None) -> dict:
    ex_id = _pick(ex, "id", "execution_uuid", "uuid", "executionId", "execution_id")
    st_raw = _pick(ex, "status", "Status", "execution_status", "state", "State")
    st = _norm_status(st_raw)
    ts = _pick(ex, "timestamp", "Timestamp", "time", "start_time", "startTime", "created", "createdAt")

    msg = _pick(ex, "message", "Message", "detail", "Detail", "description", "Description")
    if not msg and detail_payload is not None:
        msg = _best_message_from_detail(detail_payload)

    res = _best_resource_from_detail(detail_payload) if detail_payload is not None else None

    sev = "critical" if st == "failed" else "info"

    return {
        "timestamp": ts,
        "timestamp_ms": _parse_ts_any(ts),
        "severity": sev,
        "type": "execution",
        "resource": res,
        "message": str(msg) if msg else f"{src} execution {ex_id or '?'} status={st or 'unknown'}",
        "source": {
            "service": src,
            "execution_id": ex_id,
            "execution_status": st,
        },
        "is_synthetic": True,
    }


# Source -> (list_tool, detail_tool)
SOURCE_MAP = {
    "system": ("system_get_executions", "system_get_execution"),
    "fabric": ("fabric_get_execution_list", "fabric_get_execution_get"),
    "tenant": ("tenant_get_execution_list", "tenant_get_execution_get"),
    "inventory": ("inventory_get_execution_list", "inventory_get_execution_get"),
    "snmp": ("snmp_get_executions", "snmp_get_execution"),
    "auth": ("auth_get_executions", "auth_get_execution"),
    "rbac": ("rbac_get_executions", "rbac_get_execution_detail"),
}


def notification_get_recent_events_filtered(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2 composite: notification_get_recent_events_filtered

    Fixes added:
      - treat list-tool 404 as "not supported in this environment" (warning, not error)
      - keep client-side status filtering
      - better synthetic resource extraction (path/url/endpoint support)
    """

    inputs = inputs or {}

    sources_in = inputs.get("sources")
    if not isinstance(sources_in, list) or not sources_in:
        sources = ["system", "fabric", "tenant", "inventory", "snmp", "auth", "rbac"]
    else:
        sources = [str(x).strip().lower() for x in sources_in if str(x).strip()]

    status_req = (_norm_str(inputs.get("status")) or "all").lower()
    status_req = _norm_status(status_req) if status_req != "all" else "all"

    last_n = max(1, min(_as_int(inputs.get("last_n"), 50), 500))
    limit_per_source = max(1, min(_as_int(inputs.get("limit_per_source"), 10), 100))

    severity_min = _norm_str(inputs.get("severity_min"))
    event_type = _norm_str(inputs.get("event_type"))
    resource_q = _norm_str(inputs.get("resource"))
    query = _norm_str(inputs.get("query"))

    include_raw = _as_bool(inputs.get("include_raw"), False)

    tier1_raw: Dict[str, Any] = {}
    warnings: List[str] = []
    errors: List[dict] = []

    def call_tier1(tool_name: str, params: Optional[dict] = None) -> dict:
        tool = registry.get(tool_name)
        if not tool:
            return {"status": -1, "payload": None, "error": f"Tier-1 tool not found in registry: {tool_name}"}

        endpoint = tool.get("endpoint") or {}
        path = endpoint.get("path")
        method = tool.get("method")

        if not path or not method:
            return {"status": -1, "payload": None, "error": f"Tier-1 tool missing endpoint/method: {tool_name}"}

        try:
            return transport.request(
                method=method,
                port=endpoint.get("port"),
                path=path,
                params=params or {},
                context=context or {},
            )
        except Exception as e:
            return {"status": 0, "payload": None, "error": str(e)}

    all_events: List[dict] = []
    per_source: Dict[str, dict] = {}

    for src in sources:
        if src not in SOURCE_MAP:
            warnings.append(f"Unknown source '{src}' ignored. Valid: {sorted(SOURCE_MAP.keys())}")
            continue

        list_tool, detail_tool = SOURCE_MAP[src]

        if registry.get(list_tool) is None or registry.get(detail_tool) is None:
            warnings.append(f"Source '{src}' skipped (Tier-1 tools not registered): {list_tool}, {detail_tool}")
            per_source[src] = {"executions_fetched": 0, "events_extracted": 0, "events_after_filters": 0, "skipped": True}
            continue

        list_params = {"limit": limit_per_source}
        if status_req != "all":
            list_params["status"] = status_req

        lr = call_tier1(list_tool, list_params)
        if include_raw:
            tier1_raw[list_tool] = lr

        if lr.get("status") == 404:
            warnings.append(f"Source '{src}' not supported in this lab (Tier-1 list returned 404): {list_tool}")
            per_source[src] = {"executions_fetched": 0, "events_extracted": 0, "events_after_filters": 0, "unsupported": True}
            continue

        if lr.get("status") != 200:
            warnings.append(f"Source '{src}' list failed: {list_tool} status={lr.get('status')}")
            errors.append({"source": src, "tool": list_tool, "status": lr.get("status"), "error": lr.get("error")})
            per_source[src] = {"executions_fetched": 0, "events_extracted": 0, "events_after_filters": 0}
            continue

        execs = _extract_records(lr.get("payload"))
        if not execs:
            if isinstance(lr.get("payload"), list) and all(isinstance(x, dict) for x in lr.get("payload")):
                execs = lr.get("payload")

        if status_req != "all":
            kept = []
            for ex in execs:
                st = _norm_status(_pick(ex, "status", "Status", "execution_status", "state", "State"))
                if st == status_req:
                    kept.append(ex)
            execs = kept

        events_src: List[dict] = []

        for ex in execs:
            if not isinstance(ex, dict):
                continue

            ex_id = _pick(ex, "id", "execution_uuid", "uuid", "executionId", "execution_id")
            ex_status = _norm_status(_pick(ex, "status", "Status", "execution_status", "state", "State"))

            if not ex_id:
                events_src.append(_synthetic_from_execution(src, ex))
                continue

            dr = call_tier1(detail_tool, {"id": str(ex_id)})
            if include_raw:
                tier1_raw[f"{detail_tool}:{ex_id}"] = dr

            if dr.get("status") != 200:
                errors.append({"source": src, "tool": detail_tool, "id": ex_id, "status": dr.get("status"), "error": dr.get("error")})
                events_src.append(_synthetic_from_execution(src, ex))
                continue

            detail_payload = dr.get("payload")
            evrecs = _find_event_records(detail_payload)

            if not evrecs:
                events_src.append(_synthetic_from_execution(src, ex, detail_payload=detail_payload))
                continue

            for r in evrecs[:2000]:
                if not isinstance(r, dict):
                    continue
                events_src.append(_normalize_event(
                    src=src,
                    execution_id=str(ex_id),
                    execution_status=ex_status,
                    rec=r,
                ))

        filtered: List[dict] = []
        for e in events_src:
            if not _sev_ok(e.get("severity", "unknown"), severity_min):
                continue
            if event_type and event_type.lower() not in str(e.get("type") or "").lower():
                continue
            if resource_q and resource_q.lower() not in str(e.get("resource") or "").lower():
                continue
            if query:
                blob = (str(e.get("type") or "") + " " + str(e.get("resource") or "") + " " + str(e.get("message") or "")).lower()
                if query.lower() not in blob:
                    continue
            filtered.append(e)

        per_source[src] = {
            "executions_fetched": len(execs),
            "events_extracted": len(events_src),
            "events_after_filters": len(filtered),
        }
        all_events.extend(filtered)

    all_events.sort(key=lambda e: int(e.get("timestamp_ms") or 0), reverse=True)
    returned = all_events[:last_n]

    by_sev: Dict[str, int] = {}
    for e in returned:
        s = _norm_sev(e.get("severity"))
        by_sev[s] = by_sev.get(s, 0) + 1

    payload = {
        "input_echo": {
            "sources": sources,
            "status": status_req,
            "last_n": last_n,
            "limit_per_source": limit_per_source,
            "severity_min": severity_min,
            "event_type": event_type,
            "resource": resource_q,
            "query": query,
            "include_raw": include_raw,
        },
        "summary": {
            "sources_used": [s for s in sources if s in SOURCE_MAP],
            "events_returned": len(returned),
            "by_severity": by_sev,
            "per_source": per_source,
            "errors": len(errors),
        },
        "events": returned,
        "errors": errors,
        "warnings": warnings + ([] if returned else [
            "No events matched filters. Try broader sources/status, increase limit_per_source, or remove filters."
        ]),
        "next_actions": [
            {"action": "retry", "hint": "Increase limit_per_source (e.g., 25) to search more executions per source."},
            {"action": "retry", "hint": "Set status='failed' to focus on failures."},
            {"action": "retry", "hint": "Use query='<keyword>' to grep message/resource/type."},
        ],
    }

    if include_raw:
        payload["tier1_raw"] = tier1_raw

    return {"status": 200, "payload": payload}

