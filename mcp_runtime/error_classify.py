# Copyright 2025 Extreme Networks, Inc.
# SPDX-License-Identifier: Apache-2.0
# mcp_runtime/error_classify.py
"""
Human-readable error classification for XCO API responses.

Parses raw XCO error payloads and produces actionable operator guidance.
Used by:
  - MCPWorkflowRunner (plan execution — step failures)
  - MCPServer.invoke() (Tier-1 direct calls — human_hint field)

This module was extracted from workflow.py so the same classification
logic is available to both plan execution and direct /invoke calls.
"""

from typing import Dict, List


def format_step_error(tool: str, status: int, payload) -> str:
    """Return a human-readable, actionable error message for a failed tool call.

    Parses XCO API error responses and classifies them into categories so MCP
    clients can surface clear remediation guidance to operators:

      1. fabric_deploy HTTP 500 — per-device error breakdown:
         - Code 5010 "no device" → fabric state / async timing issue
         - Code 5010 other       → physical cabling / LLDP topology mismatch
         - Stale config artifacts → EVPN, IPs, loopback, MCT, overlay gateway
         - Other device-level errors
      2. Dict with {code, message} — XCO API error codes:
         - Unknown field / schema mismatch
         - Tenant / VRF not found, quota exhausted
         - Stale / conflicting configuration
      3. Fallback — raw payload for unrecognised patterns
    """
    # ── 1. fabric_deploy HTTP 500: per-device error breakdown ──────────
    if tool == "fabric_deploy" and status == 500 and isinstance(payload, list):
        return _format_fabric_deploy_error(payload)

    # ── 2. Dict with code/message (tenant, VRF, EPG, generic XCO) ─────
    if isinstance(payload, dict) and ("code" in payload or "message" in payload):
        return _format_xco_api_error(tool, status, payload)

    # ── 3. Fallback ───────────────────────────────────────────────────
    return f"Tool '{tool}' returned HTTP {status}: {payload}"


# ── Keywords that indicate stale switch configuration blocking deployment ──
_STALE_CONFIG_KEYWORDS = [
    "already configured", "already exists", "conflict",
    "in use", "pre-existing", "duplicate",
]

# ── Artifact names whose presence in error messages indicates stale config ──
_STALE_ARTIFACT_KEYWORDS = [
    "evpn", "loopback", "overlay", "overlay-gateway",
    "mct", "vlan", "ve ", "router-id", "bgp",
    "interface ethernet", "interface loopback",
]


def _format_fabric_deploy_error(payload: list) -> str:
    """Parse fabric_deploy per-device errors into categorised, actionable output.

    The payload is a list of device dicts, each containing:
      - ip-address, host-name, role, model, chassis-name, …
      - error: [{code: int, message: str}, …]

    We classify every error into one of four buckets and return a structured
    message with remediation guidance for each category.
    """
    # ── Collect all device-level errors ──
    device_errors: List[Dict] = []
    for device in payload:
        if not isinstance(device, dict):
            continue
        ip = device.get("ip-address", device.get("device_ip", "?"))
        hostname = device.get("host-name", "")
        role = device.get("role", "")
        label = f"{hostname} ({ip})" if hostname else ip

        for err in device.get("error", []):
            if not isinstance(err, dict):
                continue
            msg = err.get("message", "").strip()
            if not msg:
                continue
            device_errors.append({
                "ip": ip, "hostname": hostname, "role": role,
                "label": label,
                "code": err.get("code"),
                "message": msg,
            })

    if not device_errors:
        # No parseable errors — show device IPs for context
        dev_ips = [
            d.get("ip-address", d.get("device_ip", "?"))
            for d in payload if isinstance(d, dict)
        ]
        return (
            f"fabric_deploy returned HTTP 500 for devices: "
            f"{', '.join(dev_ips)}.\n"
            "No error details were returned by XCO. Check the XCO UI for more info."
        )

    # ── Classify errors into buckets ──
    no_device: List[Dict] = []       # code 5010, "no device" — async timing
    cabling: List[Dict] = []         # code 5010, other — cabling/LLDP
    stale_config: List[Dict] = []    # stale artifacts blocking deployment
    other: List[Dict] = []           # anything else

    for e in device_errors:
        msg_lower = e["message"].lower()
        code = e["code"]

        if code == 5010 and "no device" in msg_lower:
            no_device.append(e)
        elif code == 5010:
            cabling.append(e)
        elif any(kw in msg_lower for kw in _STALE_CONFIG_KEYWORDS):
            stale_config.append(e)
        elif any(kw in msg_lower for kw in _STALE_ARTIFACT_KEYWORDS):
            stale_config.append(e)
        else:
            other.append(e)

    lines: List[str] = ["Fabric deploy failed.\n"]

    # ── A. Fabric state / async timing ──
    if no_device:
        lines.append("══ FABRIC STATE ISSUE (NOT a cabling problem) ══")
        lines.append(
            "XCO reports no devices are committed to the fabric (code 5010)."
        )
        for e in no_device:
            lines.append(f"  • {e['label']}: {e['message']}")
        lines.append(
            "\nThis is likely a timing issue. fabric_add_device calls were "
            "accepted by XCO but the async background worker has not yet "
            "committed them."
        )
        lines.append(
            "REMEDIATION: Wait 30–60 s, verify with fabric_get_devices, "
            "then retry fabric_deploy."
        )
        lines.append("")

    # ── B. Physical cabling / LLDP mismatch ──
    if cabling:
        lines.append("══ CABLING / TOPOLOGY ERROR ══")
        lines.append("Physical cabling or LLDP topology mismatch detected.")
        for e in cabling:
            lines.append(f"  • {e['label']}: {e['message']}")
        lines.append(
            "\nChanges have been rolled back."
        )
        lines.append(
            "REMEDIATION: Verify physical cabling matches the intended "
            "topology. Use fabric_validate_physical_topology to diagnose, "
            "then retry fabric_deploy."
        )
        lines.append("")

    # ── C. Stale switch configuration ──
    if stale_config:
        lines.append("══ STALE SWITCH CONFIGURATION ══")
        lines.append(
            "Pre-existing configuration on switch(es) is blocking deployment."
        )
        for e in stale_config:
            lines.append(f"  • {e['label']} (code {e['code']}): {e['message']}")
        lines.append(
            "\nStale artifacts (EVPN instances, IP addresses on Ethernet/ "
            "Loopback interfaces, MCT clusters, overlay gateways, VLANs, "
            "etc.) from a previous deployment were not fully removed."
        )
        lines.append(
            "REMEDIATION: the stale fabric config must be cleared on the "
            "affected switch(es) before the operation can succeed — a "
            "configuration change, performed outside this read-only server."
        )
        affected = sorted(set(e["ip"] for e in stale_config))
        lines.append(f"  Affected: {', '.join(affected)}")
        lines.append("")

    # ── D. Other / unclassified ──
    if other:
        lines.append("══ OTHER ERRORS ══")
        for e in other:
            lines.append(f"  • {e['label']} (code {e['code']}): {e['message']}")
        lines.append("")

    # ── Summary ──
    all_ips = sorted(set(e["ip"] for e in device_errors))
    lines.append(f"Affected devices ({len(all_ips)}): {', '.join(all_ips)}")
    return "\n".join(lines)


