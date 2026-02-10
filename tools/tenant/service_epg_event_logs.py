# tools/tenant/service_epg_event_logs.py

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional


MAX_EVENTS_DEFAULT = 200
MAX_EXECUTIONS_SCAN_DEFAULT = 20
MAX_FAULTMANAGER_SCAN_DEFAULT = 300  # alerts default in your lab


# -------------------------
# Helpers
# -------------------------
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


def _lower(s: Any) -> str:
    return str(s or "").strip().lower()


def _parse_iso_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None


def _ts_in_range(ts: Optional[str], start: Optional[str], end: Optional[str]) -> bool:
    if not ts:
        return False
    if not start and not end:
        return True

    tdt = _parse_iso_dt(ts)
    sdt = _parse_iso_dt(start) if start else None
    edt = _parse_iso_dt(end) if end else None

    # fallback: lexicographic for iso-like strings
    if tdt is None:
        if start and ts < start:
            return False
        if end and ts > end:
            return False
        return True

    if sdt and tdt < sdt:
        return False
    if edt and tdt > edt:
        return False
    return True


def _severity_rank(sev: Optional[str]) -> int:
    s = _lower(sev)
    if s in ("crit",):
        s = "critical"
    if s in ("warn",):
        s = "warning"

    rank = {
        "critical": 4,
        "major": 3,
        "minor": 2,
        "warning": 2,
        "info": 1,
        "informational": 1,
        "debug": 0,
        "unknown": 0,
        "": 0,
        None: 0,
    }
    return rank.get(s, 0)


def _severity_meets_min(sev: Optional[str], sev_min: Optional[str]) -> bool:
    if not sev_min:
        return True
    return _severity_rank(sev) >= _severity_rank(sev_min)


