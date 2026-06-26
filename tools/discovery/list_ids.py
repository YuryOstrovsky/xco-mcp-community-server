# tools/discovery/list_ids.py
"""Paired ID-listing tools.

Every tool whose input_schema requires a discriminator (`device_id`,
`tenant` name, …) needs a paired listing tool so an LLM client never has to
hard-code an ID from a cached sample.  `fabric_get_fabric_names` covers
fabrics; these add devices and tenants, in clean **snake_case**, composed over
the existing tier-1 reads.

  inventory_list_device_ids  → device_ids[] + devices[{device_id, ip, hostname}]
  tenant_list_ids            → tenant_ids[]  + tenants[{tenant_id, tenant_name}]
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _pick(d: Any, keys: List[str]) -> Optional[Any]:
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _items_of(payload: Any) -> List[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in ("items", "data", "result", "switches", "tenants",
                  "tenant", "device", "devices"):
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        return [payload] if payload else []
    return []


def _call_tier1(registry, transport, context, tool_name: str) -> Dict[str, Any]:
    tool = registry.get(tool_name)
    if not tool:
        return {"status": 0, "payload": None, "error": f"tier-1 tool not found: {tool_name}"}
    endpoint = tool.get("endpoint") or {}
    path, method = endpoint.get("path"), tool.get("method")
    if not path or not method:
        return {"status": 0, "payload": None, "error": f"{tool_name} missing endpoint/method"}
    try:
        return transport.request(method=method, port=endpoint.get("port"),
                                 path=path, params={}, context=context or {})
    except Exception as e:  # noqa: BLE001
        return {"status": 0, "payload": None, "error": str(e)}


def inventory_list_device_ids(*, inputs=None, registry, transport, context=None, **kwargs) -> dict:
    """SAFE_READ — the paired list for device-id-required inventory tools."""
    res = _call_tier1(registry, transport, context, "inventory_getswitches")
    if res.get("error") and res.get("payload") is None:
        return {"status": 0, "payload": None, "error": res["error"]}

    devices: List[Dict[str, Any]] = []
    device_ids: List[Any] = []
    for it in _items_of(res.get("payload")):
        did = _pick(it, ["device-id", "device_id", "id", "deviceId"])
        ip = _pick(it, ["ip-address", "ip_address", "ipAddress", "mgmt-ip", "host"])
        host = _pick(it, ["host-name", "hostname", "name", "switch-name", "fwName"])
        # the discriminator other tools require is device_id; fall back to ip.
        key = did if did is not None else ip
        if key in (None, ""):
            continue
        entry: Dict[str, Any] = {"device_id": key}
        if ip is not None:
            entry["ip"] = ip
        if host is not None:
            entry["hostname"] = host
        devices.append(entry)
        device_ids.append(key)

    payload: Dict[str, Any] = {
        "device_ids": device_ids,
        "devices": devices,
        "count": len(device_ids),
    }
    status = res.get("status", 0)
    if status not in (200, 0) and not device_ids:
        payload["warning"] = f"inventory_getswitches returned status={status}"
        return {"status": status, "payload": payload}
    return {"status": 200, "payload": payload}


def tenant_list_ids(*, inputs=None, registry, transport, context=None, **kwargs) -> dict:
    """SAFE_READ — the paired list for tenant-name-required tenant tools."""
    res = _call_tier1(registry, transport, context, "tenant_get_tenants")
    if res.get("error") and res.get("payload") is None:
        return {"status": 0, "payload": None, "error": res["error"]}

    tenants: List[Dict[str, Any]] = []
    tenant_ids: List[Any] = []
    for it in _items_of(res.get("payload")):
        name = _pick(it, ["name", "tenant-name", "tenant_name", "tenantName"])
        if name in (None, ""):
            continue
        tid = _pick(it, ["id", "tenant-id", "tenant_id", "tenantId"]) or name
        entry = {"tenant_id": tid, "tenant_name": name}
        tenants.append(entry)
        tenant_ids.append(tid)

    payload: Dict[str, Any] = {
        "tenant_ids": tenant_ids,
        "tenants": tenants,
        "count": len(tenant_ids),
    }
    status = res.get("status", 0)
    if status not in (200, 0) and not tenant_ids:
        payload["warning"] = f"tenant_get_tenants returned status={status}"
        return {"status": status, "payload": payload}
    return {"status": 200, "payload": payload}
