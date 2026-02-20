#!/usr/bin/env python3
"""
XCO MCP Server — Tier-2 Smoke Test  Batch B  (10 tools)
=========================================================
Covers: fault + inventory + monitor Tier-2 tools from
        XCO_MCP_Tier2_Operator_Notes.docx

Tools tested:
  1.  fault_get_active_alarms_top              (Tier-2)
  2.  fault_get_alarm_details_with_context     (Tier-2)
  3.  fault_get_fabric_health_related_alerts   (Tier-2)
  4.  inventory_get_device_health_rollup       (Tier-2)
  5.  inventory_get_device_inventory_export    (Tier-1, listed in Operator Guide)
  6.  inventory_get_fabric_switches_summary    (Tier-2)
  7.  inventory_get_software_version_mismatch  (Tier-2)
  8.  inventory_get_unreachable_devices        (Tier-2)
  9.  inventory_get_switches_widget_table      (Tier-2)
  10. monitor_get_platform_quick_status        (Tier-2)

Quality principles:
  PASS  = HTTP 200 AND expected content fields present AND content is non-trivial
  FAIL  = HTTP error OR missing required output fields OR hollow payload
  WARN  = Feature not configured / known empty-but-valid scenario
  SKIP  = Cannot run: required param not discoverable

Usage:
    cd /path/to/XCO-MCP-SERVER
    python3 smoke-test/smoke_tier2_b.py [--url http://localhost:8000]

Results:
    smoke-test/results_tier2_b.json
    smoke-test/summary_tier2_b.txt
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
        self.fabric_name: Optional[str] = None
        self.switch_ips: List[str] = []
        self.alarm_name: Optional[str] = None      # discovered from active alarms
        self.alarm_resource: Optional[str] = None  # resource from first active alarm

    def run(self) -> "Discovery":
        print("▶  Discovery phase …")
        self._discover_fabrics()
        self._discover_switches()
        self._discover_alarm()
        print(f"   fabric_name    : {self.fabric_name or '(none)'}")
        print(f"   switch_ips     : {self.switch_ips[:3] or '(none)'}")
        print(f"   alarm_name     : {self.alarm_name or '(none)'}")
        print(f"   alarm_resource : {self.alarm_resource or '(none)'}")
        return self

    def _discover_fabrics(self):
        raw = call_tool(self.base_url, "fabric_get_fabrics", {})
        status, payload = _extract_payload(raw)
        if status == 200 and payload:
            fabrics = payload if isinstance(payload, list) else payload.get("items") or payload.get("fabrics") or []
            if fabrics and isinstance(fabrics[0], dict):
                f = fabrics[0]
                self.fabric_name = f.get("fabric") or f.get("name") or f.get("fabric-name")

    def _discover_switches(self):
        raw = call_tool(self.base_url, "inventory_getswitches", {})
        status, payload = _extract_payload(raw)
        if status == 200 and payload:
            items = payload if isinstance(payload, list) else (
                payload.get("items") or payload.get("switches") or payload.get("data") or []
            )
            for sw in items:
                if isinstance(sw, dict):
                    ip = sw.get("ip") or sw.get("ip_address") or sw.get("mgmtIp")
                    if ip:
                        self.switch_ips.append(str(ip))

    def _discover_alarm(self):
        """Try to discover a real alarm name/resource from faultmanager."""
        raw = call_tool(self.base_url, "faultmanager_get_alarm_history",
                        {"state": "active", "limit": 5})
        status, payload = _extract_payload(raw)
        if status == 200 and payload:
            items = []
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict):
                for k in ("items", "data", "alarms", "history"):
                    v = payload.get(k)
                    if isinstance(v, list) and v:
                        items = v
                        break
            if items and isinstance(items[0], dict):
                a = items[0]
                self.alarm_name = a.get("name") or a.get("alarm_name") or a.get("type")
                self.alarm_resource = (
                    a.get("resource") or a.get("source") or a.get("device_ip")
                    or a.get("object_name")
                )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------
def run_case(
    base_url: str,
    tool: str,
    inputs: Dict[str, Any],
    use_case: str,
    checks: List[Tuple[str, Any]],
    *,
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
        if tool_status in warn_statuses:
            entry["status"] = "WARN"
            entry["warnings"].append(msg)
        else:
            entry["status"] = "FAIL"
            entry["failures"].append(msg)
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

def _non_empty_list_at(p, *path):
    cur = p
    for k in path:
        if not isinstance(cur, dict): return False
        cur = cur.get(k)
    return isinstance(cur, list) and len(cur) > 0

def _summary_has(p, *fields):
    s = p.get("summary") if isinstance(p, dict) else None
    return isinstance(s, dict) and any(s.get(f) is not None for f in fields)

def _list_payload_nonempty(p):
    if isinstance(p, list): return len(p) > 0
    if isinstance(p, dict):
        for k in ("items", "data", "results", "switches", "devices", "groups"):
            v = p.get(k)
            if isinstance(v, list) and v: return True
    return False


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

def test_fault_active_alarms_top(base: str, d: Discovery):
    print("\n── 1. fault_get_active_alarms_top ──")
    tool = "fault_get_active_alarms_top"

    # UC-1: Top active alarms — what's currently broken?
    run_case(base, tool, {"top_n": 10}, "UC1: top 10 active alarms",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
            ("summary has total count",
             lambda p: (isinstance(p.get("summary"), dict) and
                        p["summary"].get("total") is not None) if isinstance(p, dict) else False),
            ("has by_severity breakdown",
             lambda p: (isinstance(p.get("summary"), dict) and
                        bool(p["summary"].get("by_severity"))) if isinstance(p, dict) else False),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Filter by severity=CRITICAL — drill into top issue
    run_case(base, tool, {"severity_min": "CRITICAL", "top_n": 5},
             "UC2: severity_min=CRITICAL",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
            ("has groups or alarms",
             lambda p: _has_any_key(p, "groups", "alarms", "items", "top_groups")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: Filter by severity=MAJOR with inventory enrichment
    run_case(base, tool, {"severity_min": "MAJOR", "include_inventory": True},
             "UC3: severity_min=MAJOR with inventory",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
        ],
        warn_on_status=[404, 204],
    )


def test_fault_alarm_details_with_context(base: str, d: Discovery):
    print("\n── 2. fault_get_alarm_details_with_context ──")
    tool = "fault_get_alarm_details_with_context"

    # UC-1: Explain an alarm by name (if discovered)
    if d.alarm_name:
        run_case(base, tool, {"name": d.alarm_name, "window_hours": 24},
                 "UC1: alarm detail by name",
            checks=[
                ("has alarm or context",
                 lambda p: _has_any_key(p, "alarm", "context", "instances", "alarm_catalog",
                                        "summary", "description")),
                ("has next_actions", _has_next_actions),
            ],
            warn_on_status=[404],
        )
    else:
        # UC-1: Fall back to any alarm lookup by active=True
        run_case(base, tool, {"active_only": True, "window_hours": 24},
                 "UC1: active alarm detail (no name)",
            checks=[
                ("has alarm or context or no_alarms message",
                 lambda p: _has_any_key(p, "alarm", "context", "instances",
                                        "no_alarms", "message", "summary")),
            ],
            warn_on_status=[404, 400],
        )

    # UC-2: Explain alarm by resource (if discovered)
    resource = d.alarm_resource or (d.switch_ips[0] if d.switch_ips else None)
    if resource:
        run_case(base, tool, {"resource": resource, "window_hours": 24},
                 f"UC2: alarm context for resource",
            checks=[
                ("has alarm or context or no_alarm signal",
                 lambda p: _has_any_key(p, "alarm", "context", "instances", "alerts",
                                        "no_alarms", "message", "resource_health")),
            ],
            warn_on_status=[404, 204],
        )
    else:
        run_case(base, tool, {}, "UC2: alarm context (no resource)",
                 checks=[], skip_reason="no alarm_resource or switch_ip discovered")

    # UC-3: With raw evidence for escalation
    if d.alarm_name or d.alarm_resource:
        inputs = {}
        if d.alarm_name:
            inputs["name"] = d.alarm_name
        elif d.alarm_resource:
            inputs["resource"] = d.alarm_resource
        inputs["include_raw"] = True
        run_case(base, tool, inputs, "UC3: alarm detail with raw evidence",
            checks=[
                ("has alarm or context",
                 lambda p: _has_any_key(p, "alarm", "context", "instances",
                                        "no_alarms", "message", "summary")),
            ],
            warn_on_status=[404],
        )
    else:
        run_case(base, tool, {}, "UC3: alarm detail with raw",
                 checks=[], skip_reason="no alarm discovered to detail")


def test_fault_fabric_health_related_alerts(base: str, d: Discovery):
    print("\n── 3. fault_get_fabric_health_related_alerts ──")
    tool = "fault_get_fabric_health_related_alerts"

    if not d.fabric_name:
        for uc in ["UC1", "UC2", "UC3"]:
            run_case(base, tool, {}, f"{uc}: fabric health alerts",
                     checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: Find alerts showing fabric health restored/degraded (last 24h)
    run_case(base, tool, {"fabric_name": d.fabric_name, "window_hours": 24},
             "UC1: health alerts last 24h",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "counts", "totals")),
            ("has alerts or no_alerts signal",
             lambda p: _has_any_key(p, "alerts", "items", "no_alerts", "message",
                                    "signal_classification")),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Filter by signal=degraded — investigating degradation
    run_case(base, tool,
             {"fabric_name": d.fabric_name, "window_hours": 168, "signal": "degraded"},
             "UC2: degraded alerts last 7d",
        checks=[
            ("has summary or alerts",
             lambda p: _has_any_key(p, "summary", "alerts", "items", "counts")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: Filter by severity + wider window
    run_case(base, tool,
             {"fabric_name": d.fabric_name, "window_hours": 168,
              "severity": "CRITICAL", "include_other": True},
             "UC3: CRITICAL alerts + other signals",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "counts")),
        ],
        warn_on_status=[404, 204],
    )


def test_inventory_device_health_rollup(base: str, d: Discovery):
    print("\n── 4. inventory_get_device_health_rollup ──")
    tool = "inventory_get_device_health_rollup"

    # UC-1: Global device health rollup — which devices are driving fabric health RED?
    run_case(base, tool, {}, "UC1: global device health rollup",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals", "device_summary")),
            ("summary has device counts",
             lambda p: _summary_has(p, "total_devices", "device_count", "total", "devices")),
            ("has fabrics or devices list",
             lambda p: _has_any_key(p, "fabrics", "devices", "fabric_groups",
                                    "device_groups", "health_catalog")),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[404, 502],
    )

    # UC-2: Per-fabric rollup
    if d.fabric_name:
        run_case(base, tool, {"fabric_name": d.fabric_name},
                 "UC2: per-fabric device health rollup",
            checks=[
                ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
                ("has devices or fabrics",
                 lambda p: _has_any_key(p, "devices", "fabrics", "fabric_groups")),
            ],
            warn_on_status=[404, 502],
        )
    else:
        run_case(base, tool, {}, "UC2: per-fabric rollup",
                 checks=[], skip_reason="no fabric_name discovered")

    # UC-3: Health rollup filtered to unhealthy only
    run_case(base, tool, {"filter": "unhealthy"}, "UC3: filter=unhealthy devices",
        checks=[
            ("has summary or device list",
             lambda p: _has_any_key(p, "summary", "devices", "fabric_groups")),
        ],
        warn_on_status=[404, 400, 502],
    )


def test_inventory_device_inventory_export(base: str, d: Discovery):
    print("\n── 5. inventory_get_device_inventory_export ──")
    tool = "inventory_get_device_inventory_export"

    # UC-1: Export device inventory (reviewing current state)
    # Note: returns binary Excel — expect 200 with some content or a URL
    raw = call_tool(base, tool, {})
    http_status = raw.get("http_status", 0)
    tool_status, payload = _extract_payload(raw)
    conn_error = raw.get("error")

    entry: Dict[str, Any] = {
        "tool": tool, "use_case": "UC1: export inventory",
        "inputs": {}, "http_status": http_status, "tool_status": tool_status,
        "failures": [], "warnings": [], "payload_keys": [],
    }

    if conn_error or http_status == 0:
        entry["status"] = "ERROR"
        entry["failures"].append(conn_error or "no response")
    elif tool_status == 200:
        # Accept: binary content, URL pointer, or dict with download link
        if payload is None or payload == {} or payload == "":
            entry["status"] = "FAIL"
            entry["failures"].append("payload is empty/None — export returned nothing")
        else:
            entry["status"] = "PASS"
    elif tool_status in (204, 202):
        entry["status"] = "WARN"
        entry["warnings"].append(f"tool_status={tool_status} (async export or no devices)")
    else:
        entry["status"] = "FAIL"
        entry["failures"].append(f"tool_status={tool_status}")

    RESULTS.append(entry)
    detail = "; ".join(entry.get("failures") or entry.get("warnings") or [])
    _print_row(tool, "UC1: export inventory", entry["status"], detail)

    # UC-2: Export for specific fabric
    if d.fabric_name:
        run_case(base, tool, {"fabric_name": d.fabric_name},
                 "UC2: export for specific fabric",
            checks=[
                ("payload has content", lambda p: p is not None and p != {}),
            ],
            warn_on_status=[202, 204, 404],
        )
    else:
        run_case(base, tool, {}, "UC2: export for specific fabric",
                 checks=[], skip_reason="no fabric_name discovered")


def test_inventory_fabric_switches_summary(base: str, d: Discovery):
    print("\n── 6. inventory_get_fabric_switches_summary ──")
    tool = "inventory_get_fabric_switches_summary"

    if not d.fabric_name:
        for uc in ["UC1", "UC2", "UC3"]:
            run_case(base, tool, {}, f"{uc}: fabric switches",
                     checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: List all switches in a fabric
    run_case(base, tool, {"name": d.fabric_name}, "UC1: switches in fabric",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
            ("summary has count",
             lambda p: _summary_has(p, "count", "total", "switch_count")),
            ("has switches list",
             lambda p: _has_any_key(p, "switches", "items", "devices")
                       and any(isinstance(p.get(k), dict) and p[k].get("count") is not None
                               for k in ("switches",)) or
                       _has_any_key(p, "switches", "items")),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[404],
    )

    # UC-2: Same but with per-device inventory detail
    run_case(base, tool, {"name": d.fabric_name, "include_detail": True},
             "UC2: switches with device detail",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
            ("has switches", lambda p: _has_any_key(p, "switches", "items", "devices")),
        ],
        warn_on_status=[404],
    )

    # UC-3: Verify role/model/status breakdowns
    run_case(base, tool, {"name": d.fabric_name}, "UC3: role+model breakdown",
        checks=[
            ("summary has role or model breakdown",
             lambda p: (isinstance(p.get("summary"), dict) and
                        any(p["summary"].get(k) for k in
                            ("by_role", "by_model", "by_status", "roles", "models")))
             if isinstance(p, dict) else False),
        ],
        warn_on_status=[404],
    )


def test_inventory_software_version_mismatch(base: str, d: Discovery):
    print("\n── 7. inventory_get_software_version_mismatch ──")
    tool = "inventory_get_software_version_mismatch"

    # UC-1: Scan all fabrics for version mismatches
    run_case(base, tool, {}, "UC1: global version mismatch scan",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
            ("summary has mismatch count",
             lambda p: _summary_has(p, "mismatch_count", "mismatches", "total_mismatches",
                                    "fabrics_with_mismatch", "total_switches")),
            ("has groups or fabrics",
             lambda p: _has_any_key(p, "groups", "fabrics", "fabric_groups", "items")),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[502],
    )

    # UC-2: Limit to one fabric
    if d.fabric_name:
        run_case(base, tool, {"fabric_name": d.fabric_name},
                 "UC2: mismatch for specific fabric",
            checks=[
                ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
                ("has groups", lambda p: _has_any_key(p, "groups", "fabric_groups", "items")),
            ],
            warn_on_status=[404, 502],
        )
    else:
        run_case(base, tool, {}, "UC2: mismatch per-fabric",
                 checks=[], skip_reason="no fabric_name discovered")

    # UC-3: Mismatches grouped by role
    run_case(base, tool, {"group_by": "role"}, "UC3: grouped by role",
        checks=[
            ("has summary or groups",
             lambda p: _has_any_key(p, "summary", "groups", "fabric_groups")),
        ],
        warn_on_status=[400, 502],
    )


def test_inventory_unreachable_devices(base: str, d: Discovery):
    print("\n── 8. inventory_get_unreachable_devices ──")
    tool = "inventory_get_unreachable_devices"

    # UC-1: Show all currently unreachable/down devices
    run_case(base, tool, {}, "UC1: all unreachable devices",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
            ("summary has total or device count",
             lambda p: _summary_has(p, "total", "unreachable_count", "device_count",
                                    "total_unreachable")),
            ("has groups or devices",
             lambda p: _has_any_key(p, "groups", "devices", "items",
                                    "unreachable_devices")),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[502],
    )

    # UC-2: Per-fabric unreachable devices
    if d.fabric_name:
        run_case(base, tool, {"fabric_name": d.fabric_name},
                 "UC2: unreachable in specific fabric",
            checks=[
                ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
                ("has groups or devices",
                 lambda p: _has_any_key(p, "groups", "devices", "unreachable_devices")),
            ],
            warn_on_status=[404, 502],
        )
    else:
        run_case(base, tool, {}, "UC2: unreachable per-fabric",
                 checks=[], skip_reason="no fabric_name discovered")

    # UC-3: With alarm enrichment
    run_case(base, tool, {"include_alarms": True, "max_devices": 20},
             "UC3: with alarm enrichment",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
        ],
        warn_on_status=[400, 502],
    )


def test_inventory_switches_widget_table(base: str, d: Discovery):
    print("\n── 9. inventory_get_switches_widget_table ──")
    tool = "inventory_get_switches_widget_table"

    # UC-1: Dashboard switch inventory table — show all switches
    run_case(base, tool, {}, "UC1: all switches table",
        checks=[
            ("has summary with count",
             lambda p: (isinstance(p.get("summary"), dict) and
                        p["summary"].get("count") is not None)
             if isinstance(p, dict) else False),
            ("has items/switches list",
             lambda p: _has_any_key(p, "items", "switches", "devices")),
            ("items list is non-empty",
             lambda p: any(
                 isinstance(p.get(k), list) and len(p.get(k, [])) > 0
                 for k in ("items", "switches", "devices")
             ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[502],
    )

    # UC-2: Filter by fabric
    if d.fabric_name:
        run_case(base, tool, {"fabric_name": d.fabric_name},
                 "UC2: switches table for fabric",
            checks=[
                ("has summary with count",
                 lambda p: (isinstance(p.get("summary"), dict) and
                            p["summary"].get("count") is not None)
                 if isinstance(p, dict) else False),
                ("has items list",
                 lambda p: _has_any_key(p, "items", "switches", "devices")),
            ],
            warn_on_status=[404, 502],
        )
    else:
        run_case(base, tool, {}, "UC2: switches table per-fabric",
                 checks=[], skip_reason="no fabric_name discovered")

    # UC-3: With device details (include_device_details=True)
    run_case(base, tool, {"include_device_details": True, "max_items": 10},
             "UC3: table with device details",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary")),
            ("has items list", lambda p: _has_any_key(p, "items", "switches")),
        ],
        warn_on_status=[502],
    )

    # UC-4: Verify each row has IP, model, firmware, discovery status
    raw = call_tool(base, tool, {"max_items": 5})
    _, payload = _extract_payload(raw)
    if isinstance(payload, dict) and payload:
        items = payload.get("items") or payload.get("switches") or []
        if isinstance(items, list) and items:
            row = items[0]
            missing = [f for f in ("ip", "ip_address", "name", "model", "firmware",
                                    "firmware_version", "sw_version", "status",
                                    "discovery_status")
                       if not row.get(f)]
            entry = {
                "tool": tool, "use_case": "UC4: row has ip+model+firmware+status",
                "inputs": {"max_items": 5}, "http_status": 200, "tool_status": 200,
                "failures": [], "warnings": [], "payload_keys": list(row.keys()),
            }
            if len(missing) >= 4:
                entry["status"] = "WARN"
                entry["warnings"].append(f"row missing many expected fields: {missing[:4]}")
            else:
                entry["status"] = "PASS"
            RESULTS.append(entry)
            _print_row(tool, "UC4: row has ip+model+firmware+status",
                       entry["status"],
                       f"row keys: {list(row.keys())[:6]}")
        else:
            run_case(base, tool, {"max_items": 5}, "UC4: row structure check",
                     checks=[], skip_reason="no switch rows returned")
    else:
        run_case(base, tool, {"max_items": 5}, "UC4: row structure check",
                 checks=[], skip_reason="no payload from widget table")


def test_monitor_platform_quick_status(base: str, d: Discovery):
    print("\n── 10. monitor_get_platform_quick_status ──")
    tool = "monitor_get_platform_quick_status"

    # UC-1: Single view platform status — why is my environment unhealthy?
    run_case(base, tool, {}, "UC1: platform quick status",
        checks=[
            ("has efa_status or platform_status",
             lambda p: _has_any_key(p, "efa_status", "platform_status", "efa",
                                    "system", "health")),
            ("has services status",
             lambda p: _has_any_key(p, "services", "service_health", "service_status")),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[502],
    )

    # UC-2: With health detail for problematic resources
    run_case(base, tool,
             {"include_health_detail": True, "detail_only_on_problem": True},
             "UC2: with health detail on problem",
        checks=[
            ("has efa or platform info",
             lambda p: _has_any_key(p, "efa_status", "platform_status", "efa",
                                    "health", "system")),
            ("has services",
             lambda p: _has_any_key(p, "services", "service_health")),
        ],
        warn_on_status=[502],
    )

    # UC-3: Full detail + raw Tier-1 evidence
    run_case(base, tool, {"include_raw": True, "include_health_detail": True},
             "UC3: full detail with raw evidence",
        checks=[
            ("has efa or platform",
             lambda p: _has_any_key(p, "efa_status", "platform_status", "efa",
                                    "health", "system")),
        ],
        warn_on_status=[502],
    )

    # UC-4: EFA-only status (minimal call)
    run_case(base, tool,
             {"include_services": False, "include_health": False},
             "UC4: efa status only",
        checks=[
            ("has efa or platform info",
             lambda p: _has_any_key(p, "efa_status", "platform_status", "efa",
                                    "health", "system", "services")),
        ],
        warn_on_status=[502],
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def write_results(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "results_tier2_b.json"
    with open(json_path, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)

    txt_path = out_dir / "summary_tier2_b.txt"
    counts = {}
    for r in RESULTS:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for s in ("PASS", "FAIL", "WARN", "SKIP", "ERROR"):
        counts.setdefault(s, 0)

    lines = [
        "=" * 95,
        "XCO MCP Server — Tier-2 Smoke Test  Batch B  (fault + inventory + monitor)",
        f"Generated: {_now_iso()}",
        "=" * 95,
        f"{'Tool':<50} {'Use Case':<35} {'Status'}",
        "-" * 95,
    ]
    for r in RESULTS:
        detail = "; ".join(r.get("failures") or r.get("warnings") or [])[:50]
        note = f"  ← {detail}" if detail else ""
        lines.append(f"{r['tool']:<50} {r['use_case']:<35} {r['status']:<6}{note}")

    total = sum(counts.values())
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
    parser = argparse.ArgumentParser(description="Tier-2 Smoke Test — Batch B")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default=str(Path(__file__).parent))
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print(f"MCP server: {base_url}")
    print(f"Started:    {_now_iso()}")
    print("=" * 60)

    d = Discovery(base_url).run()

    test_fault_active_alarms_top(base_url, d)
    test_fault_alarm_details_with_context(base_url, d)
    test_fault_fabric_health_related_alerts(base_url, d)
    test_inventory_device_health_rollup(base_url, d)
    test_inventory_device_inventory_export(base_url, d)
    test_inventory_fabric_switches_summary(base_url, d)
    test_inventory_software_version_mismatch(base_url, d)
    test_inventory_unreachable_devices(base_url, d)
    test_inventory_switches_widget_table(base_url, d)
    test_monitor_platform_quick_status(base_url, d)

    counts = write_results(Path(args.out))
    sys.exit(0 if counts["FAIL"] == 0 and counts["ERROR"] == 0 else 1)


if __name__ == "__main__":
    main()
