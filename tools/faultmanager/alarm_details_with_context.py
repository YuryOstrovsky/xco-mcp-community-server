# tools/faultmanager/alarm_details_with_context.py

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# -----------------------------
# Helpers
# -----------------------------

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
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in ("Alarms", "alarms", "alarm", "Alerts", "alerts", "alert", "items", "data", "result", "payload"):
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
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
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            n = float(v)
            if n > 1e12:
                return int(n)          # ms
            if n > 1e9:
                return int(n * 1000)   # seconds

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
        ],
    )
    return _parse_ts_to_ms(v)


def _get_severity(rec: dict) -> Optional[str]:
    sev = _pick_first(rec, ["Severity", "severity", "SEVERITY"])
    if sev is None:
        return None
    s = str(sev).strip()
    return s if s else None


def _go_time_from_ms(ms: int) -> str:
    """
    FaultManager alert history in this lab expects Go-style layout:
      "2006-01-02T15:04:05"
    (no timezone suffix, no fractional seconds)
    """
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _extract_device_ip(resource: str) -> Optional[str]:
    """
    Try to extract device_ip=... from resource strings like:
      /App/Component/Asset/Device?device_ip=10.13.9.66
    """
    if not resource:
        return None
    m = re.search(r"(?:\?|&)(?:device_ip|ip)=([0-9]{1,3}(?:\.[0-9]{1,3}){3})", resource)
    if m:
        return m.group(1)
    return None


def _slim_alarm(rec: dict) -> dict:
    return {
        "timestamp": _pick_first(rec, ["Timestamp", "timestamp", "LastRaised", "lastRaised", "TimeCreated", "timeCreated", "created", "createdAt"]),
        "severity": _get_severity(rec),
        "name": _pick_first(rec, ["name", "Name", "alarmName", "alarm_name"]),
        "alarm_id": _pick_first(rec, ["alarm_id", "alarmId", "AlarmId", "id"]),
        "alarm_type": _pick_first(rec, ["alarm_type", "alarmType", "AlarmType"]),
        "resource": _pick_first(rec, ["resource", "Resource"]),
        "message": _pick_first(rec, ["message", "Message", "description", "Description", "detail", "Detail"]),
        "state": {
            "unacked": _pick_first(rec, ["unacked"]),
            "acked": _pick_first(rec, ["acked"]),
            "cleared": _pick_first(rec, ["cleared"]),
            "closed": _pick_first(rec, ["closed"]),
        },
    }


def _slim_alert(rec: dict) -> dict:
    return {
        "timestamp": _pick_first(rec, ["Timestamp", "timestamp", "TimeCreated", "timeCreated", "created", "createdAt"]),
        "severity": _pick_first(rec, ["severity", "Severity"]),
        "alert_id": _pick_first(rec, ["alert_id", "alertId", "AlertId", "id"]),
        "resource": _pick_first(rec, ["resource", "Resource"]),
        "message": _pick_first(rec, ["message", "Message", "description", "Description", "detail", "Detail"]),
    }


# -----------------------------
# Tool #18
# -----------------------------

