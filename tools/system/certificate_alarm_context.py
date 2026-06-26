from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

SEVERITY_ORDER = ["Info", "Warning", "Minor", "Major", "Critical"]
SEV_RANK = {s.lower(): i for i, s in enumerate(SEVERITY_ORDER)}


def _canon_severity(sev: Optional[str]) -> Optional[str]:
    """Normalize severity strings to canonical Title-Case labels when possible.
    Example: 'critical' -> 'Critical'
    """
    if sev is None:
        return None
    s = str(sev).strip()
    if not s:
        return None
    s_l = s.lower()
    for label in SEVERITY_ORDER:
        if label.lower() == s_l:
            return label
    return s  # keep unknown as-is


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


def _pick_first(d: Dict[str, Any], keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


def _extract_records(payload: Any) -> List[dict]:
    """Best-effort extraction for Tier-1 payloads that may be list/dict/nested."""
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


def _parse_ts_to_ms(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            n = float(v)
            if n > 1e12:
                return int(n)  # ms
            if n > 1e9:
                return int(n * 1000)  # seconds
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            # numeric
            try:
                n = float(s)
                if n > 1e12:
                    return int(n)
                if n > 1e9:
                    return int(n * 1000)
            except Exception:
                pass
            # ISO-ish
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
        (
            "Timestamp",
            "timestamp",
            "LastRaised",
            "lastRaised",
            "TimeCreated",
            "timeCreated",
            "created",
            "createdAt",
            "lastUpdated",
            "last_updated",
        ),
    )
    return _parse_ts_to_ms(v)


def _get_severity(rec: dict) -> Optional[str]:
    sev = _pick_first(rec, ("Severity", "severity", "SEVERITY"))
    return _canon_severity(sev)


def _severity_pass(sev: Optional[str], severity_min: Optional[str]) -> bool:
    if not severity_min:
        return True
    if sev is None:
        return False
    return SEV_RANK.get(sev.lower(), -1) >= SEV_RANK.get(str(severity_min).lower(), -1)


def _extract_device_ip(resource: Optional[str]) -> Optional[str]:
    if not resource:
        return None
    m = re.search(r"(?:\?|&)(?:device_ip|ip)=([0-9]{1,3}(?:\.[0-9]{1,3}){3})", resource)
    return m.group(1) if m else None


_RE_CN = re.compile(r"(?:\bCN\s*=\s*|\bCommon\s+Name\s*[:=]\s*)([^,;\n\r]+)", re.IGNORECASE)
_RE_SERIAL = re.compile(r"(?:\bserial(?:\s+number)?\s*[:=]\s*)([0-9a-fA-F:]{4,})", re.IGNORECASE)


def _extract_cn(text: str) -> Optional[str]:
    if not text:
        return None
    m = _RE_CN.search(text)
    if not m:
        return None
    cn = m.group(1).strip().strip('"\'')
    return cn if cn else None


def _extract_serial(text: str) -> Optional[str]:
    if not text:
        return None
    m = _RE_SERIAL.search(text)
    if not m:
        return None
    s = m.group(1).strip().strip('"\'')
    return s if s else None


def _slim_alarm(rec: dict) -> dict:
    return {
        "timestamp": _pick_first(
            rec,
            (
                "Timestamp",
                "timestamp",
                "LastRaised",
                "lastRaised",
                "TimeCreated",
                "timeCreated",
                "created",
                "createdAt",
            ),
        ),
        "severity": _get_severity(rec),
        "name": _pick_first(rec, ("name", "Name", "alarmName", "alarm_name")),
        "alarm_id": _pick_first(rec, ("alarm_id", "alarmId", "AlarmId", "id")),
        "alarm_type": _pick_first(rec, ("alarm_type", "alarmType", "AlarmType")),
        "resource": _pick_first(rec, ("resource", "Resource")),
        "message": _pick_first(rec, ("message", "Message", "description", "Description", "detail", "Detail")),
        "state": {
            "unacked": _pick_first(rec, ("unacked",)),
            "acked": _pick_first(rec, ("acked",)),
            "cleared": _pick_first(rec, ("cleared",)),
            "closed": _pick_first(rec, ("closed",)),
        },
    }


# ------------------------------------------------------------
# Expiry context normalization (Tier-1 monitor/inventory)
# ------------------------------------------------------------

_DATE_KEYS = (
    "expires_at",
    "expiresAt",
    "expires",
    "expiry",
    "expiry_date",
    "expiryDate",
    "expiration",
    "expiration_date",
    "expirationDate",
    "validUntil",
    "valid_until",
    "notAfter",
    "NotAfter",
    "endDate",
    "end_date",
)


def _parse_dt(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            v = float(val)
            if v > 1e12:
                v = v / 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except Exception:
            return None
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s:
        return None
    try:
        s2 = s[:-1] + "+00:00" if s.endswith("Z") else s
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _iter_dicts(obj: Any, *, depth: int = 0, max_depth: int = 6):
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v, depth=depth + 1, max_depth=max_depth)
    elif isinstance(obj, list):
        for it in obj:
            yield from _iter_dicts(it, depth=depth + 1, max_depth=max_depth)


def _extract_expiry(rec: dict) -> Optional[datetime]:
    for k in _DATE_KEYS:
        if k in rec:
            dt = _parse_dt(rec.get(k))
            if dt:
                return dt
    for v in rec.values():
        if isinstance(v, dict):
            for kk in _DATE_KEYS:
                if kk in v:
                    dt = _parse_dt(v.get(kk))
                    if dt:
                        return dt
    return None


def _best_label(rec: dict, *, source: str) -> str:
    # device context if present
    for k in ("device_ip", "deviceIP", "ip", "IP", "hostname", "deviceName", "node", "nodeName"):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            return f"{source}:{v.strip()}"
    # then cert-ish
    for k in (
        "certificateName",
        "certName",
        "commonName",
        "cn",
        "CN",
        "name",
        "certificate",
        "subject",
        "Resource",
        "resource",
    ):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            return f"{source}:{v.strip()}"
    return f"{source}:unknown"


def _normalize_expiry_records(payload: Any, *, source: str, now: datetime) -> List[dict]:
    out: List[dict] = []
    for d in _iter_dicts(payload):
        if not isinstance(d, dict):
            continue
        exp = _extract_expiry(d)
        if not exp:
            continue
        days_remaining = int((exp - now).total_seconds() / 86400)
        norm: Dict[str, Any] = {
            "source": source,
            "label": _best_label(d, source=source),
            "expires_at": exp.isoformat(),
            "days_remaining": days_remaining,
        }
        # common identity fields (best-effort)
        for k in ("device_ip", "deviceIP", "ip", "IP"):
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                norm["device_ip"] = v.strip()
                break
        for k in ("certificateName", "certName", "commonName", "cn", "CN", "name", "certificate"):
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                norm["cert_name"] = v.strip()
                break
        out.append(norm)
    return out


# ------------------------------------------------------------
# system_get_certificate_alarm_context
# ------------------------------------------------------------

def system_get_certificate_alarm_context(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """Tier-2 composite: certificate expiry alarms + "which cert" context.

    Uses ONLY existing Tier-1 tools:
      - faultmanager_get_alarm_history (current alarms)
      - monitor_get_certificate_expiry (EFA/platform cert metadata)
      - inventory_get_device_certificates_expiry (device cert metadata)
    """
    inputs = inputs or {}

    include_raw = _as_bool(inputs.get("include_raw"), False)

    # alarms inputs
    active_only = _as_bool(inputs.get("active_only"), True)
    severity_min = _norm_str(inputs.get("severity_min"))
    require_expiry_terms = _as_bool(inputs.get("require_expiry_terms"), True)
    max_alarms = _as_int(inputs.get("max_alarms"), 200)
    max_alarms = max(1, min(max_alarms, 2000))

    # expiry context inputs
    include_expiry_context = _as_bool(inputs.get("include_expiry_context"), True)
    include_efa_certs = _as_bool(inputs.get("include_efa_certs"), True)
    include_device_certs = _as_bool(inputs.get("include_device_certs"), True)

    device_ips = inputs.get("device_ips")
    fabric_name = _norm_str(inputs.get("fabric_name"))
    fabric_all = _as_bool(inputs.get("fabric_all"), False)

    warnings: List[str] = []
    tier1_raw: Dict[str, Any] = {}

    def call_tier1(tool_name: str, params: Optional[dict] = None) -> dict:
        tool = registry.get(tool_name)
        if not tool:
            return {"status": 0, "payload": None, "error": f"Tier-1 tool not found: {tool_name}"}
        endpoint = tool.get("endpoint") or {}
        path = endpoint.get("path")
        method = tool.get("method")
        if not path or not method:
            return {
                "status": 0,
                "payload": None,
                "error": f"Tier-1 tool missing endpoint/method: {tool_name}",
            }
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
    # 1) Fetch alarms (Tier-1)
    # -------------------------
    alarm_params: Dict[str, Any] = {}
    if active_only:
        alarm_params.update({"unacked": True, "acked": False, "cleared": False, "closed": False})
    # optional exact-match filters (kept for power users)
    if _norm_str(inputs.get("name")):
        alarm_params["name"] = _norm_str(inputs.get("name"))
    if inputs.get("alarm_id") is not None:
        alarm_params["alarm_id"] = inputs.get("alarm_id")
    if _norm_str(inputs.get("alarm_type")):
        alarm_params["alarm_type"] = _norm_str(inputs.get("alarm_type"))
    if _norm_str(inputs.get("resource")):
        alarm_params["resource"] = _norm_str(inputs.get("resource"))

    hist = call_tier1("faultmanager_get_alarm_history", alarm_params)
    if include_raw:
        tier1_raw["faultmanager_get_alarm_history"] = hist

    if int(hist.get("status") or 0) != 200:
        warnings.append(f"faultmanager_get_alarm_history returned {hist.get('status')}")
        return {
            "input_echo": {
                "active_only": active_only,
                "severity_min": severity_min,
                "require_expiry_terms": require_expiry_terms,
                "max_alarms": max_alarms,
                "include_expiry_context": include_expiry_context,
                "include_efa_certs": include_efa_certs,
                "include_device_certs": include_device_certs,
                "device_ips": device_ips,
                "fabric_name": fabric_name,
                "fabric_all": fabric_all,
                "include_raw": include_raw,
            },
            "summary": {
                "has_certificate_alarms": False,
                "counts": {"alarms_total_fetched": 0, "alarms_certificate": 0},
                "signals": {"expiry_context_fetched": False},
            },
            "alarms": [],
            "warnings": warnings,
            **({"tier1_raw": tier1_raw} if include_raw else {}),
        }

    alarms_all = _extract_records(hist.get("payload"))

    CERT_WORDS = ("certificate", "cert", "x509", "tls", "ssl")
    EXP_WORDS = ("expire", "expiry", "expiration", "expiring", "expired", "notafter", "validuntil")

    def is_cert_alarm(rec: dict) -> bool:
        t = _record_text(rec)
        has_cert = any(w in t for w in CERT_WORDS)
        if not has_cert:
            return False
        if require_expiry_terms:
            return any(w in t for w in EXP_WORDS)
        return True

    # filter + severity gate
    alarms_filtered: List[dict] = []
    for rec in alarms_all:
        sev = _get_severity(rec)
        if not _severity_pass(sev, severity_min):
            continue
        if not is_cert_alarm(rec):
            continue
        alarms_filtered.append(rec)

    # sort newest-first, then severity
    def sort_key(rec: dict) -> Tuple[int, int]:
        ms = _get_time_ms(rec) or 0
        sev = _get_severity(rec)
        return (ms, SEV_RANK.get(str(sev).lower(), -1))

    alarms_filtered.sort(key=sort_key, reverse=True)
    alarms_filtered = alarms_filtered[:max_alarms]

    # -------------------------
    # 2) Fetch expiry context (Tier-1)
    # -------------------------
    now = datetime.now(timezone.utc)
    efa_expiry: List[dict] = []
    dev_expiry: List[dict] = []

    if include_expiry_context and include_efa_certs:
        r = call_tier1("monitor_get_certificate_expiry", {})
        if include_raw:
            tier1_raw["monitor_get_certificate_expiry"] = r
        if int(r.get("status") or 0) == 200:
            efa_expiry = _normalize_expiry_records(r.get("payload"), source="efa", now=now)
        else:
            warnings.append(f"monitor_get_certificate_expiry returned {r.get('status')}")

    # Fallback context: keep EFA expiry sorted (soonest to expire first)
    efa_expiry_sorted: List[dict] = sorted(efa_expiry, key=lambda x: x.get("days_remaining", 10**9))

    device_scan = "disabled" if not (include_expiry_context and include_device_certs) else "unknown"
    if include_expiry_context and include_device_certs:
        params: Dict[str, Any] = {}
        if isinstance(device_ips, list) and device_ips:
            params["device_ips"] = device_ips
        if fabric_name:
            params["fabric_name"] = fabric_name
        if fabric_all:
            params["fabric-all"] = True

        r = call_tier1("inventory_get_device_certificates_expiry", params)
        if include_raw:
            tier1_raw["inventory_get_device_certificates_expiry"] = r

        if int(r.get("status") or 0) == 200:
            dev_expiry = _normalize_expiry_records(r.get("payload"), source="device", now=now)
            device_scan = "ok"
        elif int(r.get("status") or 0) == 409:
            # common lab behavior: "No devices found"
            device_scan = "skipped_no_devices"
            warnings.append("inventory_get_device_certificates_expiry: no devices found")
        else:
            warnings.append(f"inventory_get_device_certificates_expiry returned {r.get('status')}")
            device_scan = "error"

    # build light lookup indexes
    by_device_ip: Dict[str, List[dict]] = {}
    for rec in dev_expiry:
        ip = rec.get("device_ip")
        if isinstance(ip, str) and ip.strip():
            by_device_ip.setdefault(ip.strip(), []).append(rec)

    efa_by_name: Dict[str, List[dict]] = {}
    for rec in efa_expiry:
        cn = rec.get("cert_name") or rec.get("label")
        if isinstance(cn, str) and cn.strip():
            efa_by_name.setdefault(cn.strip().lower(), []).append(rec)

    def match_context(*, device_ip: Optional[str], cn: Optional[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "matches": [],
            "match_signals": {"by_device_ip": False, "by_cn": False, "fallback_efa": False},
        }
        matches: List[dict] = []

        if device_ip and device_ip in by_device_ip:
            out["match_signals"]["by_device_ip"] = True
            items = sorted(by_device_ip.get(device_ip, []), key=lambda x: x.get("days_remaining", 10**9))
            matches.extend(items[:10])

        if cn:
            cn_l = cn.lower()
            for k, vals in efa_by_name.items():
                if k == cn_l or cn_l in k or k in cn_l:
                    out["match_signals"]["by_cn"] = True
                    matches.extend(vals[:10])
                    break

        # Fallback: if the alarm has no hints and we didn't match anything,
        # attach the soonest-expiring EFA certs as likely context.
        if not matches and not device_ip and not cn and efa_expiry_sorted:
            out["match_signals"]["fallback_efa"] = True
            urgent = [x for x in efa_expiry_sorted if x.get("days_remaining", 10**9) <= 90]
            matches.extend((urgent or efa_expiry_sorted)[:5])


        # de-dupe by (source,label,expires_at)
        seen = set()
        uniq: List[dict] = []
        for m in matches:
            key = (m.get("source"), m.get("label"), m.get("expires_at"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(m)

        out["matches"] = uniq[:10]
        return out

    # -------------------------
    # 3) Build final alarm list
    # -------------------------
    alarms_out: List[dict] = []
    unique_cert_keys = set()
    sev_counts: Dict[str, int] = {s: 0 for s in SEVERITY_ORDER}

    for rec in alarms_filtered:
        slim = _slim_alarm(rec)

        sev = slim.get("severity")
        if isinstance(sev, str):
            sev_c = _canon_severity(sev)
            if sev_c and sev_c in sev_counts:
                sev_counts[sev_c] += 1
            slim["severity"] = sev_c or sev  # keep normalized for display

        resource = slim.get("resource")
        msg = slim.get("message") or ""
        name = slim.get("name") or ""
        text = " ".join([str(x) for x in (name, msg, resource) if x])

        device_ip = _extract_device_ip(resource if isinstance(resource, str) else None)
        cn = _extract_cn(text)
        serial = _extract_serial(text)

        ctx = match_context(device_ip=device_ip, cn=cn)

        slim["certificate_hint"] = {
            "device_ip": device_ip,
            "cn": cn,
            "serial": serial,
        }
        slim["certificate_context"] = ctx

        # unique grouping key
        unique_cert_keys.add((device_ip or "", (cn or "").lower(), (serial or "").lower()))

        alarms_out.append(slim)

    has_certificate_alarms = len(alarms_out) > 0
    platform_ok = not has_certificate_alarms

    summary = {
        "platform_ok": platform_ok,
        "has_certificate_alarms": has_certificate_alarms,
        "counts": {
            "alarms_total_fetched": len(alarms_all),
            "alarms_certificate": len(alarms_out),
            "unique_certificate_keys": len([k for k in unique_cert_keys if any(k)]),
        },
        "by_severity": {k: v for k, v in sev_counts.items() if v > 0},
        "signals": {
            "expiry_context_fetched": bool(include_expiry_context and (include_efa_certs or include_device_certs)),
            "efa_expiry_records": len(efa_expiry),
            "device_expiry_records": len(dev_expiry),
            "device_scan": device_scan,
        },
    }

    out = {
        "input_echo": {
            "active_only": active_only,
            "severity_min": severity_min,
            "require_expiry_terms": require_expiry_terms,
            "max_alarms": max_alarms,
            "name": _norm_str(inputs.get("name")),
            "alarm_id": inputs.get("alarm_id"),
            "alarm_type": _norm_str(inputs.get("alarm_type")),
            "resource": _norm_str(inputs.get("resource")),
            "include_expiry_context": include_expiry_context,
            "include_efa_certs": include_efa_certs,
            "include_device_certs": include_device_certs,
            "device_ips": device_ips,
            "fabric_name": fabric_name,
            "fabric_all": fabric_all,
            "include_raw": include_raw,
        },
        "summary": summary,
        "alarms": alarms_out,
        "warnings": warnings,
    }
    if include_raw:
        out["tier1_raw"] = tier1_raw
    return out

