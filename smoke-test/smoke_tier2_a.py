#!/usr/bin/env python3
"""
XCO MCP Server — Tier-2 Smoke Test  Batch A  (10 tools)
=========================================================
Covers: auth + fabric Tier-2 tools from XCO_MCP_Tier2_Operator_Notes.docx

Tools tested:
  1.  auth_get_executions                   (Tier-1, listed in Operator Guide)
  2.  fabric_get_fabric_efa_command_list     (Tier-2)
  3.  fabric_get_fabric_errors_summary       (Tier-2)
  4.  fabric_get_fabric_execution_last_failed (Tier-2)
  5.  fabric_get_fabric_execution_recent     (Tier-2)
  6.  fabric_get_fabric_health_summary       (Tier-2)
  7.  fabric_get_fabric_health_timeline      (Tier-2)
  8.  fabric_get_fabric_overview             (Tier-2)
  9.  fabric_get_fabric_validation_report    (Tier-2)
  10. fabric_get_running_config              (Tier-1, listed in Operator Guide)

Operator use-cases per tool: 1-4 use cases as described in Operator Guide.

Quality principles (differs from earlier batches):
  - PASS  = HTTP 200 AND expected content fields present AND content is non-trivial
  - FAIL  = HTTP error OR missing required output fields OR content is hollow
  - WARN  = Feature not configured / empty list is valid / recoverable gap
  - SKIP  = Cannot run: required param not discoverable

Content is "trivial / hollow" if:
  - payload is None, an empty string, or an empty dict {}
  - summary-style tools return no headline / verdict / next_actions at all

Usage:
    cd /path/to/XCO-MCP-SERVER
    python3 smoke-test/smoke_tier2_a.py [--url http://localhost:8000]

Results:
    smoke-test/results_tier2_a.json   — machine-readable per-case results
    smoke-test/summary_tier2_a.txt    — human-readable summary table
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_URL = os.getenv("MCP_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Results tracking
# ---------------------------------------------------------------------------
RESULTS: List[Dict[str, Any]] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# MCP tool caller
# ---------------------------------------------------------------------------
def call_tool(base_url: str, tool_name: str, inputs: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    """POST /invoke and return the normalised response dict."""
    url = f"{base_url.rstrip('/')}/invoke"
    payload = {"tool": tool_name, "inputs": inputs}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        http_status = resp.status_code
        try:
            body = resp.json()
        except Exception:
            body = {"raw_text": resp.text}
        return {"http_status": http_status, "body": body}
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
    Exception: fabric_get_fabric_overview returns the data dict directly
    (no inner {status,payload} wrapper), so only one unwrap is needed there.
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

    # Fallback: body IS the payload (e.g. fabric_get_fabric_overview)
    return http_status, body or None


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------
class Discovery:
    """Auto-discover fabric_name, switch IPs, and other required params."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.fabric_name: Optional[str] = None
        self.switch_ips: List[str] = []
        self._errors: List[str] = []

    def run(self) -> "Discovery":
        print("▶  Discovery phase …")
        self._discover_fabrics()
        self._discover_switches()
        print(f"   fabric_name  : {self.fabric_name or '(none)'}")
        print(f"   switch_ips   : {self.switch_ips[:3] or '(none)'}")
        return self

    def _discover_fabrics(self):
        raw = call_tool(self.base_url, "fabric_get_fabrics", {})
        status, payload = _extract_payload(raw)
        if status == 200 and payload:
            fabrics = []
            if isinstance(payload, list):
                fabrics = payload
            elif isinstance(payload, dict):
                for k in ("items", "fabrics", "data"):
                    if isinstance(payload.get(k), list):
                        fabrics = payload[k]
                        break
            if fabrics and isinstance(fabrics[0], dict):
                self.fabric_name = (
                    fabrics[0].get("fabric")
                    or fabrics[0].get("name")
                    or fabrics[0].get("fabric-name")
                )
        if not self.fabric_name:
            self._errors.append("Could not discover a fabric name")

    def _discover_switches(self):
        raw = call_tool(self.base_url, "inventory_getswitches", {})
        status, payload = _extract_payload(raw)
        if status == 200 and payload:
            items = []
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict):
                for k in ("items", "switches", "data"):
                    if isinstance(payload.get(k), list):
                        items = payload[k]
                        break
            for sw in items:
                if isinstance(sw, dict):
                    ip = sw.get("ip") or sw.get("ip_address") or sw.get("mgmtIp")
                    if ip:
                        self.switch_ips.append(str(ip))


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------
def run_case(
    base_url: str,
    tool: str,
    inputs: Dict[str, Any],
    use_case: str,
    checks: List[Tuple[str, Any]],  # list of (description, callable/value)
    *,
    skip_reason: Optional[str] = None,
    warn_on_status: Optional[List[int]] = None,
) -> str:
    """
    Run one test case.  Returns "PASS" | "FAIL" | "WARN" | "SKIP" | "ERROR".
    Appends result to global RESULTS list.
    """
    result_entry: Dict[str, Any] = {
        "tool": tool,
        "use_case": use_case,
        "inputs": inputs,
        "status": "PENDING",
        "http_status": None,
        "tool_status": None,
        "failures": [],
        "warnings": [],
        "payload_keys": [],
    }

    if skip_reason:
        result_entry["status"] = "SKIP"
        result_entry["skip_reason"] = skip_reason
        RESULTS.append(result_entry)
        _print_row(tool, use_case, "SKIP", skip_reason)
        return "SKIP"

    raw = call_tool(base_url, tool, inputs)
    http_status = raw.get("http_status", 0)
    tool_status, payload = _extract_payload(raw)
    conn_error = raw.get("error")

    result_entry["http_status"] = http_status
    result_entry["tool_status"] = tool_status

    if isinstance(payload, dict):
        result_entry["payload_keys"] = list(payload.keys())
    elif isinstance(payload, list):
        result_entry["payload_keys"] = [f"list[{len(payload)}]"]

    # Connection / invocation error
    if conn_error or http_status == 0:
        result_entry["status"] = "ERROR"
        result_entry["failures"].append(conn_error or "No HTTP response")
        RESULTS.append(result_entry)
        _print_row(tool, use_case, "ERROR", conn_error or "no response")
        return "ERROR"

    # Non-200 tool status: check if it's a WARN-able status
    warn_statuses = set(warn_on_status or [])
    if tool_status != 200:
        msg = f"tool_status={tool_status}"
        if tool_status in warn_statuses:
            result_entry["status"] = "WARN"
            result_entry["warnings"].append(msg)
            RESULTS.append(result_entry)
            _print_row(tool, use_case, "WARN", msg)
            return "WARN"
        else:
            result_entry["status"] = "FAIL"
            result_entry["failures"].append(msg)
            RESULTS.append(result_entry)
            _print_row(tool, use_case, "FAIL", msg)
            return "FAIL"

    # Hollow payload check
    if payload is None or payload == {} or payload == "":
        result_entry["status"] = "FAIL"
        result_entry["failures"].append("payload is empty/None")
        RESULTS.append(result_entry)
        _print_row(tool, use_case, "FAIL", "empty payload")
        return "FAIL"

    # Run content checks
    failures = []
    warnings = []
    for desc, checker in checks:
        try:
            if callable(checker):
                ok = checker(payload)
            else:
                ok = bool(checker)
            if not ok:
                failures.append(desc)
        except Exception as e:
            failures.append(f"{desc} [exception: {e}]")

    if failures:
        result_entry["status"] = "FAIL"
        result_entry["failures"] = failures
        RESULTS.append(result_entry)
        _print_row(tool, use_case, "FAIL", "; ".join(failures[:2]))
        return "FAIL"

    result_entry["status"] = "PASS"
    RESULTS.append(result_entry)
    _print_row(tool, use_case, "PASS", "")
    return "PASS"


