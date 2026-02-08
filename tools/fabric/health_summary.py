# tools/fabric/health_summary.py

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
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return items
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


def _known_fabric_names(out: Dict[str, Any]) -> set:
    """
    Build a set of known fabric names from out["global_context"]["fabrics"] if present.
    """
    names = set()
    fabrics = _safe_get(out, "global_context", "fabrics", default=[])
    if isinstance(fabrics, list):
        for f in fabrics:
            if isinstance(f, dict) and f.get("fabric"):
                names.add(str(f["fabric"]))
    return names


# ---------------------------
# Transport adapter
# ---------------------------

def _transport_get(transport: Any, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort adapter for whatever transport object the runtime passes.
    Expected return: {"status": int, "payload": Any, ...}
    """
    # Try: transport.request(method="GET", path="/...", params={...})
    for meth_name in ("request", "send", "call"):
        fn = getattr(transport, meth_name, None)
        if not callable(fn):
            continue
        try:
            res = fn(method="GET", path=path, params=params)
            if isinstance(res, dict) and "status" in res:
                return res
        except TypeError:
            # signature mismatch
            pass
        except Exception as e:
            return {"status": 500, "payload": None, "error": f"transport.{meth_name} failed: {e}"}

    # Try: transport.get("/...", params={...})
    fn = getattr(transport, "get", None)
    if callable(fn):
        try:
            res = fn(path, params=params)
            if isinstance(res, dict) and "status" in res:
                return res
        except Exception as e:
            return {"status": 500, "payload": None, "error": f"transport.get failed: {e}"}

    return {"status": 500, "payload": None, "error": "No compatible GET method found on transport"}


# ---------------------------
# Tier-1 calling helper
# ---------------------------

def _call_tier1(
    tool_name: str,
    tool_inputs: Dict[str, Any],
    *,
    registry: Any = None,
    transport: Any = None,
) -> Dict[str, Any]:
    """
    Call Tier-1 tools in the most reliable way available:
    1) If registry exposes invoke/call/run methods, try those.
    2) Else if registry exposes tool catalog + transport exists, call endpoint via transport.
    3) Else (last resort) call known fabric endpoints directly via transport.
    """
    # 1) Preferred: registry invoke-style APIs
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

        # 2) Try registry tool catalog to get endpoint info
        tool_def = None
        get_tool = getattr(registry, "get_tool", None)
        if callable(get_tool):
            try:
                tool_def = get_tool(tool_name)
            except Exception:
                tool_def = None

        if tool_def is None:
            tools_dict = getattr(registry, "tools", None)
            if isinstance(tools_dict, dict):
                tool_def = tools_dict.get(tool_name)

        if tool_def and transport is not None and isinstance(tool_def, dict):
            endpoint = tool_def.get("endpoint", {}) or {}
            path = endpoint.get("path")
            method = (tool_def.get("method") or "GET").upper()
            if method == "GET" and isinstance(path, str) and path.startswith("/"):
                return _transport_get(transport, path, tool_inputs)

    # 3) Last-resort hardcoded paths (kept tight to only what we need)
    if transport is not None:
        if tool_name == "fabric_get_fabrics_health":
            return _transport_get(transport, "/v1/fabric/fabrics-health", tool_inputs)
        if tool_name in ("fabric_get_fabric_health", "fabric_get_health"):
            # fabric_get_health is ambiguous; in some deployments it maps to fabric-health too
            return _transport_get(transport, "/v1/fabric/fabric-health", tool_inputs)
        if tool_name == "fabric_get_fabrics_errors":
            return _transport_get(transport, "/v1/fabric/fabrics-errors", tool_inputs)
        if tool_name == "fabric_get_fabric_errors":
            return _transport_get(transport, "/v1/fabric/fabric-errors", tool_inputs)

    return {"status": 500, "payload": None, "error": f"Tool not registered / callable: {tool_name}"}


# ---------------------------
# Normalizers for global data
# ---------------------------

def _normalize_global_fabric_row(row: Dict[str, Any]) -> Dict[str, Any]:
    fname = _pick_first(row, ["fabric-name", "fabric_name", "name", "fabric"])
    fhealth = _pick_first(row, ["fabric-health", "fabric_health", "health"])
    topo = _safe_get(row, "fabric-level-physical-topology-health", "health", default=None)

    out = {
        "fabric": fname,
        "fabric_health": fhealth,
        "topology_health": topo,
    }

    # preserve a few useful IDs/attributes if present (matches your observed output)
    for k in ("fabric-id", "fabric-type", "fabric-stage", "fabric-status"):
        if k in row:
            out[k] = row.get(k)

    return out


def _extract_service_health(payload: Any) -> Optional[Dict[str, Any]]:
    """
    Your observed payload is: {"Service":"Ok","MessageBus":"Ok"}.
    If payload is already that dict, just return it.
    If nested, try to extract a reasonable dict.
    """
    if isinstance(payload, dict):
        # common simplest form
        if "Service" in payload or "MessageBus" in payload:
            return payload
        # sometimes under "payload" or "health"
        for k in ("health", "payload", "service_health", "status"):
            v = payload.get(k)
            if isinstance(v, dict) and ("Service" in v or "MessageBus" in v):
                return v
    return None


# ---------------------------
# Errors helpers
# ---------------------------

def _normalize_errors_items(payload: Any) -> List[Dict[str, Any]]:
    """
    Normalize fabrics-errors / fabric-errors payload into list of dicts.
    We keep it permissive because XCO deployments can differ.
    """
    items = _as_list(payload)
    out: List[Dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict):
            out.append(it)
    # Sometimes payload itself is a dict describing one fabric's errors
    if not out and isinstance(payload, dict):
        out.append(payload)
    return out


def _find_global_errors_for_fabric(global_error_items: List[Dict[str, Any]], fabric_name: str) -> Optional[Dict[str, Any]]:
    for it in global_error_items:
        if not isinstance(it, dict):
            continue
        fname = _pick_first(it, ["fabric_name", "fabric-name", "fabric", "name"])
        if fname == fabric_name:
            return it
    return None


def _derive_fabric_errors_from_global(global_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return deviceErrorResponse entries if present.
    If the global entry has no actionable error details, return [] (cleaner than returning a stub).
    """
    der = global_entry.get("deviceErrorResponse")
    if isinstance(der, list):
        out: List[Dict[str, Any]] = []
        for x in der:
            if isinstance(x, dict):
                out.append(x)
        return out  # could be empty; that's fine

    # If the global entry is just metadata (fabric_name/fabric_id), treat as "no details"
    keys = set(global_entry.keys())
    if keys.issubset({"fabric_name", "fabric-id", "fabric_id", "fabric-name", "fabric"}):
        return []

    # Otherwise return it as a single item (rare case where entry itself contains useful fields)
    return [global_entry]


