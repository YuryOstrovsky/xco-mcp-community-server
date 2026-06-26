# tools/fabric/bgp_summary.py
"""restconf_get_bgp_summary — LIVE BGP session status from SLX switches.

Reads OPERATIONAL state (not config) via SSH `show ip bgp summary` and
`show bgp evpn summary`, returning per-neighbor:
  - State (ESTAB / IDLE / CONNECT / ACTIVE …)
  - Uptime (Time)
  - Prefixes accepted (Rt:Accepted)
  - Remote ASN, address-family

Why SSH and not RESTCONF: the SLX RESTCONF *operational* BGP tree returns
HTTP 406/404 on these platforms; only `/rest/config/running/router/bgp`
(config, no live state) responds. So the only honest source of live session
state is the CLI `show ... summary` operational commands.

Also provides a fabric-wide health roll-up (all sessions Established) and an
`_agent_translation_note` one-liner for natural-language clients.
"""
from __future__ import annotations

import os
import re
import time as _time
from typing import Any, Dict, List, Optional

from mcp_runtime.logging import get_logger

logger = get_logger("mcp.bgp")

_IP_RE = re.compile(r"^[0-9]{1,3}(?:\.[0-9]{1,3}){3}$|^[0-9a-fA-F:]+:[0-9a-fA-F:]+$")
_ROUTER_RE = re.compile(r"Router ID:\s*(\S+)\s+Local AS Number:\s*(\S+)")
_COUNT_RE = re.compile(r"Number of Neighbors Configured:\s*(\d+),\s*UP:\s*(\d+)")


def _to_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _ssh_show(host: str, username: str, password: str,
              commands: List[str], timeout: int = 20) -> Dict[str, str]:
    """Run `show` commands over SSH on an SLX switch; return {cmd: output}."""
    import paramiko  # lazy import — only the SSH-based tools pull this in
    out: Dict[str, str] = {}
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(host, username=username, password=password, timeout=timeout,
                look_for_keys=False, allow_agent=False)
    try:
        sh = cli.invoke_shell(width=240, height=4000)
        _time.sleep(1.2)
        if sh.recv_ready():
            sh.recv(65535)

        def run(cmd: str, wait: float = 2.5) -> str:
            sh.send(cmd + "\n")
            _time.sleep(wait)
            buf = b""
            t0 = _time.time()
            while _time.time() - t0 < wait + 6:
                if sh.recv_ready():
                    buf += sh.recv(65535)
                    t0 = _time.time() - wait + 0.5
                else:
                    _time.sleep(0.3)
                if buf.rstrip().endswith(b"#"):
                    break
            return buf.decode(errors="replace")

        run("terminal length 0", 1.0)  # disable paging
        for c in commands:
            out[c] = run(c)
    finally:
        cli.close()
    return out


def _parse_bgp_summary_text(text: str, address_family: str) -> Dict[str, Any]:
    """Parse `show ip bgp summary` / `show bgp evpn summary` operational output."""
    res: Dict[str, Any] = {
        "address_family": address_family,
        "router_id": None,
        "local_as": None,
        "configured": None,
        "up": None,
        "neighbors": [],
    }
    m = _ROUTER_RE.search(text)
    if m:
        res["router_id"], res["local_as"] = m.group(1), m.group(2)
    m = _COUNT_RE.search(text)
    if m:
        res["configured"], res["up"] = int(m.group(1)), int(m.group(2))

    in_table = False
    for line in text.splitlines():
        if "Neighbor Address" in line and "State" in line:
            in_table = True
            continue
        if not in_table:
            continue
        toks = line.split()
        if len(toks) < 4 or not _IP_RE.match(toks[0]):
            continue
        state = toks[2].upper()
        res["neighbors"].append({
            "neighbor_ip": toks[0],
            "remote_as": toks[1],
            "state": state,
            "uptime": toks[3],
            "prefixes_accepted": _to_int(toks[4]) if len(toks) > 4 else None,
            "address_family": address_family,
            "established": "ESTAB" in state,
        })
    return res


