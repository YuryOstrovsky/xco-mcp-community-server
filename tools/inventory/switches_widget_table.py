from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple


# ------------------------------------------------------------
# Small helpers (match style of your other Tier-2 composites)
# ------------------------------------------------------------

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


def _extract_records(payload: Any) -> List[dict]:
    """
    Best-effort extraction for Tier-1 payloads that may be list/dict/nested.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        # common containers
        for k in ("items", "data", "result", "payload", "switches", "devices", "fabrics"):
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        # fallback: first list value
        for v in payload.values():
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _pick_first(d: Dict[str, Any], keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


def _canon_health(v: Any) -> Optional[str]:
    """
    Normalize health-ish fields to what the UI can use consistently.
    We keep strings like Green/Red/Yellow, but also accept 'healthy'/'unhealthy'.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).strip()
    if not s:
        return None
    s_l = s.lower()
    if s_l in ("green", "ok", "healthy", "good", "up"):
        return "Green"
    if s_l in ("yellow", "warning", "degraded", "minor"):
        return "Yellow"
    if s_l in ("red", "critical", "down", "bad", "unhealthy", "major"):
        return "Red"
    return s  # unknown labels kept as-is


def _list_to_csv_str(v: Any) -> Optional[str]:
    """
    Some Tier-1 tools in your catalog use 'device_ips' as a STRING (csv),
    not an array. Accept both and normalize to csv.
    """
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, list):
        parts = [str(x).strip() for x in v if str(x).strip()]
        return ",".join(parts) if parts else None
    s = str(v).strip()
    return s if s else None


# ------------------------------------------------------------
# Tier-2 Composite: inventory_get_switches_widget_table
# ------------------------------------------------------------

