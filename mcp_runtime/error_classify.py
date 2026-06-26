# mcp_runtime/error_classify.py
"""
Human-readable error classification for XCO API responses.

Parses raw XCO error payloads and produces actionable operator guidance,
used by `MCPServer.invoke()` to populate the `human_hint` field on non-2xx
responses. This is a read-only edition, so guidance points at diagnosis
(verify names/IDs, check the input schema) — not configuration changes.
"""


def format_step_error(tool: str, status: int, payload) -> str:
    """Return a human-readable, actionable message for a failed tool call.

    Classifies dict-style XCO API errors (`{code, message}`) into categories so
    clients can surface clear guidance; falls back to the raw payload otherwise.
    """
    if isinstance(payload, dict) and ("code" in payload or "message" in payload):
        return _format_xco_api_error(tool, status, payload)
    return f"Tool '{tool}' returned HTTP {status}: {payload}"


# Keywords that indicate the request hit pre-existing / conflicting config.
_STALE_CONFIG_KEYWORDS = [
    "already configured", "already exists", "conflict",
    "in use", "pre-existing", "duplicate",
]
_STALE_ARTIFACT_KEYWORDS = [
    "evpn", "loopback", "overlay", "overlay-gateway",
    "mct", "vlan", "ve ", "router-id", "bgp",
    "interface ethernet", "interface loopback",
]


def _format_xco_api_error(tool: str, status: int, payload: dict) -> str:
    """Format a dict-style XCO API error (code + message) with guidance."""
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
            "The tool inputs don't match the XCO API schema (an unrecognised "
            "field name).\n"
            "REMEDIATION: check the tool's input_schema in the catalog for the "
            "correct field names (underscores vs hyphens, nested vs flat)."
        )

    # ── Resource not found ──
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
            "REMEDIATION: verify the name/ID — the discovery tools "
            "(fabric_get_fabric_names, tenant_list_ids, inventory_list_device_ids) "
            "list valid values."
        )

    # ── Quota / limit reached ──
    if "quota" in msg_lower or "limit" in msg_lower:
        return f"{header}\n\nAn XCO quota or limit has been reached for this resource."

    # ── Pre-existing / conflicting configuration ──
    if any(kw in msg_lower for kw in _STALE_CONFIG_KEYWORDS + _STALE_ARTIFACT_KEYWORDS):
        return (
            f"{header}\n\n"
            "Pre-existing configuration on the switch(es) is blocking this "
            "operation. Clearing it is a configuration change, performed outside "
            "this read-only server."
        )

    # ── Overlay-auto fabric restriction ──
    if "overlay" in msg_lower and "auto" in msg_lower:
        return (
            f"{header}\n\n"
            "This operation is not supported on overlay-auto fabrics."
        )

    # ── Generic — just the header ──
    return header
