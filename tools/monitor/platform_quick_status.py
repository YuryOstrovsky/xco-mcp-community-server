# tools/monitor/platform_quick_status.py

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ------------------------------------------------------------
# Small helpers (defensive parsing)
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


def _safe_get(d: Any, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _extract_list(payload: Any, preferred_keys: List[str]) -> List[dict]:
    """Extract a list[dict] from common response shapes."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in preferred_keys:
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        items = payload.get("items")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
    return []


def _health_is_problem(rec: dict) -> bool:
    """
    Health manager varies across environments. In your lab:
      - StatusText may be "Success"
      - HQI.Color may be "Black"
      - HQI.Value may be non-zero even when OK
    So we treat StatusText Success/OK/Healthy as healthy, and only treat
    explicit bad colors / text / contributors as problems.
    """
    st = str(rec.get("StatusText") or "").strip().lower()

    # Your lab's healthy signal
    if st in ("success", "ok", "healthy"):
        return False

    # If status text explicitly indicates problems
    if any(tok in st for tok in ("fail", "error", "unhealthy", "degraded", "down")):
        return True

    hqi = rec.get("HQI") if isinstance(rec, dict) else None
    if isinstance(hqi, dict):
        color = str(hqi.get("Color") or "").strip().lower()

        # treat only clearly bad colors as problems
        if color in ("red", "orange", "yellow"):
            return True

        # don't treat non-green as automatically bad in this lab
        # (black/unknown may still be fine)

    # Default: if nothing screams "bad", consider healthy
    return False



def _service_is_problem(rec: dict) -> bool:
    status = str(rec.get("status") or "").strip().lower()
    active = str(rec.get("active") or "").strip().lower()

    # systemd-style strings from your lab, e.g.
    # "active (running) since Mon ..."
    if "(running)" in active or active.startswith("active"):
        return False

    # common health words
    if status in ("ok", "healthy", "running", "active", "up"):
        return False

    # some payloads may use boolean-ish active fields
    if active in ("true", "yes", "1", "active", "running", "up"):
        return False

    # explicit negative tokens
    if any(tok in status for tok in ("down", "fail", "error", "unhealthy", "stopped", "inactive")):
        return True
    if any(tok in active for tok in ("down", "false", "no", "0", "inactive", "stopped", "dead", "failed")):
        return True

    # if we really can't tell, don't mark as problem
    return False



def _node_is_problem(rec: dict) -> bool:
    status = str(rec.get("status") or "").strip().lower()
    if status in ("up", "ready", "ok", "healthy", "running"):
        return False
    if any(tok in status for tok in ("down", "fail", "error", "unhealthy", "notready", "not ready")):
        return True
    return bool(status) and status not in ("up", "ready", "ok", "healthy", "running")


# ------------------------------------------------------------
# Tool implementation
# ------------------------------------------------------------

def monitor_get_platform_quick_status(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """Tier-2 composite: platform heartbeat (EFA + services + health).

    Uses ONLY existing Tier-1 tools in this repo:
      - monitor_get_efa_status
      - monitor_get_service_status
      - monitor_get_health
      - monitor_get_health_detail (optional)
    """

    inputs = inputs or {}

    include_efa = _as_bool(inputs.get("include_efa"), True)
    include_services = _as_bool(inputs.get("include_services"), True)
    include_health = _as_bool(inputs.get("include_health"), True)
    include_health_detail = _as_bool(inputs.get("include_health_detail"), False)
    detail_only_on_problem = _as_bool(inputs.get("detail_only_on_problem"), True)
    max_detail = max(0, min(_as_int(inputs.get("max_detail"), 10), 200))
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

    # --------------------------------------------------------
    # 1) Fetch requested Tier-1 payloads
    # --------------------------------------------------------

    efa_res = None
    svc_res = None
    health_res = None

    if include_efa:
        efa_res = call_tier1("monitor_get_efa_status")
        if include_raw:
            tier1_raw["monitor_get_efa_status"] = efa_res
        if int(efa_res.get("status") or 0) != 200:
            warnings.append(f"monitor_get_efa_status failed (status={efa_res.get('status')}).")

    if include_services:
        svc_res = call_tier1("monitor_get_service_status")
        if include_raw:
            tier1_raw["monitor_get_service_status"] = svc_res
        if int(svc_res.get("status") or 0) != 200:
            warnings.append(f"monitor_get_service_status failed (status={svc_res.get('status')}).")

    if include_health:
        # keep it light: summary view; health_detail provides deep-dive
        health_res = call_tier1("monitor_get_health", {"detail": False})
        if include_raw:
            tier1_raw["monitor_get_health"] = health_res
        if int(health_res.get("status") or 0) != 200:
            warnings.append(f"monitor_get_health failed (status={health_res.get('status')}).")

    ok_any = any(
        int((r or {}).get("status") or 0) == 200
        for r in (efa_res, svc_res, health_res)
        if r is not None
    )
    if not ok_any:
        return {
            "status": 502,
            "error": "all tier1 calls failed",
            "payload": {
                "input_echo": {
                    "include_efa": include_efa,
                    "include_services": include_services,
                    "include_health": include_health,
                    "include_health_detail": include_health_detail,
                    "detail_only_on_problem": detail_only_on_problem,
                    "max_detail": max_detail,
                    "include_raw": include_raw,
                },
                "warnings": warnings or ["No Tier-1 data could be fetched."],
                **({"tier1_raw": tier1_raw} if include_raw else {}),
            },
        }

    # --------------------------------------------------------
    # 2) Parse + summarize
    # --------------------------------------------------------

    efa_nodes: List[dict] = []
    services: List[dict] = []
    health_items: List[dict] = []

    if isinstance(efa_res, dict) and int(efa_res.get("status") or 0) == 200:
        efa_nodes = _extract_list(efa_res.get("payload"), ["nodes", "Nodes"])

    if isinstance(svc_res, dict) and int(svc_res.get("status") or 0) == 200:
        services = _extract_list(svc_res.get("payload"), ["services", "Services"])

    if isinstance(health_res, dict) and int(health_res.get("status") or 0) == 200:
        health_items = _extract_list(health_res.get("payload"), ["items", "Items"])

    efa_problems = [n for n in efa_nodes if _node_is_problem(n)]
    svc_problems = [s for s in services if _service_is_problem(s)]
    health_problems = [h for h in health_items if _health_is_problem(h)]

    def _hqi_value(h: dict) -> int:
        try:
            return int(_safe_get(h, "HQI", "Value", default=0) or 0)
        except Exception:
            return 0

    health_problems_sorted = sorted(health_problems, key=_hqi_value, reverse=True)

    top_health_problems = []
    for h in health_problems_sorted[: min(len(health_problems_sorted), 20)]:
        top_health_problems.append(
            {
                "resource": h.get("Resource"),
                "hqi": h.get("HQI"),
                "status_text": h.get("StatusText"),
            }
        )

    # --------------------------------------------------------
    # 3) Optional health detail (only for selected resources)
    # --------------------------------------------------------

    health_detail: List[dict] = []
    if include_health and include_health_detail and max_detail > 0 and health_items:
        candidates = health_items
        if detail_only_on_problem:
            candidates = health_problems_sorted

        selected_resources: List[str] = []
        for h in candidates:
            r = _norm_str(h.get("Resource"))
            if r and r not in selected_resources:
                selected_resources.append(r)
            if len(selected_resources) >= max_detail:
                break

        for r in selected_resources:
            det = call_tier1("monitor_get_health_detail", {"resource": r})
            if include_raw:
                tier1_raw[f"monitor_get_health_detail:{r}"] = det
            if int(det.get("status") or 0) != 200:
                warnings.append(f"monitor_get_health_detail failed for resource={r} (status={det.get('status')}).")
                continue
            payload = det.get("payload")
            if isinstance(payload, dict):
                health_detail.append(
                    {
                        "resource": payload.get("Resource") or r,
                        "hqi": payload.get("HQI"),
                        "contributors": payload.get("Contributors"),
                        "status_text": payload.get("StatusText"),
                    }
                )

    # --------------------------------------------------------
    # 4) Overall summary + response
    # --------------------------------------------------------

    summary = {
        "efa": {
            "included": include_efa,
            "nodes_total": len(efa_nodes),
            "nodes_problem": len(efa_problems),
        },
        "services": {
            "included": include_services,
            "services_total": len(services),
            "services_problem": len(svc_problems),
        },
        "health": {
            "included": include_health,
            "resources_total": len(health_items),
            "resources_problem": len(health_problems),
            "detail_fetched": len(health_detail),
        },
    }

    platform_ok = True
    if include_efa and len(efa_problems) > 0:
        platform_ok = False
    if include_services and len(svc_problems) > 0:
        platform_ok = False
    if include_health and len(health_problems) > 0:
        platform_ok = False

    payload = {
        "input_echo": {
            "include_efa": include_efa,
            "include_services": include_services,
            "include_health": include_health,
            "include_health_detail": include_health_detail,
            "detail_only_on_problem": detail_only_on_problem,
            "max_detail": max_detail,
            "include_raw": include_raw,
        },
        "platform_ok": platform_ok,
        "summary": summary,
        "efa": (
            {"nodes": efa_nodes, "problems": efa_problems}
            if include_efa
            else None
        ),
        "services": (
            {"services": services, "problems": svc_problems}
            if include_services
            else None
        ),
        "health": (
            {
                "items": health_items,
                "top_problems": top_health_problems,
                "detail": health_detail if include_health_detail else None,
            }
            if include_health
            else None
        ),
        "warnings": warnings,
        **({"tier1_raw": tier1_raw} if include_raw else {}),
    }

    return {"status": 200, "payload": payload}

