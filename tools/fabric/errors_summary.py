# tools/fabric/errors_summary.py

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


def _truncate_list(items: List[Any], max_items: int) -> Tuple[List[Any], bool]:
    if max_items <= 0:
        return [], bool(items)
    if len(items) <= max_items:
        return items, False
    return items[:max_items], True


def _pick_first(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


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


# ---------------------------
# Transport adapter
# ---------------------------

def _transport_get(transport: Any, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort adapter for whatever transport object the runtime passes.
    Expected return: {"status": int, "payload": Any, ...}
    """
    for meth_name in ("request", "send", "call"):
        fn = getattr(transport, meth_name, None)
        if not callable(fn):
            continue
        try:
            res = fn(method="GET", path=path, params=params)
            if isinstance(res, dict) and "status" in res:
                return res
        except TypeError:
            # signature mismatch, try next
            pass
        except Exception as e:
            return {"status": 500, "payload": None, "error": f"transport.{meth_name} failed: {e}"}

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
    3) Else last-resort hardcoded GET paths for the small set we need.
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
                    # signature mismatch, try next
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

    # 3) Last-resort hardcoded paths (kept tight)
    if transport is not None:
        if tool_name == "fabric_get_fabrics":
            return _transport_get(transport, "/v1/fabric/fabrics", tool_inputs)
        if tool_name == "fabric_get_fabric_errors":
            return _transport_get(transport, "/v1/fabric/errors", tool_inputs)
        if tool_name == "fabric_get_fabrics_errors":
            return _transport_get(transport, "/v1/fabric/fabrics/errors", tool_inputs)
        if tool_name in ("fabric_get_fabric_health", "fabric_get_health"):
            return _transport_get(transport, "/v1/fabric/fabric-health", tool_inputs)

    return {"status": 500, "payload": None, "error": f"Tool not registered / callable: {tool_name}"}


# ---------------------------
# Normalizers / summarizers
# ---------------------------

def _extract_fabric_summary_row(fabrics_payload: Any, name: str) -> Optional[Dict[str, Any]]:
    items = _as_list(fabrics_payload)
    for row in items:
        if not isinstance(row, dict):
            continue
        fname = _pick_first(row, ["fabric-name", "fabric_name", "name", "fabric"])
        if fname == name:
            return row
    return None


def _normalize_errors_items(payload: Any) -> List[Dict[str, Any]]:
    """
    Fabric errors payload shapes vary by deployment.
    We try to produce a list of dict items when possible.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
        nested = payload.get("payload")
        if isinstance(nested, dict):
            items2 = nested.get("items")
            if isinstance(items2, list):
                return [x for x in items2 if isinstance(x, dict)]
    return []


def _summarize_errors(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Produce lightweight rollups: top types, affected devices, severities, etc.
    Works even if fields are unknown (best-effort).
    """
    type_counts: Dict[str, int] = {}
    sev_counts: Dict[str, int] = {}
    device_set = set()

    def bump(m: Dict[str, int], k: Optional[Any]):
        if k is None:
            return
        ks = str(k)
        if not ks:
            return
        m[ks] = m.get(ks, 0) + 1

    for it in items:
        if not isinstance(it, dict):
            continue

        etype = _pick_first(it, ["type", "error_type", "category", "code", "name", "title"])
        sev = _pick_first(it, ["severity", "level", "priority"])
        dev = _pick_first(it, ["device_ip", "device-ip", "ip", "ip-address", "device", "device_name", "host-name"])

        bump(type_counts, etype)
        bump(sev_counts, sev)
        if dev is not None:
            device_set.add(str(dev))

    top_types = sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    top_sev = sorted(sev_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

    return {
        "top_error_types": [{"type": k, "count": v} for k, v in top_types],
        "top_severities": [{"severity": k, "count": v} for k, v in top_sev],
        "affected_devices": sorted(device_set)[:50],
        "affected_devices_truncated": len(device_set) > 50,
    }


def _health_counts(health_payload: Any) -> Dict[str, Any]:
    """
    From fabric-health payload, extract:
    - fabric health
    - topology health
    - device aggregated-health counts
    """
    out = {
        "fabric_health": None,
        "topology_health": None,
        "device_health_counts": {},
        "unhealthy_devices": 0,
    }
    if not isinstance(health_payload, dict):
        return out

    out["fabric_health"] = _pick_first(health_payload, ["fabric-health", "fabric_health", "health"])
    out["topology_health"] = _safe_get(health_payload, "fabric-level-physical-topology-health", "health", default=None)

    devs = health_payload.get("device-health")
    if isinstance(devs, list):
        counts: Dict[str, int] = {}
        bad = 0
        for d in devs:
            if not isinstance(d, dict):
                continue
            agg = _safe_get(d, "device-health", "aggregated-health", default=None)
            if agg is None:
                continue
            agg_s = str(agg)
            counts[agg_s] = counts.get(agg_s, 0) + 1
            if agg_s.lower() != "green":
                bad += 1
        out["device_health_counts"] = counts
        out["unhealthy_devices"] = bad

    return out


# ---------------------------
# Tier-2 tool
# ---------------------------

def fabric_get_fabric_errors_summary(
    inputs: Dict[str, Any],
    *,
    registry=None,
    transport=None,
    http_client=None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Tier-2: Fabric errors summary.
    Composite of:
      - fabric_get_fabrics (validate fabric exists)
      - fabric_get_fabric_errors (per-fabric errors)
      - optional fabric_get_fabrics_errors (global errors context)
      - optional fabric_get_fabric_health (health context)
    """
    _ = http_client  # Tier-2 should not call HTTP directly

    # Inputs
    name = inputs.get("name") or inputs.get("fabric_name") or inputs.get("fabric-name")
    if not name:
        return {"status": 400, "payload": {"error": "Missing required input: name"}, "error": "bad request"}

    include_health = _coerce_bool(inputs.get("include_health"), True)
    include_global = _coerce_bool(inputs.get("include_global"), False)
    include_raw = _coerce_bool(inputs.get("include_raw"), False)
    max_error_items = _coerce_int(inputs.get("max_error_items"), 50)

    filt = {
        "name": name,
        "include_health": include_health,
        "include_global": include_global,
        "max_error_items": max_error_items,
        "include_raw": include_raw,
    }

    # Track raw tier-1 responses (for include_raw)
    ge_res: Optional[Dict[str, Any]] = None
    h_res: Optional[Dict[str, Any]] = None

    # Validate fabric exists via fabric_get_fabrics
    fabrics_res = _call_tier1("fabric_get_fabrics", {}, registry=registry, transport=transport)
    fabrics_status = int(fabrics_res.get("status") or 500)
    fabrics_payload = fabrics_res.get("payload")

    row = None
    if fabrics_status == 200:
        row = _extract_fabric_summary_row(fabrics_payload, name)

    if row is None:
        out_404 = {
            "filter": filt,
            "error": f"Fabric '{name}' not found",
            "known_fabrics_count": len(_as_list(fabrics_payload)) if fabrics_status == 200 else None,
            "next_actions": [
                {
                    "reason": "List valid fabrics (or use overview to discover names).",
                    "tool": "fabric_get_fabric_overview",
                    "inputs": {"include_health": True, "include_errors": True},
                }
            ],
        }
        return {"status": 404, "payload": out_404, "error": "fabric not found"}

    # Call per-fabric errors (Tier-1 schema uses "fabric-name")
    per_errors_res = _call_tier1(
        "fabric_get_fabric_errors",
        {"fabric-name": name},
        registry=registry,
        transport=transport,
    )
    per_status = int(per_errors_res.get("status") or 500)
    per_payload = per_errors_res.get("payload")

    per_items = _normalize_errors_items(per_payload) if per_status == 200 else []
    per_items, per_trunc = _truncate_list(per_items, max_error_items)

    # "Thin" endpoint detection:
    # - If payload is dict but does NOT have an "items" list, then we cannot claim "no errors",
    #   only "inconclusive".
    thin_note = None
    explicit_empty_items = False
    if per_status == 200 and isinstance(per_payload, dict):
        if "items" in per_payload and isinstance(per_payload.get("items"), list):
            explicit_empty_items = (len(per_payload.get("items")) == 0)
        elif "payload" in per_payload and isinstance(per_payload.get("payload"), dict):
            nested = per_payload.get("payload")
            if isinstance(nested, dict) and "items" in nested and isinstance(nested.get("items"), list):
                explicit_empty_items = (len(nested.get("items")) == 0)
            else:
                thin_note = "Errors endpoint returned no item list; explicit errors are unknown (treat as inconclusive)."
        else:
            thin_note = "Errors endpoint returned no item list; explicit errors are unknown (treat as inconclusive)."

    # Optional global context
    global_errors = None
    if include_global:
        ge_res = _call_tier1("fabric_get_fabrics_errors", {}, registry=registry, transport=transport)
        global_status = int(ge_res.get("status") or 500)
        ge_payload = ge_res.get("payload")
        ge_items = _normalize_errors_items(ge_payload) if global_status == 200 else []
        global_errors = {
            "status": global_status,
            "count": len(ge_items),
            "note": None,
        }
        if global_status != 200:
            global_errors["note"] = "Global fabrics errors endpoint did not return 200."
        elif len(ge_items) == 0:
            global_errors["note"] = "Global endpoint returned no error items."

    # Optional health context
    health_ctx = None
    health_headline = None
    if include_health:
        h_res = _call_tier1(
            "fabric_get_fabric_health",
            {"name": name},
            registry=registry,
            transport=transport,
        )
        h_status = int(h_res.get("status") or 500)
        h_payload = h_res.get("payload")
        health_headline = _health_counts(h_payload) if h_status == 200 else None
        health_ctx = {"status": h_status, "headline": health_headline}

    # Summaries
    errors_summary = _summarize_errors(per_items)

    # ---------------------------
    # Determine verdict (honest + context-aware)
    # ---------------------------
    verdict = "WARN"

    if per_status == 200:
        if len(per_items) > 0:
            verdict = "FAIL"
        else:
            # Only PASS if endpoint explicitly reports empty list (not thin)
            if thin_note:
                verdict = "WARN"
            else:
                # explicit empty list OR payload list empty is considered PASS (errors-only)
                verdict = "PASS"
    else:
        verdict = "WARN"

    # If health indicates problems, don't claim PASS
    if verdict == "PASS" and include_health and isinstance(health_headline, dict):
        fabric_health = (health_headline.get("fabric_health") or "")
        unhealthy = int(health_headline.get("unhealthy_devices") or 0)
        if fabric_health and str(fabric_health).strip().lower() != "green":
            verdict = "WARN"
        if unhealthy > 0:
            verdict = "WARN"

    # If global context shows errors exist, prefer WARN (cannot attribute without details)
    if verdict == "PASS" and include_global and isinstance(global_errors, dict):
        if int(global_errors.get("count") or 0) > 0:
            verdict = "WARN"

    # ---------------------------
    # Recommendations + next actions
    # ---------------------------
    recommendations: List[str] = []
    next_actions: List[Dict[str, Any]] = []

    if verdict == "FAIL":
        recommendations.append("Fabric errors detected. Inspect error details and correlate with events/executions.")
        next_actions.extend(
            [
                {
                    "reason": "See recent fabric events (often explains reported errors).",
                    "tool": "fabric_get_event_history_list",
                    "inputs": {"name": name},
                },
                {
                    "reason": "Check recent executions and their outcomes.",
                    "tool": "fabric_get_execution_list",
                    "inputs": {"name": name},
                },
                {
                    "reason": "Get a broader health + context summary (devices, service health, optional errors).",
                    "tool": "fabric_get_fabric_health_summary",
                    "inputs": {"name": name, "include_errors": True},
                },
            ]
        )
    else:
        # PASS / WARN
        if thin_note:
            recommendations.append(thin_note)
            next_actions.append(
                {
                    "reason": "If health is degraded, check timeline/executions for root cause.",
                    "tool": "fabric_get_fabric_health_timeline",
                    "inputs": {"name": name, "include_exec_details": False},
                }
            )

        if include_global and isinstance(global_errors, dict) and int(global_errors.get("count") or 0) > 0:
            recommendations.append("Global fabric errors exist. Review whether they relate to this fabric.")
            next_actions.append(
                {
                    "reason": "Inspect global fabrics errors to see what fabrics/devices are affected.",
                    "tool": "fabric_get_fabrics_errors",
                    "inputs": {},
                }
            )

    # Build output
    out: Dict[str, Any] = {
        "filter": filt,
        "summary": {
            "fabric": name,
            "verdict": verdict,
            "errors_count": len(per_items) if per_status == 200 else None,
            "errors_truncated": per_trunc if per_status == 200 else None,
        },
        "signals": {
            "fabric_summary_row": {
                "fabric-name": row.get("fabric-name"),
                "fabric-id": row.get("fabric-id"),
                "fabric-health": row.get("fabric-health"),
                "fabric-status": row.get("fabric-status"),
                "fabric-type": row.get("fabric-type"),
                "fabric-stage": row.get("fabric-stage"),
            },
            "errors": {
                "status": per_status,
                "count": len(per_items) if per_status == 200 else 0,
                "items": per_items if per_status == 200 else [],
                "truncated": per_trunc if per_status == 200 else False,
                "note": thin_note,
            },
            "errors_summary": errors_summary,
            "global_errors": global_errors,
            "health": health_ctx,
        },
        "recommendations": recommendations,
        "next_actions": next_actions,
    }

    if include_raw:
        raw: Dict[str, Any] = {
            "fabric_get_fabrics": fabrics_res,
            "fabric_get_fabric_errors": per_errors_res,
        }
        if include_health and h_res is not None:
            raw["fabric_get_fabric_health"] = h_res
        if include_global and ge_res is not None:
            raw["fabric_get_fabrics_errors"] = ge_res
        out["raw"] = raw

    # If Tier-1 per-errors endpoint failed, provide actionable next steps
    if per_status != 200:
        out["recommendations"].append(
            "Per-fabric errors endpoint did not return 200; treat errors state as unknown."
        )
        out["next_actions"].extend(
            [
                {
                    "reason": "Try overview (often includes errors context via other endpoints).",
                    "tool": "fabric_get_fabric_overview",
                    "inputs": {"fabric_name": name, "include_health": True, "include_errors": True},
                },
                {
                    "reason": "Check health timeline for correlated events/executions.",
                    "tool": "fabric_get_fabric_health_timeline",
                    "inputs": {"name": name, "include_exec_details": False},
                },
            ]
        )

    return {"status": 200, "payload": out}

