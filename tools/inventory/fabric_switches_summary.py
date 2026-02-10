# tools/inventory/fabric_switches_summary.py

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------
# Small safe helpers
# ---------------------------

_FORBIDDEN_KEYS = {"certificate_file", "key_file"}


def _coerce_bool(v: Any, default: bool) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "on")
    return default


def _coerce_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _pick_first(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _as_list(payload: Any) -> List[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("items", "switches", "data"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
    return []


def _truncate(items: List[Any], max_items: int) -> Tuple[List[Any], bool]:
    if max_items <= 0:
        return [], bool(items)
    if len(items) <= max_items:
        return items, False
    return items[:max_items], True


def _redact(obj: Any) -> Any:
    """Recursively remove forbidden keys from dict/list structures."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _FORBIDDEN_KEYS:
                continue
            out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _compact_switch_row(d: Dict[str, Any]) -> Dict[str, Any]:
    sid = _pick_first(d, ["id", "device_id", "device-id", "switch-id", "switch_id"])
    hostname = _pick_first(
        d, ["hostname", "host-name", "host_name", "name", "device-name", "device_name"]
    )
    serial = _pick_first(
        d, ["serial", "serial-number", "serial_number", "sn", "device-serial", "device_serial"]
    )
    model = _pick_first(d, ["model", "platform", "product", "device-model", "device_model"])
    role = _pick_first(d, ["role", "node-role", "node_role", "device-role", "device_role"])

    # Many list endpoints don't provide IP; keep it optional
    ip = _pick_first(d, ["ip", "ip_address", "ip-address", "mgmt_ip", "management_ip", "management-ip"])

    return {
        "id": str(sid) if sid is not None else None,
        "hostname": hostname,
        "serial": serial,
        "model": model,
        "role": role,
        "ip": ip,
    }


def _extract_ip(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        direct = _pick_first(
            payload, ["ip", "ip_address", "ip-address", "mgmt_ip", "management_ip", "management-ip"]
        )
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        # common nested pattern
        for k in ("management", "mgmt", "device", "switch"):
            v = payload.get(k)
            if isinstance(v, dict):
                nested = _pick_first(
                    v, ["ip", "ip_address", "ip-address", "mgmt_ip", "management_ip", "management-ip"]
                )
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return None


def inventory_get_fabric_switches_summary(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
) -> dict:
    """
    Tier-2 composite tool: inventory_get_fabric_switches_summary

    Use-cases:
      1) "What switches are in fabric DC and what's the high-level breakdown?"
         - counts + breakdown by role/model/status + compact first N list
      2) "Quick anomaly scan"
         - missing hostname/serial, duplicate IPs (when available), odd model distribution, zero switches
      3) "Drill into a few switches" (include_per_switch_summary=true)
         - best-effort per-switch detail for first N switches
         - MUST NOT leak certificate_file / key_file

    Rules:
      - Calls ONLY existing Tier-1 tools via registry (no invented endpoints).
      - SAFE_READ: redact sensitive fields.
    """

    # -------------------------------
    # Inputs (safe defaults)
    # -------------------------------
    name = inputs.get("name")
    max_items = _coerce_int(inputs.get("max_items", 200), 200)
    max_items = max(1, min(max_items, 5000))

    include_per_switch_summary = _coerce_bool(inputs.get("include_per_switch_summary"), False)
    per_switch_limit = _coerce_int(inputs.get("per_switch_limit", 5), 5)
    per_switch_limit = max(1, min(per_switch_limit, 50))

    include_raw = _coerce_bool(inputs.get("include_raw"), False)

    # Optional: allow context to provide fabric name
    if not name:
        fabric_ctx = (context or {}).get("fabric") or {}
        if isinstance(fabric_ctx, dict) and fabric_ctx.get("name"):
            name = fabric_ctx["name"]

    filt = {
        "name": name,
        "max_items": max_items,
        "include_per_switch_summary": include_per_switch_summary,
        "per_switch_limit": per_switch_limit,
        "include_raw": include_raw,
    }

    # -------------------------------
    # Helper: invoke Tier-1 by name
    # -------------------------------
    def call_tier1(tool_name: str, params: Optional[dict] = None) -> dict:
        tool = registry.get(tool_name)
        if not tool:
            return {"status": 0, "payload": None, "error": f"Tier-1 tool not found: {tool_name}"}

        endpoint = tool.get("endpoint") or {}
        path = endpoint.get("path")
        method = tool.get("method")
        if not path or not method:
            return {"status": 0, "payload": None, "error": f"Tier-1 tool missing endpoint/method: {tool_name}"}

        return transport.request(
            method=method,
            port=endpoint.get("port"),
            path=path,
            params=params or {},
            context=context or {},
        )

    # -------------------------------
    # 0) Basic input sanity
    # -------------------------------
    if not name or not str(name).strip():
        # Schema should enforce required name, but keep a safe error anyway.
        return {"status": 400, "payload": {"filter": filt, "error": "Missing required input: name"}}

    fabric_name = str(name).strip()
    warnings: List[str] = []
    recommendations: List[str] = []
    next_actions: List[dict] = []
    raw: Dict[str, Any] = {}

    # -------------------------------
    # 1) Validate fabric exists + get fabric_id
    # -------------------------------
    fabrics_res = call_tier1("fabric_get_fabrics")
    if include_raw:
        raw["fabric_get_fabrics"] = fabrics_res

    if fabrics_res.get("status") != 200:
        return {
            "status": 502,
            "payload": {
                "filter": filt,
                "error": "Failed to retrieve fabrics (fabric_get_fabrics)",
                "tier1": {"fabric_get_fabrics": fabrics_res},
            },
        }

    fabrics_list = _as_list(fabrics_res.get("payload"))
    if not fabrics_list and isinstance(fabrics_res.get("payload"), dict):
        vals = list(fabrics_res["payload"].values())
        if vals and all(isinstance(v, dict) for v in vals):
            fabrics_list = vals

    match = None
    for f in fabrics_list:
        if not isinstance(f, dict):
            continue
        f_name = _pick_first(f, ["fabric-name", "fabric_name", "name", "fabric"])
        if f_name is not None and str(f_name).strip().lower() == fabric_name.lower():
            match = f
            break

    if not match:
        return {
            "status": 404,
            "payload": {
                "filter": filt,
                "error": f"Fabric '{fabric_name}' not found",
                "signals": {"fabrics_checked": len(fabrics_list)},
                "next_actions": [
                    {"reason": "List available fabrics to find the correct fabric name.", "tool": "fabric_get_fabrics", "inputs": {}}
                ],
            },
        }

    fabric_id = _pick_first(match, ["fabric-id", "fabric_id", "id"])

    # If fabric-id not present in list row, try fabric_get_fabric(name)
    if fabric_id is None:
        fgf = call_tier1("fabric_get_fabric", {"name": fabric_name, "detail": True})
        if include_raw:
            raw["fabric_get_fabric"] = fgf
        if fgf.get("status") == 200 and isinstance(fgf.get("payload"), dict):
            fabric_id = _pick_first(fgf["payload"], ["fabric-id", "fabric_id", "id"])

    if fabric_id is None:
        warnings.append("Unable to determine fabric-id from fabric list/details; inventory list may fail if fabric-id is required.")

    # -------------------------------
    # 2) Fetch switches in fabric
    # -------------------------------
    inv_params: Dict[str, Any] = {}
    if fabric_id is not None:
        inv_params["fabric-id"] = str(fabric_id)

    switches_res = call_tier1("inventory_getswitches", inv_params)
    if include_raw:
        raw["inventory_getswitches.fabric"] = switches_res

    if switches_res.get("status") != 200:
        return {
            "status": 502,
            "payload": {
                "filter": filt,
                "error": "Failed to retrieve switches for fabric (inventory_getswitches)",
                "tier1": {"inventory_getswitches": switches_res},
                "signals": {"fabric": {"name": fabric_name, "id": str(fabric_id) if fabric_id is not None else None}},
            },
        }

    switches_all_raw = _as_list(switches_res.get("payload"))
    switches_all: List[Dict[str, Any]] = [s for s in switches_all_raw if isinstance(s, dict)]
    total = len(switches_all)

    # -------------------------------
    # 3) Compute breakdown + anomalies over ALL switches
    # -------------------------------
    roles = Counter()
    models = Counter()
    statuses = Counter()
    missing_hostname = 0
    missing_serial = 0

    ips_present = 0
    ip_values: List[str] = []

    for s in switches_all:
        hostname = _pick_first(s, ["hostname", "host-name", "host_name", "name"])
        if not hostname or not str(hostname).strip():
            missing_hostname += 1

        serial = _pick_first(s, ["serial", "serial-number", "serial_number", "sn"])
        if not serial or not str(serial).strip():
            missing_serial += 1

        role = _pick_first(s, ["role", "node-role", "node_role", "device-role", "device_role"])
        if role:
            roles[str(role)] += 1

        model = _pick_first(s, ["model", "platform", "product", "device-model", "device_model"])
        if model:
            models[str(model)] += 1

        st = _pick_first(
            s,
            ["status", "device-status", "device_status", "connection-status", "connection_status", "health"],
        )
        if st:
            statuses[str(st)] += 1

        ip = _pick_first(s, ["ip", "ip_address", "ip-address", "mgmt_ip", "management_ip", "management-ip"])
        if ip and str(ip).strip():
            ips_present += 1
            ip_values.append(str(ip).strip())

    duplicate_ips: Dict[str, int] = {}
    ip_anomalies_skipped = False
    ip_skip_reason = None

    # IMPORTANT: if list endpoint doesn't provide IP, don't produce noisy "missing_ip == total"
    if ips_present > 0:
        ip_counts = Counter(ip_values)
        duplicate_ips = {ip: c for ip, c in ip_counts.items() if c > 1}
    else:
        ip_anomalies_skipped = True
        ip_skip_reason = "Switch list payload did not include IP fields; IP anomalies computed only when IPs are available (or via drill mode)."

    odd_model_distribution = None
    if total >= 10 and models:
        top_model, top_count = models.most_common(1)[0]
        ratio = float(top_count) / float(total) if total else 0.0
        if ratio >= 0.80:
            odd_model_distribution = {
                "top_model": top_model,
                "top_count": top_count,
                "total": total,
                "ratio": round(ratio, 3),
                "note": "Single model dominates the fabric switch population (>=80%). Verify if expected.",
            }

    anomalies: Dict[str, Any] = {
        "zero_switches": (total == 0),
        "missing_hostname_count": missing_hostname,
        "missing_serial_count": missing_serial,
        "duplicate_ips": duplicate_ips,
        "ip_anomalies_skipped": ip_anomalies_skipped,
        "ip_skip_reason": ip_skip_reason,
        "odd_model_distribution": odd_model_distribution,
    }

    if total == 0:
        recommendations.append("No switches were returned for this fabric. If this fabric should have devices, confirm fabric name and fabric-id mapping.")
        next_actions.append({"reason": "Confirm fabric exists and inspect details.", "tool": "fabric_get_fabric", "inputs": {"name": fabric_name, "detail": True}})

    if missing_hostname or missing_serial:
        recommendations.append("Some switches are missing hostname and/or serial fields in the list payload. Consider drill mode to confirm identity fields.")

    # -------------------------------
    # 4) Build compact switch list (first N)
    # -------------------------------
    compact_all = [_compact_switch_row(s) for s in switches_all]
    compact_view, truncated = _truncate(compact_all, max_items)

    # -------------------------------
    # 5) Optional: drill into first N switches (best-effort)
    # -------------------------------
    drill = {"enabled": bool(include_per_switch_summary), "limit": per_switch_limit, "items": [], "notes": []}

    drill_ips: List[str] = []
    drill_missing_ip = 0
    drill_id_mismatches: List[dict] = []

    if include_per_switch_summary and per_switch_limit > 0 and switches_all:
        for s in switches_all[:per_switch_limit]:
            if not isinstance(s, dict):
                continue
            sid = _pick_first(s, ["id", "device_id", "device-id", "switch-id", "switch_id"])
            if sid is None:
                drill["notes"].append("Skipping a switch with no id/device_id field.")
                continue

            sid_str = str(sid)

            # CRITICAL: Tier-1 schema expects param name 'id' (not device_id)
            detail_res = call_tier1("inventory_getswitches", {"id": sid_str})
            if include_raw:
                raw.setdefault("inventory_getswitches.drill", []).append({"id": sid_str, "resp": detail_res})

            payload = _redact(detail_res.get("payload"))

            # Tier-1 sometimes returns {"items":[...many...]} even when called with id=.
            # In that case, extract the single switch matching sid_str.
            payload_id = None
            extracted = None

            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                for it in payload["items"]:
                    if isinstance(it, dict):
                        it_id = _pick_first(it, ["id", "device_id", "device-id"])
                        if it_id is not None and str(it_id) == sid_str:
                            extracted = it
                            break

                if extracted is not None:
                    payload = extracted
                    payload_id = sid_str
                else:
                    drill["notes"].append(
                        f"Drill: requested id {sid_str} not found in returned items list."
                    )
                    # keep payload as-is (the items list), but payload_id stays None

            elif isinstance(payload, dict):
                pid = _pick_first(payload, ["id", "device_id", "device-id"])
                if pid is not None:
                    payload_id = str(pid)

            if payload_id is not None and payload_id != sid_str:
                drill_id_mismatches.append({"requested_id": sid_str, "payload_id": payload_id})

            ip = _extract_ip(payload)
            if ip:
                drill_ips.append(ip)
            else:
                drill_missing_ip += 1

            drill["items"].append(
                {
                    "device_id": sid_str,
                    "payload_id": payload_id,
                    "status": detail_res.get("status"),
                    "payload": payload,
                    "error": detail_res.get("error"),
                }
            )


    if include_per_switch_summary:
        if drill_id_mismatches:
            anomalies["drill_id_mismatches"] = drill_id_mismatches
            recommendations.append("Drill responses returned mismatched payload.id values. This can indicate an ID mapping issue in upstream API data.")

        if drill_ips:
            ip_counts = Counter(drill_ips)
            anomalies["drill_duplicate_ips"] = {ip: c for ip, c in ip_counts.items() if c > 1}
            anomalies["drill_missing_ip_count"] = drill_missing_ip
            anomalies["ip_anomalies_source"] = "drill"

    # -------------------------------
    # Output
    # -------------------------------
    out: Dict[str, Any] = {
        "filter": filt,
        "summary": {
            "fabric": {"name": fabric_name, "id": str(fabric_id) if fabric_id is not None else None},
            "switches_total": total,
            "roles": dict(roles),
            "models": dict(models),
            "statuses": dict(statuses),
        },
        "signals": {
            "switches": {
                "count": len(compact_view),
                "items": compact_view,
                "truncated": truncated,
                "note": "Counts/breakdowns/anomalies are computed over ALL switches, even when the view is truncated.",
            },
            "anomalies": anomalies,
            "drill": drill,
            "warnings": warnings,
        },
        "recommendations": recommendations,
        "next_actions": next_actions,
    }

    if include_raw:
        out["raw"] = raw

    return {"status": 200, "payload": out}

