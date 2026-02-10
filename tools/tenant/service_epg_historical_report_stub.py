# tools/tenant/service_epg_historical_report_stub.py

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# -----------------------------
# Helpers (keep lightweight)
# -----------------------------

SEVERITY_ORDER = ["Info", "Warning", "Minor", "Major", "Critical"]
SEV_RANK = {s.lower(): i for i, s in enumerate(SEVERITY_ORDER)}


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


def _pick_first(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


def _extract_records(payload: Any) -> List[dict]:
    """
    Best-effort list extraction from common wrapper shapes:
      - list => itself
      - dict with known keys (Alarms/Alerts/items/data/result/payload)
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in (
            "Alarms",
            "alarms",
            "alarm",
            "Alerts",
            "alerts",
            "alert",
            "items",
            "data",
            "result",
            "payload",
        ):
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        # fallback: first list-like value
        for v in payload.values():
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _record_text(rec: dict) -> str:
    parts: List[str] = []
    for k, v in rec.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            parts.append(f"{k}={v}")
    return " ".join(parts).lower()


def _is_num_str(s: str) -> bool:
    try:
        float(s)
        return True
    except Exception:
        return False


def _parse_ts_to_ms(v: Any) -> Optional[int]:
    """
    Accepts:
      - epoch ms / epoch seconds (int/float or numeric string)
      - ISO strings (best-effort)
    """
    if v is None:
        return None

    try:
        # numeric
        if isinstance(v, (int, float)):
            n = float(v)
            if n > 1e12:  # ms
                return int(n)
            if n > 1e9:  # seconds
                return int(n * 1000)

        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None

            if _is_num_str(s):
                n = float(s)
                if n > 1e12:
                    return int(n)
                if n > 1e9:
                    return int(n * 1000)

            s2 = s.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(s2)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except Exception:
                return None
    except Exception:
        return None

    return None


def _get_time_ms(rec: dict) -> Optional[int]:
    v = _pick_first(
        rec,
        [
            "Timestamp",
            "timestamp",
            "LastRaised",
            "lastRaised",
            "TimeCreated",
            "timeCreated",
            "created",
            "created_at",
            "createdAt",
            "raised",
            "raisedAt",
            "raised_at",
            "lastUpdated",
            "last_updated",
            # common alarm keys in some XCO versions
            "lastUpdatedTime",
            "last_updated_time",
            "LastChanged",
            "lastChanged",
        ],
    )
    return _parse_ts_to_ms(v)


def _get_severity(rec: dict) -> Optional[str]:
    sev = _pick_first(rec, ["Severity", "severity", "SEVERITY"])
    if sev is None:
        return None
    s = str(sev).strip()
    return s if s else None


def _severity_pass(sev: Optional[str], severity: Optional[str], severity_min: Optional[str]) -> bool:
    # exact filter wins
    if severity:
        return (sev or "").strip().lower() == severity.strip().lower()
    if not severity_min:
        return True
    if sev is None:
        return False
    return SEV_RANK.get(sev.lower(), -1) >= SEV_RANK.get(severity_min.lower(), -1)


def _extract_tenant_names(payload: Any, limit: int = 50) -> List[str]:
    names: List[str] = []
    for rec in _extract_records(payload):
        n = _pick_first(rec, ["name", "Name", "tenantName", "tenant_name", "tenant"])
        if isinstance(n, str) and n.strip():
            names.append(n.strip())
        if len(names) >= limit:
            break

    # de-dupe preserving order
    seen = set()
    out = []
    for n in names:
        k = n.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out


def _is_tenant_not_found(res: dict) -> bool:
    if not isinstance(res, dict):
        return False
    err = str(res.get("error") or "").lower()
    if "not found" in err and "tenant" in err:
        return True
    payload = res.get("payload")
    if isinstance(payload, dict):
        msg = str(payload.get("message") or payload.get("error") or "").lower()
        if "not found" in msg and "tenant" in msg:
            return True
    return False


def _iso_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _go_time_from_ms(ms: int) -> str:
    """
    FaultManager alert history in this lab expects Go-style time layout:
      "2006-01-02T15:04:05"
    i.e. no timezone suffix, no fractional seconds.
    """
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def tenant_get_service_epg_historical_report_stub(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2 composite: tenant_get_service_epg_historical_report_stub (read-only, v1)

    Composite strategy (NO invented Tier-1 tools):
      - tenant_get_tenant (+ tenant_get_tenants for suggestions)
      - tenant_get_endpoint_groups (scope terms)
      - tenant_get_vrfs (scope terms)
      - faultmanager_get_alert_history (time-bounded alerts)
      - faultmanager_get_alarm_history (best-effort alarms; time-bounded locally)
    """

    tenant_name = _norm_str((inputs or {}).get("tenant_name"))
    if not tenant_name:
        return {"status": 400, "payload": {"error": "tenant_name is required"}}

    window_days = _as_int((inputs or {}).get("window_days"), 7)
    if window_days <= 0:
        window_days = 7
    if window_days > 365:
        window_days = 365

    include_alerts = _as_bool((inputs or {}).get("include_alerts"), True)
    include_alarms = _as_bool((inputs or {}).get("include_alarms"), True)
    allow_unscoped = _as_bool((inputs or {}).get("allow_unscoped"), False)
    include_raw = _as_bool((inputs or {}).get("include_raw"), False)

    severity = _norm_str((inputs or {}).get("severity"))
    severity_min = _norm_str((inputs or {}).get("severity_min"))
    query = _norm_str((inputs or {}).get("query"))

    alert_limit = _as_int((inputs or {}).get("alert_limit"), 300)
    if alert_limit < 1:
        alert_limit = 1
    if alert_limit > 500:
        alert_limit = 500

    max_records = _as_int((inputs or {}).get("max_records"), 200)
    if max_records < 1:
        max_records = 1
    if max_records > 2000:
        max_records = 2000

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

    # -----------------------
    # 0) Validate tenant exists (best-effort)
    # -----------------------
    tenant_res = call_tier1("tenant_get_tenant", {"name": tenant_name})
    if include_raw:
        raw["tenant_get_tenant"] = tenant_res

    if tenant_res.get("status") not in (200, 204):
        suggested: List[str] = []
        if _is_tenant_not_found(tenant_res):
            ten_res = call_tier1("tenant_get_tenants")
            if include_raw:
                raw["tenant_get_tenants"] = ten_res
            if ten_res.get("status") == 200:
                suggested = _extract_tenant_names(ten_res.get("payload"))
        return {
            "status": 404,
            "payload": {
                "error": "Tenant not found",
                "tenant_name": tenant_name,
                "suggested_tenants": suggested,
                "next_actions": [
                    {
                        "action": "retry",
                        "hint": "Pick a tenant from suggested_tenants and retry with that exact tenant_name.",
                    }
                ],
                "tier1_status": {"tenant_get_tenant": tenant_res.get("status")},
            },
        }

    # -----------------------
    # 1) Build scope terms (VRF + EPG names)
    # -----------------------
    scope_terms: List[str] = [tenant_name.strip().lower()]

    vrf_res = call_tier1("tenant_get_vrfs", {"tenant_name": tenant_name})
    if include_raw:
        raw["tenant_get_vrfs"] = vrf_res
    vrf_names: List[str] = []
    if vrf_res.get("status") == 200:
        for rec in _extract_records(vrf_res.get("payload")):
            n = _pick_first(rec, ["name", "Name", "vrfName", "vrf_name"])
            if isinstance(n, str) and n.strip():
                vrf_names.append(n.strip())
    else:
        warnings.append(f"tenant_get_vrfs returned status={vrf_res.get('status')}")
    if vrf_names:
        scope_terms.extend([x.lower() for x in vrf_names[:200]])

    epg_res = call_tier1("tenant_get_endpoint_groups", {"tenant_name": tenant_name})
    if include_raw:
        raw["tenant_get_endpoint_groups"] = epg_res
    epg_names: List[str] = []
    if epg_res.get("status") == 200:
        for rec in _extract_records(epg_res.get("payload")):
            n = _pick_first(rec, ["name", "Name", "endpointGroupName", "endpoint_group_name"])
            if isinstance(n, str) and n.strip():
                epg_names.append(n.strip())
    else:
        warnings.append(f"tenant_get_endpoint_groups returned status={epg_res.get('status')}")
    if epg_names:
        scope_terms.extend([x.lower() for x in epg_names[:400]])

    # de-dupe
    seen = set()
    scope_terms = [t for t in scope_terms if not (t in seen or seen.add(t))]

    # -----------------------
    # 2) Compute time window
    # -----------------------
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    after_ms = now_ms - int(window_days * 24 * 60 * 60 * 1000)

    time_range = {
        "after_timestamp": str(after_ms),
        "before_timestamp": str(now_ms),
        "after_iso": _iso_from_ms(after_ms),
        "before_iso": _iso_from_ms(now_ms),
    }

    # -----------------------
    # 3) Alerts
    # -----------------------
    alerts_all: List[dict] = []
    alerts_filtered: List[dict] = []  # after time+severity+query
    alerts_scoped: List[dict] = []    # filtered + scope_terms
    top_unscoped_resources: Counter = Counter()

    if include_alerts:
        params = {
            "after_timestamp": _go_time_from_ms(after_ms),
            "before_timestamp": _go_time_from_ms(now_ms),
            "limit": alert_limit,
        }

        if severity:
            params["severity"] = severity

        alerts_res = call_tier1("faultmanager_get_alert_history", params)
        if include_raw:
            raw["faultmanager_get_alert_history"] = alerts_res

        if alerts_res.get("status") == 200:
            alerts_all = _extract_records(alerts_res.get("payload"))
        else:
            warnings.append(f"faultmanager_get_alert_history returned status={alerts_res.get('status')}")

        def is_scoped(rec: dict) -> bool:
            txt = _record_text(rec)
            return any(term in txt for term in scope_terms)

        for rec in alerts_all:
            ts = _get_time_ms(rec)
            if ts is not None and (ts < after_ms or ts > now_ms):
                continue

            sev = _get_severity(rec)
            if not _severity_pass(sev, severity, severity_min):
                continue

            if query and query.lower() not in _record_text(rec):
                continue

            alerts_filtered.append(rec)

            if is_scoped(rec):
                alerts_scoped.append(rec)
            else:
                r = _pick_first(rec, ["resource", "Resource", "name", "Name"])
                if isinstance(r, str) and r.strip():
                    top_unscoped_resources[r.strip()] += 1

        if not alerts_scoped and alerts_all:
            warnings.append(
                "No tenant/EPG-scoped alerts matched the scope terms in this environment. "
                "This can be normal (many labs emit only global /App/System alerts)."
            )
            if not allow_unscoped:
                next_actions.append(
                    {
                        "action": "retry",
                        "hint": "Set allow_unscoped=true to include system/global alerts in the output.",
                    }
                )

    # -----------------------
    # 4) Alarms
    # -----------------------
    alarms_all: List[dict] = []
    alarms_filtered: List[dict] = []  # after time+severity+query
    alarms_scoped: List[dict] = []    # filtered + scope_terms
    top_unscoped_alarm_resources: Counter = Counter()

    if include_alarms:
        alarm_params = {"unacked616": True, "acked": False, "cleared": False, "closed": False}

        alarm_params_res = dict(alarm_params)
        alarm_params_res["resource"] = tenant_name

        alarms_res = call_tier1("faultmanager_get_alarm_history", alarm_params_res)
        if include_raw:
            raw["faultmanager_get_alarm_history_resource"] = alarms_res

        if alarms_res.get("status") == 200:
            alarms_all = _extract_records(alarms_res.get("payload"))
        else:
            warnings.append(f"faultmanager_get_alarm_history(resource=tenant) returned status={alarms_res.get('status')}")

        if not alarms_all:
            alarms_res2 = call_tier1("faultmanager_get_alarm_history", alarm_params)
            if include_raw:
                raw["faultmanager_get_alarm_history_all"] = alarms_res2
            if alarms_res2.get("status") == 200:
                alarms_all = _extract_records(alarms_res2.get("payload"))
            else:
                warnings.append(f"faultmanager_get_alarm_history returned status={alarms_res2.get('status')}")

        def is_scoped_alarm(rec: dict) -> bool:
            txt = _record_text(rec)
            return any(term in txt for term in scope_terms)

        for rec in alarms_all:
            ts = _get_time_ms(rec)
            if ts is not None and (ts < after_ms or ts > now_ms):
                continue

            sev = _get_severity(rec)
            if not _severity_pass(sev, severity, severity_min):
                continue

            if query and query.lower() not in _record_text(rec):
                continue

            alarms_filtered.append(rec)

            if is_scoped_alarm(rec):
                alarms_scoped.append(rec)
            else:
                r = _pick_first(rec, ["resource", "Resource", "name", "Name"])
                if isinstance(r, str) and r.strip():
                    top_unscoped_alarm_resources[r.strip()] += 1

        if not alarms_scoped and alarms_all:
            warnings.append(
                "No tenant/EPG-scoped alarms matched the scope terms in this environment. "
                "This can be normal; also note alarm history endpoint lacks a time filter so results vary by backend."
            )
            if not allow_unscoped:
                next_actions.append(
                    {
                        "action": "retry",
                        "hint": "Set allow_unscoped=true to include system/global alarms in the output.",
                    }
                )

    # -----------------------
    # 5) Build output (compact summary)
    # -----------------------
    def slim_record(rec: dict) -> dict:
        return {
            "timestamp": _pick_first(
                rec,
                [
                    "Timestamp",
                    "timestamp",
                    "TimeCreated",
                    "timeCreated",
                    "created",
                    "createdAt",
                    "LastRaised",
                    "lastRaised",
                    "lastUpdated",
                    "last_updated",
                    "lastUpdatedTime",
                    "last_updated_time",
                    "LastChanged",
                    "lastChanged",
                ],
            ),
            "severity": _get_severity(rec),
            "resource": _pick_first(rec, ["resource", "Resource"]),
            "name": _pick_first(rec, ["name", "Name"]),
            "message": _pick_first(rec, ["message", "Message", "description", "Description", "detail", "Detail"]),
        }

    if allow_unscoped:
        alerts_scoped_ids = {id(r) for r in alerts_scoped}
        alarms_scoped_ids = {id(r) for r in alarms_scoped}

        alerts_out = alerts_scoped + [r for r in alerts_filtered if id(r) not in alerts_scoped_ids]
        alarms_out = alarms_scoped + [r for r in alarms_filtered if id(r) not in alarms_scoped_ids]
    else:
        alerts_out = alerts_scoped
        alarms_out = alarms_scoped

    alerts_out = alerts_out[:max_records]
    alarms_out = alarms_out[:max_records]

    sev_counts = Counter()
    for rec in alerts_out:
        s = (_get_severity(rec) or "Unknown").strip()
        sev_counts[s.lower()] += 1
    for rec in alarms_out:
        s = (_get_severity(rec) or "Unknown").strip()
        sev_counts[s.lower()] += 1

    # -----------------------
    # SMALL IMPROVEMENTS (requested)
    # 1) Echo filters in the payload so logs are self-describing.
    # 2) Add "after_filters" and "filtered_out" counts to summary.
    # -----------------------

    payload: Dict[str, Any] = {
        "tenant_name": tenant_name,
        "window_days": window_days,
        "time_range": time_range,
        "input_echo": {
            "tenant_name": tenant_name,
            "window_days": window_days,
            "allow_unscoped": allow_unscoped,
            "include_alerts": include_alerts,
            "include_alarms": include_alarms,
            "severity": severity,
            "severity_min": severity_min,
            "query": query,
            "alert_limit": alert_limit,
            "max_records": max_records,
        },
        "scope": {
            "vrf_count": len(vrf_names),
            "epg_count": len(epg_names),
            "scope_terms_sample": scope_terms[:25],
        },
        "summary": {
            "alerts_total_fetched": len(alerts_all),
            "alarms_total_fetched": len(alarms_all),

            "alerts_after_filters": len(alerts_filtered),
            "alarms_after_filters": len(alarms_filtered),
            "alerts_filtered_out": max(0, len(alerts_all) - len(alerts_filtered)),
            "alarms_filtered_out": max(0, len(alarms_all) - len(alarms_filtered)),

            "alerts_matched": len(alerts_scoped),
            "alarms_matched": len(alarms_scoped),
            "returned_alerts": len(alerts_out),
            "returned_alarms": len(alarms_out),
            "by_severity": dict(sev_counts),
            "top_unscoped_resources": top_unscoped_resources.most_common(10),
            "top_unscoped_alarm_resources": top_unscoped_alarm_resources.most_common(10),
        },
        "alerts": [slim_record(r) for r in alerts_out] if include_alerts else None,
        "alarms": [slim_record(r) for r in alarms_out] if include_alarms else None,
        "warnings": warnings,
        "next_actions": next_actions,
    }

    if include_raw:
        payload["tier1_raw"] = raw

    return {"status": 200, "payload": payload}