def fault_get_alarm_details_with_context(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2 composite: fault_get_alarm_details_with_context (SAFE_READ)

    Uses ONLY existing Tier-1 tools:
      - faultmanager_get_alarm_history
      - faultmanager_get_alarm_inventory(detail=true)
      - faultmanager_get_alert_history
      - monitor_get_health_detail
      - tenant_get_event_history_list (only when device_ip can be derived)
    """

    inputs = inputs or {}

    name = _norm_str(inputs.get("name"))
    alarm_id = inputs.get("alarm_id")
    resource = _norm_str(inputs.get("resource"))

    active_only = _as_bool(inputs.get("active_only"), True)
    window_hours = _as_int(inputs.get("window_hours"), 24)
    window_hours = max(1, min(window_hours, 24 * 30))

    max_instances = _as_int(inputs.get("max_instances"), 20)
    max_instances = max(1, min(max_instances, 200))

    alert_limit = _as_int(inputs.get("alert_limit"), 100)
    alert_limit = max(1, min(alert_limit, 500))

    top_resources = _as_int(inputs.get("top_resources"), 3)
    top_resources = max(1, min(top_resources, 10))

    include_inventory = _as_bool(inputs.get("include_inventory"), True)
    include_alerts = _as_bool(inputs.get("include_alerts"), True)
    include_health = _as_bool(inputs.get("include_health"), True)
    include_tenant_events = _as_bool(inputs.get("include_tenant_events"), True)
    include_raw = _as_bool(inputs.get("include_raw"), False)

    tier1_raw: Dict[str, Any] = {}
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

    # -------------------------
    # 1) Alarm inventory detail (what it is)
    # -------------------------
    inventory_detail = None
    suggested_alarm_names: List[str] = []

    if include_inventory and (alarm_id is not None or name is not None or resource is not None):
        inv_params: Dict[str, Any] = {"detail": True}
        if alarm_id is not None:
            inv_params["alarm_id"] = alarm_id
        if name:
            inv_params["name"] = name
        if resource:
            inv_params["resource"] = resource

        inv_res = call_tier1("faultmanager_get_alarm_inventory", inv_params)
        if include_raw:
            tier1_raw["faultmanager_get_alarm_inventory"] = inv_res

        if inv_res.get("status") == 200:
            inv_recs = _extract_records(inv_res.get("payload"))
            if inv_recs:
                inventory_detail = inv_recs[0]
        else:
            warnings.append(f"faultmanager_get_alarm_inventory returned status={inv_res.get('status')} (continuing)")

    # -------------------------
    # 2) Alarm instances (what it impacts)
    # -------------------------
    hist_params: Dict[str, Any] = {}
    if name:
        hist_params["name"] = name
    if alarm_id is not None:
        hist_params["alarm_id"] = alarm_id
    if resource:
        hist_params["resource"] = resource

    if active_only:
        hist_params.update({"unacked": True, "acked": False, "cleared": False, "closed": False})

    hist_res = call_tier1("faultmanager_get_alarm_history", hist_params)
    if include_raw:
        tier1_raw["faultmanager_get_alarm_history"] = hist_res

    if hist_res.get("status") != 200:
        payload = {
            "error": "Tier-1 faultmanager_get_alarm_history failed",
            "tier1_status": {"faultmanager_get_alarm_history": hist_res.get("status")},
            "tier1_error": hist_res.get("error"),
            "next_actions": [
                {"action": "retry", "hint": "Try invoking faultmanager_get_alarm_history directly to inspect backend response."}
            ],
        }
        if include_raw:
            payload["tier1_raw"] = tier1_raw
        return {"status": 502, "payload": payload}

    alarm_recs = _extract_records(hist_res.get("payload"))[:max_instances]

    # If user provided name but got nothing: suggest names from inventory list (substring)
    if name and not alarm_recs:
        inv_list_res = call_tier1("faultmanager_get_alarm_inventory", {"detail": False})
        if include_raw:
            tier1_raw["faultmanager_get_alarm_inventory_list"] = inv_list_res

        if inv_list_res.get("status") == 200:
            inv_list = _extract_records(inv_list_res.get("payload"))
            needle = name.lower()
            for r in inv_list:
                nm = _pick_first(r, ["name", "Name", "alarmName", "alarm_name"])
                if isinstance(nm, str) and needle in nm.lower():
                    suggested_alarm_names.append(nm.strip())
                if len(suggested_alarm_names) >= 20:
                    break

        return {
            "status": 404,
            "payload": {
                "error": "Alarm not found (no matching alarm instances)",
                "name": name,
                "alarm_id": alarm_id,
                "resource": resource,
                "suggested_alarm_names": suggested_alarm_names,
                "next_actions": [
                    {"action": "retry", "hint": "Retry with exact alarm name from suggested_alarm_names."},
                    {"action": "retry", "hint": "Or provide resource to scope the search."}
                ],
                **({"tier1_raw": tier1_raw} if include_raw else {}),
            },
        }

    # Collect impacted resources
    res_counter = Counter()
    for r in alarm_recs:
        rr = _pick_first(r, ["resource", "Resource"])
        if isinstance(rr, str) and rr.strip():
            res_counter[rr.strip()] += 1

    top_res = [r for r, _ in res_counter.most_common(top_resources)]

    # -------------------------
    # 3) Related recent alerts (context / events)
    # -------------------------
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    after_ms = now_ms - window_hours * 3600 * 1000

    related_alerts: List[dict] = []
    if include_alerts and top_res:
        for rsrc in top_res:
            a_params = {
                "resource": rsrc,
                "after_timestamp": _go_time_from_ms(after_ms),
                "before_timestamp": _go_time_from_ms(now_ms),
                "limit": alert_limit,
            }
            a_res = call_tier1("faultmanager_get_alert_history", a_params)
            if include_raw:
                tier1_raw.setdefault("faultmanager_get_alert_history", []).append({rsrc: a_res})

            if a_res.get("status") == 200:
                for ar in _extract_records(a_res.get("payload")):
                    related_alerts.append(_slim_alert(ar))
            else:
                warnings.append(f"faultmanager_get_alert_history status={a_res.get('status')} for resource={rsrc}")

        def _alert_sort_key(x: dict) -> int:
            ms = _parse_ts_to_ms(x.get("timestamp"))
            return ms or 0

        related_alerts.sort(key=_alert_sort_key, reverse=True)
        related_alerts = related_alerts[:alert_limit]

    # -------------------------
    # 4) Resource health detail
    # -------------------------
    resource_health: Dict[str, Any] = {}
    if include_health and top_res:
        for rsrc in top_res:
            h_res = call_tier1("monitor_get_health_detail", {"resource": rsrc})
            if include_raw:
                tier1_raw.setdefault("monitor_get_health_detail", []).append({rsrc: h_res})

            if h_res.get("status") == 200:
                resource_health[rsrc] = h_res.get("payload")
            else:
                resource_health[rsrc] = {"error": h_res.get("error"), "status": h_res.get("status")}

    # -------------------------
    # 5) Optional tenant events (when device_ip can be derived)
    # -------------------------
    tenant_events: Dict[str, Any] = {}
    if include_tenant_events and top_res:
        ips: List[str] = []
        for rsrc in top_res:
            ip = _extract_device_ip(rsrc)
            if ip and ip not in ips:
                ips.append(ip)

        for ip in ips[:3]:
            e_res = call_tier1("tenant_get_event_history_list", {"device_ip": ip})
            if include_raw:
                tier1_raw.setdefault("tenant_get_event_history_list", []).append({ip: e_res})

            if e_res.get("status") == 200:
                tenant_events[ip] = e_res.get("payload")
            else:
                tenant_events[ip] = {"error": e_res.get("error"), "status": e_res.get("status")}

        if not ips:
            warnings.append("No device_ip could be derived from resource strings; tenant events not included.")

    # -------------------------
    # Build response
    # -------------------------
    slim_alarms = [_slim_alarm(a) for a in alarm_recs]

    resolved_name = name
    if not resolved_name and slim_alarms:
        n0 = slim_alarms[0].get("name")
        if isinstance(n0, str) and n0.strip():
            resolved_name = n0.strip()

    # ---- NEW: summary + explanation
    health_ok = 0
    health_err = 0
    if include_health and resource_health:
        for v in resource_health.values():
            if isinstance(v, dict) and ("error" in v and v.get("error")):
                health_err += 1
            else:
                health_ok += 1

    summary = {
        "alarm_instances": len(slim_alarms),
        "top_resources_count": len(top_res),
        "related_alerts_count": len(related_alerts) if include_alerts else 0,
        "health_resources_ok": health_ok if include_health else 0,
        "health_resources_error": health_err if include_health else 0,
        "tenant_events_device_ips": list(tenant_events.keys()) if include_tenant_events else [],
    }

    explanation = (
        f"{resolved_name or 'Alarm'} has {len(slim_alarms)} active instance(s) "
        f"across {len(top_res)} resource(s). "
        f"Found {summary['related_alerts_count']} related alert(s) in the last {window_hours}h. "
        f"Health fetched for {health_ok + health_err} resource(s)."
    )

    payload = {
        "input_echo": {
            "name": name,
            "alarm_id": alarm_id,
            "resource": resource,
            "active_only": active_only,
            "window_hours": window_hours,
            "max_instances": max_instances,
            "alert_limit": alert_limit,
            "top_resources": top_resources,
            "include_inventory": include_inventory,
            "include_alerts": include_alerts,
            "include_health": include_health,
            "include_tenant_events": include_tenant_events,
        },
        "resolved": {
            "resolved_name": resolved_name,
            "instance_count": len(slim_alarms),
            "top_resources": top_res,
        },
        "summary": summary,            # <-- NEW
        "explanation": explanation,    # <-- NEW
        "alarm_inventory_detail": inventory_detail,
        "alarm_instances": slim_alarms,
        "related_alerts": related_alerts,
        "resource_health": resource_health,
        "tenant_events_by_device_ip": tenant_events,
        "warnings": warnings,
        "next_actions": next_actions
        or [
            {"action": "drilldown", "hint": "Use faultmanager_get_alarm_history with resource/name filters to narrow or expand scope."},
            {"action": "drilldown", "hint": "Use monitor_get_health_detail(resource) directly for deeper health detail on a specific resource."},
        ],
    }

    if include_raw:
        payload["tier1_raw"] = tier1_raw

    return {"status": 200, "payload": payload}

