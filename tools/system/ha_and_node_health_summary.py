# tools/system/ha_and_node_health_summary.py

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _norm(s: Any) -> str:
    return str(s).strip() if s is not None else ""


def _as_list(x: Any) -> List[Any]:
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        if isinstance(x.get("items"), list):
            return x["items"]
        if isinstance(x.get("nodes"), list):
            return x["nodes"]
        if isinstance(x.get("services"), list):
            return x["services"]
    return []


def _contains_bad_tokens(text: str) -> bool:
    t = text.lower()
    return any(tok in t for tok in ("fail", "error", "down", "inactive", "stopped", "unhealthy", "degrad", "critical"))


def _health_is_problem(rec: Dict[str, Any]) -> bool:
    """
    Conservative health evaluator.
    Your lab shows HQI.Value=5 with StatusText=Success, so we:
      - trust StatusText first
      - treat obvious red/yellow/orange colors as problems
      - treat very low values as suspicious only if StatusText is not Success/OK
    """
    st = _norm(rec.get("StatusText"))
    st_l = st.lower()
    if st_l in ("success", "ok", "healthy"):
        return False
    if st and _contains_bad_tokens(st):
        return True

    hqi = rec.get("HQI") if isinstance(rec.get("HQI"), dict) else {}
    color = _norm(hqi.get("Color")).lower()
    if color in ("red", "yellow", "orange"):
        return True

    val = hqi.get("Value")
    try:
        v = int(val) if val is not None else None
    except Exception:
        v = None

    # If StatusText is unknown/empty, use value as a weak signal
    if (not st) and (v is not None) and v <= 1:
        return True

    return False


def _pick_resource_field(rec: Dict[str, Any]) -> Optional[str]:
    # health items usually use "Resource"; inventory/detail often use "resource"
    r = rec.get("resource")
    if isinstance(r, str) and r:
        return r
    r = rec.get("Resource")
    if isinstance(r, str) and r:
        return r
    return None


def _call_tier1(tool_name: str, params: Dict[str, Any], *, registry, transport, context: Dict[str, Any]) -> Dict[str, Any]:
    tool_def = registry.get(tool_name) if registry is not None else None
    if not isinstance(tool_def, dict):
        return {"status": 500, "payload": None, "error": f"Tier-1 tool not found in registry: {tool_name}"}

    endpoint = tool_def.get("endpoint", {}) or {}
    path = endpoint.get("path")
    port = endpoint.get("port")
    method = (tool_def.get("method") or "GET").upper()

    if not isinstance(path, str) or not path.startswith("/"):
        return {"status": 500, "payload": None, "error": f"Invalid endpoint path for {tool_name}"}

    return transport.request(method=method, path=path, params=params, port=port, context=context)


def _format_not_deployed_warning(tool: str, r: Dict[str, Any], human_name: str) -> str:
    """
    If a Tier-1 monitor status endpoint returns a "not deployed" message (often wrapped as 500 with code=404),
    report it as topology/config info instead of a scary failure.
    """
    payload = r.get("payload")
    if isinstance(payload, dict):
        msg = str(payload.get("message") or "").strip()
        code = payload.get("code")
        if (code == 404) and ("not deployed" in msg.lower()):
            return f"{human_name} not deployed (non-HA / single-node deployment)."
    return f"{tool} returned {r.get('status')}"