def _as_list(payload: Any) -> List[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in (
            "events",
            "event",
            "eventhistories",
            "eventHistories",
            "items",
            "data",
            "Alerts",
            "alerts",
            "Alarms",
            "alarms",
            "tenant",
            "executions",
            "execution",
            "result",
            "records",
        ):
            v = payload.get(k)
            if isinstance(v, list):
                return v

        list_values = [v for v in payload.values() if isinstance(v, list)]
        if len(list_values) == 1:
            return list_values[0]
    return []


def _pick_first(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


def _record_text_for_match(rec: Dict[str, Any]) -> str:
    parts = [
        _lower(rec.get("resource")),
        _lower(rec.get("name")),
        _lower(rec.get("message")),
        _lower(rec.get("type")),
    ]
    return " | ".join([p for p in parts if p])


def _build_scope_terms(tenant_name: str, tenant_obj: Dict[str, Any], epgs_obj: Dict[str, Any]) -> List[str]:
    """
    Build tenant scope terms used for matching.

    IMPORTANT:
    - Avoid numeric-only IDs (too broad => false positives).
    - Prefer meaningful strings: tenant name, EPG names, fabric names.
    """
    terms: List[str] = []

    if tenant_name:
        terms.append(tenant_name)

    # EPG names (strong scoping)
    epg_list = _as_list(epgs_obj.get("epg")) if isinstance(epgs_obj, dict) else []
    for epg in epg_list:
        if isinstance(epg, dict):
            nm = _norm_str(epg.get("name"))
            if nm and len(nm) >= 3:
                terms.append(nm)

    # fabric-list
    fl = tenant_obj.get("fabric-list")
    if isinstance(fl, list):
        for f in fl:
            fn = _norm_str(f)
            if fn and len(fn) >= 2:
                terms.append(fn)

    fabric_obj = tenant_obj.get("fabric")
    if isinstance(fabric_obj, list):
        for f in fabric_obj:
            if isinstance(f, dict):
                fn = _norm_str(f.get("name"))
                if fn:
                    terms.append(fn)

    # normalize, dedup
    uniq = []
    seen = set()
    for t in terms:
        tl = _lower(t)
        if tl and tl not in seen:
            seen.add(tl)
            uniq.append(tl)
    return uniq


def tenant_get_service_epg_event_logs(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
) -> dict:
    """
    Tier-2 composite:
      tenant_get_service_epg_event_logs

    Goal:
      "Event logs for Tenant+Service (filters: date range, severity, fuzzy query)."

    Tier-1 tools used (must already exist):
      - tenant_get_tenants
      - tenant_get_tenant
      - tenant_get_endpoint_groups
      - tenant_get_execution_list (optional; may fail in some labs)
      - tenant_get_event_history_list
      - faultmanager_get_alarm_history (fallback)
      - faultmanager_get_alert_history (fallback)
    """

    def call_tier1(tool_name: str, params: Optional[dict] = None) -> dict:
        tool = registry.get(tool_name)
        if not tool:
            return {"status": 0, "payload": None, "error": f"Tier-1 tool not found: {tool_name}"}

        endpoint = tool.get("endpoint") or {}
        path = endpoint.get("path")
        method = tool.get("method")
        if not path or not method:
            return {"status": 0, "payload": None, "error": f"Tier-1 tool missing method/path: {tool_name}"}

        try:
            resp = transport.request(
                method=method,
                port=endpoint.get("port"),
                path=path,
                params=params or {},
                context=context or {},
            )
            if isinstance(resp, dict) and "status" in resp and "payload" in resp:
                return resp
            return {"status": 200, "payload": resp, "error": None}
        except Exception as e:
            return {"status": 0, "payload": None, "error": str(e)}

    inobj = inputs or {}
    tenant_name = _norm_str(inobj.get("tenant_name"))
    if not tenant_name:
        return {
            "status": 400,
            "payload": {
                "error": "Missing required input: tenant_name",
                "expected": {"tenant_name": "string"},
            },
        }

    # filters
    query = _norm_str(inobj.get("query"))
    start_time = _norm_str(inobj.get("start_time"))
    end_time = _norm_str(inobj.get("end_time"))
    severity_min = _norm_str(inobj.get("severity_min"))
    device_ip = _norm_str(inobj.get("device_ip"))

    allow_unscoped = _as_bool(inobj.get("allow_unscoped"), False)
    include_raw = _as_bool(inobj.get("include_raw"), False)

    # strategy toggles
    allow_faultmanager_fallback = _as_bool(inobj.get("allow_faultmanager_fallback"), True)
    include_fault_alarms = _as_bool(inobj.get("include_fault_alarms"), True)
    include_fault_alerts = _as_bool(inobj.get("include_fault_alerts"), True)

    max_events = max(1, min(_as_int(inobj.get("max_events"), MAX_EVENTS_DEFAULT), 2000))
    max_executions = max(1, min(_as_int(inobj.get("max_executions"), MAX_EXECUTIONS_SCAN_DEFAULT), 200))
    max_fault_scan = max(1, min(_as_int(inobj.get("max_fault_scan"), MAX_FAULTMANAGER_SCAN_DEFAULT), 5000))

    warnings: List[str] = []
    tier1_debug: Dict[str, Any] = {}
    tier1_raw: Dict[str, Any] = {}

    # -------------------------
    # Validate tenant name & suggest
    # -------------------------
    tenants_resp = call_tier1("tenant_get_tenants", {})
    tier1_debug["tenant_get_tenants"] = {"status": tenants_resp.get("status"), "error": tenants_resp.get("error")}
    if include_raw:
        tier1_raw["tenant_get_tenants"] = tenants_resp

    tenant_names: List[str] = []
    if tenants_resp.get("status") == 200:
        tpayload = tenants_resp.get("payload")
        # API returns {"tenant":[...]} in your lab
        tarr = _as_list(tpayload.get("tenant")) if isinstance(tpayload, dict) else _as_list(tpayload)
        for t in tarr:
            if isinstance(t, dict):
                nm = _norm_str(t.get("name"))
                if nm:
                    tenant_names.append(nm)

    if tenant_names and tenant_name not in tenant_names:
        suggested = tenant_names[:50]
        return {
            "status": 200,
            "payload": {
                "filter": {"tenant_name": tenant_name},
                "error": f"Tenant not found: {tenant_name}",
                "suggested_tenants": suggested,
                "next_actions": [
                    {
                        "action": "choose_tenant",
                        "tool": "tenant_get_tenants",
                        "message": "Tenant name not found. Pick one of the suggested tenant names and retry.",
                        "suggested_tenants": suggested,
                    }
                ],
            },
        }

    # -------------------------
    # Fetch tenant + EPGs (scope terms)
    # -------------------------
    tenant_resp = call_tier1("tenant_get_tenant", {"name": tenant_name})
    tier1_debug["tenant_get_tenant"] = {"status": tenant_resp.get("status"), "error": tenant_resp.get("error")}
    if include_raw:
        tier1_raw["tenant_get_tenant"] = tenant_resp

    if tenant_resp.get("status") != 200:
        if tenant_resp.get("status") in (404, 409) and tenant_names:
            suggested = tenant_names[:50]
            return {
                "status": 200,
                "payload": {
                    "filter": {"tenant_name": tenant_name},
                    "error": f"Tenant not found: {tenant_name}",
                    "suggested_tenants": suggested,
                    "next_actions": [
                        {
                            "action": "choose_tenant",
                            "tool": "tenant_get_tenants",
                            "message": "Tenant name not found. Pick one of the suggested tenant names and retry.",
                            "suggested_tenants": suggested,
                        }
                    ],
                    "tier1": tier1_debug,
                    "tier1_raw": tier1_raw if include_raw else None,
                },
            }

        return {
            "status": 502,
            "payload": {
                "filter": {"tenant_name": tenant_name},
                "error": "Failed to fetch tenant details (tenant_get_tenant)",
                "tier1": {
                    "tenant_get_tenant": {
                        "status": tenant_resp.get("status"),
                        "payload": tenant_resp.get("payload"),
                        "error": tenant_resp.get("error"),
                        "meta": tenant_resp.get("meta"),
                    }
                },
                "tier1_raw": tier1_raw if include_raw else None,
            },
        }

    epgs_resp = call_tier1("tenant_get_endpoint_groups", {"tenant_name": tenant_name})
    tier1_debug["tenant_get_endpoint_groups"] = {"status": epgs_resp.get("status"), "error": epgs_resp.get("error")}
    if include_raw:
        tier1_raw["tenant_get_endpoint_groups"] = epgs_resp

    tenant_obj = tenant_resp.get("payload") if isinstance(tenant_resp.get("payload"), dict) else {}
    epgs_obj = epgs_resp.get("payload") if isinstance(epgs_resp.get("payload"), dict) else {}
    scope_terms = _build_scope_terms(tenant_name, tenant_obj, epgs_obj)

    # -------------------------
    # Collector / counters
    # -------------------------
    rows: List[Dict[str, Any]] = []
    by_severity = Counter()
    by_scope = Counter()
    scanned = 0
    matched_total = 0  # matched to filters (even if not returned due to max_events)

    # diagnostics for "unscoped"
    unscoped_resource_counter = Counter()
    unscoped_name_counter = Counter()

    def consider_event(rec: Dict[str, Any], scope: str, source: str) -> None:
        nonlocal scanned, matched_total

        scanned += 1

        ts = _pick_first(rec, ["timestamp", "Timestamp", "time", "Time", "TimeCreated", "LastRaised", "LastChanged"])
        sev = _pick_first(rec, ["severity", "Severity", "level", "Level"])
        name = _pick_first(rec, ["name", "Name", "eventName", "EventName", "title", "Title"])
        msg = _pick_first(rec, ["message", "Message", "details", "Details", "description", "Description"])
        rsrc = _pick_first(rec, ["resource", "Resource", "uri", "URI", "path", "Path"])
        typ = _pick_first(rec, ["type", "Type", "alarmType", "AlarmType", "Cause", "cause"])

        ts_s = str(ts) if ts is not None else None
        sev_s = str(sev) if sev is not None else "unknown"

        if not _ts_in_range(ts_s, start_time, end_time):
            return
        if not _severity_meets_min(sev_s, severity_min):
            return

        if query:
            text = " ".join([_lower(name), _lower(msg), _lower(rsrc), _lower(typ)])
            if _lower(query) not in text:
                return

        matched_total += 1

        sev_norm = _lower(sev_s) or "unknown"
        by_severity[sev_norm] += 1
        by_scope[scope] += 1

        if scope == "unscoped":
            unscoped_resource_counter[_lower(rsrc)] += 1
            unscoped_name_counter[_lower(name)] += 1

        if len(rows) < max_events:
            rows.append(
                {
                    "scope": scope,     # tenant_scoped/unscoped
                    "source": source,   # tenant_event/alarm/alert
                    "severity": sev_norm,
                    "name": name,
                    "type": typ,
                    "resource": rsrc,
                    "message": msg,
                    "timestamp": ts_s,
                }
            )

    # -------------------------
    # Try tenant executions -> event history
    # -------------------------
    executions_resp = call_tier1("tenant_get_execution_list", {"limit": max_executions})
    tier1_debug["tenant_get_execution_list"] = {"status": executions_resp.get("status"), "error": executions_resp.get("error")}
    if include_raw:
        tier1_raw["tenant_get_execution_list"] = executions_resp

    execution_uuids: List[str] = []
    if executions_resp.get("status") == 200:
        ex_list = _as_list(executions_resp.get("payload"))
        for ex in ex_list:
            if isinstance(ex, dict):
                uuid = _pick_first(ex, ["uuid", "execution_uuid", "executionUUID", "ExecutionUUID"])
                if uuid:
                    execution_uuids.append(str(uuid))
    else:
        warnings.append(
            "Tier-1 tenant_get_execution_list failed (often 404 in some XCO builds); "
            "falling back to tenant_get_event_history_list without execution_uuid."
        )

    if execution_uuids:
        for uuid in execution_uuids:
            if len(rows) >= max_events:
                break
            params = {"execution_uuid": uuid}
            if device_ip:
                params["device_ip"] = device_ip
            ev_resp = call_tier1("tenant_get_event_history_list", params)
            key = f"tenant_get_event_history_list({uuid})"
            tier1_debug[key] = {"status": ev_resp.get("status"), "error": ev_resp.get("error")}
            if include_raw:
                tier1_raw[key] = ev_resp

            if ev_resp.get("status") != 200:
                continue

            ev_list = _as_list(ev_resp.get("payload"))
            for ev in ev_list:
                if not isinstance(ev, dict):
                    continue
                text = _record_text_for_match(
                    {
                        "resource": _pick_first(ev, ["resource", "Resource", "uri", "URI"]),
                        "name": _pick_first(ev, ["name", "Name"]),
                        "message": _pick_first(ev, ["message", "Message"]),
                        "type": _pick_first(ev, ["type", "Type", "Cause"]),
                    }
                )
                scope = "tenant_scoped" if any(t in text for t in scope_terms) else "unscoped"
                consider_event(ev, scope=scope, source="tenant_event")

    # Global fallback (your lab returns empty object -> no events)
    if matched_total == 0:
        params = {}
        if device_ip:
            params["device_ip"] = device_ip
        ev_resp = call_tier1("tenant_get_event_history_list", params)
        tier1_debug["tenant_get_event_history_list(fallback_global)"] = {"status": ev_resp.get("status"), "error": ev_resp.get("error")}
        if include_raw:
            tier1_raw["tenant_get_event_history_list(fallback_global)"] = ev_resp

        if ev_resp.get("status") == 200:
            ev_list = _as_list(ev_resp.get("payload"))
            for ev in ev_list:
                if not isinstance(ev, dict):
                    continue
                text = _record_text_for_match(
                    {
                        "resource": _pick_first(ev, ["resource", "Resource", "uri", "URI"]),
                        "name": _pick_first(ev, ["name", "Name"]),
                        "message": _pick_first(ev, ["message", "Message"]),
                        "type": _pick_first(ev, ["type", "Type", "Cause"]),
                    }
                )
                scope = "tenant_scoped" if any(t in text for t in scope_terms) else "unscoped"
                consider_event(ev, scope=scope, source="tenant_event")

    # -------------------------
    # FaultManager fallback (has real data in your lab)
    # -------------------------
    def scan_faultmanager() -> None:
        raw_records: List[Dict[str, Any]] = []

        if include_fault_alarms:
            a_resp = call_tier1(
                "faultmanager_get_alarm_history",
                {"unacked": True, "acked": False, "cleared": False, "closed": False},
            )
            tier1_debug["faultmanager_get_alarm_history"] = {"status": a_resp.get("status"), "error": a_resp.get("error")}
            if include_raw:
                tier1_raw["faultmanager_get_alarm_history"] = a_resp
            if a_resp.get("status") == 200:
                raw_records.extend([r for r in _as_list(a_resp.get("payload")) if isinstance(r, dict)])

        if include_fault_alerts:
            al_resp = call_tier1("faultmanager_get_alert_history", {"limit": max_fault_scan})
            tier1_debug["faultmanager_get_alert_history"] = {"status": al_resp.get("status"), "error": al_resp.get("error")}
            if include_raw:
                tier1_raw["faultmanager_get_alert_history"] = al_resp
            if al_resp.get("status") == 200:
                raw_records.extend([r for r in _as_list(al_resp.get("payload")) if isinstance(r, dict)])

        for r in raw_records[:max_fault_scan]:
            text = _record_text_for_match(
                {
                    "resource": _pick_first(r, ["resource", "Resource"]),
                    "name": _pick_first(r, ["name", "Name"]),
                    "message": _pick_first(r, ["message", "Message"]),
                    "type": _pick_first(r, ["type", "Type", "AlarmType", "Cause"]),
                }
            )
            scope = "tenant_scoped" if any(t in text for t in scope_terms) else "unscoped"
            is_alarm = "AlarmID" in r or "alarmid" in {k.lower() for k in r.keys()}
            source = "alarm" if is_alarm else "alert"
            consider_event(r, scope=scope, source=source)

    tenant_scoped_returned = sum(1 for r in rows if r.get("scope") == "tenant_scoped")

    if allow_faultmanager_fallback and (matched_total == 0 or tenant_scoped_returned == 0):
        scan_faultmanager()
        tenant_scoped_returned = sum(1 for r in rows if r.get("scope") == "tenant_scoped")

    # If no scoped matches and user didn't allow unscoped => return none but include diagnostics
    if tenant_scoped_returned == 0 and not allow_unscoped:
        warnings.append(
            "Scanned tenant event history (and optional FaultManager fallback) but found 0 tenant-scoped matches. "
            "This commonly happens when records are system/global (e.g., /App/System/...) and do not include "
            "tenant/EPG identifiers in Resource/Name/Message fields. "
            "Try allow_unscoped=true to view global events."
        )
        rows = []

    # If allow_unscoped and still no scoped matches -> explain it
    if tenant_scoped_returned == 0 and allow_unscoped:
        warnings.append("No tenant-scoped matches found. Returning unscoped events because allow_unscoped=true.")

    # Sort newest-first where possible (string sort works for ISO timestamps)
    rows.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)

    # -------------------------
    # Diagnostics: top unscoped resources/names (like Tool #14)
    # -------------------------
    unscoped_top_resources = [
        {"resource": k, "count": v}
        for k, v in unscoped_resource_counter.most_common(8)
        if k
    ]
    unscoped_top_names = [
        {"name": k, "count": v}
        for k, v in unscoped_name_counter.most_common(8)
        if k
    ]

    payload: Dict[str, Any] = {
        "filter": {
            "tenant_name": tenant_name,
            "query": query,
            "severity_min": severity_min,
            "start_time": start_time,
            "end_time": end_time,
            "device_ip": device_ip,
            "allow_unscoped": allow_unscoped,
            "allow_faultmanager_fallback": allow_faultmanager_fallback,
            "max_events": max_events,
            "max_executions": max_executions,
        },
        "scope": {
            "epg_scope_count": len(_as_list(epgs_obj.get("epg"))) if isinstance(epgs_obj, dict) else 0,
            "scope_terms_count": len(scope_terms),
        },
        "counts": {
            "events_scanned": scanned,
            "matched_returned": len(rows),
            "by_severity": dict(by_severity),
            "by_scope": dict(by_scope),
        },
        "rows": rows,
        "warnings": warnings,
    }

    # Only include these when scoping didn't work (helps debug)
    if tenant_scoped_returned == 0:
        if unscoped_top_resources:
            payload["unscoped_top_resources"] = unscoped_top_resources
        if unscoped_top_names:
            payload["unscoped_top_names"] = unscoped_top_names

    if include_raw:
        payload["tier1"] = tier1_debug
        payload["tier1_raw"] = tier1_raw

    return {"status": 200, "payload": payload}

