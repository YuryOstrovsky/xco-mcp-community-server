# tools/inventory/software_version_mismatch.py

from typing import Any, Dict, List, Optional, Tuple
from collections import Counter, defaultdict


def inventory_get_software_version_mismatch(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
) -> dict:
    """
    Tier-2 composite tool: inventory_get_software_version_mismatch

    Composite Tier-1 calls used (must exist in mcp_tools.json):
      - fabric_get_fabrics
      - inventory_getswitches (called per fabric-id)

    Semantics:
      - If reference="group": outliers are switches not on the group's dominant version.
      - If reference="global": outliers are switches not on the environment's global dominant version.
      - Default reference:
          * global scan with group_by=fabric (no fabric_name) => reference="global" (Use-case B)
          * otherwise => reference="group" (Use-case A/C)

    Adds:
      - payload.headline: human-friendly sentence summarizing the scan result.
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
            for k in ("items", "data", "switches", "result", "payload"):
                v = payload.get(k)
                if isinstance(v, list):
                    return v
        return []

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
            # Normalize to {status,payload,error}
            if isinstance(resp, dict) and "status" in resp and "payload" in resp:
                return resp
            return {"status": 200, "payload": resp, "error": None}
        except Exception as e:
            return {"status": 0, "payload": None, "error": str(e)}

    # -------------------------
    # Inputs / defaults
    # -------------------------
    inobj = inputs or {}

    fabric_name = _norm_str(inobj.get("fabric_name"))
    group_by = (_norm_str(inobj.get("group_by")) or "fabric").lower()

    include_outliers = _as_bool(inobj.get("include_outliers"), True)
    outlier_limit = max(1, min(_as_int(inobj.get("outlier_limit"), 20), 200))
    min_group_size = max(1, min(_as_int(inobj.get("min_group_size"), 2), 1000))
    include_raw = _as_bool(inobj.get("include_raw"), False)

    reference = (_norm_str(inobj.get("reference")) or "").lower()
    if reference not in ("", "group", "global"):
        return {
            "status": 400,
            "payload": {
                "filter": {"fabric_name": fabric_name, "group_by": group_by, "reference": reference},
                "error": "Invalid reference. Must be one of: group, global.",
            },
        }

    allowed_group_by = {"fabric", "role", "model", "global"}
    if group_by not in allowed_group_by:
        return {
            "status": 400,
            "payload": {
                "filter": {"fabric_name": fabric_name, "group_by": group_by, "reference": reference or None},
                "error": f"Invalid group_by '{group_by}'. Allowed: {sorted(list(allowed_group_by))}",
            },
        }

    # Default reference behavior aligned with your use-cases:
    # Use-case B: {} + group_by=fabric => compare to GLOBAL dominant.
    # Use-case A/C: fabric-specific or role/model => compare to GROUP dominant.
    if reference == "":
        if (fabric_name is None) and (group_by == "fabric"):
            reference = "global"
        else:
            reference = "group"

    filt = {
        "fabric_name": fabric_name,
        "group_by": group_by,
        "reference": reference,
        "include_outliers": include_outliers,
        "outlier_limit": outlier_limit,
        "min_group_size": min_group_size,
        "include_raw": include_raw,
    }

    # -------------------------
    # 1) Get fabrics
    # -------------------------
    fabrics_res = call_tier1("fabric_get_fabrics", {})
    if fabrics_res.get("status") != 200:
        return {"status": 502, "payload": {"filter": filt, "error": "Failed to list fabrics", "tier1": fabrics_res}}

    fabrics_payload = fabrics_res.get("payload")
    fabrics_list = _as_list(fabrics_payload)

    fabrics: List[Tuple[str, str]] = []
    for f in fabrics_list:
        if not isinstance(f, dict):
            continue
        name = _norm_str(_pick_first(f, ["name", "fabric_name", "fabric-name"]))
        fid = _pick_first(f, ["id", "fabric_id", "fabric-id"])
        if name and fid is not None:
            fabrics.append((name, str(fid)))

    if fabric_name:
        match = [(n, fid) for (n, fid) in fabrics if n.lower() == fabric_name.lower()]
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
    # 2) Fetch ALL switches ONCE to avoid cross-join double-counting
    # -------------------------
    # BUG FIX: Previously called inventory_getswitches per fabric with fabric-id,
    # but XCO returns ALL switches regardless when switches are unassigned,
    # causing N_fabrics × N_switches double-counting.
    all_switches: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # Build fabric-id -> name lookup
    fid_to_fname: Dict[str, str] = {fid: fname for (fname, fid) in fabrics}
    fname_lower_to_entry: Dict[str, Tuple[str, str]] = {
        fname.lower(): (fname, fid) for (fname, fid) in fabrics
    }

    def _resolve_switch_fabric(sw: dict) -> Optional[Tuple[str, str]]:
        """Return (fabric_name, fabric_id) from switch record, or None."""
        fab = sw.get("fabric")
        if isinstance(fab, dict):
            sw_fid = _pick_first(fab, ["fabric-id", "fabric_id", "id"])
            if sw_fid is not None and str(sw_fid) in fid_to_fname:
                fid_s = str(sw_fid)
                return (fid_to_fname[fid_s], fid_s)
            sw_fn = _norm_str(_pick_first(fab, ["fabric-name", "fabric_name", "name", "fabric"]))
            if sw_fn and sw_fn.lower() in fname_lower_to_entry:
                return fname_lower_to_entry[sw_fn.lower()]
        sw_fid = _pick_first(sw, ["fabric-id", "fabric_id", "fabricId"])
        if sw_fid is not None and str(sw_fid) in fid_to_fname:
            fid_s = str(sw_fid)
            return (fid_to_fname[fid_s], fid_s)
        sw_fn = _norm_str(_pick_first(sw, ["fabric", "fabric_name", "fabric-name", "fabricName"]))
        if sw_fn and sw_fn.lower() in fname_lower_to_entry:
            return fname_lower_to_entry[sw_fn.lower()]
        return None

    inv_res = call_tier1("inventory_getswitches", {})
    if inv_res.get("status") != 200:
        warnings.append(f"Failed to fetch switches: {inv_res.get('error')}")
    else:
        sw_items = _as_list(inv_res.get("payload"))
        seen_ids: set = set()
        unassigned_count = 0
        for sw in sw_items:
            if not isinstance(sw, dict):
                continue

            sw_id = _pick_first(sw, ["id", "device_id"])
            sid_key = str(sw_id) if sw_id is not None else id(sw)
            if sid_key in seen_ids:
                continue
            seen_ids.add(sid_key)

            membership = _resolve_switch_fabric(sw)
            if membership is None:
                fname_resolved = "unassigned"
                fid_resolved = None
                unassigned_count += 1
            else:
                fname_resolved, fid_resolved = membership

            sw_firmware = _norm_str(_pick_first(sw, ["firmware", "software_version", "sw_version", "version"]))
            sw_name = _norm_str(_pick_first(sw, ["name", "hostname"]))
            sw_role = _norm_str(_pick_first(sw, ["role"]))
            sw_model = _norm_str(_pick_first(sw, ["model"]))
            sw_ip = _norm_str(_pick_first(sw, ["ip_address", "ip"]))

            all_switches.append(
                {
                    "fabric_name": fname_resolved,
                    "fabric_id": fid_resolved,
                    "id": str(sw_id) if sw_id is not None else None,
                    "name": sw_name,
                    "role": sw_role,
                    "model": sw_model,
                    "ip": sw_ip,
                    "firmware": sw_firmware,
                    "_raw": sw if include_raw else None,
                }
            )
        if unassigned_count:
            warnings.append(
                f"{unassigned_count} switch(es) not assigned to any fabric "
                f"(shown in 'unassigned' group)."
            )

    switches_scanned = len(all_switches)

    # -------------------------
    # 3) Global version stats
    # -------------------------
    global_versions = Counter()
    missing_version_count = 0
    missing_fabric_count = 0

    for sw in all_switches:
        if not sw.get("fabric_name"):
            missing_fabric_count += 1
        v = sw.get("firmware")
        if not v:
            missing_version_count += 1
        else:
            global_versions[v] += 1

    global_dominant_version = global_versions.most_common(1)[0][0] if len(global_versions) else None

    # -------------------------
    # 4) Grouping and mismatches
    # -------------------------
    def _group_key(sw: Dict[str, Any]) -> Tuple[str, ...]:
        if group_by == "global":
            return ("global",)
        if group_by == "fabric":
            return (sw.get("fabric_name") or "unknown_fabric",)
        if group_by == "role":
            return (sw.get("fabric_name") or "unknown_fabric", sw.get("role") or "unknown_role")
        if group_by == "model":
            return (sw.get("fabric_name") or "unknown_fabric", sw.get("model") or "unknown_model")
        return ("global",)

    groups_map: Dict[Tuple[str, ...], List[Dict[str, Any]]] = defaultdict(list)
    for sw in all_switches:
        groups_map[_group_key(sw)].append(sw)

    groups_out: List[Dict[str, Any]] = []
    groups_scanned = 0
    groups_with_mismatch = 0

    for gk, items in groups_map.items():
        if len(items) < min_group_size:
            continue

        groups_scanned += 1
        versions = Counter()
        missing_in_group = 0
        for sw in items:
            v = sw.get("firmware")
            if not v:
                missing_in_group += 1
            else:
                versions[v] += 1

        uniq_versions = list(versions.keys())
        group_dominant_version = versions.most_common(1)[0][0] if len(versions) else None

        # Determine which version to compare against
        reference_version = global_dominant_version if reference == "global" else group_dominant_version

        # mismatch meaning depends on reference:
        if reference_version:
            mismatch = any((sw.get("firmware") and sw.get("firmware") != reference_version) for sw in items)
        else:
            mismatch = len(versions) > 1  # fallback if we literally have no version data

        if mismatch:
            groups_with_mismatch += 1

        outliers: List[Dict[str, Any]] = []
        if include_outliers:
            for sw in items:
                v = sw.get("firmware")

                if reference_version:
                    is_outlier = (not v) or (v != reference_version)
                else:
                    is_outlier = (not v) or (len(versions) > 1)

                if not is_outlier:
                    continue

                outliers.append(
                    {
                        "id": sw.get("id"),
                        "name": sw.get("name"),
                        "role": sw.get("role"),
                        "model": sw.get("model"),
                        "ip": sw.get("ip"),
                        "firmware": sw.get("firmware"),
                        "reason": "missing_version" if not v else "non_reference_version",
                    }
                )
                if len(outliers) >= outlier_limit:
                    break

        group_obj: Dict[str, Any] = {
            "group_by": group_by,
            "key": list(gk),
            "switches": len(items),
            "missing_version": missing_in_group,
            "versions": dict(versions),
            "unique_versions": uniq_versions,
            "group_dominant_version": group_dominant_version,
            "reference": reference,
            "reference_version": reference_version,
            "mismatch": mismatch,
        }
        if include_outliers:
            group_obj["outliers"] = outliers

        groups_out.append(group_obj)

    # Sort: mismatches first, then larger groups
    groups_out.sort(key=lambda g: (not g.get("mismatch", False), -(g.get("switches", 0))))

    # -------------------------
    # 5) Headline + Recommendations
    # -------------------------
    headline: Optional[str] = None
    if switches_scanned == 0:
        headline = "No switches were scanned."
    elif global_dominant_version and len(global_versions) == 1:
        headline = f"All {switches_scanned} switches are on {global_dominant_version} — no mismatches detected."
    elif global_dominant_version:
        headline = f"Global dominant version is {global_dominant_version}; mismatches detected in {groups_with_mismatch} group(s)."
    else:
        headline = "Switches were scanned, but no firmware/version values were found."

    recommendations: List[str] = []
    if switches_scanned == 0:
        recommendations.append(
            "No switches were retrieved. Verify inventory_getswitches returns devices and fabrics exist in fabric_get_fabrics."
        )
    else:
        if global_dominant_version:
            recommendations.append(f"Global dominant firmware/version is '{global_dominant_version}'.")
        if groups_with_mismatch > 0:
            recommendations.append(
                "Firmware mismatches detected. Consider standardizing versions (same role/model typically expected to match)."
            )
        if missing_version_count > 0:
            recommendations.append("Some switches are missing firmware/version. Investigate inventory completeness.")

    payload: Dict[str, Any] = {
        "filter": filt,
        "headline": headline,
        "summary": {
            "switches_scanned": switches_scanned,
            "groups_scanned": groups_scanned,
            "groups_with_mismatch": groups_with_mismatch,
            "global_versions": dict(global_versions),
            "global_dominant_version": global_dominant_version,
            "unique_versions_global": list(global_versions.keys()),
            "missing_version_count": missing_version_count,
            "missing_fabric_count": missing_fabric_count,
        },
        "groups": groups_out,
        "signals": {"warnings": warnings},
        "recommendations": recommendations,
        "next_actions": [],
    }

    if include_raw and switches_scanned > 0:
        payload["raw_sample"] = [s.get("_raw") for s in all_switches[:3]]

    return {"status": 200, "payload": payload}

