# tools/faultmanager/fabric_health_related_alerts.py

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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


def _go_time_from_ms(ms: int) -> str:
    # matches your lab behavior for alert history
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _lower_text(rec: dict) -> str:
    parts: List[str] = []
    for k, v in rec.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            parts.append(f"{k}={v}")
    return " ".join(parts).lower()


def _classify_signal(text_lc: str) -> str:
    restored_terms = (
        "restored", "recovered", "healthy", "up", "cleared", "resolved", "success", "stabilized"
    )
    degraded_terms = (
        "degraded", "down", "failure", "failed", "error", "unreachable", "timeout", "loss", "unstable"
    )
    if any(t in text_lc for t in restored_terms):
        return "restored"
    if any(t in text_lc for t in degraded_terms):
        return "degraded"
    return "other"


def _slim_alert(rec: dict) -> dict:
    return {
        "timestamp": rec.get("Timestamp") or rec.get("timestamp") or rec.get("TimeCreated") or rec.get("timeCreated") or rec.get("created") or rec.get("createdAt"),
        "severity": rec.get("severity") or rec.get("Severity"),
        "alert_id": rec.get("alert_id") or rec.get("alertId") or rec.get("AlertId") or rec.get("id"),
        "resource": rec.get("resource") or rec.get("Resource"),
        "message": rec.get("message") or rec.get("Message") or rec.get("description") or rec.get("Description") or rec.get("detail") or rec.get("Detail"),
    }


def _walk(obj: Any):
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _extract_records(payload: Any) -> List[dict]:
    # find first list of dicts anywhere
    for node in _walk(payload):
        if isinstance(node, list) and any(isinstance(x, dict) for x in node):
            return [x for x in node if isinstance(x, dict)]
    return []


def _extract_fabric_names_from_fabrics_payload(payload: Any) -> List[str]:
    """
    Best-effort extraction of fabric names from fabric_get_fabrics payload.
    (Your lab seems to have a shape we don't parse reliably, so this may return empty.)
    """
    names: List[str] = []
    seen = set()

    def add(n: Any):
        if isinstance(n, str):
            s = n.strip()
            if s and s not in seen:
                names.append(s)
                seen.add(s)

    # Try scanning dicts for likely keys
    for node in _walk(payload):
        if isinstance(node, dict):
            add(node.get("name"))
            add(node.get("fabric_name"))
            add(node.get("fabricName"))

    # Fallback: try list-of-records and same keys
    if not names:
        recs = _extract_records(payload)
        for r in recs:
            add(r.get("name") or r.get("fabric_name") or r.get("fabricName"))

    return names


_FABRIC_RESOURCE_RE = re.compile(r"/App/Component/Fabric\?[^ ]*fabric_name=([^&\s]+)", re.IGNORECASE)