def _query_bgp(switch_ip: str, username: str, password: str) -> Dict[str, Any]:
    """SSH a switch and return its live BGP summary across IPv4-unicast + L2VPN-EVPN."""
    try:
        outputs = _ssh_show(switch_ip, username, password, [
            "show ip bgp summary",
            "show bgp evpn summary",
        ])
    except Exception as e:  # noqa: BLE001 — connection / auth / timeout
        return {"ok": False, "error": str(e)}

    afs = {
        "ipv4_unicast": _parse_bgp_summary_text(outputs.get("show ip bgp summary", ""), "ipv4-unicast"),
        "l2vpn_evpn": _parse_bgp_summary_text(outputs.get("show bgp evpn summary", ""), "l2vpn-evpn"),
    }
    local_as = afs["ipv4_unicast"]["local_as"] or afs["l2vpn_evpn"]["local_as"]
    router_id = afs["ipv4_unicast"]["router_id"] or afs["l2vpn_evpn"]["router_id"]

    all_neighbors: List[Dict] = []
    for af in afs.values():
        all_neighbors.extend(af["neighbors"])
    established = sum(1 for n in all_neighbors if n["established"])

    return {
        "ok": True,
        "source": "operational (show ip bgp summary / show bgp evpn summary)",
        "data": {
            "local_as": local_as,
            "router_id": router_id,
            "address_families": afs,
            "neighbors": all_neighbors,
            "neighbor_count": len(all_neighbors),
            "established_count": established,
        },
    }


