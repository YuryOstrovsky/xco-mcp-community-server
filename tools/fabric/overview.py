# tools/fabric/overview.py

from typing import Any, Dict, List, Optional
from collections import Counter


def fabric_get_fabric_overview(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
) -> dict:
    """
    Tier-2 composite tool: Fabric overview.

    Use-cases:
      - "Show me my fabrics"
      - "Give me a quick fabric overview with health and errors"
      - "Summarize fabric health and identify key problem devices quickly"
      - Optional: include raw payloads for deep-dive (large)

    Rules:
      - Calls ONLY existing Tier-1 tools via registry (no endpoint paths here).
      - No inference / no invented endpoints.
    """

    # -------------------------------
    # Inputs (safe defaults)
    # -------------------------------
    fabric_name = inputs.get("fabric_name")
    include_health = bool(inputs.get("include_health", True))
    include_errors = bool(inputs.get("include_errors", True))
    include_devices = bool(inputs.get("include_devices", False))
    include_raw = bool(inputs.get("include_raw", False))

    # Optional: allow context to provide fabric name
    if not fabric_name:
        fabric_ctx = (context or {}).get("fabric") or {}
        if isinstance(fabric_ctx, dict) and fabric_ctx.get("name"):
            fabric_name = fabric_ctx["name"]

    warnings: List[str] = []

    # -------------------------------
    # Helper: invoke Tier-1 by name
    # -------------------------------
    def call_tier1(tool_name: str, params: Optional[dict] = None) -> dict:
        tool = registry.get(tool_name)
        if not tool:
            return {
                "status": 0,
                "payload": None,
                "error": f"Tier-1 tool not found in registry: {tool_name}",
            }

        endpoint = tool.get("endpoint") or {}
        path = endpoint.get("path")
        method = tool.get("method")

        if not path or not method:
            return {
                "status": 0,
                "payload": None,
                "error": f"Tier-1 tool missing endpoint/method: {tool_name}",
            }

        return transport.request(
            method=method,
            port=endpoint.get("port"),
            path=path,
            params=params or {},
            context=context or {},
        )

    # -------------------------------
    # Helpers: normalize payload shapes
    # -------------------------------
    def as_list(payload: Any) -> List:
        if payload is None:
            return []
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("items", "fabrics", "fabric-list", "fabric", "data"):
                val = payload.get(key)
                if isinstance(val, list):
                    return val
        return []

    def get_fabric_name(obj: Any) -> Optional[str]:
        if not isinstance(obj, dict):
            return None
        return (
            obj.get("fabric-name")
            or obj.get("fabric_name")
            or obj.get("name")
            or obj.get("fabric")
        )

    def safe_int(x: Any, default: int = 0) -> int:
        try:
            if x is None:
                return default
            return int(x)
        except Exception:
            return default

    # -------------------------------
    # Headline builder (compact view)
    # -------------------------------
    def build_headline(summary_obj: Optional[dict], health_obj: Optional[dict]) -> dict:
        s = summary_obj or {}
        h = health_obj or {}

        headline = {
            "fabric_status": s.get("fabric-status") or s.get("fabric_status"),
            "fabric_health": s.get("fabric-health") or s.get("fabric_health") or h.get("fabric-health"),
            "topology_health": (
                (h.get("fabric-level-physical-topology-health") or {}).get("health")
                if isinstance(h.get("fabric-level-physical-topology-health"), dict)
                else None
            ),
            "counts": {
                "spines": safe_int(s.get("number-of-spine-nodes")),
                "super_spines": safe_int(s.get("number-of-super-spine-nodes")),
                "leaves_single_homed": safe_int(s.get("number-of-single-homed-leaf-nodes")),
                "leaves_multi_homed": safe_int(s.get("number-of-multi-homed-leaf-nodes")),
                "border_leaves_single_homed": safe_int(s.get("number-of-single-homed-border-leaf-nodes")),
                "border_leaves_multi_homed": safe_int(s.get("number-of-multi-homed-border-leaf-nodes")),
                "provisioned": safe_int(s.get("number-of-provisioned-nodes")),
                "provisioned_failed": safe_int(s.get("number-of-provisioned-failed-nodes")),
                "cfg_in_sync": safe_int(s.get("number-of-config-in-sync-nodes")),
                "cfg_refreshed": safe_int(s.get("number-of-config-refreshed-nodes")),
                "cfg_generation_error": safe_int(s.get("number-of-config-generation-error-nodes")),
            },
        }

        # Optional: summarize device-health from fabric health response, if present
        device_health = h.get("device-health")
        if isinstance(device_health, list):
            agg = Counter()
            for d in device_health:
                dh = (d.get("device-health") or {}) if isinstance(d, dict) else {}
                aggregated = dh.get("aggregated-health")
                if aggregated:
                    agg[str(aggregated)] += 1
            if agg:
                headline["device_health_counts"] = dict(agg)

        return headline

    # -------------------------------
    # Device summary (compact)
    # -------------------------------
    def summarize_devices(dev_payload: Any) -> dict:
        items: List[dict] = []
        if isinstance(dev_payload, dict):
            # common pattern: {"items":[...]}
            if isinstance(dev_payload.get("items"), list):
                items = dev_payload["items"]
            # sometimes nested further
            elif isinstance((dev_payload.get("fabric-devices") or {}).get("items"), list):
                items = dev_payload["fabric-devices"]["items"]
        elif isinstance(dev_payload, list):
            items = dev_payload

        roles = Counter()
        firmware = Counter()
        cfg_state = Counter()

        for d in items:
            if not isinstance(d, dict):
                continue
            role = d.get("role")
            if role:
                roles[str(role)] += 1
            fw = d.get("firmware")
            if fw:
                firmware[str(fw)] += 1
            cgs = d.get("app-config-gen-status") or d.get("app_config_gen_status")
            if cgs:
                cfg_state[str(cgs)] += 1

        return {
            "count": len(items),
            "roles": dict(roles),
            "firmware_versions": dict(firmware),
            "config_states": dict(cfg_state),
        }

    # -------------------------------
    # 1) fabric_get_fabrics (required)
    # -------------------------------
    fabrics_resp = call_tier1("fabric_get_fabrics")
    if fabrics_resp.get("status") != 200:
        return {
            "error": "Failed to retrieve fabrics",
            "tier1": {"fabric_get_fabrics": fabrics_resp},
        }

    fabrics_payload = fabrics_resp.get("payload")
    fabrics_list = as_list(fabrics_payload)

    # If payload isn't a list, try dict values as list
    if not fabrics_list and isinstance(fabrics_payload, dict):
        vals = list(fabrics_payload.values())
        if vals and all(isinstance(v, dict) for v in vals):
            fabrics_list = vals

    # Filter by fabric_name if provided
    if fabric_name:
        fabrics_list = [
            f for f in fabrics_list
            if (get_fabric_name(f) or "").lower() == str(fabric_name).lower()
        ]

    # -------------------------------
    # 2) fabric_get_fabrics_health (optional)
    # -------------------------------
    health_map: Dict[str, Any] = {}
    if include_health:
        health_resp = call_tier1("fabric_get_fabrics_health")
        if health_resp.get("status") == 200:
            health_list = as_list(health_resp.get("payload"))
            for h in health_list:
                n = get_fabric_name(h)
                if n:
                    health_map[n] = h
        else:
            warnings.append(
                f"fabric_get_fabrics_health returned status={health_resp.get('status')}"
            )

    # -------------------------------
    # 3) fabric_get_fabrics_errors (optional)
    # -------------------------------
    errors_map: Dict[str, Any] = {}
    if include_errors:
        errors_resp = call_tier1("fabric_get_fabrics_errors")
        if errors_resp.get("status") == 200:
            err_payload = errors_resp.get("payload")

            if isinstance(err_payload, list):
                for e in err_payload:
                    n = get_fabric_name(e)
                    if n:
                        errors_map[n] = e
            elif isinstance(err_payload, dict):
                for k, v in err_payload.items():
                    errors_map[str(k)] = v
            else:
                warnings.append("fabric_get_fabrics_errors payload format not recognized")
        else:
            warnings.append(
                f"fabric_get_fabrics_errors returned status={errors_resp.get('status')}"
            )

    # -------------------------------
    # 4) fabric_get_devices (optional, per fabric)
    #    We always compute a *compact* device summary if include_devices=True.
    #    Raw device payload is included ONLY if include_raw=True.
    # -------------------------------
    devices_summary_map: Dict[str, Any] = {}
    devices_raw_map: Dict[str, Any] = {}

    if include_devices:
        for f in fabrics_list:
            n = get_fabric_name(f)
            if not n:
                continue

            dev_resp = call_tier1("fabric_get_devices", {"fabric-name": n})
            if dev_resp.get("status") == 200:
                dev_payload = dev_resp.get("payload")
                devices_summary_map[n] = summarize_devices(dev_payload)
                if include_raw:
                    devices_raw_map[n] = dev_payload
            else:
                warnings.append(
                    f"fabric_get_devices({n}) returned status={dev_resp.get('status')}"
                )

    # -------------------------------
    # Build merged overview
    # -------------------------------
    fabrics_out: List[dict] = []
    for f in fabrics_list:
        n = get_fabric_name(f) or "UNKNOWN"
        health_obj = health_map.get(n)
        errors_obj = errors_map.get(n)

        out = {
            "fabric": n,
            "headline": build_headline(f if isinstance(f, dict) else None, health_obj if isinstance(health_obj, dict) else None),
        }

        # Compact device summary if requested
        if include_devices and n in devices_summary_map:
            out["devices_summary"] = devices_summary_map[n]

        # Optional: include errors (can be compact or raw)
        if include_errors and errors_obj is not None:
            out["errors"] = errors_obj

        # Raw payloads only if include_raw=True
        if include_raw:
            out["summary_raw"] = f
            if include_health and health_obj is not None:
                out["health_raw"] = health_obj
            if include_devices and n in devices_raw_map:
                out["devices_raw"] = devices_raw_map[n]

        fabrics_out.append(out)

    return {
        "filter": {
            "fabric_name": fabric_name,
            "include_health": include_health,
            "include_errors": include_errors,
            "include_devices": include_devices,
            "include_raw": include_raw,
        },
        "count": len(fabrics_out),
        "fabrics": fabrics_out,
        "warnings": warnings,
    }