def _format_xco_api_error(tool: str, status: int, payload: dict) -> str:
    """Format a dict-style XCO API error (code + message) with remediation."""
    code = payload.get("code")
    message = payload.get("message", str(payload))
    msg_lower = message.lower()

    header = f"Tool '{tool}' failed — HTTP {status}"
    if code is not None:
        header += f" (XCO code {code})"
    header += f": {message}"

    # ── Unknown field / schema mismatch ──
    if "unknown field" in msg_lower:
        return (
            f"{header}\n\n"
            "This indicates a mismatch between the tool inputs and the XCO "
            "API schema. The field name is not recognised by XCO.\n"
            "REMEDIATION: Check the tool's input_schema in the tool catalog "
            "for correct field names (underscores vs hyphens, nested objects "
            "vs flat fields)."
        )

    # ── Tenant / resource not found ──
    if "not found" in msg_lower:
        resource = "resource"
        if "tenant" in msg_lower:
            resource = "tenant"
        elif "vrf" in msg_lower:
            resource = "VRF"
        elif "fabric" in msg_lower:
            resource = "fabric"
        return (
            f"{header}\n\n"
            f"The referenced {resource} does not exist.\n"
            f"REMEDIATION: Create the {resource} first, then retry."
        )

    # ── Ports not yet discovered (timing after fabric_deploy) ──
    if "not available in the application" in msg_lower or "discovery" in msg_lower:
        return (
            f"{header}\n\n"
            "XCO has not yet discovered the switch ports. This is a timing "
            "issue — port discovery runs asynchronously after fabric_deploy.\n"
            "REMEDIATION: Wait 60–90 s after fabric_deploy completes, then "
            "retry. You can verify port availability with "
            "inventory_get_switch_detail."
        )

    # ── Tenant has no ports — blocks VRF and EPG creation ──
    if "no ports" in msg_lower or "having no ports" in msg_lower:
        return (
            f"{header}\n\n"
            "The tenant has no switch ports assigned. XCO requires port-list "
            "on tenant_create before VRFs or EPGs can be created.\n"
            "REMEDIATION: Delete the tenant (tenant_delete with force=true) "
            "and re-create it with port-list included:\n"
            '  "port-list": [{"mgmt-ip": "<leaf-ip>", '
            '"port": [{"name": "0/1", "int-type": "ethernet"}]}]'
        )

    # ── Quota exhausted ──
    if "quota" in msg_lower or "limit" in msg_lower:
        return (
            f"{header}\n\n"
            "A quota or limit has been reached.\n"
            "REMEDIATION: Increase the quota (e.g. tenant's num-of-vrf) "
            "or delete unused resources before creating new ones."
        )

    # ── Stale / conflicting configuration ──
    if any(kw in msg_lower for kw in _STALE_CONFIG_KEYWORDS + _STALE_ARTIFACT_KEYWORDS):
        return (
            f"{header}\n\n"
            "Pre-existing configuration is blocking this operation.\n"
            "REMEDIATION: the stale config must be cleared on the affected "
            "switches before retrying — a configuration change, performed "
            "outside this read-only server."
        )

    # ── Overlay auto fabric restriction ──
    if "overlay" in msg_lower and "auto" in msg_lower:
        return (
            f"{header}\n\n"
            "This operation is not supported on overlay-auto fabrics.\n"
            "REMEDIATION: Check fabric type and adjust settings accordingly."
        )

    # ── Generic — just the header ──
    return header
