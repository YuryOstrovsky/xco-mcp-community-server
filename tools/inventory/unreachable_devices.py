# Copyright 2025 Extreme Networks, Inc.
# SPDX-License-Identifier: Apache-2.0
# tools/inventory/unreachable_devices.py

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Conservative "down/unreachable" keywords
_DOWN_KEYWORDS = (
    "unreachable",
    "not reachable",
    "offline",
    "is down",
    " down",            # space prefix to reduce false positives
    " link down",
    "connection lost",
    "lost connection",
    "no response",
    "timeout",
    "timed out",
    "disconnected",
    "failed to connect",
    "not responding",
)

MAX_RETURN_DEVICES = 2000


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


def _as_list(payload: Any) -> List[Any]:
    """
    Best-effort list extraction from many possible wrapper shapes:
      - list => itself
      - dict with known keys (items/data/Alarms/Alerts/etc)
      - dict with exactly one key whose value is a list
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        # Common wrapper keys (including XCO FaultManager capitalized keys)
        for k in (
            "items", "data", "result", "payload",
            "switches",
            "alarms", "Alarms",
            "alerts", "Alerts",
        ):
            v = payload.get(k)
            if isinstance(v, list):
                return v

        # If dict contains a single list value under unknown key
        list_values = [v for v in payload.values() if isinstance(v, list)]
        if len(list_values) == 1:
            return list_values[0]

    return []


def _find_first_ip(text: str) -> Optional[str]:
    if not text:
        return None
    m = _IP_RE.search(text)
    return m.group(0) if m else None


def _looks_down(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in _DOWN_KEYWORDS)


def _coerce_ts(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    try:
        if isinstance(v, (int, float)):
            if v > 10**12:  # millis
                v = v / 1000.0
            import datetime as _dt
            return _dt.datetime.utcfromtimestamp(float(v)).isoformat() + "Z"
    except Exception:
        return None
    return None


def _compact_device(d: Dict[str, Any]) -> Dict[str, Any]:
    dev_id = _pick_first(d, ["id", "device_id", "device-id", "switch-id", "switch_id"])
    hostname = _pick_first(d, ["hostname", "host-name", "host_name", "name", "device-name", "device_name"])
    role = _pick_first(d, ["role", "node-role", "node_role", "device-role", "device_role"])
    model = _pick_first(d, ["model", "platform", "product", "device-model", "device_model"])
    ip = _pick_first(d, ["ip", "ip_address", "ip-address", "mgmt_ip", "management_ip", "management-ip"])
    return {
        "id": str(dev_id) if dev_id is not None else None,
        "hostname": hostname,
        "role": role,
        "model": model,
        "ip": ip,
    }


def inventory_get_unreachable_devices(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
) -> dict:
    """
    Tier-2 composite: inventory_get_unreachable_devices

    Tier-1 tools used (must exist already):
      - fabric_get_fabrics
      - inventory_getswitches
      - faultmanager_get_alarm_history
      - faultmanager_get_alert_history

    Reachability signal:
      - Uses active-ish alarms/alerts and matches "down/unreachable" keywords.
      - If no signal is available (no records), mark devices as 'unknown'.
    """

    inobj = inputs or {}
    fabric_name = _norm_str(inobj.get("fabric_name"))
    group_by = (_norm_str(inobj.get("group_by")) or "fabric").lower()
    unreachable_only = _as_bool(inobj.get("unreachable_only"), True)
    include_alarms = _as_bool(inobj.get("include_alarms"), False)
    alarm_limit = max(1, min(_as_int(inobj.get("alarm_limit"), 3), 20))
    include_raw = _as_bool(inobj.get("include_raw"), False)

    allowed_group_by = {"fabric", "role"}
    if group_by not in allowed_group_by:
        return {
            "status": 400,
            "payload": {
                "filter": {"fabric_name": fabric_name, "group_by": group_by},
                "error": f"Invalid group_by '{group_by}'. Allowed: {sorted(list(allowed_group_by))}",
            },
        }

    filt = {
        "fabric_name": fabric_name,
        "group_by": group_by,
        "unreachable_only": unreachable_only,
        "include_alarms": include_alarms,
        "alarm_limit": alarm_limit,
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

    # 1) fabrics
    fabrics_res = call_tier1("fabric_get_fabrics", {})
    if include_raw:
        raw["fabric_get_fabrics"] = fabrics_res
    if fabrics_res.get("status") != 200:
        return {
            "status": 502,
            "payload": {
                "filter": filt,
                "error": "Failed to list fabrics (fabric_get_fabrics)",
                "tier1": {"fabric_get_fabrics": fabrics_res},
            },
        }

    fabrics_list = _as_list(fabrics_res.get("payload"))
    fabrics: List[Tuple[str, str]] = []
    for f in fabrics_list:
        if not isinstance(f, dict):
            continue
        n = _norm_str(_pick_first(f, ["name", "fabric_name", "fabric-name"]))
        fid = _pick_first(f, ["id", "fabric_id", "fabric-id"])
        if n and fid is not None:
            fabrics.append((n, str(fid)))

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

    # 2) Fetch ALL devices ONCE to avoid cross-join double-counting
    # BUG FIX: Previously called inventory_getswitches per fabric with fabric-id,
    # but XCO returns ALL switches regardless when switches are unassigned,
    # causing N_fabrics × N_switches double-counting.
    devices: List[Dict[str, Any]] = []
    per_fabric_errors = 0

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
    if include_raw:
        raw["inventory_getswitches"] = inv_res
    if inv_res.get("status") != 200:
        per_fabric_errors += 1
        warnings.append(f"Failed to fetch switches: {inv_res.get('error')}")
    else:
        sw_items = _as_list(inv_res.get("payload"))
        seen_ids: set = set()
        unassigned_count = 0
        for sw in sw_items:
            if not isinstance(sw, dict):
                continue
            sid = _pick_first(sw, ["id", "device_id"])
            sid_key = str(sid) if sid is not None else id(sw)
            if sid_key in seen_ids:
                continue
            seen_ids.add(sid_key)

            membership = _resolve_switch_fabric(sw)
            if membership is None:
                # Include unassigned devices so they're visible
                row = _compact_device(sw)
                row["fabric_name"] = "unassigned"
                row["fabric_id"] = None
                devices.append(row)
                unassigned_count += 1
                continue
            fname_resolved, fid_resolved = membership
            # If filtering to specific fabrics, skip non-matching
            if fname_resolved not in fid_to_fname.values():
                continue
            row = _compact_device(sw)
            row["fabric_name"] = fname_resolved
            row["fabric_id"] = fid_resolved
            devices.append(row)
        if unassigned_count:
            warnings.append(
                f"{unassigned_count} switch(es) not assigned to any fabric "
                f"(shown in 'unassigned' group)."
            )

    devices_scanned = len(devices)
    fabrics_scanned = len(fabrics)

    if devices_scanned == 0:
        return {
            "status": 200,
            "payload": {
                "filter": filt,
                "signals": {
                    "fabrics_scanned": fabrics_scanned,
                    "devices_scanned": 0,
                    "reachability_source": "none",
                    "truncated": False,
                    "inventory_partial_failures": per_fabric_errors,
                },
                "counts": {"unreachable": 0, "reachable": 0, "unknown": 0},
                "groups": [],
                "warnings": warnings + ["No devices returned from inventory_getswitches (nothing to classify)."],
                "next_actions": next_actions,
                **({"raw": raw} if include_raw else {}),
            },
        }

    by_id: Dict[str, Dict[str, Any]] = {}
    by_ip: Dict[str, Dict[str, Any]] = {}
    by_host: Dict[str, Dict[str, Any]] = {}
    for d in devices:
        if d.get("id"):
            by_id[str(d["id"])] = d
        if d.get("ip"):
            by_ip[str(d["ip"])] = d
        if d.get("hostname"):
            by_host[str(d["hostname"]).lower()] = d

    # 3) alarms + alerts (bulk), with fallback
    alarm_params = {"cleared": False, "closed": False}
    alarms_res = call_tier1("faultmanager_get_alarm_history", alarm_params)
    if include_raw:
        raw["faultmanager_get_alarm_history_filtered"] = alarms_res

    alarms_ok = alarms_res.get("status") == 200
    alarm_records = _as_list(alarms_res.get("payload")) if alarms_ok else []

    # Fallback: if filtered returns empty but endpoint works, retry unfiltered
    if alarms_ok and len(alarm_records) == 0:
        alarms_res2 = call_tier1("faultmanager_get_alarm_history", {})
        if include_raw:
            raw["faultmanager_get_alarm_history_unfiltered"] = alarms_res2
        if alarms_res2.get("status") == 200:
            alarm_records = _as_list(alarms_res2.get("payload"))

    alerts_res = call_tier1("faultmanager_get_alert_history", {})
    if include_raw:
        raw["faultmanager_get_alert_history"] = alerts_res
    alerts_ok = alerts_res.get("status") == 200
    alert_records = _as_list(alerts_res.get("payload")) if alerts_ok else []

    if not alarms_ok:
        warnings.append("Unable to fetch faultmanager alarm history; alarms-based reachability may be incomplete.")
    if not alerts_ok:
        warnings.append("Unable to fetch faultmanager alert history; alerts-based reachability may be incomplete.")

    combined_records: List[Tuple[str, Dict[str, Any]]] = []
    for r in alarm_records:
        if isinstance(r, dict):
            combined_records.append(("alarm", r))
    for r in alert_records:
        if isinstance(r, dict):
            combined_records.append(("alert", r))

    has_reach_signal = len(combined_records) > 0

    if not has_reach_signal:
        warnings.append("FaultManager returned 0 alarms/alerts; reachability cannot be inferred. Marking devices as 'unknown'.")
        next_actions.append({"reason": "Inspect alarms (raw)", "tool": "faultmanager_get_alarm_history", "inputs": {}})
        next_actions.append({"reason": "Inspect alerts (raw)", "tool": "faultmanager_get_alert_history", "inputs": {}})

    # device_id -> snippets
    signals_by_device_id: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    unmapped_signal_count = 0
    down_signal_count = 0

    if has_reach_signal:
        for src, rec in combined_records:
            name = _norm_str(_pick_first(rec, ["name", "alarm_name", "alarm-name", "title"]))
            typ = _norm_str(_pick_first(rec, ["alarm_type", "alarm-type", "type"]))
            detail = _norm_str(_pick_first(rec, ["detail", "message", "description", "text", "reason"]))
            severity = _norm_str(_pick_first(rec, ["severity", "level", "priority"]))
            ts = _coerce_ts(_pick_first(rec, ["timestamp", "time", "created", "created_at", "raised", "raised_at", "date"]))

            blob = " ".join([x for x in [name, typ, detail] if x])
            if not _looks_down(blob):
                continue

            down_signal_count += 1

            dev_id = _pick_first(rec, ["device_id", "deviceId", "switch_id", "switchId", "node_id", "nodeId"])
            key: Optional[str] = None

            if dev_id is not None and str(dev_id) in by_id:
                key = str(dev_id)
            else:
                rid = _pick_first(rec, ["resource_id", "resourceId", "entity_id", "entityId"])
                if rid is not None and str(rid) in by_id:
                    key = str(rid)
                else:
                    ip = _norm_str(_pick_first(rec, ["device_ip", "deviceIp", "ip", "ip_address", "ip-address"]))
                    if ip and ip in by_ip:
                        key = str(by_ip[ip]["id"])
                    else:
                        ip2 = _find_first_ip(detail or "") or _find_first_ip(name or "") or _find_first_ip(blob)
                        if ip2 and ip2 in by_ip:
                            key = str(by_ip[ip2]["id"])
                        else:
                            hn = _norm_str(_pick_first(rec, ["hostname", "host_name", "device_name", "device-name"]))
                            if hn and hn.lower() in by_host:
                                key = str(by_host[hn.lower()]["id"])

            if not key:
                unmapped_signal_count += 1
                continue

            signals_by_device_id[key].append(
                {
                    "source": src,
                    "timestamp": ts,
                    "severity": severity,
                    "name": name or typ,
                    "detail": detail,
                }
            )

        for _, lst in signals_by_device_id.items():
            lst.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    # 4) classify + detail list
    unreachable_total = 0
    reachable_total = 0
    unknown_total = 0
    detailed_devices: List[Dict[str, Any]] = []

    for d in devices:
        did = d.get("id")
        reach = "unknown"
        last_seen = None
        last_error = None
        snips: List[Dict[str, Any]] = []

        if has_reach_signal:
            if did and str(did) in signals_by_device_id:
                reach = "unreachable"
                snips = signals_by_device_id[str(did)][:alarm_limit]
                unreachable_total += 1
                if snips:
                    last_seen = snips[0].get("timestamp")
                    last_error = snips[0].get("detail") or snips[0].get("name")
            else:
                reach = "reachable"
                reachable_total += 1
        else:
            unknown_total += 1

        if unreachable_only and reach != "unreachable":
            continue

        out = dict(d)
        out["reachability"] = reach
        if last_seen:
            out["last_seen"] = last_seen
        if last_error:
            out["last_error"] = last_error
        if include_alarms and snips:
            out["alarms"] = snips

        detailed_devices.append(out)

    # 5) rollups always
    base_group_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"devices_total": 0, "unreachable": 0})

    if group_by == "fabric":
        for d in devices:
            g = d.get("fabric_name") or "unknown_fabric"
            base_group_counts[g]["devices_total"] += 1
        if has_reach_signal:
            for did in signals_by_device_id.keys():
                dev = by_id.get(str(did))
                if dev:
                    g = dev.get("fabric_name") or "unknown_fabric"
                    base_group_counts[g]["unreachable"] += 1
    else:
        for d in devices:
            g = d.get("role") or "unknown_role"
            base_group_counts[g]["devices_total"] += 1
        if has_reach_signal:
            for did in signals_by_device_id.keys():
                dev = by_id.get(str(did))
                if dev:
                    g = dev.get("role") or "unknown_role"
                    base_group_counts[g]["unreachable"] += 1

    groups_devices_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for x in detailed_devices:
        g = (x.get("fabric_name") or "unknown_fabric") if group_by == "fabric" else (x.get("role") or "unknown_role")
        groups_devices_map[g].append(x)

    groups_out: List[Dict[str, Any]] = []
    for gname, cnts in base_group_counts.items():
        groups_out.append(
            {
                "group": {"fabric": gname} if group_by == "fabric" else {"role": gname},
                "devices_total": cnts["devices_total"],
                "unreachable_count": cnts["unreachable"],
                "devices": groups_devices_map.get(gname, []),
            }
        )

    groups_out.sort(
        key=lambda g: (g.get("unreachable_count", 0), g.get("devices_total", 0), str(g.get("group"))),
        reverse=True,
    )

    # 6) truncation
    truncated = False
    total_return = sum(len(g.get("devices", [])) for g in groups_out)
    if total_return > MAX_RETURN_DEVICES:
        truncated = True
        warnings.append(f"Response truncated (>{MAX_RETURN_DEVICES} devices). Use fabric_name filter to narrow.")
        next_actions.append({"reason": "Filter by fabric", "tool": "inventory_get_unreachable_devices", "inputs": {"fabric_name": "DC"}})

        per_group_cap = max(1, MAX_RETURN_DEVICES // max(1, len(groups_out)))
        for g in groups_out:
            devs = g.get("devices") or []
            if len(devs) > per_group_cap:
                g["devices"] = devs[:per_group_cap]

    reachability_source = "faultmanager alarms+alerts (heuristic match)" if has_reach_signal else "none"

    payload = {
        "filter": filt,
        "signals": {
            "fabrics_scanned": len(fabrics),
            "devices_scanned": devices_scanned,
            "alarm_records_scanned": len(alarm_records) if alarms_ok else None,
            "alert_records_scanned": len(alert_records) if alerts_ok else None,
            "down_signals_matched": down_signal_count if has_reach_signal else 0,
            "unmapped_signal_count": unmapped_signal_count if has_reach_signal else None,
            "reachability_source": reachability_source,
            "truncated": truncated,
            "inventory_partial_failures": per_fabric_errors,
        },
        "counts": {
            "unreachable": unreachable_total if has_reach_signal else 0,
            "reachable": reachable_total if has_reach_signal else 0,
            "unknown": unknown_total if not has_reach_signal else 0,
        },
        "groups": groups_out,
        "warnings": warnings,
        "next_actions": next_actions,
    }

    if include_raw:
        payload["raw"] = raw

    return {"status": 200, "payload": payload}