# ---------------------------
# Main tool
# ---------------------------

def fabric_get_fabric_health_summary(
    inputs: Dict[str, Any],
    *,
    registry=None,
    transport=None,
    http_client=None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Tier-2: Fabric health summary (core)

    Modes:
      A) Global mode (no name): show fabrics list + optional expanded unhealthy + optional global errors + service health
      B) Per-fabric mode (name): show fabric headline + unhealthy devices + optional per-fabric errors (+ fallback)
         + global context + service health

    Tier-1 tools used (as available):
      - fabric_get_fabrics_health
      - fabric_get_fabric_health
      - fabric_get_health (service health; also used as fallback in some deployments)
      - fabric_get_fabrics_errors
      - fabric_get_fabric_errors
    """

    # unify runtime transports
    transport = transport or http_client

    name = inputs.get("name") or inputs.get("fabric_name")

    include_global = bool(inputs.get("include_global", True))
    include_service_health = bool(inputs.get("include_service_health", True))
    include_errors = bool(inputs.get("include_errors", False))
    include_raw = bool(inputs.get("include_raw", False))

    expand_unhealthy = bool(inputs.get("expand_unhealthy", False))
    max_expand = _coerce_int(inputs.get("max_expand", 3), 3)

    max_fabrics = _coerce_int(inputs.get("max_fabrics", 200), 200)
    max_unhealthy_devices = _coerce_int(inputs.get("max_unhealthy_devices", 50), 50)
    max_error_items = _coerce_int(inputs.get("max_error_items", 50), 50)

    # ---------------------------
    # Improvement #1:
    # Always return the SAME full filter object in every mode.
    # ---------------------------
    filter_obj: Dict[str, Any] = {
        "name": name if name else None,
        "include_global": include_global,
        "include_service_health": include_service_health,
        "include_errors": include_errors,
        "expand_unhealthy": expand_unhealthy,
        "max_expand": max_expand,
        "max_fabrics": max_fabrics,
        "max_unhealthy_devices": max_unhealthy_devices,
        "max_error_items": max_error_items,
        "include_raw": include_raw,
    }

    out: Dict[str, Any] = {"filter": filter_obj}

    # ---------------------------
    # Global context (fabrics list)
    # ---------------------------
    unhealthy_fabrics: List[Dict[str, Any]] = []

    if include_global:
        g_res = _call_tier1(
            "fabric_get_fabrics_health",
            {},
            registry=registry,
            transport=transport,
        )
        g_status = _coerce_int(g_res.get("status", 0), 0)
        g_payload = g_res.get("payload")

        if g_status == 200 and g_payload is not None:
            items = _as_list(g_payload)
            normed: List[Dict[str, Any]] = []
            for it in items:
                if isinstance(it, dict):
                    normed.append(_normalize_global_fabric_row(it))

            # truncate
            normed, trunc = _truncate_list(normed, max_fabrics)

            # compute unhealthy list (used for expand_unhealthy)
            for f in normed:
                if f.get("fabric_health") != "Green":
                    unhealthy_fabrics.append(f)

            out["global_context"] = {
                "count": len(normed),
                "fabrics": normed,
            }
            if trunc:
                out["global_context"]["truncated"] = True
        else:
            # don't fail the tool if global list isn't available; we can still do per-fabric mode if name provided
            out["global_context"] = {
                "count": 0,
                "fabrics": [],
                "status": g_status,
                "error": g_res.get("error") or "Failed to fetch fabrics health",
            }

    # ---------------------------
    # Service health (global)
    # ---------------------------
    if include_service_health:
        s_res = _call_tier1(
            "fabric_get_health",
            {},  # service health typically doesn't need a name
            registry=registry,
            transport=transport,
        )
        s_status = _coerce_int(s_res.get("status", 0), 0)
        s_payload = s_res.get("payload")
        svc = _extract_service_health(s_payload)

        if s_status == 200 and svc is not None:
            out["service_health"] = svc
        else:
            # keep it non-fatal; provide a hint if requested later
            out["service_health"] = svc or {}
            out["service_health_status"] = s_status
            if s_res.get("error"):
                out["service_health_error"] = s_res.get("error")

    # ---------------------------
    # Global errors (optional)
    # ---------------------------
    global_errors_items: List[Dict[str, Any]] = []
    if include_errors:
        ge_res = _call_tier1(
            "fabric_get_fabrics_errors",
            {},
            registry=registry,
            transport=transport,
        )
        ge_status = _coerce_int(ge_res.get("status", 0), 0)
        ge_payload = ge_res.get("payload")
        global_errors_items = _normalize_errors_items(ge_payload)

        global_errors_items, ge_trunc = _truncate_list(global_errors_items, max_error_items)

        out["global_errors"] = {
            "status": ge_status,
            "count": len(global_errors_items),
            "items": global_errors_items,
            "truncated": ge_trunc,
        }

    # ---------------------------
    # If no name => GLOBAL mode response
    # ---------------------------
    if not name:
        if expand_unhealthy and unhealthy_fabrics:
            expanded_items: List[Dict[str, Any]] = []
            to_expand, _ = _truncate_list(unhealthy_fabrics, max_expand)

            for f in to_expand:
                fname = f.get("fabric")
                if not fname:
                    continue

                h_res = _call_tier1(
                    "fabric_get_fabric_health",
                    {"name": fname},
                    registry=registry,
                    transport=transport,
                )

                h_status = _coerce_int(h_res.get("status", 0), 0)
                h_payload = h_res.get("payload")

                if h_status == 200 and isinstance(h_payload, dict):
                    headline = {
                        "fabric_health": _pick_first(h_payload, ["fabric-health", "fabric_health"]),
                        "topology_health": _safe_get(
                            h_payload, "fabric-level-physical-topology-health", "health", default=None
                        ),
                    }

                    device_health_list = _as_list(h_payload.get("device-health"))
                    agg_counts: Dict[str, int] = {}
                    unhealthy_count = 0

                    for d in device_health_list:
                        if not isinstance(d, dict):
                            continue
                        agg = _safe_get(d, "device-health", "aggregated-health", default=None)
                        if agg is not None:
                            agg_counts[agg] = agg_counts.get(agg, 0) + 1
                        if agg != "Green":
                            unhealthy_count += 1

                    expanded_items.append(
                        {
                            "fabric": fname,
                            "headline": headline,
                            "device_health_counts": agg_counts,
                            "unhealthy_count": unhealthy_count,
                            "unhealthy_truncated": False,
                            "include_raw": False,
                        }
                    )
                else:
                    expanded_items.append(
                        {
                            "fabric": fname,
                            "headline": {
                                "fabric_health": f.get("fabric_health"),
                                "topology_health": f.get("topology_health"),
                            },
                            "error": "Failed to expand unhealthy fabric via per-fabric health",
                            "tier1_status": h_status,
                        }
                    )

            out["expanded_unhealthy"] = {
                "count": len(expanded_items),
                "items": expanded_items,
            }

        out["next_actions"] = [
            {
                "reason": "Pick a fabric name from global_context.fabrics and call this tool with inputs.name",
                "tool": "fabric_get_fabric_health_summary",
                "inputs": {"name": "<FABRIC_NAME>"},
            }
        ]

        return {"status": 200, "payload": out}

    # ---------------------------
    # Per-fabric name validation (Fix for DOES_NOT_EXIST => MUST be 404)
    # ---------------------------
    # If we have a known list from global_context, we can hard-fail early and avoid
    # confusing "headline: null" 200 responses when Tier-1 returns odd shapes.
    known_names = _known_fabric_names(out)
    if known_names and name not in known_names:
        out["headline"] = {"fabric_health": None, "topology_health": None}
        out["device_health_counts"] = {}
        out["unhealthy_devices"] = []
        out["unhealthy_count"] = 0
        out["unhealthy_truncated"] = False
        out["error"] = f"Fabric '{name}' not found in fabrics health list"
        out["next_actions"] = [
            {
                "reason": "Use global mode to see valid fabric names.",
                "tool": "fabric_get_fabric_health_summary",
                "inputs": {},
            }
        ]
        return {"status": 404, "payload": out, "error": "fabric not found"}

    # ---------------------------
    # Per-fabric mode
    # ---------------------------

    # Per-fabric Tier-1 health (most detailed)
    health_res = _call_tier1(
        "fabric_get_fabric_health",
        {"name": name},
        registry=registry,
        transport=transport,
    )

    status = _coerce_int(health_res.get("status", 0), 0)
    payload = health_res.get("payload")

    # If the per-fabric tool name differs in this deployment, try alternate
    if (status != 200 or not isinstance(payload, dict)) and transport is not None:
        alt = _call_tier1(
            "fabric_get_health",
            {"name": name},
            registry=registry,
            transport=transport,
        )
        alt_status = _coerce_int(alt.get("status", 0), 0)
        alt_payload = alt.get("payload")
        if alt_status == 200 and isinstance(alt_payload, dict):
            status, payload = alt_status, alt_payload

    # If per-fabric failed, fallback: find it in fabrics-health list (if available)
    if status != 200 or not isinstance(payload, dict):
        fabrics = _safe_get(out, "global_context", "fabrics", default=[])
        match = None
        if isinstance(fabrics, list):
            for it in fabrics:
                if isinstance(it, dict) and it.get("fabric") == name:
                    match = it
                    break

        if match is not None:
            out["headline"] = {
                "fabric_health": match.get("fabric_health"),
                "topology_health": match.get("topology_health"),
            }
            out["device_health_counts"] = {}
            out["unhealthy_devices"] = []
            out["unhealthy_count"] = 0
            out["unhealthy_truncated"] = False

            out["next_actions"] = [
                {
                    "reason": "Per-fabric endpoint did not return details; check executions and events for clues.",
                    "tool": "fabric_get_execution_list",
                    "inputs": {"name": name},
                },
                {
                    "reason": "See current fabric events (often explains why health changed).",
                    "tool": "fabric_get_event_history_list",
                    "inputs": {"name": name},
                },
            ]
            return {"status": 200, "payload": out}

        out["error"] = f"Fabric '{name}' not found in fabrics health list"
        out["next_actions"] = [
            {
                "reason": "Use global mode to see valid fabric names.",
                "tool": "fabric_get_fabric_health_summary",
                "inputs": {},
            }
        ]
        return {"status": 404, "payload": out, "error": "fabric not found"}

    # Build headline + unhealthy device list from per-fabric payload
    out["headline"] = {
        "fabric_health": _pick_first(payload, ["fabric-health", "fabric_health"]),
        "topology_health": _safe_get(payload, "fabric-level-physical-topology-health", "health", default=None),
    }

    device_health_list = _as_list(payload.get("device-health"))
    agg_counts: Dict[str, int] = {}
    unhealthy: List[Dict[str, Any]] = []

    for d in device_health_list:
        if not isinstance(d, dict):
            continue
        dev_ip = _pick_first(d, ["device-ip", "device_ip"])
        role = d.get("role")
        agg = _safe_get(d, "device-health", "aggregated-health", default=None)

        if agg is not None:
            agg_counts[agg] = agg_counts.get(agg, 0) + 1

        if agg != "Green":
            cfg_state = _safe_get(d, "device-health", "config-state-health", "config-state-health", default=None)
            app_state = _safe_get(d, "device-health", "config-state-health", "app-state", "app-state", default=None)
            dev_state = _safe_get(d, "device-health", "config-state-health", "dev-state", "dev-state", default=None)
            oper_state = _safe_get(d, "device-health", "oper-state-health", "oper-state-health", default=None)

            unhealthy.append(
                {
                    "device_ip": dev_ip,
                    "role": role,
                    "aggregated_health": agg,
                    "config_state_health": cfg_state,
                    "app_state": app_state,
                    "device_state": dev_state,
                    "oper_state_health": oper_state,
                }
            )

    unhealthy, unhealthy_trunc = _truncate_list(unhealthy, max_unhealthy_devices)

    out["device_health_counts"] = agg_counts
    out["unhealthy_devices"] = unhealthy
    out["unhealthy_count"] = len(unhealthy)
    out["unhealthy_truncated"] = unhealthy_trunc

    # include raw payload (optional)
    if include_raw:
        out["health_raw"] = payload

    # ---------------------------
    # Per-fabric errors (optional) + Improvement #2 fallback
    # ---------------------------
    if include_errors:
        # ensure global_errors exists for fallback, even if earlier global_errors call failed
        if "global_errors" not in out:
            ge_res = _call_tier1(
                "fabric_get_fabrics_errors",
                {},
                registry=registry,
                transport=transport,
            )
            ge_status = _coerce_int(ge_res.get("status", 0), 0)
            ge_payload = ge_res.get("payload")
            global_errors_items = _normalize_errors_items(ge_payload)
            global_errors_items, ge_trunc = _truncate_list(global_errors_items, max_error_items)
            out["global_errors"] = {
                "status": ge_status,
                "count": len(global_errors_items),
                "items": global_errors_items,
                "truncated": ge_trunc,
            }

        fe_res = _call_tier1(
            "fabric_get_fabric_errors",
            {"name": name},
            registry=registry,
            transport=transport,
        )
        fe_status = _coerce_int(fe_res.get("status", 0), 0)
        fe_payload = fe_res.get("payload")

        per_items = _normalize_errors_items(fe_payload)
        per_items, fe_trunc = _truncate_list(per_items, max_error_items)

        # ---- Improvement #2:
        # If per-fabric endpoint returns 404 (or empty), derive from global_errors entry for this fabric.
        used_fallback = False
        if fe_status == 404 or (fe_status != 200 and not per_items):
            ge_items = _safe_get(out, "global_errors", "items", default=[])
            if isinstance(ge_items, list):
                ge_match = _find_global_errors_for_fabric(ge_items, name)
                if isinstance(ge_match, dict):
                    derived = _derive_fabric_errors_from_global(ge_match)

                    if not derived:
                        out["errors"] = {
                            "status": 200,
                            "count": 0,
                            "items": [],
                            "truncated": False,
                            "source": "global_errors_fallback",
                            "original_status": fe_status,
                        }
                        out["errors_note"] = "No per-device error details were present in global_errors for this fabric."
                        used_fallback = True
                    else:
                        derived, der_trunc = _truncate_list(derived, max_error_items)
                        out["errors"] = {
                            "status": 200,
                            "count": len(derived),
                            "items": derived,
                            "truncated": der_trunc,
                            "source": "global_errors_fallback",
                            "original_status": fe_status,
                        }
                        used_fallback = True

        if not used_fallback:
            out["errors"] = {
                "status": fe_status,
                "count": len(per_items),
                "items": per_items,
                "truncated": fe_trunc,
            }

    # Next actions (per-fabric)
    next_actions: List[Dict[str, Any]] = []

    if out.get("headline", {}).get("fabric_health") == "Red" and not include_errors:
        next_actions.append(
            {
                "reason": "Fabric health is Red. Enable include_errors for fast root-cause hints.",
                "tool": "fabric_get_fabric_health_summary",
                "inputs": {"name": name, "include_errors": True},
            }
        )

    next_actions.extend(
        [
            {
                "reason": "See current fabric events (often explains why health changed).",
                "tool": "fabric_get_event_history_list",
                "inputs": {"name": name},
            },
            {
                "reason": "Check recent executions and their outcomes.",
                "tool": "fabric_get_execution_list",
                "inputs": {"name": name},
            },
            {
                "reason": "If unhealthy devices exist, fetch topology to correlate where issues are located.",
                "tool": "fabric_get_physical_topology",
                "inputs": {"name": name},
            },
            {
                "reason": "If config state is Red/refreshed, inspect config show output.",
                "tool": "fabric_get_config_show",
                "inputs": {"name": name},
            },
        ]
    )

    out["next_actions"] = next_actions
    return {"status": 200, "payload": out}
