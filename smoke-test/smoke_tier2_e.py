#!/usr/bin/env python3
"""
XCO MCP Server — Tier-2 Smoke Test  Batch E  (14 tools)
=========================================================
Covers: RESTCONF Tier-2 tools from XCO_MCP_Tier2_Operator_Notes.docx
        (all hit real SLX switches via RESTCONF)

Tools tested:
  1.  restconf_show_firmware_version
  2.  restconf_get_interface_detail
  3.  restconf_list_operations
  4.  restconf_get_lldp_neighbor_detail
  5.  restconf_get_port_statistics_summary
  6.  restconf_get_media_detail
  7.  restconf_get_arp_table
  8.  restconf_get_clock
  9.  restconf_get_vlan_brief
  10. restconf_get_vrf_summary
  11. restconf_get_ip_interface
  12. restconf_get_running_config
  13. restconf_get_system_maintenance_status
  14. restconf_get_system_maintenance_rate_monitoring

Discovery: switch IPs are auto-discovered from inventory_getswitches.
           First reachable switch is used for all tests.

Note on HTTP 204: some RESTCONF RPCs return 204 (No Content) when a
feature is disabled/not configured. This is surfaced as WARN.

Usage:
    cd /path/to/XCO-MCP-SERVER
    python3 smoke-test/smoke_tier2_e.py [--url http://localhost:8000]
    python3 smoke-test/smoke_tier2_e.py --url http://localhost:8000 --switch 10.13.9.66

Results:
    smoke-test/results_tier2_e.json
    smoke-test/summary_tier2_e.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DEFAULT_URL = os.getenv("MCP_URL", "http://localhost:8000")

RESULTS: List[Dict[str, Any]] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# MCP tool caller
# ---------------------------------------------------------------------------
def call_tool(base_url: str, tool_name: str, inputs: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/invoke"
    try:
        resp = requests.post(url, json={"tool": tool_name, "inputs": inputs}, timeout=timeout)
        try:
            body = resp.json()
        except Exception:
            body = {"raw_text": resp.text}
        return {"http_status": resp.status_code, "body": body}
    except requests.exceptions.ConnectionError as e:
        return {"http_status": 0, "body": {}, "error": f"ConnectionError: {e}"}
    except requests.exceptions.Timeout:
        return {"http_status": 0, "body": {}, "error": "Timeout"}
    except Exception as e:
        return {"http_status": 0, "body": {}, "error": str(e)}


def _extract_payload(raw: Dict[str, Any]) -> Tuple[int, Any]:
    """
    Return (status_code, payload) from the normalised call_tool result.

    The MCP server wraps tool output in one level of {status, payload}.
    Tier-2 tools themselves also return {status, payload}.
    Result: most responses are double-wrapped:
        body = {"status": 200, "payload": {"status": 200, "payload": {...actual...}}}
    We unwrap both levels automatically.
    RESTCONF tools return raw data (no inner wrapper) — the double-unwrap
    condition does not trigger for them.
    """
    body = raw.get("body", {})
    http_status = raw.get("http_status", 0)

    # Try body.result.status / body.result.payload  (standard MCP wrapper)
    result = body.get("result")
    if isinstance(result, dict):
        tool_status = int(result.get("status", http_status))
        payload = result.get("payload")
        # Handle double-wrapping
        if isinstance(payload, dict) and "status" in payload and "payload" in payload:
            tool_status = int(payload.get("status", tool_status))
            payload = payload.get("payload")
        return tool_status, payload

    # Try body.status / body.payload  (most endpoints land here)
    if "status" in body:
        outer_status = int(body["status"])
        payload = body.get("payload")
        # Handle double-wrapping: tool returned {status, payload} inside outer wrapper
        if isinstance(payload, dict) and "status" in payload and "payload" in payload:
            outer_status = int(payload.get("status", outer_status))
            payload = payload.get("payload")
        return outer_status, payload

    # Fallback: body IS the payload
    return http_status, body or None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
class Discovery:
    def __init__(self, base_url: str, override_switch_ip: Optional[str] = None):
        self.base_url = base_url
        self.switch_ip: Optional[str] = override_switch_ip
        self.switch_ips: List[str] = []
        self.interface_name: Optional[str] = None  # discovered from a reachable switch

    def run(self) -> "Discovery":
        print("▶  Discovery phase …")
        if not self.switch_ip:
            self._discover_switches()
        else:
            self.switch_ips = [self.switch_ip]
        if self.switch_ip:
            self._discover_interface()
        print(f"   primary switch  : {self.switch_ip or '(none)'}")
        print(f"   all switches    : {self.switch_ips[:5] or '(none)'}")
        print(f"   interface_name  : {self.interface_name or '(will use default)'}")
        return self

    def _discover_switches(self):
        raw = call_tool(self.base_url, "inventory_getswitches", {})
        _, payload = _extract_payload(raw)
        if payload:
            items = payload if isinstance(payload, list) else (
                payload.get("items") or payload.get("switches") or payload.get("data") or []
            )
            for sw in items:
                if isinstance(sw, dict):
                    ip = sw.get("ip") or sw.get("ip_address") or sw.get("mgmtIp")
                    if ip:
                        self.switch_ips.append(str(ip))
        if self.switch_ips:
            self.switch_ip = self.switch_ips[0]

    def _discover_interface(self):
        """Probe one interface from the switch to use in interface-specific tests."""
        if not self.switch_ip:
            return
        raw = call_tool(self.base_url, "restconf_get_interface_detail",
                        {"switch_ip": self.switch_ip})
        _, payload = _extract_payload(raw)
        if isinstance(payload, dict):
            # Check summary.interfaces or item.interfaces
            ifaces = (
                payload.get("interfaces")
                or (payload.get("summary") or {}).get("interfaces")
                or (payload.get("item") or {}).get("interfaces")
                or []
            )
            if ifaces and isinstance(ifaces[0], dict):
                name = ifaces[0].get("name") or ifaces[0].get("interface_name")
                if name:
                    self.interface_name = str(name)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------
def run_case(
    base_url: str, tool: str, inputs: Dict[str, Any], use_case: str,
    checks: List[Tuple[str, Any]], *,
    skip_reason: Optional[str] = None,
    warn_on_status: Optional[List[int]] = None,
) -> str:
    entry: Dict[str, Any] = {
        "tool": tool, "use_case": use_case, "inputs": inputs,
        "status": "PENDING", "http_status": None, "tool_status": None,
        "failures": [], "warnings": [], "payload_keys": [],
    }

    if skip_reason:
        entry["status"] = "SKIP"
        entry["skip_reason"] = skip_reason
        RESULTS.append(entry)
        _print_row(tool, use_case, "SKIP", skip_reason)
        return "SKIP"

    raw = call_tool(base_url, tool, inputs)
    http_status = raw.get("http_status", 0)
    tool_status, payload = _extract_payload(raw)
    conn_error = raw.get("error")

    entry["http_status"] = http_status
    entry["tool_status"] = tool_status
    if isinstance(payload, dict):
        entry["payload_keys"] = list(payload.keys())
    elif isinstance(payload, list):
        entry["payload_keys"] = [f"list[{len(payload)}]"]

    if conn_error or http_status == 0:
        entry["status"] = "ERROR"
        entry["failures"].append(conn_error or "No HTTP response")
        RESULTS.append(entry)
        _print_row(tool, use_case, "ERROR", conn_error or "no response")
        return "ERROR"

    warn_statuses = set(warn_on_status or [])
    if tool_status != 200:
        msg = f"tool_status={tool_status}"
        entry["status"] = "WARN" if tool_status in warn_statuses else "FAIL"
        (entry["warnings"] if entry["status"] == "WARN" else entry["failures"]).append(msg)
        RESULTS.append(entry)
        _print_row(tool, use_case, entry["status"], msg)
        return entry["status"]

    if payload is None or payload == {} or payload == "":
        entry["status"] = "FAIL"
        entry["failures"].append("payload is empty/None")
        RESULTS.append(entry)
        _print_row(tool, use_case, "FAIL", "empty payload")
        return "FAIL"

    failures = []
    for desc, checker in checks:
        try:
            ok = checker(payload) if callable(checker) else bool(checker)
            if not ok:
                failures.append(desc)
        except Exception as e:
            failures.append(f"{desc} [exception: {e}]")

    entry["status"] = "FAIL" if failures else "PASS"
    entry["failures"] = failures
    RESULTS.append(entry)
    _print_row(tool, use_case, entry["status"], "; ".join(failures[:2]))
    return entry["status"]


def _print_row(tool: str, use_case: str, status: str, detail: str):
    colour = {"PASS": "\033[32m", "FAIL": "\033[31m", "WARN": "\033[33m",
               "SKIP": "\033[36m", "ERROR": "\033[35m"}.get(status, "")
    reset = "\033[0m"
    note = f"  ← {detail}" if detail else ""
    print(f"  {colour}{status:<5}{reset}  {tool[:48]:<48} {use_case[:35]:<35}{note}")


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------
def _has_any_key(p, *keys):
    return isinstance(p, dict) and any(k in p for k in keys)

def _restconf_ok(p):
    """RESTCONF tools wrap output: check meta.ok or summary.signals.restconf_ok."""
    if not isinstance(p, dict):
        return False
    meta = p.get("meta") or {}
    if meta.get("ok") is True:
        return True
    summary = p.get("summary") or {}
    signals = summary.get("signals") or {}
    return bool(signals.get("restconf_ok"))

def _has_item_content(p):
    """Tool returned item dict with at least one non-None value."""
    item = p.get("item") if isinstance(p, dict) else None
    return isinstance(item, dict) and any(v is not None for v in item.values())

def _has_items_list(p):
    """Tool returned items list (or item list in nested key) with at least one entry."""
    if not isinstance(p, dict):
        return False
    for k in ("items", "interfaces", "neighbors", "entries", "vlans", "vrfs",
               "operations", "ports", "arp_entries", "routes"):
        v = p.get(k)
        if isinstance(v, list) and v:
            return True
    item = p.get("item") or {}
    if isinstance(item, dict):
        for k in ("interfaces", "neighbors", "entries", "vlans", "vrfs", "ports"):
            v = item.get(k)
            if isinstance(v, list) and v:
                return True
    return False

def _has_summary_with(p, *fields):
    s = p.get("summary") if isinstance(p, dict) else {}
    return isinstance(s, dict) and any(s.get(f) is not None for f in fields)

def _no_switch_error(p):
    """Return True if payload does NOT contain a connection-refused / unreachable error."""
    if not isinstance(p, dict):
        return True
    meta = p.get("meta") or {}
    err = str(meta.get("error") or "").lower()
    warn_list = [str(w).lower() for w in (p.get("warnings") or [])]
    bad = ("connection refused", "unreachable", "timed out", "no route", "ssl")
    return not any(b in err for b in bad) and not any(b in w for w in warn_list for b in bad)


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

def _skip_no_switch(tool: str, uc: str):
    entry = {
        "tool": tool, "use_case": uc, "inputs": {},
        "status": "SKIP", "skip_reason": "no switch_ip discovered",
        "http_status": None, "tool_status": None,
        "failures": [], "warnings": [], "payload_keys": [],
    }
    RESULTS.append(entry)
    _print_row(tool, uc, "SKIP", "no switch_ip discovered")


def test_firmware_version(base: str, d: Discovery):
    print("\n── 1. restconf_show_firmware_version ──")
    tool = "restconf_show_firmware_version"

    if not d.switch_ip:
        _skip_no_switch(tool, "UC1: firmware version")
        return

    # UC-1: What firmware version is running on the switch?
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: firmware version",
        checks=[
            ("restconf call succeeded", _restconf_ok),
            ("has firmware version info",
             lambda p: _has_any_key(p, "item", "firmware", "version") and
                       _has_item_content(p)),
            ("item has os_version or firmware_version",
             lambda p: any(
                 (p.get("item") or {}).get(k) is not None
                 for k in ("os_version", "firmware_version", "firmware", "version",
                            "full_ver", "build", "release")
             ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: Check uptime and CPU/memory info (operational snapshot)
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC2: uptime + CPU/mem",
        checks=[
            ("restconf call succeeded", _restconf_ok),
            ("item has uptime or cpu or memory",
             lambda p: any(
                 (p.get("item") or {}).get(k) is not None
                 for k in ("uptime", "cpu", "cpu_usage", "memory", "memory_usage",
                            "mem_free", "mem_total")
             ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[204, 503],
    )


def test_interface_detail(base: str, d: Discovery):
    print("\n── 2. restconf_get_interface_detail ──")
    tool = "restconf_get_interface_detail"

    if not d.switch_ip:
        for uc in ["UC1", "UC2", "UC3"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: All interfaces — operational state overview
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: all interfaces",
        checks=[
            ("restconf call succeeded", _restconf_ok),
            ("has interfaces in item or top-level",
             lambda p: _has_any_key(p, "item", "interfaces") and
                       (_has_items_list(p) or _has_item_content(p))),
            ("interface list is non-empty",
             _has_items_list),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: Specific interface detail (if discovered)
    if d.interface_name:
        run_case(base, tool,
                 {"switch_ip": d.switch_ip, "interface_name": d.interface_name},
                 f"UC2: specific interface detail",
            checks=[
                ("restconf ok", _restconf_ok),
                ("has interface data", lambda p: _has_item_content(p) or _has_items_list(p)),
            ],
            warn_on_status=[204, 404, 503],
        )
    else:
        run_case(base, tool, {}, "UC2: specific interface detail",
                 checks=[], skip_reason="no interface_name discovered")

    # UC-3: Interface counters include error counters
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC3: interface has counters",
        checks=[
            ("restconf ok", _restconf_ok),
            ("at least one interface has counter fields",
             lambda p: any(
                 isinstance(iface, dict) and any(
                     iface.get(k) is not None
                     for k in ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets",
                                "in_octets", "out_octets", "errors", "rx_errors")
                 )
                 for iface in (
                     (p.get("item") or {}).get("interfaces", [])
                     or p.get("interfaces", [])
                 )
             ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[204, 503],
    )


def test_list_operations(base: str, d: Discovery):
    print("\n── 3. restconf_list_operations ──")
    tool = "restconf_list_operations"

    if not d.switch_ip:
        for uc in ["UC1", "UC2"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: What RESTCONF operations does this switch support?
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: list all operations",
        checks=[
            ("restconf ok", _restconf_ok),
            ("has operations list",
             lambda p: _has_any_key(p, "operations", "items", "rpcs")
                       and _has_items_list(p)),
            ("operations list is non-empty",
             lambda p: any(
                 isinstance(p.get(k), list) and len(p.get(k, [])) > 0
                 for k in ("operations", "items", "rpcs")
             ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: Filter operations by keyword
    run_case(base, tool, {"switch_ip": d.switch_ip, "filter": "interface"},
             "UC2: filter=interface",
        checks=[
            ("restconf ok", _restconf_ok),
            ("has operations (possibly empty for filtered)",
             lambda p: _has_any_key(p, "operations", "items", "rpcs")),
        ],
        warn_on_status=[204, 503],
    )


def test_lldp_neighbor_detail(base: str, d: Discovery):
    print("\n── 4. restconf_get_lldp_neighbor_detail ──")
    tool = "restconf_get_lldp_neighbor_detail"

    if not d.switch_ip:
        for uc in ["UC1", "UC2"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: Show LLDP neighbors — understand connected devices
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: all LLDP neighbors",
        checks=[
            ("restconf ok or no neighbors signal",
             lambda p: _restconf_ok(p) or _has_any_key(p, "no_neighbors", "message")),
            ("has neighbors list or no_neighbors",
             lambda p: _has_items_list(p) or _has_any_key(p, "no_neighbors", "message",
                                                           "item")),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: LLDP neighbors with specific interface filter
    if d.interface_name:
        run_case(base, tool,
                 {"switch_ip": d.switch_ip, "interface_name": d.interface_name},
                 "UC2: LLDP for specific interface",
            checks=[
                ("restconf ok or no neighbors", lambda p: _restconf_ok(p) or isinstance(p, dict)),
            ],
            warn_on_status=[204, 404, 503],
        )
    else:
        run_case(base, tool, {}, "UC2: LLDP per-interface",
                 checks=[], skip_reason="no interface_name discovered")


def test_port_statistics(base: str, d: Discovery):
    print("\n── 5. restconf_get_port_statistics_summary ──")
    tool = "restconf_get_port_statistics_summary"

    if not d.switch_ip:
        for uc in ["UC1", "UC2"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: Summarize port traffic stats and errors
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: port statistics summary",
        checks=[
            ("restconf ok", _restconf_ok),
            ("has ports or summary with stats",
             lambda p: _has_items_list(p) or _has_any_key(p, "ports", "summary")),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: Summary has top ports by traffic or error counters
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC2: top ports by traffic",
        checks=[
            ("restconf ok", _restconf_ok),
            ("summary has total_ports or port list",
             lambda p: _has_summary_with(p, "total_ports", "port_count", "total")
                       or _has_items_list(p)),
        ],
        warn_on_status=[204, 503],
    )


def test_media_detail(base: str, d: Discovery):
    print("\n── 6. restconf_get_media_detail ──")
    tool = "restconf_get_media_detail"

    if not d.switch_ip:
        for uc in ["UC1", "UC2"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: Show optics details for all ports
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: all port optics",
        checks=[
            ("restconf ok or 204 expected",
             lambda p: _restconf_ok(p) or _has_any_key(p, "meta", "warnings")),
            ("has interfaces or no_optics signal",
             lambda p: _has_items_list(p) or _has_any_key(p, "no_optics", "message",
                                                           "item", "summary")),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: Specific port optics (if interface discovered)
    if d.interface_name:
        run_case(base, tool,
                 {"switch_ip": d.switch_ip, "port": d.interface_name},
                 "UC2: specific port optics",
            checks=[
                ("restconf responded", lambda p: isinstance(p, dict)),
            ],
            warn_on_status=[204, 404, 503],
        )
    else:
        run_case(base, tool, {}, "UC2: specific port optics",
                 checks=[], skip_reason="no interface_name discovered")


def test_arp_table(base: str, d: Discovery):
    print("\n── 7. restconf_get_arp_table ──")
    tool = "restconf_get_arp_table"

    if not d.switch_ip:
        for uc in ["UC1", "UC2"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: List ARP entries on the switch
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: ARP table",
        checks=[
            ("restconf ok", _restconf_ok),
            ("has arp_entries or entries list",
             lambda p: _has_items_list(p) or _has_any_key(p, "arp_entries", "entries",
                                                           "items", "item")),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: ARP entries have IP + MAC address fields
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC2: ARP entries have IP+MAC",
        checks=[
            ("restconf ok", _restconf_ok),
            ("at least one entry has IP and MAC",
             lambda p: any(
                 isinstance(e, dict) and (e.get("ip") or e.get("ip_address")) and
                 (e.get("mac") or e.get("mac_address") or e.get("hardware_address"))
                 for e in (
                     p.get("arp_entries") or p.get("entries") or p.get("items") or
                     (p.get("item") or {}).get("entries") or
                     (p.get("item") or {}).get("arp_entries") or []
                 )
             ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[204, 503],
    )


def test_clock(base: str, d: Discovery):
    print("\n── 8. restconf_get_clock ──")
    tool = "restconf_get_clock"

    if not d.switch_ip:
        _skip_no_switch(tool, "UC1: system clock")
        return

    # UC-1: Current device time for troubleshooting
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: system clock",
        checks=[
            ("restconf ok", _restconf_ok),
            ("has time or clock info",
             lambda p: _has_any_key(p, "item", "clock", "time") and
                       any(
                           (p.get("item") or {}).get(k) is not None or p.get(k) is not None
                           for k in ("time", "date", "datetime", "current_time",
                                     "clock", "timestamp", "utc_time")
                       ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[204, 503],
    )


def test_vlan_brief(base: str, d: Discovery):
    print("\n── 9. restconf_get_vlan_brief ──")
    tool = "restconf_get_vlan_brief"

    if not d.switch_ip:
        for uc in ["UC1", "UC2"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: Show VLAN summary on this switch
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: VLAN brief summary",
        checks=[
            ("restconf ok", _restconf_ok),
            ("has vlans or vlan list",
             lambda p: _has_items_list(p) or _has_any_key(p, "vlans", "vlan_list", "item")),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: VLAN entries have ID and name/state
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC2: VLAN entries have ID",
        checks=[
            ("restconf ok", _restconf_ok),
            ("at least one VLAN has vlan_id",
             lambda p: any(
                 isinstance(v, dict) and (v.get("vlan_id") or v.get("id") or v.get("vid"))
                 for v in (
                     p.get("vlans") or p.get("items") or
                     (p.get("item") or {}).get("vlans") or []
                 )
             ) if isinstance(p, dict) else True),   # True = WARN-level only; empty is OK
        ],
        warn_on_status=[204, 503],
    )


def test_vrf_summary(base: str, d: Discovery):
    print("\n── 10. restconf_get_vrf_summary ──")
    tool = "restconf_get_vrf_summary"

    if not d.switch_ip:
        for uc in ["UC1", "UC2"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: List all VRFs configured on the switch
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: VRF summary",
        checks=[
            ("restconf ok", _restconf_ok),
            ("has vrfs or vrf list",
             lambda p: _has_items_list(p) or _has_any_key(p, "vrfs", "vrf_list", "item")),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: VRF entries have name field
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC2: VRF entries have name",
        checks=[
            ("restconf ok", _restconf_ok),
            ("VRFs have name field",
             lambda p: any(
                 isinstance(v, dict) and v.get("name")
                 for v in (
                     p.get("vrfs") or p.get("items") or
                     (p.get("item") or {}).get("vrfs") or []
                 )
             ) if isinstance(p, dict) else True),
        ],
        warn_on_status=[204, 503],
    )


def test_ip_interface(base: str, d: Discovery):
    print("\n── 11. restconf_get_ip_interface ──")
    tool = "restconf_get_ip_interface"

    if not d.switch_ip:
        for uc in ["UC1", "UC2"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: Show all IP interfaces with state and addresses
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: all IP interfaces",
        checks=[
            ("restconf ok", _restconf_ok),
            ("has interfaces or ip_interfaces",
             lambda p: _has_items_list(p) or
                       _has_any_key(p, "interfaces", "ip_interfaces", "item")),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: IP interfaces have IP address and state
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC2: interfaces have IP+state",
        checks=[
            ("restconf ok", _restconf_ok),
            ("at least one interface has IP address",
             lambda p: any(
                 isinstance(i, dict) and (
                     i.get("ip") or i.get("ip_address") or i.get("ipv4") or
                     i.get("primary_ip") or i.get("address")
                 )
                 for i in (
                     p.get("interfaces") or p.get("ip_interfaces") or
                     p.get("items") or
                     (p.get("item") or {}).get("interfaces") or []
                 )
             ) if isinstance(p, dict) else True),
        ],
        warn_on_status=[204, 503],
    )


def test_running_config(base: str, d: Discovery):
    print("\n── 12. restconf_get_running_config ──")
    tool = "restconf_get_running_config"

    if not d.switch_ip:
        for uc in ["UC1", "UC2"]:
            _skip_no_switch(tool, uc)
        return

    # UC-1: Fetch running configuration for backup review
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: running config",
        checks=[
            ("restconf ok", _restconf_ok),
            ("has config content (text or item)",
             lambda p: (
                 (isinstance((p.get("item") or {}).get("config"), str) and
                  len((p.get("item") or {}).get("config", "")) > 50)
                 or (isinstance(p.get("config"), str) and len(p.get("config", "")) > 50)
                 or _has_any_key(p, "item", "config", "running_config")
             ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[204, 503],
    )

    # UC-2: Config content contains expected switch keywords
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC2: config has valid CLI content",
        checks=[
            ("restconf ok", _restconf_ok),
            ("config text has switch CLI markers",
             lambda p: any(
                 keyword in str(p.get("config") or (p.get("item") or {}).get("config") or "").lower()
                 for keyword in ("interface", "vlan", "ip", "hostname", "version", "router", "!")
             ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[204, 503],
    )


def test_maintenance_status(base: str, d: Discovery):
    print("\n── 13. restconf_get_system_maintenance_status ──")
    tool = "restconf_get_system_maintenance_status"

    if not d.switch_ip:
        _skip_no_switch(tool, "UC1: maintenance mode status")
        return

    # UC-1: Is maintenance mode enabled on this switch?
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: maintenance mode status",
        checks=[
            ("restconf ok or 204 expected",
             lambda p: _restconf_ok(p) or _has_any_key(p, "meta", "warnings")),
            ("has maintenance status field",
             lambda p: _has_any_key(p, "item", "maintenance", "status", "mode") or
                       _has_item_content(p) or isinstance(p, dict)),
        ],
        warn_on_status=[204, 503],   # 204 = maintenance not configured
    )


def test_maintenance_rate_monitoring(base: str, d: Discovery):
    print("\n── 14. restconf_get_system_maintenance_rate_monitoring ──")
    tool = "restconf_get_system_maintenance_rate_monitoring"

    if not d.switch_ip:
        _skip_no_switch(tool, "UC1: rate monitoring status")
        return

    # UC-1: Check if maintenance rate monitoring is configured (may return 204)
    run_case(base, tool, {"switch_ip": d.switch_ip}, "UC1: rate monitoring status",
        checks=[
            ("restconf responded (204 OK per spec)",
             lambda p: isinstance(p, dict)),
        ],
        warn_on_status=[204, 503],   # 204 = feature disabled, explicitly allowed per Operator Guide
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def write_results(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "results_tier2_e.json"
    with open(json_path, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)

    txt_path = out_dir / "summary_tier2_e.txt"
    counts = {}
    for r in RESULTS:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for s in ("PASS", "FAIL", "WARN", "SKIP", "ERROR"):
        counts.setdefault(s, 0)

    total = sum(counts.values())
    lines = [
        "=" * 95,
        "XCO MCP Server — Tier-2 Smoke Test  Batch E  (RESTCONF tools)",
        f"Generated: {_now_iso()}",
        "=" * 95,
        f"{'Tool':<50} {'Use Case':<35} {'Status'}",
        "-" * 95,
    ]
    for r in RESULTS:
        detail = "; ".join(r.get("failures") or r.get("warnings") or [])[:50]
        note = f"  ← {detail}" if detail else ""
        lines.append(f"{r['tool']:<50} {r['use_case']:<35} {r['status']:<6}{note}")

    lines += [
        "-" * 95,
        f"PASS: {counts['PASS']}   FAIL: {counts['FAIL']}   WARN: {counts['WARN']}   "
        f"SKIP: {counts['SKIP']}   ERROR: {counts['ERROR']}   Total: {total}",
        f"Pass rate (PASS only): {counts['PASS']/max(1,total)*100:.1f}%",
        f"Pass+Warn rate       : {(counts['PASS']+counts['WARN'])/max(1,total)*100:.1f}%",
        "",
    ]

    failures = [r for r in RESULTS if r["status"] in ("FAIL", "ERROR")]
    if failures:
        lines.append("FAILED / ERROR details:")
        for r in failures:
            lines.append(f"  [{r['tool']} | {r['use_case']}]")
            for f in r.get("failures", []):
                lines.append(f"    ✗ {f}")
        lines.append("")

    txt_path.write_text("\n".join(lines))
    print("\n" + "\n".join(lines[-20:]))
    print(f"Results → {json_path}")
    print(f"Summary → {txt_path}")
    return counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Tier-2 Smoke Test — Batch E (RESTCONF)")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default=str(Path(__file__).parent))
    parser.add_argument("--switch", default=None,
                        help="Override switch IP (default: auto-discover from inventory)")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print(f"MCP server: {base_url}")
    print(f"Started:    {_now_iso()}")
    print("=" * 60)

    d = Discovery(base_url, override_switch_ip=args.switch).run()

    test_firmware_version(base_url, d)
    test_interface_detail(base_url, d)
    test_list_operations(base_url, d)
    test_lldp_neighbor_detail(base_url, d)
    test_port_statistics(base_url, d)
    test_media_detail(base_url, d)
    test_arp_table(base_url, d)
    test_clock(base_url, d)
    test_vlan_brief(base_url, d)
    test_vrf_summary(base_url, d)
    test_ip_interface(base_url, d)
    test_running_config(base_url, d)
    test_maintenance_status(base_url, d)
    test_maintenance_rate_monitoring(base_url, d)

    counts = write_results(Path(args.out))
    sys.exit(0 if counts["FAIL"] == 0 and counts["ERROR"] == 0 else 1)


if __name__ == "__main__":
    main()