def inventory_get_switches_widget_table(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Build a widget-friendly switches table:
      - base list from inventory_getswitches
      - optional health/status from inventory_switch_inventory_summary
      - optional discovery interval/reason from inventory_get_device_details
      - optional fabric filter (fabric_name -> fabric_id via fabric_get_fabrics)

    Output is optimized for a UI widget (flat rows, stable keys).
    """
    inputs = inputs or {}
    warnings: List[str] = []
    tier1_raw: Dict[str, Any] = {}

    include_raw = _as_bool(inputs.get("include_raw"), False)

    # Filters / options
    fabric_name = _norm_str(inputs.get("fabric_name"))
    device_type = _norm_str(inputs.get("device_type"))  # passed to inventory_getswitches if provided
    max_items = _as_int(inputs.get("max_items"), 200)
    max_items = max(1, min(max_items, 5000))

    # Enrichment toggles
    include_status = _as_bool(inputs.get("include_status"), True)
    include_device_details = _as_bool(inputs.get("include_device_details"), False)

    # Optional explicit device filter
    device_ips_in = inputs.get("device_ips")
    device_ips_csv = _list_to_csv_str(device_ips_in)

    # -------------------------
    # Tier-1 caller
    # -------------------------
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
    # 1) Resolve fabric_name -> fabric_id (optional)
    # -------------------------
    fabric_id: Optional[int] = None
    if fabric_name:
        r_fabs = call_tier1("fabric_get_fabrics", {})
        if include_raw:
            tier1_raw["fabric_get_fabrics"] = r_fabs

        if int(r_fabs.get("status") or 0) == 200:
            fabs = _extract_records(r_fabs.get("payload"))

            def _fab_name(f: dict) -> Optional[str]:
                return _norm_str(
                    _pick_first(
                        f,
                        ("fabric_name", "fabricName", "name", "fabric", "Fabric", "display_name", "displayName"),
                    )
                )

            def _fab_id(f: dict) -> Optional[int]:
                v = _pick_first(f, ("fabric_id", "fabricId", "id", "Id"))
                try:
                    return int(v) if v is not None else None
                except Exception:
                    return None

            match = None
            for f in fabs:
                n = _fab_name(f)
                if n and n.lower() == fabric_name.lower():
                    match = f
                    break

            if match:
                fabric_id = _fab_id(match)
                if fabric_id is None:
                    warnings.append(f"fabric '{fabric_name}' matched but no fabric_id field found; returning all fabrics")
            else:
                warnings.append(f"fabric_name '{fabric_name}' not found via fabric_get_fabrics; returning all fabrics")
        else:
            warnings.append(f"fabric_get_fabrics returned {r_fabs.get('status')}; returning all fabrics")

    # -------------------------
    # 2) Base switches list (inventory_getswitches)
    # -------------------------
    params_sw: Dict[str, Any] = {}
    if fabric_id is not None:
        # Tier-1 schema uses 'fabric-id'
        params_sw["fabric-id"] = fabric_id
    if device_type:
        params_sw["device_type"] = device_type
    # inventory_getswitches schema supports 'id' too, but we keep widget wide.

    r_sw = call_tier1("inventory_getswitches", params_sw)
    if include_raw:
        tier1_raw["inventory_getswitches"] = r_sw

    if int(r_sw.get("status") or 0) != 200:
        return {
            "input_echo": {
                "fabric_name": fabric_name,
                "device_type": device_type,
                "device_ips": device_ips_in,
                "max_items": max_items,
                "include_status": include_status,
                "include_device_details": include_device_details,
                "include_raw": include_raw,
            },
            "summary": {
                "count": 0,
                "by_fabric": {},
                "by_role": {},
                "signals": {
                    "switches_ok": False,
                    "status_enriched": False,
                    "details_enriched": False,
                    "summary_enriched": False,
                },
            },
            "items": [],
            "warnings": [f"inventory_getswitches returned {r_sw.get('status')}"] + warnings,
            **({"tier1_raw": tier1_raw} if include_raw else {}),
        }

    switches = _extract_records(r_sw.get("payload"))

    # Optional device_ips filter (client-side)
    if device_ips_csv:
        wanted = {x.strip() for x in device_ips_csv.split(",") if x.strip()}
        if wanted:
            switches = [s for s in switches if _norm_str(_pick_first(s, ("ip_address", "ip", "management_ip", "device_ip"))) in wanted]

    # Convert to flat widget rows
    def _row_from_switch(s: dict) -> dict:
        fab = s.get("fabric") or {}
        fab_name = None
        if isinstance(fab, dict):
            fab_name = _norm_str(_pick_first(fab, ("fabric_name", "name", "fabric")))
        if not fab_name:
            fab_name = _norm_str(_pick_first(s, ("fabric", "fabric_name", "fabricName")))

        return {
            "name": _norm_str(_pick_first(s, ("name", "switch_name", "device_name"))) or "",
            "fabric": fab_name or "default",
            "role": _norm_str(_pick_first(s, ("role", "device_role"))) or "",
            "ip_address": _norm_str(_pick_first(s, ("ip_address", "ip", "management_ip", "mgmt_ip", "device_ip"))) or "",
            "device_type": _norm_str(_pick_first(s, ("device_type", "type", "deviceType"))) or "",
            "model": _norm_str(_pick_first(s, ("model", "chassis_name", "chassisName"))) or "",
            "firmware": _norm_str(_pick_first(s, ("firmware", "software", "software_version", "sw_version"))) or "",
            "health": "disabled",  # overwritten if include_status succeeds
            "discovery_status": _norm_str(_pick_first(s, ("discovery_status", "discoveryStatus"))) or "",
            "last_discovery_time": _norm_str(_pick_first(s, ("last_discovery_time", "lastDiscoveryTime"))) or "",
            "discovery_interval": _pick_first(s, ("discovery_interval", "discoveryInterval")),
            "discovery_reason": _pick_first(s, ("discovery_reason", "discoveryReason")),
            "id": _pick_first(s, ("id", "device_id", "deviceId")),
            "mac_address": _norm_str(_pick_first(s, ("mac_address", "mac", "macAddress"))) or "",
        }

    items: List[dict] = [_row_from_switch(s) for s in switches]
    # local truncate (UI)
    items = items[:max_items]

    # Build fast lookup keys
    by_ip: Dict[str, dict] = {it["ip_address"]: it for it in items if it.get("ip_address")}
    by_id: Dict[Any, dict] = {it.get("id"): it for it in items if it.get("id") is not None}
    by_name: Dict[str, dict] = {it["name"].lower(): it for it in items if it.get("name")}

    # -------------------------
    # 3) Enrich health/status (inventory_switch_inventory_summary)
    # -------------------------
    status_enriched = False
    if include_status:
        r_sum = call_tier1("inventory_switch_inventory_summary", {})
        if include_raw:
            tier1_raw["inventory_switch_inventory_summary"] = r_sum

        if int(r_sum.get("status") or 0) == 200:
            recs = _extract_records(r_sum.get("payload"))

            merged = 0
            for r in recs:
                rid = _pick_first(r, ("device_id", "deviceId", "id"))
                rip = _norm_str(_pick_first(r, ("ip_address", "ip", "management_ip", "mgmt_ip", "device_ip")))
                rname = _norm_str(_pick_first(r, ("name", "device_name", "switch_name")))

                target = None
                if rid is not None and rid in by_id:
                    target = by_id[rid]
                elif rip and rip in by_ip:
                    target = by_ip[rip]
                elif rname and rname.lower() in by_name:
                    target = by_name[rname.lower()]

                if not target:
                    continue

                # health-ish
                hv = _pick_first(r, ("health", "device_health", "switch_health", "overall_health", "status"))
                h = _canon_health(hv)
                if h:
                    target["health"] = h

                # also allow firmware/model overrides if present (best-effort)
                fw = _norm_str(_pick_first(r, ("firmware", "software_version", "software", "sw_version")))
                if fw and not target.get("firmware"):
                    target["firmware"] = fw

                mdl = _norm_str(_pick_first(r, ("model", "chassis", "chassis_name")))
                if mdl and (not target.get("model") or target["model"] == ""):
                    target["model"] = mdl

                merged += 1

            status_enriched = merged > 0
        else:
            warnings.append(f"inventory_switch_inventory_summary returned {r_sum.get('status')}; health will be 'disabled'")

    # -------------------------
    # 4) Enrich discovery interval/reason (inventory_get_device_details)
    # -------------------------
    details_enriched = False
    if include_device_details:
        # Tier-1 schema says device_ips is a STRING; accept list and send csv.
        params_dd: Dict[str, Any] = {}
        if fabric_name:
            params_dd["fabric_name"] = fabric_name
        ips_csv = _list_to_csv_str([it["ip_address"] for it in items if it.get("ip_address")])
        if ips_csv:
            params_dd["device_ips"] = ips_csv

        r_dd = call_tier1("inventory_get_device_details", params_dd)
        if include_raw:
            tier1_raw["inventory_get_device_details"] = r_dd

        if int(r_dd.get("status") or 0) == 200:
            recs = _extract_records(r_dd.get("payload"))

            merged = 0
            for r in recs:
                rip = _norm_str(_pick_first(r, ("ip_address", "ip", "device_ip", "management_ip", "mgmt_ip")))
                if not rip:
                    continue
                target = by_ip.get(rip)
                if not target:
                    continue

                di = _pick_first(r, ("discovery_interval", "discoveryInterval", "interval"))
                dr = _pick_first(r, ("discovery_reason", "discoveryReason", "reason"))

                # Only set if we got something meaningful
                if di is not None:
                    target["discovery_interval"] = di
                if dr is not None:
                    target["discovery_reason"] = dr

                merged += 1

            details_enriched = merged > 0
        else:
            warnings.append(f"inventory_get_device_details returned {r_dd.get('status')}")

    # -------------------------
    # 5) Summary breakdowns
    # -------------------------
    by_fabric_counts: Dict[str, int] = {}
    by_role_counts: Dict[str, int] = {}
    for it in items:
        f = it.get("fabric") or "default"
        r = it.get("role") or "unknown"
        by_fabric_counts[str(f)] = by_fabric_counts.get(str(f), 0) + 1
        by_role_counts[str(r)] = by_role_counts.get(str(r), 0) + 1

    out = {
        "input_echo": {
            "fabric_name": fabric_name,
            "device_type": device_type,
            "device_ips": device_ips_in,
            "max_items": max_items,
            "include_status": include_status,
            "include_device_details": include_device_details,
            "include_raw": include_raw,
        },
        "summary": {
            "count": len(items),
            "by_fabric": by_fabric_counts,
            "by_role": by_role_counts,
            "signals": {
                "switches_ok": True,
                "status_enriched": bool(include_status and status_enriched),
                "details_enriched": bool(include_device_details and details_enriched),
                "summary_enriched": False,  # reserved for future
            },
        },
        "items": items,
        "warnings": warnings,
    }
    if include_raw:
        out["tier1_raw"] = tier1_raw
    return out

