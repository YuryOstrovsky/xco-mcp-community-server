# tools/tenant/all_endpoint_groups.py
from __future__ import annotations
from typing import Any, Dict, List, Optional


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
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("items", "data", "result", "payload", "epg", "endpointGroups", "endpoint_groups"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
        list_values = [v for v in payload.values() if isinstance(v, list)]
        if len(list_values) == 1:
            return list_values[0]
    return []


def _extract_tenant_names(payload: Any) -> List[str]:
    """
    tenant_get_tenants returns {"tenant":[{"name":"..."}...]}.
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


def tenant_get_all_endpoint_groups(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
) -> dict:
    """
    Tier-2 composite: tenant_get_all_endpoint_groups

    Discovers every tenant via tenant_get_tenants, then fetches EPGs
    for each tenant via tenant_get_endpoint_groups. Returns a unified
    view grouped by tenant with aggregate counts.

    Tier-1 tools used:
      - tenant_get_tenants
      - tenant_get_endpoint_groups
    """

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

    warnings: List[str] = []

    # -------------------------
    # 1) Discover all tenants
    # -------------------------
    tenants_res = call_tier1("tenant_get_tenants", {})
    if tenants_res.get("status") != 200:
        return {
            "status": 502,
            "payload": {
                "error": "Failed to list tenants (tenant_get_tenants)",
                "tier1": {"tenant_get_tenants": tenants_res},
            },
        }

    tenant_names = _extract_tenant_names(tenants_res.get("payload"))
    if not tenant_names:
        return {
            "status": 200,
            "payload": {
                "total_epgs": 0,
                "tenant_count": 0,
                "tenants": [],
                "warnings": ["tenant_get_tenants returned no tenants."],
            },
        }

    # -------------------------
    # 2) Fetch EPGs per tenant
    # -------------------------
    results: List[Dict[str, Any]] = []
    for name in tenant_names:
        epg_res = call_tier1("tenant_get_endpoint_groups", {"tenant_name": name})
        if epg_res.get("status") != 200:
            warnings.append(f"Failed to fetch EPGs for tenant '{name}' (status {epg_res.get('status')}); skipped.")
            results.append({"tenant_name": name, "epg_count": None, "epg": None, "error": True})
            continue
        epg_list = [x for x in _as_list(epg_res.get("payload")) if isinstance(x, dict)]
        results.append({
            "tenant_name": name,
            "epg_count": len(epg_list),
            "epg": epg_list,
        })

    # -------------------------
    # 3) Aggregate
    # -------------------------
    total_epgs = sum(r["epg_count"] or 0 for r in results)
    failed = [r["tenant_name"] for r in results if r.get("error")]

    return {
        "status": 200,
        "payload": {
            "total_epgs": total_epgs,
            "tenant_count": len(tenant_names),
            "tenants": results,
            "warnings": warnings,
            **({"failed_tenants": failed} if failed else {}),
        },
    }