def _extract_fabric_names_from_alert_resources(alert_records: List[dict]) -> List[str]:
    """
    Extract fabric_name values from alert 'resource' strings.
    Example resource:
      /App/Component/Fabric?fabric_name=DC
    """
    names: List[str] = []
    seen = set()
    for rec in alert_records:
        rsrc = rec.get("resource") or rec.get("Resource")
        if not isinstance(rsrc, str):
            continue
        m = _FABRIC_RESOURCE_RE.search(rsrc)
        if not m:
            continue
        name = m.group(1).strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def fault_get_fabric_health_related_alerts(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2 composite: fault_get_fabric_health_related_alerts (SAFE_READ)

    Uses ONLY existing Tier-1 tools:
      - fabric_get_fabrics (validate + suggestions when parseable)
      - faultmanager_get_alert_history (resource + time window; plus validation-only unscoped discovery fallback)
    """

    inputs = inputs or {}
    fabric_name = _norm_str(inputs.get("fabric_name"))
    if not fabric_name:
        return {"status": 400, "payload": {"error": "fabric_name is required"}}

    window_hours = max(1, min(_as_int(inputs.get("window_hours"), 24), 24 * 30))
    max_records = max(1, min(_as_int(inputs.get("max_records"), 200), 1000))
    alert_limit = max(1, min(_as_int(inputs.get("alert_limit"), 300), 1000))

    severity = _norm_str(inputs.get("severity"))
    signal = _norm_str(inputs.get("signal"))
    if signal:
        signal = signal.lower()
        if signal not in ("restored", "degraded"):
            return {"status": 400, "payload": {"error": "signal must be 'restored' or 'degraded'"}}

    include_other = _as_bool(inputs.get("include_other"), False)
    include_raw = _as_bool(inputs.get("include_raw"), False)

    tier1_raw: Dict[str, Any] = {}
    warnings: List[str] = []

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
    # 1) Validate fabric_name (strict if we can)
    # -------------------------
    fabrics_res = call_tier1("fabric_get_fabrics", {})
    if include_raw:
        tier1_raw["fabric_get_fabrics"] = fabrics_res

    fabric_names: List[str] = []
    if fabrics_res.get("status") == 200:
        fabric_names = _extract_fabric_names_from_fabrics_payload(fabrics_res.get("payload"))

    # If fabric_get_fabrics isn't parseable, do discovery via alert resources (validation-only)
    if not fabric_names:
        # Use a bigger lookback ONLY for validation/discovery (does not affect returned results)
        validation_hours = max(window_hours, 720)  # 30 days, capped by alert_limit
        now_ms_v = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        after_ms_v = now_ms_v - validation_hours * 3600 * 1000

        discover_params: Dict[str, Any] = {
            "after_timestamp": _go_time_from_ms(after_ms_v),
            "before_timestamp": _go_time_from_ms(now_ms_v),
            "limit": alert_limit,
        }
        # Do NOT apply severity to discovery; we want any fabric resource hits
        discover_res = call_tier1("faultmanager_get_alert_history", discover_params)
        if include_raw:
            tier1_raw["faultmanager_get_alert_history_discovery"] = discover_res

        if discover_res.get("status") == 200:
            discover_recs = _extract_records(discover_res.get("payload"))
            fabric_names = _extract_fabric_names_from_alert_resources(discover_recs)

        if fabric_names:
            warnings.append("Fabric validation derived from alert resource discovery (fabric_get_fabrics payload not parseable).")
        else:
            warnings.append("Could not validate fabric_name (no fabric list extractable from fabric_get_fabrics; no fabric resources discovered in alert history). Continuing without strict validation.")

    # If we have any known fabrics, enforce strict validation now
    if fabric_names and (fabric_name not in fabric_names):
        needle = fabric_name.lower()
        subs = [x for x in fabric_names if needle in x.lower()]
        return {
            "status": 404,
            "payload": {
                "error": "Fabric not found",
                "fabric_name": fabric_name,
                "suggested_fabrics": subs[:20] or fabric_names[:20],
                "next_actions": [{"action": "retry", "hint": "Pick a fabric_name from suggested_fabrics and retry."}],
                **({"tier1_raw": tier1_raw} if include_raw else {}),
            },
        }

    # -------------------------
    # 2) Fetch alerts (resource-scoped first; fallback unscoped+filter)
    # -------------------------
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    after_ms = now_ms - window_hours * 3600 * 1000

    fabric_resource = f"/App/Component/Fabric?fabric_name={fabric_name}"
    fabric_resource_lc = fabric_resource.lower()

    a_params_scoped: Dict[str, Any] = {
        "resource": fabric_resource,
        "after_timestamp": _go_time_from_ms(after_ms),
        "before_timestamp": _go_time_from_ms(now_ms),
        "limit": alert_limit,
    }
    if severity:
        a_params_scoped["severity"] = severity

    alerts_res_scoped = call_tier1("faultmanager_get_alert_history", a_params_scoped)
    if include_raw:
        tier1_raw["faultmanager_get_alert_history_scoped"] = alerts_res_scoped

    if alerts_res_scoped.get("status") != 200:
        payload = {
            "error": "Tier-1 faultmanager_get_alert_history failed",
            "fabric_name": fabric_name,
            "resource": fabric_resource,
            "tier1_status": {"faultmanager_get_alert_history": alerts_res_scoped.get("status")},
            "tier1_error": alerts_res_scoped.get("error"),
            "warnings": warnings,
            "next_actions": [{"action": "retry", "hint": "Invoke faultmanager_get_alert_history directly with the same params to inspect backend response."}],
        }
        if include_raw:
            payload["tier1_raw"] = tier1_raw
        return {"status": 502, "payload": payload}

    scoped_alerts = _extract_records(alerts_res_scoped.get("payload"))
    used_mode = "resource_scoped"
    all_alerts = scoped_alerts

    if len(scoped_alerts) == 0:
        used_mode = "fallback_unscoped_filtered"
        a_params_unscoped: Dict[str, Any] = {
            "after_timestamp": _go_time_from_ms(after_ms),
            "before_timestamp": _go_time_from_ms(now_ms),
            "limit": alert_limit,
        }
        if severity:
            a_params_unscoped["severity"] = severity

        alerts_res_unscoped = call_tier1("faultmanager_get_alert_history", a_params_unscoped)
        if include_raw:
            tier1_raw["faultmanager_get_alert_history_unscoped"] = alerts_res_unscoped

        if alerts_res_unscoped.get("status") == 200:
            unscoped = _extract_records(alerts_res_unscoped.get("payload"))
            filtered = []
            for rec in unscoped:
                rsrc = rec.get("resource") or rec.get("Resource") or ""
                if isinstance(rsrc, str) and fabric_resource_lc in rsrc.lower():
                    filtered.append(rec)
            all_alerts = filtered
        else:
            warnings.append("Fallback unscoped fetch failed; returning empty result.")

    # -------------------------
    # 3) Classify
    # -------------------------
    restored: List[dict] = []
    degraded: List[dict] = []
    other: List[dict] = []
    by_severity: Dict[str, int] = {}

    for rec in all_alerts:
        txt = _lower_text(rec)
        sig = _classify_signal(txt)

        sev = rec.get("severity") or rec.get("Severity") or "unknown"
        sev_lc = str(sev).lower()
        by_severity[sev_lc] = by_severity.get(sev_lc, 0) + 1

        slim = _slim_alert(rec)
        slim["signal"] = sig

        if sig == "restored":
            restored.append(slim)
        elif sig == "degraded":
            degraded.append(slim)
        else:
            other.append(slim)

    if signal == "restored":
        selected = restored
    elif signal == "degraded":
        selected = degraded
    else:
        selected = restored + degraded + (other if include_other else [])

    selected.sort(key=lambda a: str(a.get("timestamp") or ""), reverse=True)
    selected = selected[:max_records]

    payload = {
        "input_echo": {
            "fabric_name": fabric_name,
            "window_hours": window_hours,
            "severity": severity,
            "signal": signal,
            "include_other": include_other,
            "alert_limit": alert_limit,
            "max_records": max_records,
        },
        "resource_scope": {
            "fabric_resource": fabric_resource,
            "tier1_mode_used": used_mode,
        },
        "summary": {
            "alerts_total_fetched": len(all_alerts),
            "restored": len(restored),
            "degraded": len(degraded),
            "other": len(other),
            "returned": len(selected),
            "by_severity": by_severity,
        },
        "alerts": selected,
        "warnings": warnings + ([] if (selected or restored or degraded or (include_other and other)) else [
            "No fabric-scoped alerts found in this window. This can be normal if fabric health transitions are infrequent.",
            "Try window_hours=720 (30 days) for a wider lookback.",
        ]),
        "next_actions": [
            {"action": "retry", "hint": "Use window_hours=720 (30 days) for a broader lookback."},
            {"action": "retry", "hint": "Use signal='degraded' to focus on negative transitions."},
            {"action": "retry", "hint": "Use include_other=true to include non-transition fabric alerts."},
        ],
    }

    if include_raw:
        payload["tier1_raw"] = tier1_raw

    return {"status": 200, "payload": payload}

