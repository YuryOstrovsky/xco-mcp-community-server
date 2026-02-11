from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ------------------------------------------------------------
# Tier-1 call helpers (same calling convention as your Tier-2s)
# ------------------------------------------------------------
def _transport_get(*, transport, path: str, port: int | None, params: dict, context: dict) -> dict:
    return transport.request(
        method="GET",
        port=port,
        path=path,
        params=params or {},
        context=context or {},
    )


def _call_tier1(*, tool_name: str, params: dict, registry, transport, context: dict) -> dict:
    tool = registry.get(tool_name)
    if not tool:
        return {"status": 404, "payload": {"message": f"Tier-1 tool not found: {tool_name}"}}

    endpoint = tool.get("endpoint") or {}
    path = endpoint.get("path")
    if not path:
        return {"status": 500, "payload": {"message": f"Tier-1 tool missing endpoint.path: {tool_name}"}}

    port = endpoint.get("port")
    return _transport_get(transport=transport, path=path, port=port, params=params or {}, context=context)


# ------------------------------------------------------------
# Parsing / normalization
# ------------------------------------------------------------
_DATE_KEYS = (
    "expires_at", "expiresAt", "expires", "expiry", "expiry_date", "expiryDate",
    "expiration", "expiration_date", "expirationDate",
    "validUntil", "valid_until", "notAfter", "NotAfter",
    "endDate", "end_date",
)

_NAME_KEYS = (
    "name", "certificate", "certificateName", "certName", "commonName", "cn", "CN",
    "subject", "resource", "Resource",
    "device", "deviceName", "hostname", "node", "nodeName",
    "device_ip", "deviceIP", "ip", "IP",
    "serial", "serialNumber", "serial_number",
)


def _parse_dt(val: Any) -> datetime | None:
    """Best-effort parse of expiry timestamps into UTC datetime."""
    if val is None:
        return None

    # epoch seconds / ms
    if isinstance(val, (int, float)):
        try:
            v = float(val)
            # ms heuristic
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

    # ISO-ish
    try:
        # handle trailing Z
        if s.endswith("Z"):
            s2 = s[:-1] + "+00:00"
        else:
            s2 = s
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # common non-ISO patterns can be added here if needed
    return None


def _extract_expiry(rec: dict) -> datetime | None:
    for k in _DATE_KEYS:
        if k in rec:
            dt = _parse_dt(rec.get(k))
            if dt:
                return dt

    # sometimes nested
    for k, v in rec.items():
        if isinstance(v, dict):
            for kk in _DATE_KEYS:
                if kk in v:
                    dt = _parse_dt(v.get(kk))
                    if dt:
                        return dt
    return None


def _best_label(rec: dict, *, source: str) -> str:
    parts: list[str] = []

    # prefer device ip/hostname context if present
    for k in ("device_ip", "deviceIP", "ip", "IP", "hostname", "deviceName", "node", "nodeName"):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
            break

    # then cert-ish name
    for k in ("certificateName", "certName", "commonName", "cn", "CN", "name", "certificate", "subject", "Resource", "resource"):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
            break

    if not parts:
        # fallback: first useful field among known keys
        for k in _NAME_KEYS:
            v = rec.get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
                break

    if not parts:
        return f"{source}:unknown"

    if len(parts) == 1:
        return f"{source}:{parts[0]}"
    return f"{source}:{parts[0]} | {parts[1]}"


def _iter_candidate_dicts(obj: Any, *, depth: int = 0, max_depth: int = 6):
    """Yield dicts that could represent certificate records."""
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_candidate_dicts(v, depth=depth + 1, max_depth=max_depth)
    elif isinstance(obj, list):
        for it in obj:
            yield from _iter_candidate_dicts(it, depth=depth + 1, max_depth=max_depth)


def _severity(days_remaining: int) -> tuple[str, str]:
    """
    UI-ish severity buckets:
      expired / <=30 = red
      <=60 = orange
      <=90 = yellow
      else = green
    """
    if days_remaining < 0:
        return ("expired", "red")
    if days_remaining <= 30:
        return ("expiring_30", "red")
    if days_remaining <= 60:
        return ("expiring_60", "orange")
    if days_remaining <= 90:
        return ("expiring_90", "yellow")
    return ("ok", "green")


