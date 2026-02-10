# tools/tenant/service_epg_health_summary.py

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional


MAX_EPG_SCAN = 300
MAX_VRF_SCAN = 200
MAX_ROW_RETURN = 2000


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
    Best-effort list extraction from common wrapper shapes:
      - list => itself
      - dict with known keys (items/data/result/payload)
      - dict with exactly one list value
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("items", "data", "result", "payload", "vrfs", "endpointGroups", "endpoint_groups", "errors"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
        list_values = [v for v in payload.values() if isinstance(v, list)]
        if len(list_values) == 1:
            return list_values[0]
    return []


def _as_str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        out = []
        for x in v:
            s = _norm_str(x)
            if s:
                out.append(s)
        return out
    s = _norm_str(v)
    return [s] if s else []


def _health_from_error_count(err_count: Optional[int], fetch_ok: bool) -> str:
    if not fetch_ok:
        return "unknown"
    if err_count is None:
        return "unknown"
    return "degraded" if err_count > 0 else "ok"


def _is_tenant_not_found(res: dict) -> bool:
    """
    Detect XCO 'tenant not found' conditions in a Tier-1 response.
    Example:
      status: 409
      payload: { "code": 1308, "message": "A Tenant with specified name is not found" }
    """
    if not isinstance(res, dict):
        return False
    status = res.get("status")
    payload = res.get("payload")
    if not isinstance(payload, dict):
        return False

    code = payload.get("code")
    msg = str(payload.get("message") or "").lower()

    if code == 1308:
        return True
    if status in (404, 409) and ("tenant" in msg and "not found" in msg):
        return True
    return False


def _extract_tenant_names(payload: Any) -> List[str]:
    """
    tenant_get_tenants commonly returns {"tenant":[{"name":"..."}...]}.
    Best-effort extraction.
    """
    if payload is None:
        return []

    if isinstance(payload, dict):
        t = payload.get("tenant")
        if isinstance(t, list):
            names: List[str] = []
            for x in t:
                if isinstance(x, dict):
                    n = _norm_str(x.get("name"))
                    if n:
                        names.append(n)
            return names

        # If it's a dict with exactly one list value, try that list
        list_values = [v for v in payload.values() if isinstance(v, list)]
        if len(list_values) == 1:
            names = []
            for x in list_values[0]:
                if isinstance(x, dict):
                    n = _norm_str(x.get("name"))
                    if n:
                        names.append(n)
            return names

    if isinstance(payload, list):
        names = []
        for x in payload:
            if isinstance(x, dict):
                n = _norm_str(x.get("name"))
                if n:
                    names.append(n)
        return names

    return []


def tenant_get_service_epg_health_summary(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
) -> dict:
    """
    Tier-2 composite: tenant_get_service_epg_health_summary

    Goal:
      Real-time, table-friendly rollup of a tenant's VRFs + Endpoint Groups (EPGs),
      enriched with "health-like" signals by querying each object's error endpoint.

    Tier-1 tools used (must exist already):
      - tenant_get_tenant
      - tenant_get_tenants (best-effort suggestion only on "tenant not found")
      - tenant_get_vrfs
      - tenant_get_endpoint_groups
      - tenant_get_vrf_error
      - tenant_get_endpoint_group_error
      - tenant_get_execution_list (optional)
      - tenant_get_event_history_list (optional)
      - tenant_get_locks (optional)

    NOTE:
      This tool intentionally does NOT invent new Tier-1 calls. If a Tier-1 tool is
      missing from the registry, the response includes a clear error.
    """

    inobj = inputs or {}

    tenant_name = _norm_str(inobj.get("tenant_name")) or _norm_str(inobj.get("name"))
    if not tenant_name:
        return {
            "status": 400,
            "payload": {
                "error": "Missing required input: tenant_name",
                "expected": {"tenant_name": "string"},
            },
        }

    include_rows = _as_bool(inobj.get("include_rows"), True)
    include_vrf_summary = _as_bool(inobj.get("include_vrf_summary"), True)
    include_recent_executions = _as_bool(inobj.get("include_recent_executions"), True)
    execution_limit = max(1, min(_as_int(inobj.get("execution_limit"), 20), 200))
    execution_status = _norm_str(inobj.get("execution_status"))  # optional (e.g. FAILED)
    include_events = _as_bool(inobj.get("include_events"), False)
    include_locks = _as_bool(inobj.get("include_locks"), False)

    max_epgs = max(1, min(_as_int(inobj.get("max_epgs"), MAX_EPG_SCAN), MAX_EPG_SCAN))
    max_vrfs = max(1, min(_as_int(inobj.get("max_vrfs"), MAX_VRF_SCAN), MAX_VRF_SCAN))
    max_rows = max(1, min(_as_int(inobj.get("max_rows"), MAX_ROW_RETURN), MAX_ROW_RETURN))

    include_raw = _as_bool(inobj.get("include_raw"), False)

    filt = {
        "tenant_name": tenant_name,
        "include_rows": include_rows,
        "include_vrf_summary": include_vrf_summary,
        "include_recent_executions": include_recent_executions,
        "execution_limit": execution_limit,
        "execution_status": execution_status,
        "include_events": include_events,
        "include_locks": include_locks,
        "max_epgs": max_epgs,
        "max_vrfs": max_vrfs,
        "max_rows": max_rows,
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

    # -----------------------
    # 0) Validate tenant exists (best-effort)
    # -----------------------
    tenant_res = call_tier1("tenant_get_tenant", {"name": tenant_name})
    if include_raw:
        raw["tenant_get_tenant"] = tenant_res

    if tenant_res.get("status") not in (200, 204):
        # Special handling: tenant not found -> suggest valid tenant names (best-effort)
        suggested: List[str] = []
        if _is_tenant_not_found(tenant_res):
            tenants_res = call_tier1("tenant_get_tenants", {})
            if include_raw:
                raw["tenant_get_tenants"] = tenants_res
            if tenants_res.get("status") == 200:
                suggested = _extract_tenant_names(tenants_res.get("payload"))

        if suggested:
            next_actions.append(
                {
                    "action": "choose_tenant",
                    "tool": "tenant_get_tenants",
                    "message": "Tenant name not found. Pick one of the suggested tenant names and retry.",
                    "suggested_tenants": suggested[:50],
                }
            )

        error_msg = "Failed to fetch tenant details (tenant_get_tenant)"
        if _is_tenant_not_found(tenant_res):
            error_msg = f"Tenant not found: {tenant_name}"

        out_payload: Dict[str, Any] = {
            "filter": filt,
            "error": error_msg,
            "tier1": {"tenant_get_tenant": tenant_res},
            "warnings": warnings,
            "next_actions": next_actions,
        }
        if suggested:
            out_payload["suggested_tenants"] = suggested[:50]
        if include_raw:
            out_payload["tier1_raw"] = raw

        return {"status": 502, "payload": out_payload}

    tenant_payload = tenant_res.get("payload")
    tenant_obj = tenant_payload if isinstance(tenant_payload, dict) else {}

    # -----------------------
    # 1) Fetch VRFs + EPGs
    # -----------------------
    vrfs_res = call_tier1("tenant_get_vrfs", {"tenant_name": tenant_name})
    if include_raw:
        raw["tenant_get_vrfs"] = vrfs_res
    if vrfs_res.get("status") != 200:
        return {
            "status": 502,
            "payload": {
                "filter": filt,
                "error": "Failed to list VRFs (tenant_get_vrfs)",
                "tier1": {"tenant_get_vrfs": vrfs_res},
            },
        }

    epgs_res = call_tier1("tenant_get_endpoint_groups", {"tenant_name": tenant_name})
    if include_raw:
        raw["tenant_get_endpoint_groups"] = epgs_res
    if epgs_res.get("status") != 200:
        return {
            "status": 502,
            "payload": {
                "filter": filt,
                "error": "Failed to list Endpoint Groups (tenant_get_endpoint_groups)",
                "tier1": {"tenant_get_endpoint_groups": epgs_res},
            },
        }

    vrfs_list = [x for x in _as_list(vrfs_res.get("payload")) if isinstance(x, dict)]
    epgs_list = [x for x in _as_list(epgs_res.get("payload")) if isinstance(x, dict)]

    total_vrfs = len(vrfs_list)
    total_epgs = len(epgs_list)

    if total_vrfs > max_vrfs:
        warnings.append(f"VRFs truncated for scan: {total_vrfs} total, scanning first {max_vrfs}.")
        vrfs_list = vrfs_list[:max_vrfs]
    if total_epgs > max_epgs:
        warnings.append(f"EPGs truncated for scan: {total_epgs} total, scanning first {max_epgs}.")
        epgs_list = epgs_list[:max_epgs]

    # -----------------------
    # 2) Per-object error lookups (health-ish signals)
    # -----------------------
    vrf_errors: Dict[str, Dict[str, Any]] = {}
    epg_errors: Dict[str, Dict[str, Any]] = {}

    # VRF errors
    for v in vrfs_list:
        vrf_name = _norm_str(_pick_first(v, ["name", "vrf_name", "vrfName", "vrf"]))
        if not vrf_name:
            continue
        res = call_tier1("tenant_get_vrf_error", {"name": vrf_name, "tenant_name": tenant_name})
        if include_raw and len(vrf_errors) < 5:
            raw[f"tenant_get_vrf_error::{vrf_name}"] = res
        ok = (res.get("status") == 200)
        errs = _as_list(res.get("payload")) if ok else []
        vrf_errors[vrf_name] = {
            "fetch_ok": ok,
            "error_count": len(errs) if ok else None,
            "sample": (errs[0] if errs else None),
        }

    # EPG errors
    for e in epgs_list:
        epg_name = _norm_str(_pick_first(e, ["name", "epg_name", "epgName", "endpoint_group", "endpointGroup"]))
        if not epg_name:
            continue
        res = call_tier1("tenant_get_endpoint_group_error", {"name": epg_name, "tenant_name": tenant_name})
        if include_raw and len(epg_errors) < 5:
            raw[f"tenant_get_endpoint_group_error::{epg_name}"] = res
        ok = (res.get("status") == 200)
        errs = _as_list(res.get("payload")) if ok else []
        epg_errors[epg_name] = {
            "fetch_ok": ok,
            "error_count": len(errs) if ok else None,
            "sample": (errs[0] if errs else None),
        }

    # -----------------------
    # 3) Build table-friendly rows
    # -----------------------
    rows: List[Dict[str, Any]] = []

    # Precompute VRF rollups
    vrf_summary: List[Dict[str, Any]] = []
    vrf_status_counts = defaultdict(int)

    for v in vrfs_list:
        vrf_name = _norm_str(_pick_first(v, ["name", "vrf_name", "vrfName", "vrf"]))
        if not vrf_name:
            continue
        ve = vrf_errors.get(vrf_name, {})
        status = _health_from_error_count(ve.get("error_count"), bool(ve.get("fetch_ok")))
        vrf_status_counts[status] += 1
        if include_vrf_summary:
            vrf_summary.append(
                {
                    "vrf_name": vrf_name,
                    "status": status,
                    "error_count": ve.get("error_count"),
                    "sample_error": ve.get("sample"),
                }
            )

    # EPG rows
    if include_rows:
        for e in epgs_list:
            epg_name = _norm_str(_pick_first(e, ["name", "epg_name", "epgName", "endpoint_group", "endpointGroup"]))
            if not epg_name:
                continue

            # Try to attach VRF name (best-effort from common keys)
            vrf_name = _norm_str(_pick_first(e, ["vrf_name", "vrfName", "vrf", "vrf-name"]))
            # Some schemas might embed VRF object
            if not vrf_name and isinstance(e.get("vrf"), dict):
                vrf_name = _norm_str(_pick_first(e["vrf"], ["name", "vrf_name", "vrfName"]))

            # Services (best-effort)
            services: List[str] = []
            for k in ("services", "service_names", "serviceNames", "service", "serviceName"):
                if k in e and e.get(k) is not None:
                    services = _as_str_list(e.get(k))
                    break

            ee = epg_errors.get(epg_name, {})
            epg_status = _health_from_error_count(ee.get("error_count"), bool(ee.get("fetch_ok")))

            if vrf_name and vrf_name in vrf_errors:
                ve = vrf_errors.get(vrf_name, {})
                vrf_status = _health_from_error_count(ve.get("error_count"), bool(ve.get("fetch_ok")))
            else:
                vrf_status = "unknown" if vrf_name else None

            row = {
                "tenant_name": tenant_name,
                "epg_name": epg_name,
                "vrf_name": vrf_name,
                "services": services,
                "epg_status": epg_status,
                "epg_error_count": ee.get("error_count"),
                "epg_sample_error": ee.get("sample"),
                "vrf_status": vrf_status,
            }
            rows.append(row)

            if len(rows) >= max_rows:
                warnings.append(f"Rows truncated: returning first {max_rows} rows.")
                break

    # -----------------------
    # 4) Recent executions & events (optional)
    # -----------------------
    executions_block: Dict[str, Any] = {}
    events_block: Dict[str, Any] = {}
    if include_recent_executions:
        ex_params = {"limit": execution_limit}
        if execution_status:
            ex_params["status"] = execution_status
        ex_res = call_tier1("tenant_get_execution_list", ex_params)
        if include_raw:
            raw["tenant_get_execution_list"] = ex_res

        if ex_res.get("status") == 200:
            ex_list = [x for x in _as_list(ex_res.get("payload")) if isinstance(x, dict)]
            status_counts = defaultdict(int)
            latest: List[dict] = []
            for x in ex_list:
                st = _norm_str(_pick_first(x, ["status", "state"])) or "unknown"
                status_counts[st] += 1

                uuid = _norm_str(_pick_first(x, ["uuid", "execution_uuid", "executionUuid", "id"]))
                started = _pick_first(x, ["start_time", "startTime", "started", "created_at", "createdAt"])
                finished = _pick_first(x, ["end_time", "endTime", "finished", "completed_at", "completedAt"])
                latest.append(
                    {
                        "execution_uuid": uuid,
                        "status": st,
                        "start_time": started,
                        "end_time": finished,
                        "summary": _norm_str(_pick_first(x, ["summary", "message", "description"])) or None,
                    }
                )

            executions_block = {
                "scanned": len(ex_list),
                "status_counts": dict(status_counts),
                "latest": latest[: min(10, len(latest))],
            }

            # Optionally fetch event history for most recent FAILED execution (best-effort)
            if include_events:
                failed_uuid = None
                for x in latest:
                    if (x.get("status") or "").upper() == "FAILED" and x.get("execution_uuid"):
                        failed_uuid = x["execution_uuid"]
                        break
                if failed_uuid:
                    ev_res = call_tier1("tenant_get_event_history_list", {"execution_uuid": failed_uuid})
                    if include_raw:
                        raw[f"tenant_get_event_history_list::{failed_uuid}"] = ev_res
                    if ev_res.get("status") == 200:
                        ev_list = _as_list(ev_res.get("payload"))
                        events_block = {
                            "execution_uuid": failed_uuid,
                            "event_count": len(ev_list),
                            "events": ev_list[:50],  # cap
                        }
                    else:
                        warnings.append("Failed to fetch event history for last FAILED execution.")
        else:
            warnings.append("Failed to fetch recent executions (tenant_get_execution_list).")

    # -----------------------
    # 5) Locks (optional)
    # -----------------------
    locks_block: Dict[str, Any] = {}
    if include_locks:
        lock_types = ["service", "vrf", "epg"]
        lock_counts: Dict[str, Any] = {}
        lock_samples: Dict[str, Any] = {}
        for lt in lock_types:
            lr = call_tier1("tenant_get_locks", {"type": lt})
            if include_raw:
                raw[f"tenant_get_locks::{lt}"] = lr
            if lr.get("status") == 200:
                lst = _as_list(lr.get("payload"))
                lock_counts[lt] = len(lst)
                if lst:
                    lock_samples[lt] = lst[:10]
            else:
                lock_counts[lt] = None
        locks_block = {"counts": lock_counts, "samples": lock_samples}

    # -----------------------
    # 6) Rollups
    # -----------------------
    epg_status_counts = defaultdict(int)
    for r in rows:
        epg_status_counts[r.get("epg_status") or "unknown"] += 1

    counts = {
        "vrfs_total": total_vrfs,
        "vrfs_scanned": len(vrfs_list),
        "vrfs_ok": vrf_status_counts.get("ok", 0),
        "vrfs_degraded": vrf_status_counts.get("degraded", 0),
        "vrfs_unknown": vrf_status_counts.get("unknown", 0),
        "epgs_total": total_epgs,
        "epgs_scanned": len(epgs_list),
        "epgs_ok": epg_status_counts.get("ok", 0),
        "epgs_degraded": epg_status_counts.get("degraded", 0),
        "epgs_unknown": epg_status_counts.get("unknown", 0),
        "rows_returned": len(rows),
    }

    overall_status = "ok"
    if counts["epgs_degraded"] > 0 or counts["vrfs_degraded"] > 0:
        overall_status = "degraded"
    elif counts["epgs_unknown"] > 0 or counts["vrfs_unknown"] > 0:
        overall_status = "unknown"

    payload: Dict[str, Any] = {
        "filter": filt,
        "tenant": {
            "name": tenant_name,
            "details": tenant_obj if tenant_obj else None,
        },
        "overall_status": overall_status,
        "counts": counts,
        "vrf_summary": vrf_summary if include_vrf_summary else None,
        "rows": rows if include_rows else None,
        "executions": executions_block if include_recent_executions else None,
        "events": events_block if (include_recent_executions and include_events) else None,
        "locks": locks_block if include_locks else None,
        "warnings": warnings,
        "next_actions": next_actions,
    }

    if include_raw:
        payload["tier1_raw"] = raw

    return {"status": 200, "payload": payload}

