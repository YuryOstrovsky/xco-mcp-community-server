# tools/fabric/validation_report.py

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ---------------------------
# Small safe helpers
# ---------------------------

def _safe_get(d: Any, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _as_list(payload: Any) -> List[Any]:
    """
    Normalize common API shapes into a list.
    Handles:
      - list
      - dict with items/locks/data/results/errors
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("items", "locks", "data", "results", "errors"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
    return []


def _pick_first(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _coerce_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _truncate_list(items: List[Any], max_items: int) -> Tuple[List[Any], bool]:
    if max_items <= 0:
        return [], bool(items)
    if len(items) <= max_items:
        return items, False
    return items[:max_items], True


def _normalize_health_color(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    mapping = {
        "green": "Green",
        "ok": "Green",
        "healthy": "Green",
        "yellow": "Yellow",
        "amber": "Yellow",
        "orange": "Yellow",
        "red": "Red",
        "critical": "Red",
        "error": "Red",
    }
    return mapping.get(s.lower(), s)


def _get_fabric_name(obj: Any) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    return _pick_first(obj, ["fabric-name", "fabric_name", "name", "fabric"])  # type: ignore[arg-type]


def _is_lock_active(lock_obj: Any) -> bool:
    """
    A lock is ACTIVE only if locked == true (bool) or a truthy string like "true"/"yes"/"1".
    Anything else counts as inactive.
    """
    if not isinstance(lock_obj, dict):
        return False
    v = lock_obj.get("locked")
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1", "locked", "active")
    return False


# ---------------------------
# Transport adapter
# ---------------------------

def _transport_request(
    transport: Any,
    *,
    method: str,
    path: str,
    params: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    port: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Best-effort adapter for the runtime transport.

    In this codebase, transport commonly supports:
      request(method=..., path=..., params=..., port=None, context=None)
    """
    for meth_name in ("request", "send", "call"):
        fn = getattr(transport, meth_name, None)
        if not callable(fn):
            continue
        try:
            res = fn(method=method, path=path, params=params, context=context, port=port)
            if isinstance(res, dict) and "status" in res:
                return res
        except TypeError:
            # Signature mismatch; try without optional args
            try:
                res = fn(method=method, path=path, params=params)
                if isinstance(res, dict) and "status" in res:
                    return res
            except Exception as e:
                return {"status": 500, "payload": None, "error": f"transport.{meth_name} failed: {e}"}
        except Exception as e:
            return {"status": 500, "payload": None, "error": f"transport.{meth_name} failed: {e}"}

    # Try: transport.get(path, params={...})
    fn = getattr(transport, "get", None)
    if callable(fn):
        try:
            res = fn(path, params=params)
            if isinstance(res, dict) and "status" in res:
                return res
        except Exception as e:
            return {"status": 500, "payload": None, "error": f"transport.get failed: {e}"}

    return {"status": 500, "payload": None, "error": "No compatible transport method found"}


# ---------------------------
# Tier-1 calling helper
# ---------------------------

def _call_tier1(
    tool_name: str,
    tool_inputs: Dict[str, Any],
    *,
    registry: Any = None,
    transport: Any = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Call Tier-1 tools using registry tool catalog + transport.

    We avoid calling HTTP directly (no hardcoded URLs).
    We take the Tier-1 tool definition from registry.tools and use transport.request().
    """

    # 1) If registry exposes invoke-style APIs, try them (future-proof)
    if registry is not None:
        for meth in ("invoke_tool", "invoke", "call", "run", "invoke_tier1"):
            fn = getattr(registry, meth, None)
            if callable(fn):
                try:
                    res = fn(tool_name, tool_inputs)
                    if isinstance(res, dict) and "status" in res:
                        return res
                except TypeError:
                    pass
                except Exception as e:
                    return {"status": 500, "payload": None, "error": f"registry.{meth} failed: {e}"}

        # 2) Fetch tool definition from registry catalog
        tool_def = None
        get_tool = getattr(registry, "get", None)
        if callable(get_tool):
            try:
                tool_def = get_tool(tool_name)
            except Exception:
                tool_def = None

        if tool_def is None:
            tools_dict = getattr(registry, "tools", None)
            if isinstance(tools_dict, dict):
                tool_def = tools_dict.get(tool_name)

        if isinstance(tool_def, dict) and transport is not None:
            endpoint = tool_def.get("endpoint", {}) or {}
            path = endpoint.get("path")
            method = (tool_def.get("method") or "GET").upper()
            port = endpoint.get("port")
            if isinstance(path, str) and path.startswith("/"):
                return _transport_request(
                    transport,
                    method=method,
                    path=path,
                    params=tool_inputs,
                    context=context,
                    port=port,
                )

    return {"status": 500, "payload": None, "error": f"Tool not registered / callable: {tool_name}"}


# ---------------------------
# Validation interpretation
# ---------------------------

def _interpret_validation_payload(payload: Any) -> Dict[str, Any]:
    """
    Best-effort extraction of validation result fields.
    Different XCO endpoints may return different shapes.

    NOTE: This does NOT know HTTP status; we attach http_status separately.
    """
    if payload is None:
        return {"ok": None, "status": None, "warnings": [], "errors": [], "raw_shape": None}

    if isinstance(payload, dict):
        ok = _pick_first(payload, ["ok", "valid", "isValid", "is_valid", "success"])  # type: ignore[arg-type]
        status = _pick_first(payload, ["status", "result", "verdict", "state"])  # type: ignore[arg-type]

        warnings: List[Any] = []
        errors: List[Any] = []

        for k in ("warnings", "warning", "warningItems"):
            v = payload.get(k)
            if isinstance(v, list):
                warnings = [x for x in v if isinstance(x, (dict, str))]
                break

        for k in ("errors", "error", "errorItems", "violations"):
            v = payload.get(k)
            if isinstance(v, list):
                errors = [x for x in v if isinstance(x, (dict, str))]
                break

        # Sometimes issues are nested under items/results and include severity
        if not warnings and not errors:
            items = _as_list(payload)
            for it in items:
                if not isinstance(it, dict):
                    continue
                sev = str(it.get("severity") or it.get("level") or "").lower()
                if sev in ("warn", "warning"):
                    warnings.append(it)
                elif sev in ("err", "error", "critical", "fail", "failed"):
                    errors.append(it)

        # Derive ok from status/verdict if needed
        if ok is None and status is not None:
            s = str(status).lower()
            if s in ("pass", "passed", "ok", "success"):
                ok = True
            elif s in ("fail", "failed", "error", "critical"):
                ok = False

        if isinstance(ok, str):
            ok = ok.lower() in ("true", "yes", "1", "ok", "pass", "passed")

        return {
            "ok": ok if isinstance(ok, bool) else None,
            "status": status,
            "warnings": warnings,
            "errors": errors,
            "raw_shape": "dict",
        }

    if isinstance(payload, list):
        errors = [x for x in payload if isinstance(x, (dict, str))]
        return {"ok": False if errors else True, "status": None, "warnings": [], "errors": errors, "raw_shape": "list"}

    return {"ok": None, "status": None, "warnings": [], "errors": [], "raw_shape": type(payload).__name__}


def _derive_verdict(
    *,
    fabric_health: Optional[str],
    topology_health: Optional[str],
    error_count: int,
    lock_active_count: int,
    validate_fabric_ok: Optional[bool],
    validate_topology_ok: Optional[bool],
) -> str:
    """
    PASS/WARN/FAIL based on multiple signals.
    Conservative defaults:
      - Red fabric health => FAIL
      - any errors => FAIL
      - active locks => WARN
      - unknown validate => WARN (but not FAIL)
    """
    fh = _normalize_health_color(fabric_health)
    th = _normalize_health_color(topology_health)

    if fh == "Red":
        return "FAIL"
    if validate_fabric_ok is False or validate_topology_ok is False:
        return "FAIL"
    if error_count > 0:
        return "FAIL"

    if fh in ("Yellow",) or th in ("Red", "Yellow"):
        return "WARN"
    if lock_active_count > 0:
        return "WARN"

    # If we're missing key signals, return WARN (insufficient evidence)
    if fh is None or validate_fabric_ok is None:
        return "WARN"

    return "PASS"


# ---------------------------
# Main tool
# ---------------------------

def fabric_get_fabric_validation_report(
    inputs: Dict[str, Any],
    *,
    registry=None,
    transport=None,
    http_client=None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Tier-2: Fabric validation report (pre-change readiness / audit).

    Signals (Tier-1 tools):
      - fabric_get_fabrics (existence + canonical name)
      - fabric_get_fabric_health (health + device-health counts)
      - fabric_get_fabric_errors (actionable error list)
      - fabric_get_service_locks (locks that may block operations)
      - fabric_validate_fabric (basic validation)
      - fabric_validate_physical_topology (optional, deeper validation)

    Returns:
      {"status": <int>, "payload": {...}, "error": "...?"}
    """

    transport = transport or http_client
    context = kwargs.get("context") or {}

    name = inputs.get("name") or inputs.get("fabric_name") or inputs.get("fabric-name")
    if not name:
        fabric_ctx = (context or {}).get("fabric") or {}
        if isinstance(fabric_ctx, dict) and fabric_ctx.get("name"):
            name = fabric_ctx.get("name")

    include_errors = bool(inputs.get("include_errors", True))
    include_locks = bool(inputs.get("include_locks", True))
    include_health = bool(inputs.get("include_health", True))
    include_validate_fabric = bool(inputs.get("include_validate_fabric", True))
    include_topology_validation = bool(inputs.get("include_topology_validation", False))
    include_raw = bool(inputs.get("include_raw", False))

    max_error_items = _coerce_int(inputs.get("max_error_items", 50), 50)
    max_lock_items = _coerce_int(inputs.get("max_lock_items", 50), 50)
    max_validation_items = _coerce_int(inputs.get("max_validation_items", 50), 50)

    filter_obj: Dict[str, Any] = {
        "name": name,
        "include_health": include_health,
        "include_errors": include_errors,
        "include_locks": include_locks,
        "include_validate_fabric": include_validate_fabric,
        "include_topology_validation": include_topology_validation,
        "max_error_items": max_error_items,
        "max_lock_items": max_lock_items,
        "max_validation_items": max_validation_items,
        "include_raw": include_raw,
    }

    out: Dict[str, Any] = {"filter": filter_obj}

    if not name:
        out["error"] = "inputs.name (or fabric_name) is required"
        out["next_actions"] = [
            {
                "reason": "List fabrics, then re-run this tool with a valid fabric name.",
                "tool": "fabric_get_fabric_overview",
                "inputs": {"include_health": True, "include_errors": True},
            }
        ]
        return {"status": 400, "payload": out, "error": "missing name"}

    # ---------------------------
    # 1) Existence check + canonical name
    # ---------------------------
    fabrics_res = _call_tier1(
        "fabric_get_fabrics",
        {},
        registry=registry,
        transport=transport,
        context=context,
    )
    fabrics_status = _coerce_int(fabrics_res.get("status", 0), 0)
    fabrics_payload = fabrics_res.get("payload")

    fabrics_list = _as_list(fabrics_payload)

    # Some implementations return dict keyed by name -> values are fabric rows
    if not fabrics_list and isinstance(fabrics_payload, dict):
        vals = list(fabrics_payload.values())
        if vals and all(isinstance(v, dict) for v in vals):
            fabrics_list = vals

    canonical_name = None
    fabric_obj = None
    if fabrics_status == 200 and fabrics_list:
        for f in fabrics_list:
            if not isinstance(f, dict):
                continue
            fn = _get_fabric_name(f)
            if fn and str(fn).lower() == str(name).lower():
                canonical_name = str(fn)
                fabric_obj = f
                break

    if canonical_name:
        name = canonical_name
        out["filter"]["name"] = name

    if fabrics_status != 200 or not fabrics_list:
        out["warning"] = "Unable to fetch fabrics list; proceeding without existence validation"
        out["tier1_status"] = {"fabric_get_fabrics": fabrics_status}
        if include_raw:
            out["raw"] = {"fabric_get_fabrics": fabrics_res}
    else:
        if canonical_name is None:
            out["error"] = f"Fabric '{name}' not found"
            out["known_fabrics_count"] = len(fabrics_list)
            out["next_actions"] = [
                {
                    "reason": "List valid fabrics (or use overview to discover names).",
                    "tool": "fabric_get_fabric_overview",
                    "inputs": {"include_health": True, "include_errors": True},
                }
            ]
            return {"status": 404, "payload": out, "error": "fabric not found"}

    # ---------------------------
    # 2) Health (headline)
    # ---------------------------
    fabric_health = None
    topology_health = None
    device_health_counts: Dict[str, int] = {}
    unhealthy_count = 0

    health_res = None
    if include_health:
        health_res = _call_tier1(
            "fabric_get_fabric_health",
            {"name": name},
            registry=registry,
            transport=transport,
            context=context,
        )
        h_status = _coerce_int((health_res or {}).get("status", 0), 0)
        h_payload = (health_res or {}).get("payload")

        if h_status == 200 and isinstance(h_payload, dict):
            fabric_health = _pick_first(h_payload, ["fabric-health", "fabric_health"])  # type: ignore[arg-type]
            topology_health = _safe_get(
                h_payload,
                "fabric-level-physical-topology-health",
                "health",
                default=None,
            )

            for d in _as_list(h_payload.get("device-health")):
                if not isinstance(d, dict):
                    continue
                agg = _safe_get(d, "device-health", "aggregated-health", default=None)
                if agg is None:
                    continue
                agg_s = str(agg)
                device_health_counts[agg_s] = device_health_counts.get(agg_s, 0) + 1
                if agg_s != "Green":
                    unhealthy_count += 1
        else:
            out.setdefault("warnings", []).append(f"fabric_get_fabric_health returned status={h_status}")

    # ---------------------------
    # 3) Errors
    # ---------------------------
    errors_items: List[Any] = []
    errors_truncated = False
    errors_res = None

    if include_errors:
        errors_res = _call_tier1(
            "fabric_get_fabric_errors",
            {"fabric-name": name},
            registry=registry,
            transport=transport,
            context=context,
        )
        e_status = _coerce_int((errors_res or {}).get("status", 0), 0)
        e_payload = (errors_res or {}).get("payload")

        if e_status == 200 and e_payload is not None:
            errors_items = [x for x in _as_list(e_payload) if isinstance(x, (dict, str))]
            errors_items, errors_truncated = _truncate_list(errors_items, max_error_items)
        else:
            out.setdefault("warnings", []).append(f"fabric_get_fabric_errors returned status={e_status}")

    # ---------------------------
    # 4) Locks (global endpoint) — ACTIVE vs TOTAL
    # ---------------------------
    locks_active: List[Any] = []
    locks_inactive: List[Any] = []
    locks_active_truncated = False
    locks_res = None

    if include_locks:
        locks_res = _call_tier1(
            "fabric_get_service_locks",
            {},
            registry=registry,
            transport=transport,
            context=context,
        )
        l_status = _coerce_int((locks_res or {}).get("status", 0), 0)
        l_payload = (locks_res or {}).get("payload")

        if l_status == 200 and l_payload is not None:
            raw_locks = [x for x in _as_list(l_payload) if isinstance(x, (dict, str))]

            # Best-effort fabric filter (often locks don't include fabric anyway)
            filtered: List[Any] = []
            for it in raw_locks:
                if not isinstance(it, dict):
                    filtered.append(it)
                    continue
                fn = _get_fabric_name(it)
                if fn is None or str(fn).lower() == str(name).lower():
                    filtered.append(it)

            for it in filtered:
                if _is_lock_active(it):
                    locks_active.append(it)
                else:
                    locks_inactive.append(it)

            # Truncate ACTIVE list only (inactive is informational)
            locks_active, locks_active_truncated = _truncate_list(locks_active, max_lock_items)
        else:
            out.setdefault("warnings", []).append(f"fabric_get_service_locks returned status={l_status}")

    # ---------------------------
    # 5) Validate fabric (ensure http_status + status fallback)
    # ---------------------------
    validate_fabric: Dict[str, Any] = {
        "ok": None,
        "status": None,
        "http_status": None,
        "warnings": [],
        "errors": [],
        "raw_shape": None,
        "note": None,
    }
    validate_fabric_res = None

    if include_validate_fabric:
        validate_fabric_res = _call_tier1(
            "fabric_validate_fabric",
            {"fabric-name": name},
            registry=registry,
            transport=transport,
            context=context,
        )
        vf_status = _coerce_int((validate_fabric_res or {}).get("status", 0), 0)
        vf_payload = (validate_fabric_res or {}).get("payload")

        if vf_status == 200:
            validate_fabric = _interpret_validation_payload(vf_payload)
            validate_fabric["warnings"], _ = _truncate_list(validate_fabric.get("warnings", []), max_validation_items)
            validate_fabric["errors"], _ = _truncate_list(validate_fabric.get("errors", []), max_validation_items)
        else:
            out.setdefault("warnings", []).append(f"fabric_validate_fabric returned status={vf_status}")

        # Always attach HTTP status + fallback status
        validate_fabric["http_status"] = vf_status
        if validate_fabric.get("status") is None:
            validate_fabric["status"] = vf_status

        # If endpoint doesn't provide a verdict, be explicit (so UI doesn't look broken)
        if vf_status == 200 and validate_fabric.get("ok") is None and not validate_fabric.get("warnings") and not validate_fabric.get("errors"):
            validate_fabric["note"] = "Validation endpoint returned no explicit verdict; ok is unknown."
        elif vf_status != 200:
            validate_fabric["note"] = "Validation call failed or returned non-200."

    # ---------------------------
    # 6) Validate physical topology (optional) — ensure http_status + status fallback
    # ---------------------------
    validate_topology: Dict[str, Any] = {
        "ok": None,
        "status": None,
        "http_status": None,
        "warnings": [],
        "errors": [],
        "raw_shape": None,
        "note": None,
    }
    validate_topology_res = None

    if include_topology_validation:
        validate_topology_res = _call_tier1(
            "fabric_validate_physical_topology",
            {"fabric-name": name},
            registry=registry,
            transport=transport,
            context=context,
        )
        vt_status = _coerce_int((validate_topology_res or {}).get("status", 0), 0)
        vt_payload = (validate_topology_res or {}).get("payload")

        if vt_status == 200:
            validate_topology = _interpret_validation_payload(vt_payload)
            validate_topology["warnings"], _ = _truncate_list(validate_topology.get("warnings", []), max_validation_items)
            validate_topology["errors"], _ = _truncate_list(validate_topology.get("errors", []), max_validation_items)
        else:
            out.setdefault("warnings", []).append(f"fabric_validate_physical_topology returned status={vt_status}")

        # Always attach HTTP status + fallback status
        validate_topology["http_status"] = vt_status
        if validate_topology.get("status") is None:
            validate_topology["status"] = vt_status

        if vt_status == 200 and validate_topology.get("ok") is None and not validate_topology.get("warnings") and not validate_topology.get("errors"):
            validate_topology["note"] = "Validation endpoint returned no explicit verdict; ok is unknown."
        elif vt_status != 200:
            validate_topology["note"] = "Validation call failed or returned non-200."

    # ---------------------------
    # Summary + verdict
    # ---------------------------
    locks_active_count = len(locks_active)
    locks_total_count = len(locks_active) + len(locks_inactive)

    verdict = _derive_verdict(
        fabric_health=fabric_health,
        topology_health=topology_health,
        error_count=len(errors_items),
        lock_active_count=locks_active_count,
        validate_fabric_ok=validate_fabric.get("ok") if include_validate_fabric else None,
        validate_topology_ok=validate_topology.get("ok") if include_topology_validation else None,
    )

    out["summary"] = {
        "fabric": name,
        "verdict": verdict,
        "fabric_health": _normalize_health_color(fabric_health),
        "topology_health": _normalize_health_color(topology_health),
        "counts": {
            "unhealthy_devices": unhealthy_count,
            "device_health_counts": device_health_counts,
            "errors": len(errors_items),

            # Accurate lock counts
            "locks_active": locks_active_count,
            "locks_total": locks_total_count,

            "validate_fabric_errors": len(validate_fabric.get("errors", [])) if include_validate_fabric else 0,
            "validate_topology_errors": len(validate_topology.get("errors", [])) if include_topology_validation else 0,
        },
    }

    out["signals"] = {
        "health": {
            "fabric_health": _normalize_health_color(fabric_health),
            "topology_health": _normalize_health_color(topology_health),
            "device_health_counts": device_health_counts,
            "unhealthy_devices": unhealthy_count,
        } if include_health else None,
        "errors": {
            "count": len(errors_items),
            "items": errors_items,
            "truncated": errors_truncated,
        } if include_errors else None,

        # Backwards compatible keys:
        # - count/items refer to ACTIVE locks only.
        # Added transparency fields so you still see total/inactive.
        "locks": {
            "count": locks_active_count,          # ACTIVE ONLY
            "items": locks_active,                # ACTIVE ONLY
            "truncated": locks_active_truncated,
            "total_count": locks_total_count,
            "inactive_count": len(locks_inactive),
        } if include_locks else None,

        "validate_fabric": validate_fabric if include_validate_fabric else None,
        "validate_physical_topology": validate_topology if include_topology_validation else None,
    }

    # ---------------------------
    # Recommendations + next actions
    # ---------------------------
    recommendations: List[str] = []
    next_actions: List[Dict[str, Any]] = []

    if verdict == "PASS":
        recommendations.append("Fabric appears healthy and ready for safe operations.")

    # Only warn if ACTIVE locks exist
    if include_locks and locks_active_count > 0:
        recommendations.append("Active service locks detected. Avoid disruptive operations until locks clear.")
        next_actions.append(
            {"reason": "Inspect active locks.", "tool": "fabric_get_service_locks", "inputs": {}}
        )

    if include_errors and errors_items:
        recommendations.append("Fabric errors detected. Investigate errors before making changes.")
        next_actions.append(
            {"reason": "Get detailed error list for this fabric.", "tool": "fabric_get_fabric_errors", "inputs": {"fabric-name": name}}
        )
        next_actions.append(
            {"reason": "Correlate errors with device health and recent events.", "tool": "fabric_get_fabric_health_summary", "inputs": {"name": name, "include_errors": True}}
        )

    if include_health and _normalize_health_color(fabric_health) in ("Red", "Yellow"):
        recommendations.append("Fabric health is not Green. Review timeline and recent executions.")
        next_actions.append(
            {"reason": "See health timeline + recent executions/events.", "tool": "fabric_get_fabric_health_timeline", "inputs": {"name": name, "include_exec_details": False}}
        )

    if include_validate_fabric and validate_fabric.get("ok") is False:
        recommendations.append("Fabric validation reported failures. Resolve validation errors first.")
        next_actions.append(
            {"reason": "Re-run fabric validation (raw output may include precise failure reasons).", "tool": "fabric_validate_fabric", "inputs": {"fabric-name": name}}
        )

    if include_topology_validation and validate_topology.get("ok") is False:
        recommendations.append("Physical topology validation failed. Fix topology issues before changes.")
        next_actions.append(
            {"reason": "Re-run physical topology validation.", "tool": "fabric_validate_physical_topology", "inputs": {"fabric-name": name}}
        )
        next_actions.append(
            {"reason": "Pull current physical topology for inspection.", "tool": "fabric_get_physical_topology", "inputs": {"fabric-name": name}}
        )

    if not next_actions:
        next_actions.append(
            {"reason": "Get a compact overview for more context.", "tool": "fabric_get_fabric_overview", "inputs": {"fabric_name": name, "include_health": True, "include_errors": True}}
        )

    out["recommendations"] = recommendations
    out["next_actions"] = next_actions

    if include_raw:
        out.setdefault("raw", {})
        out["raw"].update(
            {
                "fabric_get_fabrics": fabrics_res,
                "fabric_get_fabric_health": health_res,
                "fabric_get_fabric_errors": errors_res,
                "fabric_get_service_locks": locks_res,
                "fabric_validate_fabric": validate_fabric_res,
                "fabric_validate_physical_topology": validate_topology_res,
            }
        )
        if fabric_obj is not None:
            out["raw"]["fabric_summary_row"] = fabric_obj

    return {"status": 200, "payload": out}

