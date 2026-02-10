# tools/inventory/device_health_rollup.py

from typing import Any, Dict, List, Optional
from collections import Counter, defaultdict


def inventory_get_device_health_rollup(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
) -> dict:
    """
    Tier-2 composite: inventory_get_device_health_rollup

    Uses ONLY these Tier-1 tools (must exist in mcp_tools.json):
      - fabric_get_fabrics
      - fabric_get_fabrics_health
      - inventory_getswitches
      - monitor_get_health_inventory

    IMPORTANT REALITY (confirmed in lab):
      - monitor_get_health_inventory(resource="device") returns a *catalog of endpoints* (strings),
        not per-device health records.
      - fabric_get_fabrics_health returns fabric-health and per-device aggregated-health (device-health list).
    """

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

    def _pick_first(d: dict, keys: List[str]) -> Any:
        for k in keys:
            if k in d and d.get(k) is not None:
                return d.get(k)
        return None

    def _as_list(payload: Any) -> List[Any]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for k in ("items", "data", "result", "payload", "fabrics", "devices", "nodes"):
                v = payload.get(k)
                if isinstance(v, list):
                    return v
        return []

    def _normalize_severity(v: Any) -> str:
        if v is None:
            return "unknown"
        s = str(v).strip().lower()
        if s in ("red", "critical", "down", "error", "failed", "severe"):
            return "red"
        if s in ("yellow", "warning", "degraded", "minor", "medium"):
            return "yellow"
        if s in ("green", "healthy", "ok", "up", "good", "normal"):
            return "green"
        return "unknown"

    def _severity_rank(sev: str) -> int:
        s = (sev or "unknown").lower()
        if s == "red":
            return 3
        if s == "yellow":
            return 2
        if s == "green":
            return 1
        return 0

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

    # -------------------------
    # Inputs
    # -------------------------
    inobj = inputs or {}
    fabric_name = _norm_str(inobj.get("fabric_name"))
    group_by = (_norm_str(inobj.get("group_by")) or "fabric").lower()
    min_severity = (_norm_str(inobj.get("min_severity")) or "yellow").lower()
    driver_limit = max(1, min(_as_int(inobj.get("driver_limit"), 10), 200))
    include_healthy = _as_bool(inobj.get("include_healthy"), False)
    health_resource = _norm_str(inobj.get("health_resource")) or "device"
    include_raw = _as_bool(inobj.get("include_raw"), False)

    allowed_group_by = {"fabric", "role", "global"}
    if group_by not in allowed_group_by:
        return {
            "status": 400,
            "payload": {
                "filter": {"fabric_name": fabric_name, "group_by": group_by},
                "error": f"Invalid group_by '{group_by}'. Allowed: {sorted(list(allowed_group_by))}",
            },
        }

    allowed_min = {"red", "yellow", "green", "unknown"}
    if min_severity not in allowed_min:
        return {
            "status": 400,
            "payload": {
                "filter": {"fabric_name": fabric_name, "min_severity": min_severity},
                "error": f"Invalid min_severity '{min_severity}'. Allowed: {sorted(list(allowed_min))}",
            },
        }

    filt = {
        "fabric_name": fabric_name,
        "group_by": group_by,
        "min_severity": min_severity,
        "driver_limit": driver_limit,
        "include_healthy": include_healthy,
        "health_resource": health_resource,
        "include_raw": include_raw,
    }

    min_rank = _severity_rank(min_severity)

    def _include_device(sev: str) -> bool:
        if include_healthy:
            return True
        return _severity_rank(sev) >= min_rank

    # -------------------------
    # 1) Fabric name <-> id map
    # -------------------------
    fabrics_res = call_tier1("fabric_get_fabrics", {})
    if fabrics_res.get("status") != 200:
        return {"status": 502, "payload": {"filter": filt, "error": "Failed to list fabrics", "tier1": fabrics_res}}

    fabrics_list = _as_list(fabrics_res.get("payload"))
    fabrics: List[Dict[str, str]] = []
    for f in fabrics_list:
        if not isinstance(f, dict):
            continue
        n = _norm_str(_pick_first(f, ["name", "fabric_name", "fabric-name"]))
        fid = _pick_first(f, ["id", "fabric_id", "fabric-id"])
        if n and fid is not None:
            fabrics.append({"name": n, "id": str(fid)})

    if fabric_name:
        match = [f for f in fabrics if f["name"].lower() == fabric_name.lower()]
        if not match:
            return {
                "status": 404,
                "payload": {
                    "filter": filt,
                    "error": f"Fabric '{fabric_name}' not found",
                    "signals": {"fabrics_checked": len(fabrics)},
                    "next_actions": [{"reason": "List available fabrics", "tool": "fabric_get_fabrics", "inputs": {}}],
                },
            }
        fabrics = match

    # -------------------------
    # 2) monitor_get_health_inventory: catalog (NOT per-device health)
    # -------------------------
    health_catalog_res = call_tier1("monitor_get_health_inventory", {"resource": health_resource})
    health_catalog = health_catalog_res.get("payload") if health_catalog_res.get("status") == 200 else None
    catalog_items = _as_list(health_catalog)
    catalog_count = len([x for x in catalog_items if isinstance(x, str)])

    # -------------------------
    # 3) fabric_get_fabrics_health: TRUE health source (fabric + per-device)
    # -------------------------
    fh_res = call_tier1("fabric_get_fabrics_health", {})
    if fh_res.get("status") != 200:
        return {"status": 502, "payload": {"filter": filt, "error": "Failed to fetch fabrics health", "tier1": fh_res}}

    fh_list = _as_list(fh_res.get("payload"))

    # fabric health by name + device health by (fabric_name, device_id)
    fabric_health_by_name: Dict[str, str] = {}
    device_health_by_fabric_and_id: Dict[tuple, Dict[str, Any]] = {}

    for fh in fh_list:
        if not isinstance(fh, dict):
            continue

        fname = _norm_str(_pick_first(fh, ["fabric-name", "fabric_name", "name", "fabricName"]))
        fid = _pick_first(fh, ["fabric-id", "fabric_id", "id"])
        fsev_raw = _pick_first(fh, ["fabric-health", "fabric_health", "health", "status", "severity", "color"])
        if fname:
            fabric_health_by_name[fname] = _normalize_severity(fsev_raw)

        dev_list = fh.get("device-health")
        if isinstance(dev_list, list):
            for d in dev_list:
                if not isinstance(d, dict):
                    continue
                did = _pick_first(d, ["device-id", "device_id", "id"])
                dip = _pick_first(d, ["device-ip", "device_ip", "ip", "ip_address"])
                role = _pick_first(d, ["role"])
                dh = d.get("device-health") if isinstance(d.get("device-health"), dict) else {}

                agg_raw = None
                if isinstance(dh, dict):
                    agg_raw = _pick_first(dh, ["aggregated-health", "aggregated_health", "health", "status", "severity"])

                sev = _normalize_severity(agg_raw)

                # best-effort "reason" (we keep it compact and safe)
                reason = None
                if isinstance(dh, dict):
                    csh = dh.get("config-state-health")
                    if isinstance(csh, dict):
                        app = csh.get("app-state")
                        if isinstance(app, dict):
                            reason = _pick_first(app, ["app-state", "state", "message"])
                        if not reason:
                            reason = _pick_first(csh, ["config-state-health", "health"])
                key = (fname or str(fid) if fid is not None else "unknown", str(did) if did is not None else "unknown")
                device_health_by_fabric_and_id[key] = {
                    "severity": sev,
                    "severity_raw": agg_raw,
                    "device_ip": dip,
                    "role": role,
                    "reason": reason,
                }

    # -------------------------
    # 4) Inventory metadata per fabric (enrichment)
    # -------------------------
    warnings: List[str] = []
    per_fabric_rollup: List[Dict[str, Any]] = []
    drivers_global: List[Dict[str, Any]] = []

    for f in fabrics:
        fname = f["name"]
        fid = f["id"]

        inv_res = call_tier1("inventory_getswitches", {"fabric-id": fid})
        if inv_res.get("status") != 200:
            warnings.append(f"Failed to fetch switches for fabric '{fname}' (id={fid}): {inv_res.get('error')}")
            continue

        sw_items = _as_list(inv_res.get("payload"))

        fabric_counts = Counter()
        role_counts = Counter()
        drivers: List[Dict[str, Any]] = []

        devices_total = 0
        for sw in sw_items:
            if not isinstance(sw, dict):
                continue
            devices_total += 1

            sid = _pick_first(sw, ["id", "device_id"])
            sid_str = str(sid) if sid is not None else None

            hostname = _norm_str(_pick_first(sw, ["name", "hostname"]))
            role = _norm_str(_pick_first(sw, ["role"])) or "unknown"
            model = _norm_str(_pick_first(sw, ["model"]))
            ip = _norm_str(_pick_first(sw, ["ip_address", "ip"]))  # may exist or not

            # Primary health: fabric_get_fabrics_health per-device aggregated-health
            sev = "unknown"
            sev_raw = None
            reason = None
            source = "fabric_get_fabrics_health"

            if sid_str is not None:
                k1 = (fname, sid_str)
                k2 = (str(int(fid)) if fid.isdigit() else fid, sid_str)  # tolerate name/id keying
                rec = device_health_by_fabric_and_id.get(k1) or device_health_by_fabric_and_id.get(k2)
                if rec:
                    sev = rec.get("severity") or "unknown"
                    sev_raw = rec.get("severity_raw")
                    reason = rec.get("reason")
                    # If ip missing from inventory, use device-ip from health list
                    if not ip and rec.get("device_ip"):
                        ip = str(rec.get("device_ip"))
                    if rec.get("role") and role == "unknown":
                        role = str(rec.get("role"))

            # Fallback only if health record not found:
            if sev == "unknown":
                inv_health_raw = _pick_first(sw, ["device_health", "health", "status"])
                sev = _normalize_severity(inv_health_raw)
                sev_raw = inv_health_raw
                source = "inventory_fallback"

            fabric_counts[sev] += 1
            role_counts[role] += 1

            if not _include_device(sev):
                continue

            dev = {
                "id": sid_str,
                "hostname": hostname,
                "role": role,
                "model": model,
                "ip": ip,
                "severity": sev,
                "severity_raw": sev_raw,
                "source": source,
                "reason": reason,
            }
            if include_raw:
                dev["_raw"] = sw

            drivers.append(dev)
            drivers_global.append({**dev, "fabric_name": fname})

        drivers.sort(key=lambda d: (-_severity_rank(d.get("severity", "unknown")), d.get("hostname") or "", d.get("id") or ""))
        drivers = drivers[:driver_limit]

        fabric_health = fabric_health_by_name.get(fname, "unknown")

        per_fabric_rollup.append(
            {
                "fabric": {"name": fname, "id": fid, "health": fabric_health},
                "devices_total": devices_total,
                "health_counts": {
                    "red": fabric_counts.get("red", 0),
                    "yellow": fabric_counts.get("yellow", 0),
                    "green": fabric_counts.get("green", 0),
                    "unknown": fabric_counts.get("unknown", 0),
                },
                "role_counts": dict(role_counts),
                "drivers": drivers,
            }
        )

    # -------------------------
    # 5) Grouping output
    # -------------------------
    groups_out: List[Dict[str, Any]] = []

    if group_by == "fabric":
        groups_out = per_fabric_rollup

    elif group_by == "role":
        by_role = defaultdict(list)
        for d in drivers_global:
            by_role[d.get("role") or "unknown"].append(d)

        for role, lst in by_role.items():
            lst.sort(key=lambda x: (-_severity_rank(x.get("severity", "unknown")), x.get("fabric_name") or "", x.get("hostname") or ""))
            groups_out.append(
                {
                    "role": role,
                    "drivers": lst[:driver_limit],
                    "health_counts": dict(Counter([x.get("severity", "unknown") for x in lst])),
                    "devices_listed": min(len(lst), driver_limit),
                }
            )

        # sort roles by worst first
        groups_out.sort(key=lambda g: (-g.get("health_counts", {}).get("red", 0), -g.get("health_counts", {}).get("yellow", 0)))

    else:  # global
        drivers_global.sort(key=lambda d: (-_severity_rank(d.get("severity", "unknown")), d.get("fabric_name") or "", d.get("hostname") or ""))
        groups_out = [
            {
                "global": True,
                "drivers": drivers_global[:driver_limit],
                "health_counts": dict(Counter([x.get("severity", "unknown") for x in drivers_global])),
            }
        ]

    fabrics_scanned = len(per_fabric_rollup)
    devices_scanned = sum(g.get("devices_total", 0) for g in per_fabric_rollup) if per_fabric_rollup else 0
    reds = sum(g.get("health_counts", {}).get("red", 0) for g in per_fabric_rollup)
    yellows = sum(g.get("health_counts", {}).get("yellow", 0) for g in per_fabric_rollup)

    if devices_scanned == 0:
        headline = "No devices were scanned."
    elif reds == 0 and yellows == 0:
        headline = f"Scanned {devices_scanned} devices across {fabrics_scanned} fabric(s): no unhealthy devices at or above '{min_severity}'."
    else:
        headline = f"Scanned {devices_scanned} devices across {fabrics_scanned} fabric(s): {reds} red, {yellows} yellow (>= '{min_severity}')."

    recommendations: List[str] = []
    if devices_scanned == 0:
        recommendations.append("No devices found. Verify inventory_getswitches returns switches for the selected fabric(s).")
    else:
        if reds > 0:
            recommendations.append("Investigate RED drivers first; they typically dominate fabric health impact.")
        if fabric_name and fabric_health_by_name.get(fabric_name) == "red":
            recommendations.append(f"Fabric '{fabric_name}' health is RED; focus on devices with aggregated-health=Red.")

    # Important: clarify what monitor_get_health_inventory actually returned
    if health_catalog_res.get("status") == 200:
        recommendations.append(
            f"monitor_get_health_inventory(resource='{health_resource}') returned a catalog of {catalog_count} endpoint templates (not per-device health)."
        )

    payload: Dict[str, Any] = {
        "filter": filt,
        "headline": headline,
        "summary": {
            "fabrics_scanned": fabrics_scanned,
            "devices_scanned": devices_scanned,
            "unhealthy_counts_global": {
                "red": reds,
                "yellow": yellows,
                "green": sum(g.get("health_counts", {}).get("green", 0) for g in per_fabric_rollup),
                "unknown": sum(g.get("health_counts", {}).get("unknown", 0) for g in per_fabric_rollup),
            },
            "health_catalog_used_resource": health_resource,
            "health_catalog_count": catalog_count,
        },
        "groups": groups_out,
        "signals": {
            "warnings": warnings,
        },
        "recommendations": recommendations,
        "next_actions": [],
    }

    # Optionally expose the catalog raw if include_raw (safe: it's just endpoint templates)
    if include_raw:
        payload["signals"]["health_catalog"] = catalog_items

    return {"status": 200, "payload": payload}

