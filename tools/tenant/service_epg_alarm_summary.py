# tools/tenant/service_epg_alarm_summary.py

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from collections import Counter, defaultdict


SEV_RANK = {
    "critical": 5,
    "major": 4,
    "minor": 3,
    "warning": 2,
    "info": 1,
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


def _lower(v: Any) -> str:
    return str(v or "").strip().lower()


def _extract_records(payload: Any) -> List[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in (
            "Alarms", "alarms", "alarm",
            "Alerts", "alerts", "alert",
            "items", "data", "result", "payload"
        ):
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        lists = [v for v in payload.values() if isinstance(v, list)]
        if len(lists) == 1:
            return [x for x in lists[0] if isinstance(x, dict)]
    return []


def _is_tenant_not_found(res: dict) -> bool:
    if not isinstance(res, dict):
        return False
    status = res.get("status")
    payload = res.get("payload")
    if not isinstance(payload, dict):
        return False
    code = payload.get("code")
    msg = str(payload.get("message") or "").lower()
    if code == 1308:
        return True
    if status in (404, 409) and ("tenant" in msg and "not found" in msg):
        return True
    return False


def _extract_tenant_names(payload: Any) -> List[str]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        t = payload.get("tenant")
        if isinstance(t, list):
            out = []
            for x in t:
                if isinstance(x, dict):
                    n = _norm_str(x.get("name"))
                    if n:
                        out.append(n)
            return out
        lists = [v for v in payload.values() if isinstance(v, list)]
        if len(lists) == 1:
            out = []
            for x in lists[0]:
                if isinstance(x, dict):
                    n = _norm_str(x.get("name"))
                    if n:
                        out.append(n)
            return out
    if isinstance(payload, list):
        out = []
        for x in payload:
            if isinstance(x, dict):
                n = _norm_str(x.get("name"))
                if n:
                    out.append(n)
        return out
    return []


def _sev_ok(sev: Optional[str], exact: Optional[str], min_sev: Optional[str]) -> bool:
    if not (exact or min_sev):
        return True
    s = _lower(sev)
    if exact:
        return s == _lower(exact)
    want = SEV_RANK.get(_lower(min_sev), 0)
    have = SEV_RANK.get(s, 0)
    return have >= want


def _pick_first(d: dict, keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


def _get_sev(rec: dict) -> Optional[str]:
    return _pick_first(rec, ["Severity", "severity", "sev", "level", "Level"])


def _get_id(rec: dict) -> Optional[Any]:
    return _pick_first(rec, ["AlarmID", "AlertID", "id", "alarm_id", "alert_id", "alarmId", "alertId", "uuid"])


def _get_type(rec: dict) -> Optional[str]:
    return _pick_first(rec, ["AlarmType", "alarm_type", "Type", "type", "category", "Category", "Name", "name"])


def _get_resource(rec: dict) -> Optional[str]:
    return _pick_first(rec, ["Resource", "resource", "source", "Source"])


def _get_message(rec: dict) -> Optional[str]:
    return _pick_first(rec, ["Message", "message", "Description", "description", "details", "Details", "text"])


def _get_time(rec: dict) -> Optional[Any]:
    return _pick_first(rec, ["Timestamp", "timestamp", "LastRaised", "lastRaised", "TimeCreated", "timeCreated",
                            "created", "created_at", "createdAt"])


def _record_text(rec: dict) -> str:
    parts: List[str] = []

    for k in ("Resource", "resource", "Name", "name", "Message", "message",
              "Description", "description", "Cause", "cause", "AlarmType", "alarm_type"):
        if k in rec and rec.get(k) is not None:
            parts.append(str(rec.get(k)))

    scl = rec.get("StatusChangeList") or rec.get("statusChangeList")
    if isinstance(scl, list):
        for item in scl[:50]:
            if isinstance(item, dict):
                m = item.get("Message") or item.get("message")
                s = item.get("Severity") or item.get("severity")
                t = item.get("Time") or item.get("time")
                if m is not None:
                    parts.append(str(m))
                if s is not None:
                    parts.append(str(s))
                if t is not None:
                    parts.append(str(t))

    return " ".join(parts).lower()


def _build_scope_terms(tenant_name: str, tenant_id: Optional[Any], epg_names: List[str]) -> List[str]:
    """
    IMPORTANT:
      Do NOT include bare tenant_id like "3" (false positives).
      Only include explicit tenant-id patterns.
    """
    terms: List[str] = []

    tn = tenant_name.strip()
    if tn:
        terms.append(tn)
        terms.append(f"tenant={tn}")
        terms.append(f"tenant:{tn}")
        terms.append(f"tenant {tn}")
        terms.append(f"/tenant/{tn}")
        terms.append(f"/tenants/{tn}")

    if tenant_id is not None:
        tid = str(tenant_id).strip()
        if tid:
            terms.append(f"tenantid={tid}")
            terms.append(f"tenant_id={tid}")
            terms.append(f"tenant id {tid}")
            terms.append(f"/tenant/{tid}")
            terms.append(f"/tenants/{tid}")

    for n in epg_names:
        if n and isinstance(n, str):
            terms.append(n)

    seen = set()
    out: List[str] = []
    for t in terms:
        t2 = t.strip()
        if not t2:
            continue
        key = t2.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t2)
    return out


def tenant_get_service_epg_alarm_summary(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
) -> dict:
    inobj = inputs or {}

    tenant_name = _norm_str(inobj.get("tenant_name")) or _norm_str(inobj.get("name"))
    if not tenant_name:
        return {
            "status": 400,
            "payload": {
                "error": "Missing required input: tenant_name",
                "expected": {"tenant_name": "string"},
            },
        }

    include_alarms = _as_bool(inobj.get("include_alarms"), True)
    include_alerts = _as_bool(inobj.get("include_alerts"), True)

    severity = _norm_str(inobj.get("severity"))
    severity_min = _norm_str(inobj.get("severity_min"))
    alarm_type = _norm_str(inobj.get("alarm_type"))

    resource_contains = _norm_str(inobj.get("resource_contains"))
    message_contains = _norm_str(inobj.get("message_contains"))
    epg_name_contains = _norm_str(inobj.get("epg_name_contains"))

    unacked = _as_bool(inobj.get("unacked"), True)
    acked = _as_bool(inobj.get("acked"), False)
    cleared = _as_bool(inobj.get("cleared"), False)
    closed = _as_bool(inobj.get("closed"), False)

    alert_limit = max(1, min(_as_int(inobj.get("alert_limit"), 300), 500))
    max_records = max(1, min(_as_int(inobj.get("max_records"), 200), 2000))

    include_raw = _as_bool(inobj.get("include_raw"), False)
    allow_unscoped = _as_bool(inobj.get("allow_unscoped"), False)

    filt = {
        "tenant_name": tenant_name,
        "include_alarms": include_alarms,
        "include_alerts": include_alerts,
        "severity": severity,
        "severity_min": severity_min,
        "alarm_type": alarm_type,
        "resource_contains": resource_contains,
        "message_contains": message_contains,
        "epg_name_contains": epg_name_contains,
        "unacked": unacked,
        "acked": acked,
        "cleared": cleared,
        "closed": closed,
        "alert_limit": alert_limit,
        "max_records": max_records,
        "allow_unscoped": allow_unscoped,
        "include_raw": include_raw,
    }

    raw: Dict[str, Any] = {}
    warnings: List[str] = []
    next_actions: List[dict] = []

    def call_tier1(tool_name: str, params: Optional[dict] = None) -> dict:
        tool = registry.get(tool_name)
        if not tool:
            return {"status": 0, "payload": None, "error": f"Tier-1 tool not found: {tool_name}"}
        endpoint = tool.get("endpoint") or {}
        path = endpoint.get("path")
        method = tool.get("method")
        if not path or not method:
            return {"status": 0, "payload": None, "error": f"Tier-1 tool missing endpoint/method: {tool_name}"}
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

    # Validate tenant
    tenant_res = call_tier1("tenant_get_tenant", {"name": tenant_name})
    if include_raw:
        raw["tenant_get_tenant"] = tenant_res

    if tenant_res.get("status") not in (200, 204):
        suggested: List[str] = []
        if _is_tenant_not_found(tenant_res):
            tenants_res = call_tier1("tenant_get_tenants", {})
            if include_raw:
                raw["tenant_get_tenants"] = tenants_res
            if tenants_res.get("status") == 200:
                suggested = _extract_tenant_names(tenants_res.get("payload"))

        if suggested:
            next_actions.append(
                {
                    "action": "choose_tenant",
                    "tool": "tenant_get_tenants",
                    "message": "Tenant name not found. Pick one of the suggested tenant names and retry.",
                    "suggested_tenants": suggested[:50],
                }
            )

        err = "Failed to fetch tenant details (tenant_get_tenant)"
        if _is_tenant_not_found(tenant_res):
            err = f"Tenant not found: {tenant_name}"

        out_payload: Dict[str, Any] = {
            "filter": filt,
            "error": err,
            "tier1": {"tenant_get_tenant": tenant_res},
            "warnings": warnings,
            "next_actions": next_actions,
        }
        if suggested:
            out_payload["suggested_tenants"] = suggested[:50]
        if include_raw:
            out_payload["tier1_raw"] = raw
        return {"status": 502, "payload": out_payload}

    tenant_obj = tenant_res.get("payload") if isinstance(tenant_res.get("payload"), dict) else {}
    tenant_id = tenant_obj.get("id")

    # Build EPG scope list
    epg_names: List[str] = []
    for x in (tenant_obj.get("epg-list") or []):
        n = _norm_str(x)
        if n:
            epg_names.append(n)

    epgs_res = call_tier1("tenant_get_endpoint_groups", {"tenant_name": tenant_name})
    if include_raw:
        raw["tenant_get_endpoint_groups"] = epgs_res

    if epgs_res.get("status") == 200:
        payload = epgs_res.get("payload")
        epg_list = []
        if isinstance(payload, dict) and isinstance(payload.get("epg"), list):
            epg_list = payload.get("epg")
        elif isinstance(payload, list):
            epg_list = payload
        for e in epg_list:
            if isinstance(e, dict):
                n = _norm_str(e.get("name"))
                if n:
                    epg_names.append(n)
    else:
        warnings.append("Failed to fetch endpoint groups (tenant_get_endpoint_groups). EPG scoping may be weaker.")

    if epg_name_contains:
        needle = epg_name_contains.lower()
        epg_names = [x for x in epg_names if needle in x.lower()]

    seen_epg = set()
    epg_names = [x for x in epg_names if not (x.lower() in seen_epg or seen_epg.add(x.lower()))]

    scope_terms = _build_scope_terms(tenant_name, tenant_id, epg_names)

    # Fetch faults
    alarms: List[dict] = []
    alerts: List[dict] = []
    tier1_fail: Dict[str, Any] = {}

    if include_alarms:
        a_params: Dict[str, Any] = {
            "unacked": unacked,
            "acked": acked,
            "cleared": cleared,
            "closed": closed,
        }
        if alarm_type:
            a_params["alarm_type"] = alarm_type

        a_res = call_tier1("faultmanager_get_alarm_history", a_params)
        if include_raw:
            raw["faultmanager_get_alarm_history"] = a_res
        if a_res.get("status") == 200:
            alarms = _extract_records(a_res.get("payload"))
        else:
            tier1_fail["faultmanager_get_alarm_history"] = a_res

    if include_alerts:
        al_params: Dict[str, Any] = {"limit": alert_limit}
        if severity:
            al_params["severity"] = severity

        a2_res = call_tier1("faultmanager_get_alert_history", al_params)
        if include_raw:
            raw["faultmanager_get_alert_history"] = a2_res
        if a2_res.get("status") == 200:
            alerts = _extract_records(a2_res.get("payload"))
        else:
            tier1_fail["faultmanager_get_alert_history"] = a2_res

    if tier1_fail:
        return {
            "status": 502,
            "payload": {
                "filter": filt,
                "error": "Failed to fetch alarm/alert history from FaultManager",
                "tier1": tier1_fail,
            },
        }

    def post_filter_common(rec: dict) -> bool:
        txt = _record_text(rec)
        if resource_contains and resource_contains.lower() not in txt:
            return False
        if message_contains and message_contains.lower() not in txt:
            return False
        return True

    def match_scope(rec: dict) -> Tuple[bool, Optional[str]]:
        if not scope_terms:
            return False, None
        txt = _record_text(rec)
        for t in scope_terms:
            if t.lower() in txt:
                return True, t
        return False, None

    rows: List[dict] = []
    sev_counts = defaultdict(int)
    src_counts = defaultdict(int)
    match_term_counts = Counter()

    unscoped_resources = Counter()
    unscoped_names = Counter()

    def track_unscoped(rec: dict) -> None:
        r = _get_resource(rec)
        n = _pick_first(rec, ["Name", "name"])
        if r:
            unscoped_resources[str(r)] += 1
        if n:
            unscoped_names[str(n)] += 1

    def push_row(source: str, rec: dict, matched_term: Optional[str], scope: str) -> None:
        sev = _get_sev(rec)
        rows.append(
            {
                "scope": scope,  # "tenant" or "unscoped"
                "source": source,  # "alarm" or "alert"
                "id": _get_id(rec),
                "severity": sev,
                "type": _get_type(rec),
                "resource": _get_resource(rec),
                "message": _get_message(rec),
                "timestamp": _get_time(rec),
                "matched_scope_term": matched_term,
            }
        )
        src_counts[source] += 1
        sev_counts[_lower(sev) or "unknown"] += 1
        if matched_term:
            match_term_counts[matched_term] += 1

    def accept_severity(rec: dict) -> bool:
        sev = _get_sev(rec)
        return _sev_ok(sev, severity, severity_min)

    # First pass: strict tenant scope
    for rec in alarms:
        if not isinstance(rec, dict):
            continue
        track_unscoped(rec)
        if not post_filter_common(rec):
            continue
        if not accept_severity(rec):
            continue
        ok, term = match_scope(rec)
        if not ok:
            continue
        push_row("alarm", rec, term, scope="tenant")
        if len(rows) >= max_records:
            warnings.append(f"Matched records truncated: returning first {max_records}.")
            break

    if len(rows) < max_records:
        for rec in alerts:
            if not isinstance(rec, dict):
                continue
            track_unscoped(rec)
            if not post_filter_common(rec):
                continue
            if not accept_severity(rec):
                continue
            ok, term = match_scope(rec)
            if not ok:
                continue
            push_row("alert", rec, term, scope="tenant")
            if len(rows) >= max_records:
                warnings.append(f"Matched records truncated: returning first {max_records}.")
                break

    # If strict scope yields none, optionally return unscoped rows
    if len(rows) == 0 and allow_unscoped:
        warnings.append(
            "No tenant-scoped matches found. Returning unscoped FaultManager records because allow_unscoped=true."
        )
        # return alarms first, then alerts
        for rec in alarms:
            if not isinstance(rec, dict):
                continue
            if not post_filter_common(rec):
                continue
            if not accept_severity(rec):
                continue
            push_row("alarm", rec, matched_term=None, scope="unscoped")
            if len(rows) >= max_records:
                warnings.append(f"Unscoped records truncated: returning first {max_records}.")
                break

        if len(rows) < max_records:
            for rec in alerts:
                if not isinstance(rec, dict):
                    continue
                if not post_filter_common(rec):
                    continue
                if not accept_severity(rec):
                    continue
                push_row("alert", rec, matched_term=None, scope="unscoped")
                if len(rows) >= max_records:
                    warnings.append(f"Unscoped records truncated: returning first {max_records}.")
                    break

    counts: Dict[str, Any] = {
        "alarms_scanned": len(alarms),
        "alerts_scanned": len(alerts),
        "matched_returned": len(rows),
        "by_source": dict(src_counts),
        "by_severity": dict(sev_counts),
        "scope": {
            "epg_scope_count": len(epg_names),
            "scope_terms_count": len(scope_terms),
            "match_term_top": [{"term": t, "count": c} for t, c in match_term_counts.most_common(10)],
        },
    }

    if (len(alarms) + len(alerts)) > 0 and len(rows) == 0:
        warnings.append(
            "Scanned FaultManager alarms/alerts but found 0 tenant-scoped matches. "
            "This commonly happens when FaultManager records are system/global (e.g., /App/System/...) "
            "and do not include tenant/EPG identifiers in Resource/Name/Message fields."
        )
        counts["unscoped_top_resources"] = [{"resource": r, "count": c} for r, c in unscoped_resources.most_common(5)]
        counts["unscoped_top_names"] = [{"name": n, "count": c} for n, c in unscoped_names.most_common(5)]
        next_actions.append(
            {
                "action": "use_allow_unscoped_or_filter",
                "message": "If you still want a useful table, call again with allow_unscoped=true, or use resource_contains/message_contains/severity filters.",
            }
        )

    payload: Dict[str, Any] = {
        "filter": filt,
        "tenant": {
            "name": tenant_name,
            "id": tenant_id,
            "details": tenant_obj if tenant_obj else None,
        },
        "counts": counts,
        "rows": rows,
        "warnings": warnings,
        "next_actions": next_actions,
    }

    if include_raw:
        payload["tier1_raw"] = raw

    return {"status": 200, "payload": payload}