# ------------------------------------------------------------
# Tool implementation
# ------------------------------------------------------------
def system_get_certificates_expiring_soon(*, inputs: dict, registry, transport, context: dict) -> dict:
    window_days = int(inputs.get("window_days") or 90)
    include_efa = bool(inputs.get("include_efa_certs", True))
    include_dev = bool(inputs.get("include_device_certs", True))

    include_ok = bool(inputs.get("include_ok", False))
    include_raw = bool(inputs.get("include_raw", False))
    max_items = int(inputs.get("max_items") or 200)

    # passthrough filters to Tier-1 device cert expiry
    device_ips = inputs.get("device_ips")
    fabric_name = inputs.get("fabric_name")
    fabric_all = inputs.get("fabric_all")

    now = datetime.now(timezone.utc)

    warnings: list[str] = []
    tier1_raw: dict[str, Any] = {}

    records: list[dict] = []

    # optional summary signal
    device_scan = "disabled" if not include_dev else "unknown"

    # ---- EFA / platform certs (monitor) ----
    if include_efa:
        r = _call_tier1(
            tool_name="monitor_get_certificate_expiry",
            params={},
            registry=registry,
            transport=transport,
            context=context,
        )
        if include_raw:
            tier1_raw["monitor_get_certificate_expiry"] = r

        if int(r.get("status") or 0) != 200:
            warnings.append(f"monitor_get_certificate_expiry returned {r.get('status')}")
        else:
            payload = r.get("payload")
            for d in _iter_candidate_dicts(payload):
                if not isinstance(d, dict):
                    continue
                exp = _extract_expiry(d)
                if not exp:
                    continue
                rec_label = _best_label(d, source="efa")
                delta_days = int((exp - now).total_seconds() / 86400)

                bucket, color = _severity(delta_days)
                norm = {
                    "source": "efa",
                    "label": rec_label,
                    "expires_at": exp.isoformat(),
                    "days_remaining": delta_days,
                    "bucket": bucket,
                    "ui_color": color,
                }
                # keep a couple helpful identity fields if present
                for k in ("name", "certificateName", "commonName", "cn", "CN", "subject"):
                    if k in d and isinstance(d.get(k), str) and d.get(k).strip():
                        norm["cert_name"] = d.get(k).strip()
                        break
                records.append(norm)

    # ---- device certs (inventory) ----
    if include_dev:
        params: dict[str, Any] = {}
        if isinstance(device_ips, list) and device_ips:
            params["device_ips"] = device_ips
        if isinstance(fabric_name, str) and fabric_name.strip():
            params["fabric_name"] = fabric_name.strip()
        if fabric_all is True:
            params["fabric-all"] = True

        r = _call_tier1(
            tool_name="inventory_get_device_certificates_expiry",
            params=params,
            registry=registry,
            transport=transport,
            context=context,
        )
        if include_raw:
            tier1_raw["inventory_get_device_certificates_expiry"] = r

        status_code = int(r.get("status") or 0)
        payload = r.get("payload")

        if status_code != 200:
            # Common / expected lab situation: no inventory devices
            if status_code == 409 and isinstance(payload, dict) and int(payload.get("code") or 0) == 1002:
                device_scan = "skipped_no_devices"
                warnings.append(
                    "No devices found in inventory (device certificate expiry skipped). "
                    "Provide device_ips or ensure inventory has devices to enable device cert scanning."
                )
            else:
                device_scan = f"error_{status_code}" if status_code else "error"
                msg = ""
                if isinstance(payload, dict):
                    msg = str(payload.get("message") or "").strip()
                if msg:
                    warnings.append(f"inventory_get_device_certificates_expiry returned {status_code}: {msg}")
                else:
                    warnings.append(f"inventory_get_device_certificates_expiry returned {status_code}")
        else:
            device_scan = "ok"
            for d in _iter_candidate_dicts(payload):
                if not isinstance(d, dict):
                    continue
                exp = _extract_expiry(d)
                if not exp:
                    continue
                rec_label = _best_label(d, source="device")
                delta_days = int((exp - now).total_seconds() / 86400)

                bucket, color = _severity(delta_days)
                norm = {
                    "source": "device",
                    "label": rec_label,
                    "expires_at": exp.isoformat(),
                    "days_remaining": delta_days,
                    "bucket": bucket,
                    "ui_color": color,
                }
                # preserve device identity if present
                for k in ("device_ip", "deviceIP", "ip", "IP", "deviceName", "hostname", "serial", "serialNumber"):
                    v = d.get(k)
                    if isinstance(v, str) and v.strip():
                        norm.setdefault("device", v.strip())
                        break
                records.append(norm)

    # ---- de-dup (same label + same expiry) ----
    seen = set()
    uniq: list[dict] = []
    for r in records:
        key = (r.get("source"), r.get("label"), r.get("expires_at"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    # ---- filter window ----
    in_window: list[dict] = []
    for r in uniq:
        days = int(r.get("days_remaining") or 0)
        if include_ok:
            in_window.append(r)
        else:
            if days <= window_days:
                in_window.append(r)

    # sort: most urgent first
    in_window.sort(key=lambda x: int(x.get("days_remaining") or 0))

    # cap
    if max_items > 0:
        in_window = in_window[:max_items]

    # buckets for UI-like display
    buckets: dict[str, list[dict]] = {"expired": [], "expiring_30": [], "expiring_60": [], "expiring_90": [], "ok": []}
    for r in in_window:
        b = r.get("bucket") or "ok"
        if b not in buckets:
            buckets[b] = []
        buckets[b].append(r)

    summary = {
        "window_days": window_days,
        "sources": {"efa": include_efa, "device": include_dev},
        "device_scan": device_scan,
        "counts": {
            "total_records_normalized": len(uniq),
            "returned": len(in_window),
            "expired": len(buckets.get("expired", [])),
            "expiring_30": len(buckets.get("expiring_30", [])),
            "expiring_60": len(buckets.get("expiring_60", [])),
            "expiring_90": len(buckets.get("expiring_90", [])),
            "ok": len(buckets.get("ok", [])),
        },
    }

    out = {
        "input_echo": {
            "window_days": window_days,
            "include_efa_certs": include_efa,
            "include_device_certs": include_dev,
            "device_ips": device_ips if isinstance(device_ips, list) else None,
            "fabric_name": fabric_name,
            "fabric_all": bool(fabric_all),
            "max_items": max_items,
            "include_ok": include_ok,
            "include_raw": include_raw,
        },
        "summary": summary,
        "items": in_window,
        "buckets": {
            "expired": buckets.get("expired", []),
            "expiring_30": buckets.get("expiring_30", []),
            "expiring_60": buckets.get("expiring_60", []),
            "expiring_90": buckets.get("expiring_90", []),
        },
        "warnings": warnings,
    }

    if include_raw:
        out["tier1_raw"] = tier1_raw

    return out