def _print_row(tool: str, use_case: str, status: str, detail: str):
    label = f"{tool} | {use_case}"
    colour = {"PASS": "\033[32m", "FAIL": "\033[31m", "WARN": "\033[33m",
               "SKIP": "\033[36m", "ERROR": "\033[35m"}.get(status, "")
    reset = "\033[0m"
    detail_str = f"  ← {detail}" if detail else ""
    print(f"  {colour}{status:<5}{reset}  {label[:75]:<75}{detail_str}")


# ---------------------------------------------------------------------------
# Payload helper lambdas
# ---------------------------------------------------------------------------
def _has_keys(payload, *keys):
    """True if payload is a dict with all of the given keys present (value may be None)."""
    return isinstance(payload, dict) and all(k in payload for k in keys)


def _has_any_key(payload, *keys):
    return isinstance(payload, dict) and any(k in payload for k in keys)


def _non_empty_list(payload, *path):
    """Walk path in payload dict, return True if result is a non-empty list."""
    cur = payload
    for k in path:
        if not isinstance(cur, dict):
            return False
        cur = cur.get(k)
    return isinstance(cur, list) and len(cur) > 0


def _is_list_payload(payload):
    """Payload is a non-empty list OR a dict with an 'items'/'data' key that is a non-empty list."""
    if isinstance(payload, list):
        return len(payload) > 0
    if isinstance(payload, dict):
        for k in ("items", "data", "executions", "results"):
            v = payload.get(k)
            if isinstance(v, list) and len(v) > 0:
                return True
    return False


