#!/usr/bin/env python3
"""
XCO MCP Server — Tier-2 Smoke Test  Batch C  (9 tools)
========================================================
Covers: notification + system Tier-2 tools from
        XCO_MCP_Tier2_Operator_Notes.docx

Tools tested:
  1.  notification_get_last_failed_delivery_or_errors  (Tier-2)
  2.  notification_get_recent_events_filtered          (Tier-2)
  3.  system_get_certificate_alarm_context             (Tier-2)
  4.  system_get_certificates_expiring_soon            (Tier-2)
  5.  system_get_execution                             (Tier-1, in Operator Guide)
  6.  system_get_executions                            (Tier-1, in Operator Guide)
  7.  system_get_ha_and_node_health_summary            (Tier-2)
  8.  system_get_last_execution_diagnostic             (Tier-2)
  9.  system_get_running_config                        (Tier-1, in Operator Guide)

Usage:
    cd /path/to/XCO-MCP-SERVER
    python3 smoke-test/smoke_tier2_c.py [--url http://localhost:8000]

Results:
    smoke-test/results_tier2_c.json
    smoke-test/summary_tier2_c.txt
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
        self.execution_id: Optional[str] = None   # from system executions
        self.switch_ips: List[str] = []

    def run(self) -> "Discovery":
        print("▶  Discovery phase …")
        self._discover_fabrics()
        self._discover_switches()
        self._discover_execution_id()
        print(f"   fabric_name  : {self.fabric_name or '(none)'}")
        print(f"   execution_id : {self.execution_id or '(none)'}")
        print(f"   switch_ips   : {self.switch_ips[:3] or '(none)'}")
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

    def _discover_execution_id(self):
        """Try to find a real execution ID from system executions."""
        raw = call_tool(self.base_url, "system_get_executions", {})
        _, payload = _extract_payload(raw)
        if payload:
            items = []
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict):
                for k in ("items", "executions", "data", "results"):
                    v = payload.get(k)
                    if isinstance(v, list) and v:
                        items = v
                        break
            if items and isinstance(items[0], dict):
                ex = items[0]
                self.execution_id = (
                    ex.get("id") or ex.get("execution_id") or ex.get("request_id")
                    or ex.get("uuid")
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

def _non_trivial_str(p, *keys):
    """Payload has at least one key with a non-empty string value > 10 chars."""
    if not isinstance(p, dict):
        return isinstance(p, str) and len(p) > 10
    for k in keys:
        v = p.get(k)
        if isinstance(v, str) and len(v) > 10:
            return True
        if isinstance(v, list) and len(v) > 0:
            return True
    return False


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

def test_notification_last_failed(base: str, d: Discovery):
    print("\n── 1. notification_get_last_failed_delivery_or_errors ──")
    tool = "notification_get_last_failed_delivery_or_errors"

    # UC-1: Find most recent failed notification — show me recent failures
    run_case(base, tool, {"window_hours": 168}, "UC1: last failed (7d window)",
        checks=[
            ("has summary or last_failed or no_failure",
             lambda p: _has_any_key(p, "summary", "last_failed", "no_failure",
                                    "message", "execution", "most_recent_failed")),
            ("has next_actions",
             _has_next_actions),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Filter by status=failed explicitly
    run_case(base, tool, {"status": "failed", "window_hours": 24},
             "UC2: status=failed last 24h",
        checks=[
            ("has summary or failure info",
             lambda p: _has_any_key(p, "summary", "last_failed", "no_failure",
                                    "message", "execution")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: With fallback detection (catches non-success even without failed status)
    run_case(base, tool,
             {"fallback_detect_non_success": True, "window_hours": 72},
             "UC3: with fallback detection",
        checks=[
            ("payload is a dict",
             lambda p: isinstance(p, dict)),
            ("has some meaningful key",
             lambda p: _has_any_key(p, "summary", "last_failed", "no_failure",
                                    "message", "execution", "most_recent_failed")),
        ],
        warn_on_status=[404, 204],
    )


def test_notification_recent_events(base: str, d: Discovery):
    print("\n── 2. notification_get_recent_events_filtered ──")
    tool = "notification_get_recent_events_filtered"

    # UC-1: Get recent events across all services — what changed recently?
    run_case(base, tool, {"last_n": 20}, "UC1: recent events (last 20)",
        checks=[
            ("has summary or events",
             lambda p: _has_any_key(p, "summary", "events", "items", "executions")),
            ("has next_actions", _has_next_actions),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Filter by status=failed — show recent failures
    run_case(base, tool, {"status": "failed", "last_n": 10},
             "UC2: filter status=failed",
        checks=[
            ("has events or no_events signal",
             lambda p: _has_any_key(p, "events", "items", "executions",
                                    "no_events", "message", "summary")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: Filter by severity_min=CRITICAL
    run_case(base, tool, {"severity_min": "CRITICAL", "last_n": 10},
             "UC3: filter severity_min=CRITICAL",
        checks=[
            ("has events or summary",
             lambda p: _has_any_key(p, "events", "items", "summary")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-4: Keyword search across events
    run_case(base, tool, {"query": "fabric", "last_n": 20},
             "UC4: keyword query=fabric",
        checks=[
            ("has events or summary",
             lambda p: _has_any_key(p, "events", "items", "summary")),
        ],
        warn_on_status=[404, 204],
    )


def test_system_certificate_alarm_context(base: str, d: Discovery):
    print("\n── 3. system_get_certificate_alarm_context ──")
    tool = "system_get_certificate_alarm_context"

    # UC-1: Any current certificate expiry alarms?
    # Note: tool returns alarms/summary/warnings — no next_actions key.
    run_case(base, tool, {}, "UC1: current cert alarms",
        checks=[
            ("has alarms or no_alarms signal",
             lambda p: _has_any_key(p, "alarms", "alarm_count", "no_alarms",
                                    "message", "certificate_context", "summary")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Include EFA + device cert expiry context
    run_case(base, tool,
             {"include_expiry_context": True,
              "include_efa_certs": True, "include_device_certs": True},
             "UC2: cert alarms + expiry context",
        checks=[
            ("has alarms or cert data",
             lambda p: _has_any_key(p, "alarms", "no_alarms", "efa_certs",
                                    "device_certs", "expiry_context", "certificate_context")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: Filter severity to MAJOR+
    run_case(base, tool,
             {"severity_min": "MAJOR", "active_only": True},
             "UC3: MAJOR+ cert alarms only",
        checks=[
            ("has alarms or no_alarms",
             lambda p: _has_any_key(p, "alarms", "no_alarms", "message", "summary")),
        ],
        warn_on_status=[404, 204],
    )


def test_system_certificates_expiring_soon(base: str, d: Discovery):
    print("\n── 4. system_get_certificates_expiring_soon ──")
    tool = "system_get_certificates_expiring_soon"

    # UC-1: Show all certs expiring within 90 days (bucketed 30/60/90)
    # Tool returns summary.counts.{expiring_30,expiring_60,expiring_90} and top-level buckets.
    # No next_actions key.
    run_case(base, tool, {"window_days": 90}, "UC1: certs expiring in 90d",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
            ("summary has bucket counts",
             lambda p: (isinstance(p.get("summary"), dict) and
                        any(p["summary"].get(k) is not None for k in
                            ("total", "expiring_30d", "expiring_60d", "expiring_90d",
                             "expiring_soon", "critical", "counts", "window_days")))
             if isinstance(p, dict) else False),
            ("has certificates list or buckets or no_expiry signal",
             lambda p: _has_any_key(p, "certificates", "certs", "items", "buckets",
                                    "no_expiring", "no_certs", "message")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Tight window — certs expiring in 30 days (critical urgency)
    run_case(base, tool,
             {"window_days": 30, "include_efa_certs": True, "include_device_certs": True},
             "UC2: certs expiring in 30d",
        checks=[
            ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: Per-fabric cert status
    if d.fabric_name:
        run_case(base, tool,
                 {"window_days": 90, "fabric_name": d.fabric_name},
                 "UC3: cert expiry for fabric",
            checks=[
                ("has summary", lambda p: _has_any_key(p, "summary", "totals")),
            ],
            warn_on_status=[404, 204],
        )
    else:
        run_case(base, tool, {}, "UC3: cert expiry per-fabric",
                 checks=[], skip_reason="no fabric_name discovered")


def test_system_get_execution(base: str, d: Discovery):
    print("\n── 5. system_get_execution ──")
    tool = "system_get_execution"

    if not d.execution_id:
        for uc in ["UC1", "UC2"]:
            run_case(base, tool, {}, f"{uc}: execution detail",
                     checks=[], skip_reason="no execution_id discovered")
        return

    # UC-1: Get output of a specific execution (troubleshooting)
    run_case(base, tool, {"id": d.execution_id}, "UC1: execution detail by id",
        checks=[
            ("has execution content",
             lambda p: _has_any_key(p, "id", "execution_id", "request_id",
                                    "status", "command", "output", "result")),
            ("has status field",
             lambda p: p.get("status") is not None if isinstance(p, dict) else False),
        ],
        warn_on_status=[404],
    )

    # UC-2: Same call — verify output / response content is meaningful
    run_case(base, tool, {"id": d.execution_id, "include_output": True},
             "UC2: execution with output detail",
        checks=[
            ("has execution content",
             lambda p: _has_any_key(p, "id", "execution_id", "status", "command")),
        ],
        warn_on_status=[404, 400],
    )


def test_system_get_executions(base: str, d: Discovery):
    print("\n── 6. system_get_executions ──")
    tool = "system_get_executions"

    # UC-1: Get all previously executed requests
    run_case(base, tool, {}, "UC1: all executions",
        checks=[
            ("payload has items or executions",
             lambda p: (
                 (isinstance(p, list) and len(p) > 0)
                 or (isinstance(p, dict) and any(
                     isinstance(p.get(k), list) and len(p.get(k, [])) > 0
                     for k in ("items", "executions", "data", "results")
                 ))
             )),
            ("items have status field",
             lambda p: any(
                 isinstance(item, dict) and item.get("status") is not None
                 for item in (
                     p if isinstance(p, list) else
                     next((p[k] for k in ("items", "executions", "data") if isinstance(p.get(k), list) and p.get(k)), [])
                 )
             ) if p else True),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: Filter by status=failed
    run_case(base, tool, {"status": "failed"}, "UC2: filter status=failed",
        checks=[
            ("payload is not None and not empty",
             lambda p: p is not None and p != {} and p != []),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: Filter by status=success
    run_case(base, tool, {"status": "success"}, "UC3: filter status=success",
        checks=[
            ("payload is not None", lambda p: p is not None),
        ],
        warn_on_status=[404, 204],
    )


def test_system_ha_node_health(base: str, d: Discovery):
    print("\n── 7. system_get_ha_and_node_health_summary ──")
    tool = "system_get_ha_and_node_health_summary"

    # UC-1: HA redundancy + node health summary
    # Tool returns: ha_keepalived, system_health_status, storage_gluster, k3s_nodes,
    # health, summary, warnings. No next_actions key.
    run_case(base, tool, {}, "UC1: HA + node health summary",
        checks=[
            ("has ha_keepalived or system_health_status",
             lambda p: _has_any_key(p, "ha_status", "redundancy", "keepalived",
                                    "ha_info", "system_health", "node_health",
                                    "health_status", "ha_keepalived",
                                    "system_health_status")),
            ("has k3s or gluster or storage signals",
             lambda p: _has_any_key(p, "k3s_nodes", "gluster", "storage",
                                    "nodes", "node_health", "ha_status",
                                    "system_health", "storage_gluster",
                                    "ha_keepalived")),
        ],
        warn_on_status=[502],
    )

    # UC-2: With health detail for problematic resources
    run_case(base, tool,
             {"include_health_detail": True, "detail_only_on_problem": True},
             "UC2: HA health with problem detail",
        checks=[
            ("has ha or health info",
             lambda p: _has_any_key(p, "ha_status", "redundancy", "system_health",
                                    "health_status", "node_health",
                                    "ha_keepalived", "system_health_status",
                                    "health", "summary")),
        ],
        warn_on_status=[502],
    )

    # UC-3: Minimal call — just HA / keepalived status
    run_case(base, tool,
             {"include_k3s_nodes": False, "include_gluster": False,
              "include_health": False},
             "UC3: keepalived only",
        checks=[
            ("has some HA or system info",
             lambda p: _has_any_key(p, "ha_status", "keepalived", "system_health",
                                    "health_status", "redundancy",
                                    "ha_keepalived", "system_health_status",
                                    "summary")),
        ],
        warn_on_status=[502],
    )

    # UC-4: Full raw evidence for escalation
    run_case(base, tool, {"include_raw": True}, "UC4: full raw evidence",
        checks=[
            ("has some HA or system info",
             lambda p: _has_any_key(p, "ha_status", "keepalived", "system_health",
                                    "redundancy", "health_status",
                                    "ha_keepalived", "system_health_status",
                                    "summary")),
        ],
        warn_on_status=[502],
    )


def test_system_last_execution_diagnostic(base: str, d: Discovery):
    print("\n── 8. system_get_last_execution_diagnostic ──")
    tool = "system_get_last_execution_diagnostic"

    # UC-1: Show most recent failed system execution — why did it fail?
    # Tool returns: execution_id+status+summary+details (success) or message+execution (no match).
    run_case(base, tool, {}, "UC1: last failed system execution",
        checks=[
            ("has execution info or no_failure signal",
             lambda p: _has_any_key(p, "execution", "last_failed", "no_failure",
                                    "message", "diagnostic", "status_message",
                                    "most_recent", "execution_id", "status",
                                    "summary")),
            ("has details or message or status",
             lambda p: _has_next_actions(p) or bool(
                 p.get("message") or p.get("status_message") or p.get("no_failure")
                 or p.get("status") or p.get("execution_id") or p.get("summary")
             ) if isinstance(p, dict) else False),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: With limit — look at last 5 failed executions
    run_case(base, tool, {"limit": 5}, "UC2: last 5 failures diagnostic",
        checks=[
            ("has execution info or no_failure",
             lambda p: _has_any_key(p, "execution", "last_failed", "no_failure",
                                    "message", "diagnostic", "most_recent",
                                    "execution_id", "status", "summary")),
        ],
        warn_on_status=[404, 204],
    )

    # UC-3: Filter by status=failed to diagnose failures specifically
    run_case(base, tool, {"status": "failed", "limit": 1},
             "UC3: status=failed, limit=1",
        checks=[
            ("payload is not hollow",
             lambda p: isinstance(p, dict) and len(p) > 0),
        ],
        warn_on_status=[404, 204],
    )


def test_system_running_config(base: str, d: Discovery):
    print("\n── 9. system_get_running_config ──")
    tool = "system_get_running_config"

    # UC-1: Get running configuration CLI commands (operational review)
    # Tool returns {"items": ["cmd1", "cmd2", ...]} via the RunningConfigResponse schema.
    run_case(base, tool, {}, "UC1: running config",
        checks=[
            ("has config content",
             lambda p: (
                 _non_trivial_str(p, "config", "running_config", "text", "output",
                                  "content", "commands", "items")
                 or (isinstance(p, list) and len(p) > 0)
                 or (isinstance(p, str) and len(p) > 10)
             )),
        ],
        warn_on_status=[404, 204],
    )

    # UC-2: With fabric scope (review before a change)
    if d.fabric_name:
        run_case(base, tool, {"fabric_name": d.fabric_name},
                 "UC2: running config for fabric",
            checks=[
                ("has config content",
                 lambda p: p is not None and p != {} and p != ""),
            ],
            warn_on_status=[404, 204, 400],
        )
    else:
        run_case(base, tool, {}, "UC2: running config per-fabric",
                 checks=[], skip_reason="no fabric_name discovered")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def write_results(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "results_tier2_c.json"
    with open(json_path, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)

    txt_path = out_dir / "summary_tier2_c.txt"
    counts = {}
    for r in RESULTS:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    for s in ("PASS", "FAIL", "WARN", "SKIP", "ERROR"):
        counts.setdefault(s, 0)

    total = sum(counts.values())
    lines = [
        "=" * 95,
        "XCO MCP Server — Tier-2 Smoke Test  Batch C  (notification + system)",
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
    parser = argparse.ArgumentParser(description="Tier-2 Smoke Test — Batch C")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default=str(Path(__file__).parent))
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print(f"MCP server: {base_url}")
    print(f"Started:    {_now_iso()}")
    print("=" * 60)

    d = Discovery(base_url).run()

    test_notification_last_failed(base_url, d)
    test_notification_recent_events(base_url, d)
    test_system_certificate_alarm_context(base_url, d)
    test_system_certificates_expiring_soon(base_url, d)
    test_system_get_execution(base_url, d)
    test_system_get_executions(base_url, d)
    test_system_ha_node_health(base_url, d)
    test_system_last_execution_diagnostic(base_url, d)
    test_system_running_config(base_url, d)

    counts = write_results(Path(args.out))
    sys.exit(0 if counts["FAIL"] == 0 and counts["ERROR"] == 0 else 1)


if __name__ == "__main__":
    main()
