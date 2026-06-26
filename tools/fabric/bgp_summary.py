# tools/fabric/bgp_summary.py
"""restconf_get_bgp_summary — configured BGP per SLX switch (read-only).

Reads the BGP section of the switch running-config via RESTCONF
(GET /rest/config/running/router/bgp, XML) and returns, per switch:
  - local AS
  - configured neighbors (IP, remote-AS, peer-group)
  - peer-group definitions (remote-AS, description)

NOTE: this reflects **configured** BGP, not live session state. These SLX builds
do not expose the operational BGP tree via RESTCONF (the get-bgp-summary RPC
returns 400/404), so per-neighbor Established/prefixes/uptime are not available
here — use the running-config view this tool provides.

Query individual switches (switch_ips) or a whole fabric (fabric_name
auto-discovers member switches via the tier-1 fabric_get_devices tool).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from restconf.client import make_client, RestconfError
from mcp_runtime.logging import get_logger

logger = get_logger("mcp.bgp")

_BGP_NS = {"bgp": "urn:brocade.com:mgmt:brocade-bgp"}


def _query_bgp(switch_ip: str, username, password, verify_tls,
               include_raw: bool = False) -> Dict[str, Any]:
    """Read configured BGP from one switch's running-config (XML) via RESTCONF."""
    try:
        client = make_client(switch_ip, username=username, password=password,
                             verify_tls=verify_tls)
        status, _headers, text = client.get_running_config_xml(config_path="/router/bgp")
    except RestconfError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}

    if status != 200:
        return {"ok": False, "error": f"BGP running-config query failed: HTTP {status}"}

    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return {"ok": False, "error": f"XML parse error: {e}"}

    local_as_elem = root.find("bgp:local-as", _BGP_NS)
    local_as = local_as_elem.text if local_as_elem is not None else None

    # Peer-group definitions (remote-as / description live here, not on the neighbor).
    peer_groups: Dict[str, Dict[str, Any]] = {}
    for pg in root.findall(".//bgp:neighbor-peer-grp", _BGP_NS):
        pg_addr = pg.find("bgp:address", _BGP_NS)
        pg_as = pg.find("bgp:remote-as", _BGP_NS)
        pg_desc = pg.find("bgp:description", _BGP_NS)
        if pg_addr is not None and pg_addr.text:
            peer_groups[pg_addr.text] = {
                "remote_as": pg_as.text if pg_as is not None else None,
                "description": pg_desc.text if pg_desc is not None else None,
            }

    # Configured neighbors.
    neighbors: List[Dict[str, Any]] = []
    for nbr in root.findall(".//bgp:neighbor-addr", _BGP_NS):
        addr = nbr.find("bgp:address", _BGP_NS)
        peer_group = nbr.find("bgp:peer-group", _BGP_NS)
        remote_as = nbr.find("bgp:remote-as", _BGP_NS)
        n: Dict[str, Any] = {
            "neighbor_ip": addr.text if addr is not None else None,
            "peer_group": peer_group.text if peer_group is not None else None,
            "remote_as": remote_as.text if remote_as is not None else None,
        }
        # Inherit remote-as / description from the peer-group when not set directly.
        if not n["remote_as"] and n["peer_group"]:
            pg_info = peer_groups.get(n["peer_group"], {})
            n["remote_as"] = pg_info.get("remote_as")
            n["peer_group_description"] = pg_info.get("description")
        neighbors.append(n)

    out: Dict[str, Any] = {
        "ok": True,
        "source": "running-config",
        "data": {
            "local_as": local_as,
            "neighbor_count": len(neighbors),
            "peer_groups": peer_groups,
            "neighbors": neighbors,
        },
    }
    if include_raw:
        out["raw"] = text
    return out


def _discover_fabric_switches(fabric_name: str, registry, transport, context) -> List[str]:
    """Best-effort: resolve a fabric's member switch IPs via tier-1 fabric_get_devices."""
    try:
        tool = registry.get("fabric_get_devices") if registry else None
        if not tool or not transport:
            return []
        ep = tool.get("endpoint") or {}
        resp = transport.request(
            method=tool.get("method", "GET"), port=ep.get("port"),
            path=ep.get("path", "/v1/fabric/devices"),
            params={"fabric-name": fabric_name}, context=context or {},
        )
        payload = resp.get("payload", {}) if isinstance(resp, dict) else {}
        if isinstance(payload, dict):
            devices = payload.get("items") or payload.get("device") or []
        elif isinstance(payload, list):
            devices = payload
        else:
            devices = []
        ips = []
        for d in devices:
            if isinstance(d, dict):
                ip = d.get("ip-address") or d.get("ip_address") or d.get("ip")
                if ip:
                    ips.append(ip)
        return ips
    except Exception as e:  # noqa: BLE001
        logger.warning("bgp_summary: fabric device discovery failed: %s", e)
        return []


def restconf_get_bgp_summary(
    *,
    inputs: Dict[str, Any],
    registry=None,
    transport=None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Query configured BGP from one or more SLX switches (or a whole fabric)."""
    switch_ips = inputs.get("switch_ips") or []
    if isinstance(switch_ips, str):
        switch_ips = [switch_ips]

    fabric_name = inputs.get("fabric_name")
    if fabric_name and not switch_ips:
        switch_ips = _discover_fabric_switches(fabric_name, registry, transport, context)

    if not switch_ips:
        return {"status": 400, "payload": {
            "error": "Provide switch_ips (a string or list) or fabric_name.",
        }}

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    include_raw = bool(inputs.get("include_raw") or False)

    results: List[Dict[str, Any]] = []
    total_neighbors = 0
    for ip in switch_ips:
        logger.info("bgp_summary: querying %s", ip)
        r = _query_bgp(ip, username, password, verify_tls, include_raw)
        if r.get("ok"):
            data = r["data"]
            total_neighbors += data["neighbor_count"]
            entry = {
                "switch_ip": ip, "ok": True, "source": r.get("source"),
                "local_as": data["local_as"], "neighbor_count": data["neighbor_count"],
                "peer_groups": data["peer_groups"], "neighbors": data["neighbors"],
            }
            if include_raw and "raw" in r:
                entry["raw"] = r["raw"]
            results.append(entry)
        else:
            results.append({
                "switch_ip": ip, "ok": False, "error": r.get("error"),
                "neighbor_count": 0, "neighbors": [],
            })

    switches_ok = sum(1 for r in results if r["ok"])
    return {"status": 200, "payload": {
        "switches": results,
        "summary": {
            "total_switches": len(results),
            "switches_ok": switches_ok,
            "switches_errored": len(results) - switches_ok,
            "total_configured_neighbors": total_neighbors,
            "note": ("Configured BGP from running-config; operational session state "
                     "(Established/prefixes/uptime) is not exposed via RESTCONF on these "
                     "SLX builds."),
        },
        "fabric_name": fabric_name,
    }}
