# tools/faultmanager/active_alarms_top.py

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


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
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in ("Alarms", "alarms", "alarm", "items", "data", "result", "payload"):
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
                return int(n)
            if n > 1e9:
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
    )
    return _parse_ts_to_ms(v)


def _get_severity(rec: dict) -> Optional[str]:
    sev = _pick_first(rec, ["Severity", "severity", "SEVERITY"])
    if sev is None:
        return None
    s = str(sev).strip()
    return s if s else None


def _severity_pass(sev: Optional[str], severity_min: Optional[str]) -> bool:
    if not severity_min:
        return True
    if sev is None:
        return False
    return SEV_RANK.get(sev.lower(), -1) >= SEV_RANK.get(severity_min.lower(), -1)


def _best_severity_from_counter(c: Counter) -> Optional[str]:
    best = None
    best_rank = -1
    for k, cnt in c.items():
        if cnt <= 0:
            continue
        r = SEV_RANK.get(str(k).lower(), -1)
        if r > best_rank:
            best_rank = r
            best = k
    return best


def fault_get_active_alarms_top(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2 composite: fault_get_active_alarms_top (SAFE_READ)

    Uses ONLY existing Tier-1 tools:
      - faultmanager_get_alarm_history  (active alarms)
      - faultmanager_get_alarm_inventory(detail=true)  (optional enrichment)

    Produces grouped/sorted top alarms with severity + top resources.
    """

    inputs = inputs or {}

    top_n = _as_int(inputs.get("top_n"), 10)
    top_n = min(max(top_n, 1), 100)

    max_records = _as_int(inputs.get("max_records"), 500)
    max_records = min(max(max_records, 1), 5000)

    severity_min = _norm_str(inputs.get("severity_min"))
    query = _norm_str(inputs.get("query"))
    alarm_type = _norm_str(inputs.get("alarm_type"))
    resource = _norm_str(inputs.get("resource"))
    resource_query = _norm_str(inputs.get("resource_query"))

    include_inventory = _as_bool(inputs.get("include_inventory"), False)
    include_samples = _as_bool(inputs.get("include_samples"), True)
    # 2026-06-18: default was 3, which silently hid
    # ~80% of fired instances even at top_n=10.  Raise the default and the cap
    # so consumers see real coverage; 0 still means "no samples, counts only".
    sample_per_group = _as_int(inputs.get("sample_per_group"), 25)
    sample_per_group = min(max(sample_per_group, 0), 200)

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
    # 1) Fetch active alarms (Tier-1)
    # -------------------------
    history_params: Dict[str, Any] = {
        "unacked": True,
        "acked": False,
        "cleared": False,
        "closed": False,
    }
    if alarm_type:
        history_params["alarm_type"] = alarm_type
    if resource:
        history_params["resource"] = resource

    hist_res = call_tier1("faultmanager_get_alarm_history", history_params)
    if include_raw:
        tier1_raw["faultmanager_get_alarm_history"] = hist_res

    if hist_res.get("status") != 200:
        payload = {
            "error": "Tier-1 faultmanager_get_alarm_history failed",
            "tier1_status": {"faultmanager_get_alarm_history": hist_res.get("status")},
            "tier1_error": hist_res.get("error"),
            "next_actions": [
                {"action": "retry", "hint": "Invoke faultmanager_get_alarm_history directly to inspect backend response."}
            ],
        }
        if include_raw:
            payload["tier1_raw"] = tier1_raw
        return {"status": 502, "payload": payload}

    alarms_all = _extract_records(hist_res.get("payload"))[:max_records]

    # -------------------------
    # 2) Optional inventory enrichment
    # -------------------------
    inv_by_id: Dict[str, dict] = {}
    inv_by_name: Dict[str, dict] = {}

    if include_inventory:
        inv_params: Dict[str, Any] = {"detail": True}
        if alarm_type:
            inv_params["alarm_type"] = alarm_type

        inv_res = call_tier1("faultmanager_get_alarm_inventory", inv_params)
        if include_raw:
            tier1_raw["faultmanager_get_alarm_inventory"] = inv_res

        if inv_res.get("status") == 200:
            inv_records = _extract_records(inv_res.get("payload"))
            for r in inv_records:
                # try id-based index
                aid = _pick_first(r, ["alarm_id", "alarmId", "id", "AlarmId", "alarmID"])
                if aid is not None:
                    inv_by_id[str(aid)] = r

                # fallback name-based index (matches your environment)
                nm = _pick_first(r, ["name", "Name", "alarmName", "alarm_name"])
                if isinstance(nm, str) and nm.strip():
                    inv_by_name[nm.strip().lower()] = r
        else:
            warnings.append(f"faultmanager_get_alarm_inventory returned status={inv_res.get('status')} (continuing without enrichment)")

    # -------------------------
    # 3) Filter + group/sort
    # -------------------------
    def alarm_resource(rec: dict) -> str:
        r = _pick_first(rec, ["resource", "Resource"])
        return r.strip() if isinstance(r, str) else ""

    def alarm_name(rec: dict) -> str:
        n = _pick_first(rec, ["name", "Name", "alarmName", "alarm_name"])
        return n.strip() if isinstance(n, str) else ""

    def alarm_id(rec: dict) -> Optional[str]:
        aid = _pick_first(rec, ["alarm_id", "alarmId", "AlarmId", "id"])
        return str(aid) if aid is not None else None

    def slim(rec: dict) -> dict:
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
                ],
            ),
            "severity": _get_severity(rec),
            "alarm_id": alarm_id(rec),
            "alarm_type": _pick_first(rec, ["alarm_type", "alarmType", "AlarmType"]),
            "name": alarm_name(rec) or None,
            "resource": alarm_resource(rec) or None,
            "message": _pick_first(rec, ["message", "Message", "description", "Description", "detail", "Detail"]),
        }

    active_filtered: List[dict] = []
    by_sev_all = Counter()
    groups: Dict[str, dict] = {}
    labels: Dict[str, dict] = {}

    for rec in alarms_all:
        sev = _get_severity(rec) or "Unknown"
        res = alarm_resource(rec)
        nm = alarm_name(rec)
        aid = alarm_id(rec)
        txt = _record_text(rec)

        # severity_min
        if sev == "Unknown":
            if severity_min:
                continue
        else:
            if not _severity_pass(sev, severity_min):
                continue

        # query filter
        if query and query.lower() not in txt:
            continue

        # resource_query substring filter
        if resource_query and resource_query.lower() not in res.lower():
            continue

        active_filtered.append(rec)
        by_sev_all[sev.lower()] += 1

        # grouping key
        key = aid if aid else (nm if nm else "unknown")

        if key not in groups:
            groups[key] = {
                "count": 0,
                "severity_counts": Counter(),
                "resource_counts": Counter(),
                "samples": [],
                "latest_ts_ms": None,
                "alarm_id": aid,
                "name": nm if nm else None,
            }

        g = groups[key]
        g["count"] += 1
        g["severity_counts"][sev] += 1
        if res:
            g["resource_counts"][res] += 1

        ts_ms = _get_time_ms(rec)
        if ts_ms is not None:
            cur = g["latest_ts_ms"]
            if cur is None or ts_ms > cur:
                g["latest_ts_ms"] = ts_ms

        if include_samples and sample_per_group > 0 and len(g["samples"]) < sample_per_group:
            g["samples"].append(slim(rec))

    filtered_out = max(0, len(alarms_all) - len(active_filtered))

    # sort: severity (highest), then count, then latest timestamp
    def group_sort_key(item: Tuple[str, dict]) -> Tuple[int, int, int]:
        _, g = item
        best_sev = _best_severity_from_counter(g["severity_counts"]) or "Unknown"
        sev_rank = SEV_RANK.get(str(best_sev).lower(), -1)
        latest = g["latest_ts_ms"] or 0
        return (sev_rank, g["count"], latest)

    top_items = sorted(groups.items(), key=group_sort_key, reverse=True)[:top_n]

    top_out: List[dict] = []
    for _, g in top_items:
        best_sev = _best_severity_from_counter(g["severity_counts"]) or "Unknown"
        top_resources = g["resource_counts"].most_common(10)

        inv_detail = None
        if include_inventory:
            # join by id if available, otherwise by name
            if g.get("alarm_id") is not None:
                inv_detail = inv_by_id.get(str(g["alarm_id"]))
            if inv_detail is None and g.get("name"):
                inv_detail = inv_by_name.get(str(g["name"]).lower())

        entry = {
            "alarm_id": g.get("alarm_id"),
            "name": g.get("name"),
            "severity": best_sev,
            "count": g["count"],
            # Explicit: each top[] entry is a GROUP of N alarm instances, not a
            # single alarm.  `instance_count` aliases `count` so consumers can't
            # mistake "8 groups" for "8 alarms".
            "instance_count": g["count"],
            "top_resources": top_resources,  # legacy tuple shape [[resource, count], ...]
            # Path-friendly object shape for JSONata/path consumers.
            "top_resources_objects": [
                {"resource": r, "count": c} for r, c in top_resources
            ],
            "samples": g["samples"] if include_samples else [],
        }
        if inv_detail is not None:
            entry["inventory_detail"] = inv_detail

        top_out.append(entry)

    payload = {
        "input_echo": {
            "top_n": top_n,
            "max_records": max_records,
            "severity_min": severity_min,
            "query": query,
            "alarm_type": alarm_type,
            "resource": resource,
            "resource_query": resource_query,
            "include_inventory": include_inventory,
            "include_samples": include_samples,
            "sample_per_group": sample_per_group,
        },
        "summary": {
            "active_total_fetched": len(alarms_all),
            "active_after_filters": len(active_filtered),
            # Unambiguous instance vs group counts:
            # consumers iterating top[] must not read len(top) as "alarm count".
            "total_alarm_instances": len(active_filtered),
            "filtered_out": filtered_out,
            "by_severity": dict(by_sev_all),
            "returned_groups": len(top_out),
            "group_count": len(top_out),
            "result_is_grouped": True,
            "grouping_note": (
                "top[] entries are alarm GROUPS (by name/class), not individual "
                "alarms. Each entry.instance_count is how many alarms fired in "
                "that group; sum(instance_count) == total_alarm_instances. "
                "len(top) is the number of GROUPS, not the number of alarms."
            ),
            "inventory_join_mode": (
                "alarm_id_then_name" if include_inventory else "none"
            ),
        },
        "top": top_out,
        "warnings": warnings,
        "next_actions": [
            {"action": "drilldown", "hint": "Use resource_query or severity_min to narrow scope, or call faultmanager_get_alarm_history directly for full detail."}
        ],
    }

    if include_raw:
        payload["tier1_raw"] = tier1_raw

    return {"status": 200, "payload": payload}