def system_get_ha_and_node_health_summary(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
):
    """
    Tier-2: HA + node + storage + health correlation summary.

    Uses ONLY existing Tier-1 tools:
      - system_get_health_status
      - monitor_get_keep_alived_info
      - monitor_get_gluster_fs_info
      - monitor_get_k3s_nodes
      - monitor_get_health
      - monitor_get_health_inventory (optional)
      - monitor_get_health_detail (optional)
    """

    include_system = bool(inputs.get("include_system_health_status", True))
    include_monitor = bool(inputs.get("include_monitor", True))

    include_keepalived = bool(inputs.get("include_keepalived", True))
    include_gluster = bool(inputs.get("include_gluster", True))
    include_k3s_nodes = bool(inputs.get("include_k3s_nodes", True))

    include_health = bool(inputs.get("include_health", True))
    include_health_inventory = bool(inputs.get("include_health_inventory", True))
    include_health_detail = bool(inputs.get("include_health_detail", False))
    detail_only_on_problem = bool(inputs.get("detail_only_on_problem", True))
    max_detail = int(inputs.get("max_detail", 10) or 10)
    max_detail = max(1, min(max_detail, 50))

    include_raw = bool(inputs.get("include_raw", False))

    input_echo = {
        "include_system_health_status": include_system,
        "include_monitor": include_monitor,
        "include_keepalived": include_keepalived,
        "include_gluster": include_gluster,
        "include_k3s_nodes": include_k3s_nodes,
        "include_health": include_health,
        "include_health_inventory": include_health_inventory,
        "include_health_detail": include_health_detail,
        "detail_only_on_problem": detail_only_on_problem,
        "max_detail": max_detail,
        "include_raw": include_raw,
    }

    warnings: List[str] = []
    tier1_raw: Dict[str, Any] = {}

    # ----------------------------
    # 1) Tier-1 pulls
    # ----------------------------
    system_status = None
    if include_system:
        r = _call_tier1("system_get_health_status", {}, registry=registry, transport=transport, context=context)
        if include_raw:
            tier1_raw["system_get_health_status"] = r
        if int(r.get("status") or 500) == 200:
            system_status = r.get("payload")
        else:
            warnings.append(f"system_get_health_status returned {r.get('status')}")

    keepalived = None
    gluster = None
    k3s_nodes = None

    if include_monitor:
        if include_keepalived:
            r = _call_tier1("monitor_get_keep_alived_info", {}, registry=registry, transport=transport, context=context)
            if include_raw:
                tier1_raw["monitor_get_keep_alived_info"] = r
            if int(r.get("status") or 500) == 200:
                keepalived = r.get("payload")
            else:
                warnings.append(_format_not_deployed_warning("monitor_get_keep_alived_info", r, "Keepalived"))

        if include_gluster:
            r = _call_tier1("monitor_get_gluster_fs_info", {}, registry=registry, transport=transport, context=context)
            if include_raw:
                tier1_raw["monitor_get_gluster_fs_info"] = r
            if int(r.get("status") or 500) == 200:
                gluster = r.get("payload")
            else:
                warnings.append(_format_not_deployed_warning("monitor_get_gluster_fs_info", r, "GlusterFS"))

        if include_k3s_nodes:
            r = _call_tier1("monitor_get_k3s_nodes", {}, registry=registry, transport=transport, context=context)
            if include_raw:
                tier1_raw["monitor_get_k3s_nodes"] = r
            if int(r.get("status") or 500) == 200:
                k3s_nodes = r.get("payload")
            else:
                warnings.append(f"monitor_get_k3s_nodes returned {r.get('status')}")

    health_items: List[Dict[str, Any]] = []
    if include_health and include_monitor:
        r = _call_tier1("monitor_get_health", {"detail": False}, registry=registry, transport=transport, context=context)
        if include_raw:
            tier1_raw["monitor_get_health"] = r
        if int(r.get("status") or 500) == 200 and isinstance(r.get("payload"), dict):
            health_items = [x for x in _as_list(r["payload"]) if isinstance(x, dict)]
        else:
            warnings.append(f"monitor_get_health returned {r.get('status')}")

    # ----------------------------
    # 2) Basic problem signals
    # ----------------------------
    ha_problem = False
    storage_problem = False
    node_problem = False

    # HA heuristic: scan keepalived text
    if isinstance(keepalived, (dict, list)):
        if _contains_bad_tokens(_norm(keepalived)):
            ha_problem = True

    # Storage heuristic: scan gluster text
    if isinstance(gluster, (dict, list)):
        if _contains_bad_tokens(_norm(gluster)):
            storage_problem = True

    # K3s node heuristic: look for Ready/NotReady if present
    if isinstance(k3s_nodes, dict):
        nodes = _as_list(k3s_nodes)
        for n in nodes:
            if not isinstance(n, dict):
                continue
            st = _norm(n.get("status") or n.get("Status") or n.get("state"))
            if st and _contains_bad_tokens(st):
                node_problem = True
            # common k8s-style
            if st.lower() in ("notready", "not ready"):
                node_problem = True

    # Health problems
    health_problems = [x for x in health_items if _health_is_problem(x)]
    health_problem = len(health_problems) > 0

    # ----------------------------
    # 3) Optional: inventory + detail correlation
    # ----------------------------
    health_detail: Optional[List[Dict[str, Any]]] = None
    detail_fetched = 0

    if include_health and include_monitor and include_health_detail:
        # discover candidate resources
        candidates: List[str] = []
        if include_health_inventory:
            inv = _call_tier1("monitor_get_health_inventory", {"resource": "/"}, registry=registry, transport=transport, context=context)
            if include_raw:
                tier1_raw["monitor_get_health_inventory:/"] = inv
            if int(inv.get("status") or 500) == 200:
                inv_items = [x for x in _as_list(inv.get("payload")) if isinstance(x, dict)]
                for rec in inv_items:
                    rpath = _pick_resource_field(rec)
                    if not rpath:
                        continue
                    rp_l = rpath.lower()
                    if any(tok in rp_l for tok in ("ha", "keepaliv", "gluster", "stor", "node", "k3s", "mariadb")):
                        candidates.append(rpath)

        # Always include root if we have nothing else
        if not candidates:
            candidates = ["/"]

        # de-dupe, cap
        seen = set()
        uniq = []
        for c in candidates:
            if c in seen:
                continue
            seen.add(c)
            uniq.append(c)
        candidates = uniq[:max_detail]

        details: List[Dict[str, Any]] = []
        for rpath in candidates:
            d = _call_tier1("monitor_get_health_detail", {"resource": rpath}, registry=registry, transport=transport, context=context)
            if include_raw:
                tier1_raw[f"monitor_get_health_detail:{rpath}"] = d
            if int(d.get("status") or 500) != 200:
                continue

            payload = d.get("payload")
            if isinstance(payload, list):
                rows = payload
            elif isinstance(payload, dict):
                rows = _as_list(payload)
            else:
                rows = []

            for row in rows:
                if not isinstance(row, dict):
                    continue
                # If detail_only_on_problem, keep only problematic detail rows
                if detail_only_on_problem and (not _health_is_problem(row)):
                    continue
                details.append(row)

            detail_fetched += 1

        health_detail = details if details else []

    # ----------------------------
    # 4) Output
    # ----------------------------
    platform_ok = not (ha_problem or storage_problem or node_problem or health_problem)

    summary = {
        "platform_ok": platform_ok,
        "signals": {
            "ha_problem": ha_problem,
            "storage_problem": storage_problem,
            "node_problem": node_problem,
            "health_problem": health_problem,
        },
        "counts": {
            "health_items_total": len(health_items),
            "health_items_problem": len(health_problems),
            "health_detail_fetched": detail_fetched,
        },
    }

    out = {
        "input_echo": input_echo,
        "summary": summary,
        "system_health_status": system_status,
        "ha_keepalived": keepalived,
        "storage_gluster": gluster,
        "k3s_nodes": k3s_nodes,
        "health": {
            "items": health_items,
            "top_problems": health_problems[:max_detail],
            "detail": health_detail,
        } if include_health else None,
        "warnings": warnings,
    }

    if include_raw:
        out["tier1_raw"] = tier1_raw

    return out