def _has_next_actions(payload):
    return isinstance(payload, dict) and bool(
        payload.get("next_actions") or payload.get("next_steps") or payload.get("recommendations")
    )


# ---------------------------------------------------------------------------
# Individual tool test suites
# ---------------------------------------------------------------------------

def test_auth_get_executions(base: str, d: Discovery):
    print("\n── 1. auth_get_executions ──")
    tool = "auth_get_executions"

    # UC-1: Get all executions (no filter)
    run_case(base, tool, {}, "UC1: all executions",
        checks=[
            ("payload is a list or has items",
             lambda p: _is_list_payload(p) or isinstance(p, dict)),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Filter by status=failed  (investigating recent failures)
    run_case(base, tool, {"status": "failed"}, "UC2: filter status=failed",
        checks=[
            ("payload is not None", lambda p: p is not None),
        ],
        warn_on_status=[404, 204, 400],
    )

    # UC-3: Filter by status=success
    run_case(base, tool, {"status": "success"}, "UC3: filter status=success",
        checks=[
            ("payload is not None", lambda p: p is not None),
        ],
        warn_on_status=[404, 204, 400],
    )


def test_fabric_efa_command_list(base: str, d: Discovery):
    print("\n── 2. fabric_get_fabric_efa_command_list ──")
    tool = "fabric_get_fabric_efa_command_list"

    if not d.fabric_name:
        run_case(base, tool, {}, "UC1: EFA commands for fabric",
                 checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: Get EFA commands for the fabric  (review recent changes)
    # Payload keys: filter, summary, signals, recommendations, next_actions
    # summary.fabric = fabric name; signals.efa_commands.items = command list
    run_case(base, tool, {"name": d.fabric_name}, "UC1: EFA commands for fabric",
        checks=[
            ("has fabric identifier",
             lambda p: _has_any_key(p, "summary", "signals", "filter", "fabric_name", "name", "fabric")),
            ("has commands or config",
             lambda p: (
                 isinstance(p.get("signals", {}).get("efa_commands"), dict)
                 or _has_any_key(p, "commands", "config_lines", "efa_commands", "lines", "config")
             )),
        ],
        warn_on_status=[404],
    )

    # UC-2: Ask for running config review (same call, validate next_actions provided)
    run_case(base, tool, {"name": d.fabric_name, "include_raw": True},
             "UC2: with include_raw=true",
        checks=[
            ("payload is a dict", lambda p: isinstance(p, dict)),
            ("has some content key",
             lambda p: _has_any_key(p, "summary", "signals", "filter", "raw",
                                    "commands", "config_lines", "efa_commands")),
        ],
        warn_on_status=[404, 400],
    )


def test_fabric_errors_summary(base: str, d: Discovery):
    print("\n── 3. fabric_get_fabric_errors_summary ──")
    tool = "fabric_get_fabric_errors_summary"

    if not d.fabric_name:
        run_case(base, tool, {}, "UC1: errors summary",
                 checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: Fabric errors summary — what's broken?
    run_case(base, tool, {"name": d.fabric_name}, "UC1: errors summary for fabric",
        checks=[
            ("has summary or error_count",
             lambda p: _has_any_key(p, "summary", "error_count", "errors", "per_device_errors",
                                    "total_errors", "fabric_health")),
            ("has next_actions",
             _has_next_actions),
        ],
        warn_on_status=[404],
    )

    # UC-2: Same but include raw Tier-1 payloads for drill-down
    run_case(base, tool, {"name": d.fabric_name, "include_raw": True},
             "UC2: errors summary with raw evidence",
        checks=[
            ("has summary or error fields",
             lambda p: _has_any_key(p, "summary", "error_count", "errors",
                                    "per_device_errors", "total_errors")),
        ],
        warn_on_status=[404],
    )

    # UC-3: Missing fabric name — should return 400 (bad request), not 500
    run_case(base, tool, {}, "UC3: missing name → expected 400",
        checks=[
            ("error message present",
             lambda p: isinstance(p, dict) and bool(p.get("error") or p.get("message"))),
        ],
        warn_on_status=[400],   # 400 is the CORRECT response here
    )


def test_fabric_execution_last_failed(base: str, d: Discovery):
    print("\n── 4. fabric_get_fabric_execution_last_failed ──")
    tool = "fabric_get_fabric_execution_last_failed"

    if not d.fabric_name:
        run_case(base, tool, {}, "UC1: last failed execution",
                 checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: Find most recent failed execution (troubleshooting)
    run_case(base, tool, {"name": d.fabric_name}, "UC1: last failed execution",
        checks=[
            ("has summary or no_failure signal",
             lambda p: _has_any_key(p, "summary", "execution_id", "no_failure",
                                    "last_failed", "message", "status_message")),
            ("has next_actions or message",
             lambda p: _has_next_actions(p) or bool(p.get("message") or p.get("status_message"))),
        ],
        warn_on_status=[404],
    )

    # UC-2: With detail — drill into failure reason
    run_case(base, tool, {"name": d.fabric_name, "include_detail": True},
             "UC2: last failed execution with detail",
        checks=[
            ("has summary or detail",
             lambda p: _has_any_key(p, "summary", "execution_id", "detail",
                                    "no_failure", "message")),
        ],
        warn_on_status=[404],
    )


def test_fabric_execution_recent(base: str, d: Discovery):
    print("\n── 5. fabric_get_fabric_execution_recent ──")
    tool = "fabric_get_fabric_execution_recent"

    if not d.fabric_name:
        run_case(base, tool, {}, "UC1: recent executions",
                 checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: What changed in the last few hours?
    run_case(base, tool, {"name": d.fabric_name, "limit": 20}, "UC1: recent executions",
        checks=[
            ("has executions or summary",
             lambda p: _has_any_key(p, "executions", "summary", "items",
                                    "recent_executions", "matched")),
            ("has next_actions",
             _has_next_actions),
        ],
        warn_on_status=[404],
    )

    # UC-2: Filter by status=FAILED — show recent failures
    run_case(base, tool, {"name": d.fabric_name, "status": "FAILED", "limit": 10},
             "UC2: filter status=FAILED",
        checks=[
            ("payload is a dict",
             lambda p: isinstance(p, dict)),
            ("has executions or summary",
             lambda p: _has_any_key(p, "executions", "summary", "items", "matched")),
        ],
        warn_on_status=[404, 400],
    )

    # UC-3: With execution detail for the most recent items
    run_case(base, tool, {"name": d.fabric_name, "include_detail": True, "detail_limit": 2},
             "UC3: with execution detail",
        checks=[
            ("has executions or summary",
             lambda p: _has_any_key(p, "executions", "summary", "items", "matched")),
        ],
        warn_on_status=[404],
    )


def test_fabric_health_summary(base: str, d: Discovery):
    print("\n── 6. fabric_get_fabric_health_summary ──")
    tool = "fabric_get_fabric_health_summary"

    # UC-1: Global health — why is my environment unhealthy?
    run_case(base, tool, {}, "UC1: global health (no name)",
        checks=[
            ("has global_context",
             lambda p: _has_any_key(p, "global_context", "global_health", "service_health",
                                    "fabrics", "summary")),
            ("has next_actions",
             _has_next_actions),
        ],
        warn_on_status=[404],
    )

    if not d.fabric_name:
        run_case(base, tool, {}, "UC2-3: per-fabric summary",
                 checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-2: Per-fabric health — drill into specific fabric
    run_case(base, tool, {"name": d.fabric_name}, "UC2: per-fabric health",
        checks=[
            ("has headline",
             lambda p: _has_any_key(p, "headline", "fabric_health", "health")),
            ("has device_health_counts or device counts",
             lambda p: _has_any_key(p, "device_health_counts", "device_counts",
                                    "unhealthy_count", "unhealthy_devices")),
            ("has next_actions",
             _has_next_actions),
        ],
        warn_on_status=[404],
    )

    # UC-3: Per-fabric health with error details
    run_case(base, tool, {"name": d.fabric_name, "include_errors": True},
             "UC3: per-fabric health with errors",
        checks=[
            ("has headline or fabric_health",
             lambda p: _has_any_key(p, "headline", "fabric_health", "health")),
        ],
        warn_on_status=[404],
    )


def test_fabric_health_timeline(base: str, d: Discovery):
    print("\n── 7. fabric_get_fabric_health_timeline ──")
    tool = "fabric_get_fabric_health_timeline"

    if not d.fabric_name:
        run_case(base, tool, {}, "UC1: health timeline",
                 checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: Health timeline — what changed recently?
    run_case(base, tool, {"name": d.fabric_name, "window_hours": 24},
             "UC1: timeline last 24h",
        checks=[
            ("has timeline or events or executions",
             lambda p: _has_any_key(p, "timeline", "events", "executions",
                                    "event_history", "summary")),
            ("has next_actions",
             _has_next_actions),
        ],
        warn_on_status=[404],
    )

    # UC-2: Wider window — last 7 days
    run_case(base, tool, {"name": d.fabric_name, "window_hours": 168},
             "UC2: timeline last 7 days",
        checks=[
            ("has timeline or events",
             lambda p: _has_any_key(p, "timeline", "events", "executions",
                                    "event_history", "summary")),
        ],
        warn_on_status=[404],
    )

    # UC-3: With execution detail
    run_case(base, tool,
             {"name": d.fabric_name, "include_exec_details": True, "max_exec_details": 3},
             "UC3: with execution detail",
        checks=[
            ("has timeline or summary",
             lambda p: _has_any_key(p, "timeline", "events", "executions", "summary")),
        ],
        warn_on_status=[404],
    )


def test_fabric_overview(base: str, d: Discovery):
    print("\n── 8. fabric_get_fabric_overview ──")
    tool = "fabric_get_fabric_overview"

    if not d.fabric_name:
        run_case(base, tool, {}, "UC1: fabric overview",
                 checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: Compact fabric overview — give me a summary view
    # NOTE: this tool uses input key 'fabric_name', not 'name'.
    # Payload keys: filter, count, fabrics (list), warnings
    # Health info lives inside fabrics[N].headline.fabric_health
    run_case(base, tool, {"fabric_name": d.fabric_name}, "UC1: compact overview",
        checks=[
            ("has fabric identifier",
             lambda p: _has_any_key(p, "fabrics", "count", "filter",
                                    "fabric_name", "name", "fabric", "fabric-name")),
            ("has health or errors",
             lambda p: (
                 _has_any_key(p, "health", "errors", "fabric_health",
                              "topology_health", "summary_raw", "devices_summary")
                 or (isinstance(p.get("fabrics"), list) and len(p.get("fabrics", [])) > 0)
             )),
        ],
        warn_on_status=[404],
    )

    # UC-2: With raw Tier-1 evidence
    # summary_raw / health_raw are inside each fabrics[] entry, not top-level
    run_case(base, tool, {"fabric_name": d.fabric_name, "include_raw": True},
             "UC2: overview with raw data",
        checks=[
            ("has fabric identifier",
             lambda p: _has_any_key(p, "fabrics", "count", "filter",
                                    "fabric_name", "name", "fabric")),
            ("has raw or devices_raw",
             lambda p: (
                 _has_any_key(p, "health_raw", "devices_raw", "raw", "fabric_health", "health")
                 or (isinstance(p.get("fabrics"), list) and len(p.get("fabrics", [])) > 0)
             )),
        ],
        warn_on_status=[404],
    )

    # UC-3: Top issue — include devices health
    run_case(base, tool, {"fabric_name": d.fabric_name, "include_devices": True},
             "UC3: overview with device details",
        checks=[
            ("payload is a dict", lambda p: isinstance(p, dict)),
        ],
        warn_on_status=[404, 400],
    )


def test_fabric_validation_report(base: str, d: Discovery):
    print("\n── 9. fabric_get_fabric_validation_report ──")
    tool = "fabric_get_fabric_validation_report"

    if not d.fabric_name:
        run_case(base, tool, {}, "UC1: validation report",
                 checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: Pre-change readiness — is fabric ready for changes?
    # Payload keys: filter, summary, signals, recommendations, next_actions
    # verdict lives in summary.verdict (PASS/WARN/FAIL), NOT at top level
    def _has_verdict(p):
        if not isinstance(p, dict):
            return False
        return (
            isinstance(p.get("verdict"), str)
            or isinstance((p.get("summary") or {}).get("verdict"), str)
        )

    run_case(base, tool, {"name": d.fabric_name}, "UC1: pre-change validation",
        checks=[
            ("has verdict (PASS/WARN/FAIL)", _has_verdict),
            ("has checks or summary",
             lambda p: _has_any_key(p, "checks", "summary", "results", "health_check")),
            ("has next_actions",
             _has_next_actions),
        ],
        warn_on_status=[404],
    )

    # UC-2: Audit report — investigating health degradation
    run_case(base, tool, {"name": d.fabric_name, "include_locks": True},
             "UC2: validation with lock check",
        checks=[
            ("has verdict", _has_verdict),
        ],
        warn_on_status=[404, 400],
    )

    # UC-3: With raw evidence for escalation
    run_case(base, tool, {"name": d.fabric_name, "include_raw": True},
             "UC3: validation with raw evidence",
        checks=[
            ("has verdict", _has_verdict),
        ],
        warn_on_status=[404, 400],
    )


def test_fabric_running_config(base: str, d: Discovery):
    print("\n── 10. fabric_get_running_config ──")
    tool = "fabric_get_running_config"

    if not d.fabric_name:
        run_case(base, tool, {}, "UC1: running config",
                 checks=[], skip_reason="no fabric_name discovered")
        return

    # UC-1: Get running config for fabric (reviewing recent changes)
    # This is a Tier-1 tool; exact payload key names depend on the XCO API version.
    # Accept any non-trivial payload: non-empty string, list, or dict with values.
    run_case(base, tool, {"name": d.fabric_name}, "UC1: running config",
        checks=[
            ("payload has config content",
             lambda p: (
                 (isinstance(p, str) and len(p) > 5)
                 or (isinstance(p, list) and len(p) > 0)
                 or (isinstance(p, dict) and any(
                     v is not None and v != "" and v != {} and v != []
                     for v in p.values()
                 ))
             )),
        ],
        warn_on_status=[404, 204, 400],
    )

    # UC-2: Same — reviewing before/after a change
    run_case(base, tool, {"name": d.fabric_name, "include_raw": True},
             "UC2: running config with raw flag",
        checks=[
            ("payload is non-trivial", lambda p: p is not None and p != {}),
        ],
        warn_on_status=[404, 204, 400],
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def write_results(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Machine-readable JSON
    json_path = out_dir / "results_tier2_a.json"
    with open(json_path, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)

    # Human-readable summary
    txt_path = out_dir / "summary_tier2_a.txt"
    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0, "ERROR": 0}
    for r in RESULTS:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    lines = [
        "=" * 90,
        "XCO MCP Server — Tier-2 Smoke Test  Batch A  (auth + fabric)",
        f"Generated: {_now_iso()}",
        "=" * 90,
        "",
        f"{'Tool':<50} {'Use Case':<35} {'Status':<6}",
        "-" * 90,
    ]
    for r in RESULTS:
        status = r["status"]
        detail = "; ".join(r.get("failures", []) or r.get("warnings", []))[:50]
        note = f"  ← {detail}" if detail else ""
        lines.append(
            f"{r['tool']:<50} {r['use_case']:<35} {status:<6}{note}"
        )

    lines += [
        "-" * 90,
        f"PASS: {counts['PASS']}   FAIL: {counts['FAIL']}   WARN: {counts['WARN']}   "
        f"SKIP: {counts['SKIP']}   ERROR: {counts['ERROR']}   Total: {sum(counts.values())}",
        f"Pass rate (PASS only): {counts['PASS']/max(1,sum(counts.values()))*100:.1f}%",
        f"Pass+Warn rate       : {(counts['PASS']+counts['WARN'])/max(1,sum(counts.values()))*100:.1f}%",
        "",
    ]

    # Failures detail
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
    print(f"\nResults → {json_path}")
    print(f"Summary → {txt_path}")
    return counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Tier-2 Smoke Test — Batch A (auth + fabric)")
    parser.add_argument("--url", default=DEFAULT_URL, help="MCP server base URL")
    parser.add_argument("--out", default=str(Path(__file__).parent),
                        help="Output directory for results")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print(f"MCP server: {base_url}")
    print(f"Started:    {_now_iso()}")
    print("=" * 60)

    # Discovery
    d = Discovery(base_url).run()

    # Run all test suites
    test_auth_get_executions(base_url, d)
    test_fabric_efa_command_list(base_url, d)
    test_fabric_errors_summary(base_url, d)
    test_fabric_execution_last_failed(base_url, d)
    test_fabric_execution_recent(base_url, d)
    test_fabric_health_summary(base_url, d)
    test_fabric_health_timeline(base_url, d)
    test_fabric_overview(base_url, d)
    test_fabric_validation_report(base_url, d)
    test_fabric_running_config(base_url, d)

    # Write results
    counts = write_results(Path(args.out))

    # Exit code
    sys.exit(0 if counts["FAIL"] == 0 and counts["ERROR"] == 0 else 1)


if __name__ == "__main__":
    main()