def _resolve_names_to_ips(names: List[str], transport, registry,
                          context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve switch names (chassis_name) to management IPs via inventory_getswitches.

    Returns {"ips": [...], "unresolved": [<original names not found>]}.
    """
    want = {n.strip().lower(): n.strip() for n in names
            if isinstance(n, str) and n.strip()}
    found: Dict[str, str] = {}
    if want and transport and registry:
        try:
            tool = registry.get("inventory_getswitches")
            ep = (tool.get("endpoint", {}) or {}) if tool else {}
            resp = transport.request(
                method="GET", port=ep.get("port"),
                path=ep.get("path", "/v1/inventory/switches"),
                params={}, context=context or {},
            )
            payload = resp.get("payload") if isinstance(resp, dict) else None
            rows = payload if isinstance(payload, list) else (
                payload.get("items", []) if isinstance(payload, dict) else [])
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                name = (row.get("chassis_name") or row.get("chassis-name")
                        or row.get("hostname") or "").strip().lower()
                ip = (row.get("ip_address") or row.get("ip-address")
                      or row.get("ipAddress"))
                if name and ip and name in want and name not in found:
                    found[name] = ip
        except Exception as e:  # noqa: BLE001
            logger.warning("switch-name resolution failed: %s", e)
    ips = [found[k] for k in want if k in found]
    unresolved = [orig for k, orig in want.items() if k not in found]
    return {"ips": ips, "unresolved": unresolved}


def restconf_get_bgp_summary(
    *,
    inputs: Dict[str, Any],
    registry=None,
    transport=None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """LIVE BGP session status from one or more SLX switches (via SSH operational CLI).

    Inputs:
      switch_ips: list of switch IPs (or a single IP string)
      switch_names: switch name(s) / chassis_name, resolved to IPs via inventory
      fabric_name: optional — auto-discovers all switches in the fabric
      username / password: SSH creds (default: RESTCONF_USERNAME / RESTCONF_PASSWORD env)
    """
    switch_ips = inputs.get("switch_ips", [])
    if isinstance(switch_ips, str):
        switch_ips = [switch_ips]

    # Resolve switch NAMES -> management IPs so agents can ask "BGP status for Spine-1".
    names = inputs.get("switch_names", [])
    if isinstance(names, str):
        names = [names]
    unresolved_names: List[str] = []
    if names:
        r = _resolve_names_to_ips(names, transport, registry, context)
        switch_ips = list(switch_ips) + [ip for ip in r["ips"] if ip not in switch_ips]
        unresolved_names = r["unresolved"]

    fabric_name = inputs.get("fabric_name")
    if fabric_name and not switch_ips and transport and registry:
        try:
            tool = registry.get("fabric_get_devices")
            if tool:
                ep = tool.get("endpoint", {}) or {}
                resp = transport.request(
                    method="GET", port=ep.get("port"),
                    path=ep.get("path", "/v1/fabric/devices"),
                    params={"fabric-name": fabric_name},
                    context=context or {},
                )
                payload = resp.get("payload", {}) if isinstance(resp, dict) else {}
                devices = payload.get("items", payload.get("device", [])) if isinstance(payload, dict) else []
                if isinstance(devices, list):
                    switch_ips = [d.get("ip-address") for d in devices
                                  if isinstance(d, dict) and d.get("ip-address")]
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to discover fabric devices: %s", e)

    if not switch_ips:
        msg = "Provide switch_ips, switch_names, or fabric_name."
        if unresolved_names:
            msg = ("Could not resolve switch name(s) to a management IP: "
                   f"{', '.join(unresolved_names)}. Verify the name (chassis_name) via "
                   "inventory_getswitches, or pass switch_ips directly.")
        return {"status": 400, "payload": {"error": msg, "unresolved_names": unresolved_names}}

    username = inputs.get("username") or os.environ.get("RESTCONF_USERNAME", "admin")
    password = inputs.get("password") or os.environ.get("RESTCONF_PASSWORD", "")

    results: List[Dict[str, Any]] = []
    total_established = 0
    total_neighbors = 0

    for ip in switch_ips:
        logger.info("bgp_summary: querying %s (live)", ip)
        r = _query_bgp(ip, username, password)
        if r["ok"]:
            d = r["data"]
            total_neighbors += d["neighbor_count"]
            total_established += d["established_count"]
            results.append({
                "switch_ip": ip,
                "ok": True,
                "source": r["source"],
                "local_as": d["local_as"],
                "router_id": d["router_id"],
                "neighbor_count": d["neighbor_count"],
                "established_count": d["established_count"],
                "all_established": d["established_count"] == d["neighbor_count"] and d["neighbor_count"] > 0,
                "address_families": d["address_families"],
                "neighbors": d["neighbors"],
            })
        else:
            results.append({
                "switch_ip": ip,
                "ok": False,
                "error": r.get("error"),
                "neighbor_count": 0,
                "established_count": 0,
                "neighbors": [],
            })

    all_ok = all(r["ok"] for r in results)
    switches_ok = sum(1 for r in results if r["ok"])
    all_healthy = all_ok and total_neighbors > 0 and total_established == total_neighbors

    if switches_ok == 0:
        note = f"BGP query failed on all {len(results)} switch(es) — check SSH reachability/credentials."
    elif all_healthy:
        note = (f"All {total_established} BGP session(s) Established across "
                f"{switches_ok}/{len(results)} switch(es).")
    else:
        note = (f"{total_established}/{total_neighbors} BGP session(s) Established across "
                f"{switches_ok}/{len(results)} switch(es) — some neighbors are not Established.")

    if unresolved_names:
        note += (" (Could not resolve name(s) to an IP: "
                 f"{', '.join(unresolved_names)}.)")

    return {"status": 200, "payload": {
        "switches": results,
        "summary": {
            "total_switches": len(results),
            "switches_ok": switches_ok,
            "total_neighbors": total_neighbors,
            "total_established": total_established,
            "all_healthy": all_healthy,
        },
        "fabric_name": fabric_name,
        "unresolved_names": unresolved_names,
        "_agent_translation_note": note,
    }}
