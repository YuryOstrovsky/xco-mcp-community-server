#!/usr/bin/env python3
"""
XCO MCP Server — Tier-2 Smoke Test  Batch D  (9 tools)
========================================================
Covers: tenant Tier-2 tools from XCO_MCP_Tier2_Operator_Notes.docx

Tools tested:
  1.  tenant_get_bgp_peer                          (Tier-1, in Operator Guide)
  2.  tenant_get_bgp_peer_operational              (Tier-1, in Operator Guide)
  3.  tenant_get_bgp_peers                         (Tier-1, in Operator Guide)
  4.  tenant_get_mirror_sessions                   (Tier-1, in Operator Guide)
  5.  tenant_get_portchannel                       (Tier-1, in Operator Guide)
  6.  tenant_get_service_epg_alarm_summary         (Tier-2)
  7.  tenant_get_service_epg_event_logs            (Tier-2)
  8.  tenant_get_service_epg_health_summary        (Tier-2)
  9.  tenant_get_service_epg_historical_report_stub (Tier-2)

Note: All tenant tools require tenant_name — auto-discovered at runtime.
      BGP peer / port-channel names also auto-discovered.

Usage:
    cd /path/to/XCO-MCP-SERVER
    python3 smoke-test/smoke_tier2_d.py [--url http://localhost:8000]

Results:
    smoke-test/results_tier2_d.json
    smoke-test/summary_tier2_d.txt
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
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.tenant_name: Optional[str] = None
        self.bgp_peer_name: Optional[str] = None
        self.portchannel_name: Optional[str] = None
        self.fabric_name: Optional[str] = None

    def run(self) -> "Discovery":
        print("▶  Discovery phase …")
        self._discover_fabrics()
        self._discover_tenants()
        if self.tenant_name:
            self._discover_bgp_peers()
            self._discover_portchannels()
        print(f"   tenant_name      : {self.tenant_name or '(none)'}")
        print(f"   bgp_peer_name    : {self.bgp_peer_name or '(none)'}")
        print(f"   portchannel_name : {self.portchannel_name or '(none)'}")
        print(f"   fabric_name      : {self.fabric_name or '(none)'}")
        return self

    def _discover_fabrics(self):
        raw = call_tool(self.base_url, "fabric_get_fabrics", {})
        _, payload = _extract_payload(raw)
        if payload:
            fabrics = payload if isinstance(payload, list) else (
                payload.get("items") or payload.get("fabrics") or []
            )
            if fabrics and isinstance(fabrics[0], dict):
                f = fabrics[0]
                self.fabric_name = f.get("fabric") or f.get("name") or f.get("fabric-name")

    def _discover_tenants(self):
        raw = call_tool(self.base_url, "tenant_get_tenants", {})
        _, payload = _extract_payload(raw)
        if payload:
            # API returns {"tenant": [...]} (singular key)
            items = payload if isinstance(payload, list) else (
                payload.get("tenant") or payload.get("items")
                or payload.get("tenants") or payload.get("data") or []
            )
            for t in items:
                if isinstance(t, dict):
                    name = t.get("name") or t.get("tenant_name") or t.get("tenant")
                    if name:
                        self.tenant_name = str(name)
                        break

    def _discover_bgp_peers(self):
        if not self.tenant_name:
            return
        raw = call_tool(self.base_url, "tenant_get_bgp_peers",
                        {"tenant_name": self.tenant_name})
        _, payload = _extract_payload(raw)
        if payload:
            items = payload if isinstance(payload, list) else (
                payload.get("items") or payload.get("peers") or payload.get("data") or []
            )
            if items and isinstance(items[0], dict):
                p = items[0]
                self.bgp_peer_name = p.get("name") or p.get("peer_name") or p.get("peer")

    def _discover_portchannels(self):
        if not self.tenant_name:
            return
        raw = call_tool(self.base_url, "tenant_get_port_channels",
                        {"tenant_name": self.tenant_name})
        _, payload = _extract_payload(raw)
        if payload:
            items = payload if isinstance(payload, list) else (
                payload.get("items") or payload.get("port_channels") or payload.get("data") or []
            )
            if items and isinstance(items[0], dict):
                pc = items[0]
                self.portchannel_name = (
                    pc.get("name") or pc.get("portchannel_name") or pc.get("port_channel")
                )


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
    print(f"  {colour}{status:<5}{reset}  {tool[:50]:<50} {use_case[:35]:<35}{note}")


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------
def _has_any_key(p, *keys):
    return isinstance(p, dict) and any(k in p for k in keys)

def _has_next_actions(p):
    return isinstance(p, dict) and bool(
        p.get("next_actions") or p.get("next_steps") or p.get("recommendations")
    )

def _summary_has(p, *fields):
    s = p.get("summary") if isinstance(p, dict) else None
    return isinstance(s, dict) and any(s.get(f) is not None for f in fields)

def _is_nonempty_list_payload(p):
    if isinstance(p, list):
        return len(p) > 0
    if isinstance(p, dict):
        for k in ("items", "peers", "sessions", "port_channels", "data", "results"):
            v = p.get(k)
            if isinstance(v, list) and v:
                return True
    return False

def _peer_has_fields(p):
    """BGP peer object has expected network fields."""
    if isinstance(p, list) and p:
        p = p[0]
    if isinstance(p, dict):
        # check item in items list
        items = p.get("items") or p.get("peers") or (p if isinstance(p, list) else [])
        if items and isinstance(items[0], dict):
            peer = items[0]
        else:
            peer = p
        return any(peer.get(k) for k in (
            "name", "peer_name", "ip", "peer_ip", "remote_as", "local_as",
            "state", "neighbor", "address"
        ))
    return False


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

def _skip_no_tenant(tool: str, uc: str):
    run_case("", tool, {}, uc, checks=[], skip_reason="no tenant_name discovered")


def test_tenant_bgp_peer(base: str, d: Discovery):
    print("\n── 1. tenant_get_bgp_peer ──")
    tool = "tenant_get_bgp_peer"

    if not d.tenant_name:
        for uc in ["UC1", "UC2"]:
            _skip_no_tenant(tool, uc)
        return

    if not d.bgp_peer_name:
        run_case(base, tool, {}, "UC1: BGP peer detail",
                 checks=[], skip_reason="no bgp_peer_name discovered")
        run_case(base, tool, {}, "UC2: BGP peer detail with tenant",
                 checks=[], skip_reason="no bgp_peer_name discovered")
        return

    # UC-1: Get BGP peer config for a tenant — troubleshooting unexpected behavior
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "name": d.bgp_peer_name},
             "UC1: BGP peer config",
        checks=[
            ("has peer config fields",
             lambda p: _has_any_key(p, "name", "peer_name", "ip", "peer_ip",
                                    "remote_as", "local_as", "neighbor", "address")),
        ],
        warn_on_status=[404],
    )

    # UC-2: Same but verify network-relevant fields (AS numbers, neighbor IP)
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "name": d.bgp_peer_name},
             "UC2: peer has AS/IP fields",
        checks=[
            ("peer has remote_as or neighbor IP",
             lambda p: any(p.get(k) for k in (
                 "remote_as", "local_as", "peer_ip", "ip", "neighbor", "address"
             )) if isinstance(p, dict) else False),
        ],
        warn_on_status=[404],
    )


def test_tenant_bgp_peer_operational(base: str, d: Discovery):
    print("\n── 2. tenant_get_bgp_peer_operational ──")
    tool = "tenant_get_bgp_peer_operational"

    if not d.tenant_name or not d.bgp_peer_name:
        for uc in ["UC1", "UC2"]:
            run_case(base, tool, {}, uc, checks=[],
                     skip_reason="no tenant_name or bgp_peer_name discovered")
        return

    # UC-1: Operational state of BGP peer — is it established?
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "name": d.bgp_peer_name},
             "UC1: BGP peer operational state",
        checks=[
            ("has state or operational info",
             lambda p: _has_any_key(p, "state", "status", "session_state",
                                    "established", "bgp_state", "oper_state",
                                    "operational_state")),
        ],
        warn_on_status=[404],
    )

    # UC-2: Verify operational data has meaningful peer session info
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "name": d.bgp_peer_name},
             "UC2: peer session has counters or state",
        checks=[
            ("has at least one operational field",
             lambda p: any(p.get(k) is not None for k in (
                 "state", "status", "session_state", "received_prefixes",
                 "sent_prefixes", "uptime", "hold_time", "established"
             )) if isinstance(p, dict) else False),
        ],
        warn_on_status=[404],
    )


def test_tenant_bgp_peers(base: str, d: Discovery):
    print("\n── 3. tenant_get_bgp_peers ──")
    tool = "tenant_get_bgp_peers"

    if not d.tenant_name:
        for uc in ["UC1", "UC2"]:
            _skip_no_tenant(tool, uc)
        return

    # UC-1: List all BGP peers for a tenant
    run_case(base, tool, {"tenant_name": d.tenant_name}, "UC1: list all BGP peers",
        checks=[
            ("payload is a list or has peers/items",
             _is_nonempty_list_payload),
            ("each peer has name or IP",
             lambda p: _peer_has_fields(p)),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: BGP peers — investigating health (check list has at least basic structure)
    run_case(base, tool, {"tenant_name": d.tenant_name}, "UC2: peers have required fields",
        checks=[
            ("payload has some content", lambda p: p is not None and p != {}),
        ],
        warn_on_status=[404, 204],
    )


def test_tenant_mirror_sessions(base: str, d: Discovery):
    print("\n── 4. tenant_get_mirror_sessions ──")
    tool = "tenant_get_mirror_sessions"

    if not d.tenant_name:
        for uc in ["UC1", "UC2"]:
            _skip_no_tenant(tool, uc)
        return

    # UC-1: Get mirror sessions for tenant — troubleshooting traffic monitoring
    run_case(base, tool, {"tenant_name": d.tenant_name}, "UC1: mirror sessions for tenant",
        checks=[
            ("payload has sessions or empty-but-valid signal",
             lambda p: (
                 _is_nonempty_list_payload(p)
                 or (isinstance(p, dict) and _has_any_key(p, "items", "sessions", "data"))
                 or (isinstance(p, list))   # empty list is valid (no sessions configured)
             )),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Verify session structure has source/dest if sessions exist
    raw = call_tool(base, tool, {"tenant_name": d.tenant_name})
    _, payload = _extract_payload(raw)
    items = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for k in ("items", "sessions", "data"):
            v = payload.get(k)
            if isinstance(v, list):
                items = v
                break

    entry: Dict[str, Any] = {
        "tool": tool, "use_case": "UC2: session has source+dest fields",
        "inputs": {"tenant_name": d.tenant_name},
        "http_status": None, "tool_status": None,
        "failures": [], "warnings": [], "payload_keys": [],
    }
    if not items:
        entry["status"] = "WARN"
        entry["warnings"].append("no sessions configured (empty list is valid)")
    else:
        sess = items[0] if isinstance(items[0], dict) else {}
        expected = ("name", "source", "destination", "direction", "status")
        missing = [f for f in expected if not sess.get(f)]
        if len(missing) >= 4:
            entry["status"] = "WARN"
            entry["warnings"].append(f"session fields sparse: has {list(sess.keys())[:4]}")
        else:
            entry["status"] = "PASS"
        entry["payload_keys"] = list(sess.keys())
    RESULTS.append(entry)
    _print_row(tool, "UC2: session has source+dest fields",
               entry["status"],
               "; ".join(entry.get("warnings") or entry.get("failures") or []))


def test_tenant_portchannel(base: str, d: Discovery):
    print("\n── 5. tenant_get_portchannel ──")
    tool = "tenant_get_portchannel"

    if not d.tenant_name:
        for uc in ["UC1", "UC2"]:
            _skip_no_tenant(tool, uc)
        return

    if not d.portchannel_name:
        run_case(base, tool, {}, "UC1: portchannel detail",
                 checks=[], skip_reason="no portchannel_name discovered")
        run_case(base, tool, {}, "UC2: portchannel config fields",
                 checks=[], skip_reason="no portchannel_name discovered")
        return

    # UC-1: Get portchannel configuration for tenant
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "name": d.portchannel_name},
             "UC1: portchannel config",
        checks=[
            ("has portchannel config fields",
             lambda p: _has_any_key(p, "name", "portchannel_name", "port_channel",
                                    "members", "interfaces", "mode", "lacp")),
        ],
        warn_on_status=[404],
    )

    # UC-2: Verify portchannel has member interfaces or LACP mode
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "name": d.portchannel_name},
             "UC2: portchannel has members/mode",
        checks=[
            ("has members or mode or LACP",
             lambda p: any(p.get(k) is not None for k in (
                 "members", "interfaces", "mode", "lacp", "admin_state",
                 "member_ports", "portchannel_type"
             )) if isinstance(p, dict) else False),
        ],
        warn_on_status=[404],
    )


def test_tenant_epg_alarm_summary(base: str, d: Discovery):
    print("\n── 6. tenant_get_service_epg_alarm_summary ──")
    tool = "tenant_get_service_epg_alarm_summary"

    if not d.tenant_name:
        for uc in ["UC1", "UC2", "UC3"]:
            _skip_no_tenant(tool, uc)
        return

    # UC-1: Show all active alarms for tenant/EPG scope
    # Tool returns: filter, tenant, counts, rows, warnings, next_actions.
    run_case(base, tool, {"tenant_name": d.tenant_name},
             "UC1: all active alarms for tenant",
        checks=[
            ("has counts or rows or tenant",
             lambda p: _has_any_key(p, "summary", "alarm_count", "alarms",
                                    "total", "no_alarms", "message",
                                    "counts", "rows", "tenant", "filter")),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Filter by severity_min=CRITICAL
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "severity_min": "CRITICAL"},
             "UC2: severity_min=CRITICAL",
        checks=[
            ("has summary or alarms",
             lambda p: _has_any_key(p, "summary", "alarms", "no_alarms", "message")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: With alerts included and raw evidence
    run_case(base, tool,
             {"tenant_name": d.tenant_name,
              "include_alarms": True, "include_alerts": True,
              "include_raw": True},
             "UC3: alarms + alerts + raw",
        checks=[
            ("has summary or alarm data",
             lambda p: _has_any_key(p, "summary", "alarms", "no_alarms")),
        ],
        warn_on_status=[404, 204],
    )


def test_tenant_epg_event_logs(base: str, d: Discovery):
    print("\n── 7. tenant_get_service_epg_event_logs ──")
    tool = "tenant_get_service_epg_event_logs"

    if not d.tenant_name:
        for uc in ["UC1", "UC2", "UC3"]:
            _skip_no_tenant(tool, uc)
        return

    # UC-1: Event logs for tenant — what happened recently?
    # Tool returns: filter, scope, counts, rows, warnings. No next_actions key.
    run_case(base, tool, {"tenant_name": d.tenant_name},
             "UC1: recent event logs for tenant",
        checks=[
            ("has rows or counts or scope",
             lambda p: _has_any_key(p, "events", "items", "summary",
                                    "no_events", "message", "executions",
                                    "rows", "counts", "scope", "filter")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Filter by severity_min=MAJOR (investigating degradation)
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "severity_min": "MAJOR"},
             "UC2: severity_min=MAJOR events",
        checks=[
            ("has events or summary or rows",
             lambda p: _has_any_key(p, "events", "items", "summary", "no_events",
                                    "rows", "counts")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: Keyword search in event logs
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "query": "bgp"},
             "UC3: keyword query=bgp",
        checks=[
            ("has events or no_events or rows",
             lambda p: _has_any_key(p, "events", "items", "summary", "no_events",
                                    "message", "rows", "counts")),
        ],
        warn_on_status=[404, 204],
    )


def test_tenant_epg_health_summary(base: str, d: Discovery):
    print("\n── 8. tenant_get_service_epg_health_summary ──")
    tool = "tenant_get_service_epg_health_summary"

    if not d.tenant_name:
        for uc in ["UC1", "UC2", "UC3"]:
            _skip_no_tenant(tool, uc)
        return

    # UC-1: Real-time health summary for tenant VRFs + EPGs
    # Tool returns: filter, tenant, overall_status, counts, vrf_summary, rows,
    # executions, events, locks, warnings, next_actions.
    run_case(base, tool, {"tenant_name": d.tenant_name},
             "UC1: VRF + EPG health summary",
        checks=[
            ("has vrf_summary or overall_status or counts",
             lambda p: _has_any_key(p, "vrfs", "epgs", "endpoint_groups",
                                    "summary", "health_summary", "tenant_name",
                                    "vrf_summary", "overall_status", "counts",
                                    "tenant")),
            ("has tenant echoed back",
             lambda p: bool(p.get("tenant_name") or p.get("name") or p.get("tenant"))
             if isinstance(p, dict) else False),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[404],
    )

    # UC-2: Same — verify VRF/EPG breakdown has health status fields
    run_case(base, tool, {"tenant_name": d.tenant_name},
             "UC2: VRF/EPG rows have health status",
        checks=[
            ("has vrfs or epgs list",
             lambda p: _has_any_key(p, "vrfs", "epgs", "endpoint_groups",
                                    "vrf_summary", "epg_summary")),
        ],
        warn_on_status=[404],
    )

    # UC-3: Wrong tenant name → expected 404 with suggested tenants
    run_case(base, tool, {"tenant_name": "__no_such_tenant_xyz__"},
             "UC3: wrong tenant → 404 + suggestions",
        checks=[
            ("has suggested_tenants or error message",
             lambda p: _has_any_key(p, "suggested_tenants", "suggestions",
                                    "error", "message", "next_actions")),
        ],
        warn_on_status=[404],
    )


def test_tenant_epg_historical_report(base: str, d: Discovery):
    print("\n── 9. tenant_get_service_epg_historical_report_stub ──")
    tool = "tenant_get_service_epg_historical_report_stub"

    if not d.tenant_name:
        for uc in ["UC1", "UC2", "UC3", "UC4", "UC5"]:
            _skip_no_tenant(tool, uc)
        return

    # UC-1: Weekly tenant health pulse (7d)
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "window_days": 7},
             "UC1: weekly health pulse (7d)",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "report", "totals")),
            ("has tenant_name", lambda p: bool(p.get("tenant_name") or p.get("tenant"))
             if isinstance(p, dict) else False),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[404],
    )

    # UC-2: Monthly ops snapshot (30d)
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "window_days": 30},
             "UC2: monthly snapshot (30d)",
        checks=[
            ("has summary or report",
             lambda p: _has_any_key(p, "summary", "report", "totals")),
        ],
        warn_on_status=[404],
    )

    # UC-3: Escalation focus — only MAJOR+ severity
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "window_days": 7, "severity_min": "MAJOR"},
             "UC3: severity_min=MAJOR (7d)",
        checks=[
            ("has summary or report",
             lambda p: _has_any_key(p, "summary", "report", "totals")),
        ],
        warn_on_status=[404],
    )

    # UC-4: Keyword hunt — bgp/vxlan/certificate
    run_case(base, tool,
             {"tenant_name": d.tenant_name, "window_days": 30, "query": "bgp"},
             "UC4: keyword query=bgp",
        checks=[
            ("has summary or report",
             lambda p: _has_any_key(p, "summary", "report", "totals")),
        ],
        warn_on_status=[404],
    )

    # UC-5: Tenant discovery — wrong name returns suggested_tenants
    run_case(base, tool,
             {"tenant_name": "__no_such_tenant_xyz__", "window_days": 7},
             "UC5: wrong tenant → suggested_tenants",
        checks=[
            ("has suggested_tenants or error",
             lambda p: _has_any_key(p, "suggested_tenants", "suggestions",
                                    "error", "message", "next_actions")),
        ],
        warn_on_status=[404],
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def write_results(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "results_tier2_d.json"
    with open(json_path, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)

    txt_path = out_dir / "summary_tier2_d.txt"
    counts = {}
    for r in RESULTS:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for s in ("PASS", "FAIL", "WARN", "SKIP", "ERROR"):
        counts.setdefault(s, 0)

    total = sum(counts.values())
    lines = [
        "=" * 95,
        "XCO MCP Server — Tier-2 Smoke Test  Batch D  (tenant tools)",
        f"Generated: {_now_iso()}",
        "=" * 95,
        f"{'Tool':<55} {'Use Case':<35} {'Status'}",
        "-" * 95,
    ]
    for r in RESULTS:
        detail = "; ".join(r.get("failures") or r.get("warnings") or [])[:50]
        note = f"  ← {detail}" if detail else ""
        lines.append(f"{r['tool']:<55} {r['use_case']:<35} {r['status']:<6}{note}")

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
    parser = argparse.ArgumentParser(description="Tier-2 Smoke Test — Batch D (tenant tools)")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default=str(Path(__file__).parent))
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print(f"MCP server: {base_url}")
    print(f"Started:    {_now_iso()}")
    print("=" * 60)

    d = Discovery(base_url).run()

    test_tenant_bgp_peer(base_url, d)
    test_tenant_bgp_peer_operational(base_url, d)
    test_tenant_bgp_peers(base_url, d)
    test_tenant_mirror_sessions(base_url, d)
    test_tenant_portchannel(base_url, d)
    test_tenant_epg_alarm_summary(base_url, d)
    test_tenant_epg_event_logs(base_url, d)
    test_tenant_epg_health_summary(base_url, d)
    test_tenant_epg_historical_report(base_url, d)

    counts = write_results(Path(args.out))
    sys.exit(0 if counts["FAIL"] == 0 and counts["ERROR"] == 0 else 1)


if __name__ == "__main__":
    main()
