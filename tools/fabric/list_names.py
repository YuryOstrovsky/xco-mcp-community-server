# tools/fabric/list_names.py
"""fabric_get_fabric_names — lightweight fabric discovery (Tier-2, SAFE_READ).

ID-dependent tools such as `fabric_get_fabric_health(fabric_name=...)` had no
paired discovery tool, so a consumer had to call the heavier
`fabric_get_fabrics` and hand-pick ``items[0].`fabric-name` `` — and that key is
hyphenated (JSONata-hostile).

This returns just the names (and ids), in clean **snake_case** (`fabric_name`,
`fabric_id`), ready to feed straight into the ID-dependent fabric tools.
Composite over the existing tier-1 `fabric_get_fabrics`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _pick(d: dict, keys: List[str]) -> Optional[Any]:
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d.get(k)
    return None


def _items_of(payload: Any) -> List[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in ("items", "fabrics", "fabric", "data", "result"):
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        return [payload] if payload else []
    return []


def fabric_get_fabric_names(*, inputs, registry, transport, context, **kwargs) -> dict:
    tool = registry.get("fabric_get_fabrics")
    if not tool:
        return {"status": 0, "payload": None,
                "error": "Tier-1 tool not found: fabric_get_fabrics"}
    endpoint = tool.get("endpoint") or {}
    path = endpoint.get("path")
    method = tool.get("method")
    if not path or not method:
        return {"status": 0, "payload": None,
                "error": "fabric_get_fabrics missing endpoint/method"}
    try:
        res = transport.request(
            method=method, port=endpoint.get("port"),
            path=path, params={}, context=context or {},
        )
    except Exception as e:  # noqa: BLE001
        return {"status": 0, "payload": None, "error": str(e)}

    status = res.get("status", 0)
    fabrics: List[Dict[str, Any]] = []
    names: List[str] = []
    for it in _items_of(res.get("payload")):
        name = _pick(it, ["fabric-name", "fabric_name", "name", "fabricName"])
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        entry: Dict[str, Any] = {"fabric_name": name}
        fid = _pick(it, ["fabric-id", "fabric_id", "id", "fabricId"])
        if fid is not None:
            entry["fabric_id"] = fid
        ftype = _pick(it, ["fabric-type", "fabric_type", "type"])
        if ftype is not None:
            entry["fabric_type"] = ftype
        fabrics.append(entry)
        names.append(name)

    payload: Dict[str, Any] = {
        "fabric_names": names,   # plain list of snake_case names
        "fabrics": fabrics,      # [{fabric_name, fabric_id?, fabric_type?}] — path-friendly
        "count": len(names),
    }
    if inputs.get("include_raw"):
        payload["tier1_raw"] = {"fabric_get_fabrics": res}

    # Honest status: surface a tier-1 failure when we got nothing usable.
    if status not in (200, 0) and not names:
        payload["warning"] = f"fabric_get_fabrics returned status={status}"
        return {"status": status, "payload": payload}
    return {"status": 200, "payload": payload}
