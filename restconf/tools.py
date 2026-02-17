from __future__ import annotations

import xml.etree.ElementTree as ET

def _sanitize_slx_xml(text: str) -> str:
    """Fix known SLX RESTCONF XML quirks that break strict XML parsers.
    Observed: invalid attribute xmlns:="..." (empty prefix). We strip it.
    """
    if not text:
        return text
    # Remove invalid empty-prefix xmlns declarations like:  xmlns:="urn:..."
    return re.sub(r"\s+xmlns:\s*=\s*\"[^\"]*\"", "", text)

import re

from typing import Any, Dict, List, Optional, Tuple

from restconf.client import RestconfError, make_client


# ------------------------------------------------------------
# Small helpers (match style of other Tier-2 composites)
# ------------------------------------------------------------

def _as_int(v: Any, default: int) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


def _as_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v).strip()


def _safe_get(d: dict, *path: str, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _norm_iface(s: str) -> str:
    """
    Normalize interface identifiers to help matching.
    Examples:
      "Ethernet 0/1" -> "ethernet 0/1"
      "0/1" -> "0/1"
      "Port-channel 64" -> "port-channel 64"
    """
    return " ".join(_as_str(s).lower().split())


def _match_interface(item: dict, wanted: str) -> bool:
    """
    Match by:
      - if-name (e.g. "Ethernet 0/1")
      - interface-type + interface-name (e.g. "ethernet" + "0/1" => "ethernet 0/1")
      - raw interface-name ("0/1") if user passed that
    """
    w = _norm_iface(wanted)
    if not w:
        return False

    if_name = _norm_iface(_as_str(item.get("if-name")))
    if if_name and if_name == w:
        return True

    itype = _norm_iface(_as_str(item.get("interface-type")))
    iname = _norm_iface(_as_str(item.get("interface-name")))
    combo = f"{itype} {iname}".strip()
    if combo and combo == w:
        return True

    # Allow user passing just "0/1" to match interface-name "0/1"
    if iname and iname == w:
        return True

    return False


def _extract_interface_counters(item: dict) -> Dict[str, Any]:
    """
    Extract common counters (if present). SLX returns IF-MIB-like names
    in get-interface-detail output.
    """
    keys = [
        "ifHCInOctets",
        "ifHCInUcastPkts",
        "ifHCInMulticastPkts",
        "ifHCInBroadcastPkts",
        "ifHCInErrors",
        "ifHCOutOctets",
        "ifHCOutUcastPkts",
        "ifHCOutMulticastPkts",
        "ifHCOutBroadcastPkts",
        "ifHCOutErrors",
    ]
    out: Dict[str, Any] = {}
    for k in keys:
        if k in item:
            # keep original types (ints) if provided; else string -> int best-effort
            v = item.get(k)
            if isinstance(v, int):
                out[k] = v
            else:
                out[k] = _as_int(v, default=0)
    return out


# ------------------------------------------------------------
# RESTCONF "direct switch" tools (implemented as handlers)
# NOTE on tiers:
# These are essentially "Tier-1-equivalent" (atomic device calls),
# but in this codebase Tier-1 is reserved for generic XCO HTTP wrappers.
# So we register these as Tier-2 handlers for practicality/consistency.
# ------------------------------------------------------------

def restconf_show_firmware_version(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_show_firmware_version", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "item": None,
            "warnings": [],
        }

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")  # optional override

    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
        )
        raw = client.show_firmware_version()
    except RestconfError as e:
        return {
            "meta": {
                "tool": "restconf_show_firmware_version",
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "item": None,
            "warnings": [],
        }

    items = _safe_get(raw, "brocade-firmware-ext:output", "show-firmware-version", default=[])
    first = items[0] if isinstance(items, list) and items else {}

    item = {
        "switch_ip": switch_ip,
        "os_name": _as_str(first.get("os-name")),
        "os_version": _as_str(first.get("os-version")),
        "firmware_full_version": _as_str(first.get("firmware-full-version")),
        "kernel_version": _as_str(first.get("kernel-version")),
        "build_time": _as_str(first.get("build-time")).strip(),
        "install_time": _as_str(first.get("install-time")).strip(),
        "system_uptime": _as_str(first.get("system-uptime")).strip(),
        "cpu": _as_str(first.get("control-processor-chipset")).strip(),
        "memory_mb": _as_str(first.get("control-processor-memory")).strip(),
    }

    summary = {
        "signals": {"restconf_ok": True},
        "os_version": item["os_version"],
        "firmware_full_version": item["firmware_full_version"],
        "system_uptime": item["system_uptime"],
    }

    return {
        "meta": {
            "tool": "restconf_show_firmware_version",
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_restconf",
        },
        "summary": summary,
        "item": item,
        "warnings": [],
    }


def restconf_get_interface_detail(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Read-only interface detail + counters using SLX RESTCONF RPC:
      POST /restconf/operations/get-interface-detail

    Practical notes (based on your switch output):
      - Some SLX builds return many interfaces even when a specific interface-name is provided.
      - We therefore filter client-side and return the best match for the requested interface.
    """
    switch_ip = _as_str(inputs.get("switch_ip"))
    interface_name = _as_str(inputs.get("interface_name") or inputs.get("name") or "")
    max_items = _as_int(inputs.get("max_items"), 200)

    if not switch_ip:
        return {
            "meta": {"tool": "restconf_get_interface_detail", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "item": None,
            "items": [],
            "warnings": [],
        }

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")  # optional override

    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
        )
        raw = client.get_interface_detail(interface_name if interface_name else None)
    except RestconfError as e:
        return {
            "meta": {
                "tool": "restconf_get_interface_detail",
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "item": None,
            "items": [],
            "warnings": [],
        }

    interfaces = _safe_get(raw, "brocade-interface-ext:output", "interface", default=[])
    if not isinstance(interfaces, list):
        interfaces = []

    # Filter if requested
    filtered: List[dict]
    if interface_name:
        filtered = [i for i in interfaces if isinstance(i, dict) and _match_interface(i, interface_name)]
    else:
        filtered = [i for i in interfaces if isinstance(i, dict)]

    # Normalize output rows (trim noise; keep counters)
    def norm(i: dict) -> dict:
        counters = _extract_interface_counters(i)
        return {
            "interface_type": _as_str(i.get("interface-type")),
            "interface_name": _as_str(i.get("interface-name")),
            "if_name": _as_str(i.get("if-name")),
            "if_state": _as_str(i.get("if-state")),
            "line_protocol_state": _as_str(i.get("line-protocol-state")),
            "port_role": _as_str(i.get("port-role")),
            "port_mode": _as_str(i.get("port-mode")),
            "description": _as_str(i.get("if-description")),
            "mac": _as_str(i.get("current-hardware-address") or i.get("logical-hardware-address")),
            "mtu": i.get("mtu"),
            "ip_mtu": i.get("ip-mtu"),
            "actual_line_speed": _as_str(i.get("actual-line-speed")),
            "configured_line_speed": _as_str(i.get("configured-line-speed")),
            "counters": counters,
            # keep raw for debugging (optional) – commented out to stay light
            # "raw": i,
        }

    normalized = [norm(r) for r in filtered[:max_items]]

    item = normalized[0] if (interface_name and normalized) else None

    # Build a small, UI-friendly summary
    summary: Dict[str, Any] = {"signals": {"restconf_ok": True}, "matched": bool(item)}
    if item:
        c = item.get("counters") or {}
        summary.update(
            {
                "interface": item.get("if_name") or f"{item.get('interface_type')} {item.get('interface_name')}".strip(),
                "state": item.get("if_state"),
                "line_protocol": item.get("line_protocol_state"),
                "speed": item.get("actual_line_speed") or item.get("configured_line_speed"),
                "in_octets": c.get("ifHCInOctets"),
                "out_octets": c.get("ifHCOutOctets"),
                "in_errors": c.get("ifHCInErrors"),
                "out_errors": c.get("ifHCOutErrors"),
            }
        )

    return {
        "meta": {
            "tool": "restconf_get_interface_detail",
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_restconf",
        },
        "summary": summary,
        "item": item,
        "items": normalized if not interface_name else [],
        "warnings": [],
    }
def restconf_list_operations(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    '''
    Read-only: list available RESTCONF RPC operations exposed by the switch.

    Inputs:
      - switch_ip (required)
      - filter (optional) : substring filter applied to operation names (case-insensitive)
      - max_items (optional, default 200)
      - username/password/verify_tls (optional overrides)
    '''
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_list_operations", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "operations": [],
            "warnings": [],
        }

    flt = _as_str(inputs.get("filter") or "")
    max_items = _as_int(inputs.get("max_items"), 200)

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")  # optional override

    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
        )
        raw = client.list_operations()
    except RestconfError as e:
        return {
            "meta": {
                "tool": "restconf_list_operations",
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "operations": [],
            "warnings": [],
        }

    ops_obj = _safe_get(raw, "restconf", "operations", default={})
    names = sorted(list(ops_obj.keys())) if isinstance(ops_obj, dict) else []

    if flt:
        f = flt.lower()
        names = [n for n in names if f in n.lower()]

    names = names[:max_items]

    return {
        "meta": {
            "tool": "restconf_list_operations",
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_restconf",
        },
        "summary": {
            "signals": {"restconf_ok": True},
            "filter": flt or None,
            "returned": len(names),
        },
        "operations": names,
        "warnings": [],
    }
def restconf_get_lldp_neighbor_detail(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Read-only: LLDP neighbor details via SLX RESTCONF RPC:
      brocade-lldp-ext:get-lldp-neighbor-detail

    Inputs:
      - switch_ip (required)
      - interface_name (optional): e.g. "Ethernet 0/1" or "Eth 0/1"
      - max_items (optional, default 200)
      - include_raw (optional, default false)
      - username/password/verify_tls (optional overrides)
    """
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_get_lldp_neighbor_detail", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    interface_name = _as_str(inputs.get("interface_name") or "")
    max_items = _as_int(inputs.get("max_items"), 200)
    include_raw = bool(inputs.get("include_raw") or False)

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")

    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
        )
        raw = client.get_lldp_neighbor_detail()
    except RestconfError as e:
        return {
            "meta": {
                "tool": "restconf_get_lldp_neighbor_detail",
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    # --- Parse the known SLX shape you showed ---
    out = raw.get("brocade-lldp-ext:output") if isinstance(raw, dict) else None
    rows = []
    if isinstance(out, dict):
        v = out.get("lldp-neighbor-detail")
        if isinstance(v, list):
            rows = v

    def _norm_lldp_local_iface(s: str) -> str:
        """
        Normalize local interface strings so these match:
          "Ethernet 0/1" == "Eth 0/1" == "Eth0/1" == "ethernet0/1"
        """
        if not s:
            return ""
        t = str(s).strip().lower()
        t = t.replace("ethernet", "eth")
        t = t.replace(" ", "")
        return t

    def _pick(d: dict, key: str):
        val = d.get(key)
        if val in (None, "", "nil"):
            return None
        return val

    items = []
    for r in rows:
        if not isinstance(r, dict):
            continue

        local = _pick(r, "local-interface-name")
        remote_sys = _pick(r, "remote-system-name")
        remote_sys_desc = _pick(r, "remote-system-description")
        remote_chassis = _pick(r, "remote-chassis-id")

        # This is the "remote port id" equivalent on your switch output
        remote_port_id = _pick(r, "remote-interface-name")
        remote_port_desc = _pick(r, "remote-port-description")

        item = {
            "local_interface": _as_str(local),
            "remote_system_name": _as_str(remote_sys),
            "remote_system_description": _as_str(remote_sys_desc),
            "remote_chassis_id": _as_str(remote_chassis),
            "remote_port_id": _as_str(remote_port_id),
            "remote_port_description": _as_str(remote_port_desc),
            "remote_management": None,
            "remote_capabilities": [],
        }
        items.append(item)

    # Filter by interface if requested
    if interface_name:
        wanted = _norm_lldp_local_iface(interface_name)
        items = [n for n in items if _norm_lldp_local_iface(n.get("local_interface", "")) == wanted]

    items = items[:max_items]

    neighbors = len(items)
    uniques = len({n.get("remote_system_name") for n in items if n.get("remote_system_name")})

    top = []
    for n in items[:10]:
        top.append(
            {
                "local": n.get("local_interface"),
                "remote": n.get("remote_system_name") or n.get("remote_chassis_id"),
                "remote_port": n.get("remote_port_id"),
            }
        )

    payload = {
        "meta": {
            "tool": "restconf_get_lldp_neighbor_detail",
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_restconf",
        },
        "summary": {
            "signals": {"restconf_ok": True},
            "filter_interface": interface_name or None,
            "neighbors": neighbors,
            "unique_remote_systems": uniques,
            "top": top,
        },
        "items": items,
        "warnings": [],
    }

    if include_raw:
        payload["raw"] = raw

    return payload

def restconf_get_media_detail(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2: optics/transceiver media details via RESTCONF RPC:
      POST /restconf/operations/brocade-interface-ext:get-media-detail

    Observed SLX payload shape:
      {"brocade-interface-ext:output": {"interface": [ ... ]}}

    Each interface entry may contain a module dict like:
      - "on-board"  (copper PHY, onboard)
      - "qsfp28"    (100G optics/cables)
      (others may exist: qsfp, sfp, sfp28, xfp, ...)

    Practical behavior (your live tests):
      - Some builds return FULL interface list even when you provide interface_name.
        We therefore always filter client-side when interface_name is provided.
      - If interface_name is NOT provided, we try querying "Ethernet 0/1" to coerce
        the switch into returning a full list. If that fails, we fall back to an
        empty-body RPC and may only get a minimal list.
    """
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_get_media_detail", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    interface_name = _as_str(inputs.get("interface_name") or "")
    max_items = _as_int(inputs.get("max_items"), 200)
    include_raw = bool(inputs.get("include_raw") or False)

    # Optional overrides
    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    timeout_seconds = inputs.get("timeout_seconds")

    warnings: List[str] = []

    def norm_iface(s: str) -> str:
        s = (s or "").strip().lower()
        for p in ("ethernet", "eth"):
            if s.startswith(p):
                s = s[len(p):].strip()
        return " ".join(s.split())

    def build_full_iface(iface_type: str, iface_short: str, if_name: str) -> str:
        if if_name:
            return if_name
        t = (iface_type or "").strip().lower()
        short = (iface_short or "").strip()
        if t == "ethernet" and short:
            return f"Ethernet {short}"
        return short or ""

    def pick(d: dict, *keys: str):
        if not isinstance(d, dict):
            return None
        for k in keys:
            v = d.get(k)
            if v not in (None, "", "nil"):
                return v
        return None

    # --- Fetch ---
    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
            timeout_seconds=timeout_seconds,
        )

        raw_resp = None

        # Prefer client helper if present (newer client.py)
        if hasattr(client, "get_media_detail"):
            if interface_name:
                raw_resp = client.get_media_detail(interface_name)
            else:
                try:
                    raw_resp = client.get_media_detail("Ethernet 0/1")
                    warnings.append("interface_name not provided; queried 'Ethernet 0/1' to retrieve full media list")
                except Exception:
                    raw_resp = client.get_media_detail(None)
        else:
            # Backward-compatible XML body
            if interface_name:
                raw = interface_name.strip()
                short = raw
                for prefix in ("Ethernet", "Eth", "eth", "ethernet"):
                    short = short.replace(prefix, "")
                short = short.strip()

                body = (
                    "<get-media-detail>"
                    f"<if-name>{raw}</if-name>"
                    f"<interface-name>{short}</interface-name>"
                    f"<name>{raw}</name>"
                    "</get-media-detail>"
                )
            else:
                body = (
                    "<get-media-detail>"
                    "<if-name>Ethernet 0/1</if-name>"
                    "<interface-name>0/1</interface-name>"
                    "<name>Ethernet 0/1</name>"
                    "</get-media-detail>"
                )
                warnings.append("interface_name not provided; queried 'Ethernet 0/1' to retrieve full media list")

            raw_resp = client._post_xml("/operations/brocade-interface-ext:get-media-detail", body)

    except RestconfError as e:
        return {
            "meta": {
                "tool": "restconf_get_media_detail",
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    # --- Parse ---
    out = raw_resp.get("brocade-interface-ext:output") or raw_resp.get("output") or raw_resp

    interfaces = []
    if isinstance(out, dict):
        v = out.get("interface")
        if isinstance(v, list):
            interfaces = v
        else:
            warnings.append(f"Unexpected payload shape. output keys={sorted(list(out.keys()))[:25]}")
    else:
        warnings.append("Unexpected payload shape (output not a dict).")

    total_interfaces = len(interfaces)

    wanted = norm_iface(interface_name) if interface_name else ""
    if wanted:
        filtered = []
        for r in interfaces:
            if not isinstance(r, dict):
                continue
            full = build_full_iface(r.get("interface-type"), r.get("interface-name"), r.get("if-name"))
            if norm_iface(full) == wanted or norm_iface(_as_str(r.get("interface-name"))) == wanted:
                filtered.append(r)
        interfaces = filtered

    module_keys = ("qsfp28", "qsfp", "sfp28", "sfp", "xfp", "on-board", "onboard")

    items = []
    with_media = 0

    for r in interfaces:
        if not isinstance(r, dict):
            continue

        iface_type = _as_str(r.get("interface-type"))
        iface_short = _as_str(r.get("interface-name"))
        if_name = _as_str(r.get("if-name"))
        full_iface = build_full_iface(iface_type, iface_short, if_name)

        module_kind = None
        module = None
        for mk in module_keys:
            if mk in r:
                v = r.get(mk)
                module_kind = mk
                module = v if isinstance(v, dict) else None
                break

        if module is not None:
            with_media += 1

        src = module if isinstance(module, dict) else {}

        item = {
            "interface_type": iface_type,
            "interface_name": full_iface,
            "interface_short": iface_short,
            "media_kind": module_kind,
            "speed": _as_str(pick(src, "speed")),
            "connector": _as_str(pick(src, "connector")),
            "encoding": _as_str(pick(src, "encoding")),
            "vendor_name": _as_str(pick(src, "vendor-name", "vendor")),
            "vendor_oui": _as_str(pick(src, "vendor-oui")),
            "vendor_part_number": _as_str(pick(src, "vendor-pn", "vendor-part-number", "part-number", "pn")),
            "vendor_rev": _as_str(pick(src, "vendor-rev", "rev")),
            "serial_number": _as_str(pick(src, "serial-no", "vendor-serial-number", "serial-number", "sn")),
            "date_code": _as_str(pick(src, "date-code")),
            "distance": _as_str(pick(src, "distance")),
            "media_form_factor": _as_str(pick(src, "media-form-factor")),
            "wavelength": _as_str(pick(src, "wavelength")),
        }

        if isinstance(module, dict) and module:
            item["details"] = dict(module)

        items.append(item)

    items = items[:max_items]

    payload = {
        "meta": {
            "tool": "restconf_get_media_detail",
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_restconf",
        },
        "summary": {
            "signals": {"restconf_ok": True},
            "returned": len(items),
            "filtered_by_interface": bool(interface_name),
            "interfaces_total": total_interfaces,
            "interfaces_with_media": with_media,
        },
        "items": items,
        "warnings": warnings,
    }

    if include_raw:
        payload["raw"] = raw_resp

    return payload




def restconf_get_vlan_brief(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2: VLAN brief summary via RESTCONF RPC:
      POST /restconf/operations/brocade-interface-ext:get-vlan-brief

    Notes:
      - Many platforms return VLAN membership as an "interface" list under each VLAN.
      - This tool normalizes VLANs into a table and provides a membership summary string that is also used
        for port_filter matching (e.g., "tunnel 32769 tag=tagged class=vni=1").
    """
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_get_vlan_brief", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    vlan_id_filter = inputs.get("vlan_id")
    name_filter = _as_str(inputs.get("name_filter") or "")
    port_filter = _as_str(inputs.get("port_filter") or "")
    max_items = _as_int(inputs.get("max_items"), 200)
    include_raw = bool(inputs.get("include_raw") or False)

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    timeout_seconds = inputs.get("timeout_seconds")

    warnings: list[str] = []

    # --- Fetch raw via client helper ---
    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
            timeout_seconds=timeout_seconds,
        )
        raw = client.get_vlan_brief()
    except RestconfError as e:
        return {
            "meta": {
                "tool": "restconf_get_vlan_brief",
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    # --- Locate output block robustly ---
    out = None
    if isinstance(raw, dict):
        out = raw.get("brocade-interface-ext:output") or raw.get("output") or raw
    else:
        out = raw

    # --- Extract VLAN list ---
    vlan_list: list[dict] = []
    if isinstance(out, dict):
        v = out.get("vlan")
        if isinstance(v, list):
            vlan_list = [x for x in v if isinstance(x, dict)]
        else:
            # heuristic: first list-valued key that looks like VLANs
            for k, vv in out.items():
                if isinstance(k, str) and "vlan" in k.lower() and isinstance(vv, list):
                    vlan_list = [x for x in vv if isinstance(x, dict)]
                    break

    if not vlan_list:
        warnings.append(f"Unexpected payload shape. output keys={list(out.keys()) if isinstance(out, dict) else type(out).__name__}")
        payload = {
            "meta": {"tool": "restconf_get_vlan_brief", "switch_ip": switch_ip, "ok": True, "source": "direct_switch_restconf"},
            "summary": {"signals": {"restconf_ok": True}, "returned": 0, "filtered": bool(vlan_id_filter or name_filter or port_filter), "vlans_seen": 0, "max_items": max_items},
            "items": [],
            "warnings": warnings,
        }
        if include_raw:
            payload["raw"] = raw
        return payload

    # Filters (normalized)
    vlan_id_filter_int = None
    try:
        if vlan_id_filter is not None and str(vlan_id_filter).strip() != "":
            vlan_id_filter_int = int(vlan_id_filter)
    except Exception:
        warnings.append("Invalid vlan_id; expected integer")
        vlan_id_filter_int = None

    name_filter_l = name_filter.lower().strip()
    port_filter_l = port_filter.lower().strip()

    def _norm_iface_display(interface_type: str, interface_name: str) -> str:
        it = (interface_type or "").strip()
        nm = (interface_name or "").strip()
        if not it and not nm:
            return ""
        it_l = it.lower()
        if it_l == "ethernet":
            # return a consistent "Ethernet X/Y" format
            return nm if nm.lower().startswith("ethernet ") else f"Ethernet {nm}"
        if it_l in ("port-channel", "portchannel", "lag"):
            return nm if nm.lower().startswith("port-channel ") else f"Port-channel {nm}"
        # generic (tunnel, ve, vlan, etc.)
        return f"{it} {nm}".strip()

    def _extract_members(vlan_obj: dict) -> list[dict]:
        members: list[dict] = []
        iface_list = vlan_obj.get("interface")
        if not isinstance(iface_list, list):
            return members
        for m in iface_list:
            if not isinstance(m, dict):
                continue
            itype = _as_str(m.get("interface-type") or m.get("interface_type") or "")
            iname = _as_str(m.get("interface-name") or m.get("interface_name") or m.get("if-name") or "")
            tag = _as_str(m.get("tag") or m.get("mode") or "")
            # classification list -> "vni=1" style
            classes = []
            cl = m.get("classification")
            if isinstance(cl, list):
                for c in cl:
                    if not isinstance(c, dict):
                        continue
                    ct = _as_str(c.get("classification-type") or c.get("type") or "")
                    cv = _as_str(c.get("classification-value") or c.get("value") or "")
                    if ct and cv:
                        classes.append(f"{ct}={cv}")
            display = _norm_iface_display(itype, iname)
            members.append(
                {
                    "interface_type": itype,
                    "interface_name": iname,
                    "display": display,
                    "tag": tag,
                    "classifications": classes,
                    "details": m,
                }
            )
        return members

    def _members_summary(members: list[dict], limit: int = 24) -> str:
        parts: list[str] = []
        for mm in members[: max(limit, 0)]:
            disp = _as_str(mm.get("display") or "")
            if not disp:
                continue
            extras: list[str] = []
            tg = _as_str(mm.get("tag") or "")
            if tg:
                extras.append(f"tag={tg}")
            cls = mm.get("classifications") or []
            if isinstance(cls, list) and cls:
                extras.append("class=" + ",".join([_as_str(x) for x in cls if _as_str(x)]))
            if extras:
                disp = disp + " (" + " ".join(extras) + ")"
            parts.append(disp)
        if len(members) > limit and limit > 0:
            parts.append(f"...(+{len(members)-limit})")
        return ", ".join(parts)

    items: list[dict] = []

    # Stats seen (pre-filter)
    vlans_seen = 0
    vlans_with_members_seen = 0
    members_total_seen = 0
    ethernet_members_total_seen = 0

    # Stats returned (post-filter)
    vlans_with_members = 0
    members_total = 0
    ethernet_members_total = 0

    for v in vlan_list:
        vlans_seen += 1

        # id/name
        vid_raw = v.get("vlan-id") if isinstance(v, dict) else None
        vname_raw = v.get("vlan-name") if isinstance(v, dict) else None
        try:
            vid_int = int(vid_raw) if vid_raw is not None else None
        except Exception:
            vid_int = None
        vid = _as_str(vid_raw) if vid_raw is not None else ""
        vname = _as_str(vname_raw) if vname_raw is not None else ""

        members = _extract_members(v)
        if members:
            vlans_with_members_seen += 1
            members_total_seen += len(members)
            ethernet_members_total_seen += sum(1 for m in members if (m.get("interface_type") or "").lower() == "ethernet")

        mem_summary = _members_summary(members, limit=24)

        # Filters
        if vlan_id_filter_int is not None and vid_int is not None and vid_int != vlan_id_filter_int:
            continue
        if name_filter_l and name_filter_l not in (vname or "").lower():
            continue
        if port_filter_l:
            hay = " ".join(
                [
                    vid,
                    vname,
                    mem_summary,
                    " ".join([_as_str(m.get("display") or "") for m in members]),
                    " ".join([",".join(m.get("classifications") or []) for m in members if isinstance(m.get("classifications"), list)]),
                ]
            ).lower()
            if port_filter_l not in hay:
                continue

        # Post-filter stats
        if members:
            vlans_with_members += 1
            members_total += len(members)
            ethernet_members_total += sum(1 for m in members if (m.get("interface_type") or "").lower() == "ethernet")

        items.append(
            {
                "vlan_id": vid,
                "vlan_name": vname,
                # backward-compatible "ports" field (string) — on some platforms the membership is not "ethernet ports"
                "ports": mem_summary,
                "members_summary": mem_summary,
                "members": [
                    {
                        "display": m.get("display", ""),
                        "interface_type": m.get("interface_type", ""),
                        "interface_name": m.get("interface_name", ""),
                        "tag": m.get("tag", ""),
                        "classifications": m.get("classifications", []),
                    }
                    for m in members
                ],
                "members_count": len(members),
                "details": v,
            }
        )

        if len(items) >= max_items:
            break

    # Add extra output-level counters if present
    extra = {}
    if isinstance(out, dict):
        for k in ("configured-vlans-count", "provisioned-vlans-count", "unprovisioned-vlans-count", "last-vlan-id", "has-more"):
            if k in out:
                extra[k.replace("-", "_")] = out.get(k)

    summary: dict = {
        "signals": {"restconf_ok": True},
        "returned": len(items),
        "filtered": bool(vlan_id_filter_int is not None or name_filter_l or port_filter_l),
        "vlans_seen": vlans_seen,
        "max_items": max_items,
        "vlans_with_members": vlans_with_members,
        "members_total": members_total,
        "ethernet_members_total": ethernet_members_total,
        "non_ethernet_members_total": max(members_total - ethernet_members_total, 0),
        "vlans_with_members_seen": vlans_with_members_seen,
        "members_total_seen": members_total_seen,
        "ethernet_members_total_seen": ethernet_members_total_seen,
        "non_ethernet_members_total_seen": max(members_total_seen - ethernet_members_total_seen, 0),
        **extra,
    }
    if vlan_id_filter_int is not None:
        summary["vlan_id"] = vlan_id_filter_int
    if name_filter:
        summary["name_filter"] = name_filter
    if port_filter:
        summary["port_filter"] = port_filter

    payload: dict = {
        "meta": {"tool": "restconf_get_vlan_brief", "switch_ip": switch_ip, "ok": True, "source": "direct_switch_restconf"},
        "summary": summary,
        "items": items,
        "warnings": warnings,
    }
    if include_raw:
        payload["raw"] = raw

    return payload

def restconf_get_arp_table(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2: ARP table via RESTCONF RPC:
      POST /restconf/operations/brocade-arp:get-arp

    This tool normalizes entries into a clean table and supports light client-side filtering.

    Inputs:
      - switch_ip (required)
      - ip_filter (optional): substring match on IP
      - mac_filter (optional): substring match on MAC (case-insensitive)
      - interface_name (optional): substring match on interface (supports "Ethernet 0/1" or "0/1")
      - max_items (optional, default 200)
      - include_raw (optional, default false)
      - username/password/verify_tls/timeout_seconds (optional overrides)
    """
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_get_arp_table", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    ip_filter = _as_str(inputs.get("ip_filter") or "")
    mac_filter = _as_str(inputs.get("mac_filter") or "")
    interface_name = _as_str(inputs.get("interface_name") or "")
    max_items = _as_int(inputs.get("max_items"), 200)
    include_raw = bool(inputs.get("include_raw") or False)

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    timeout_seconds = inputs.get("timeout_seconds")

    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
            timeout_seconds=timeout_seconds,
        )
        raw = client.get_arp_table()
    except RestconfError as e:
        return {
            "meta": {
                "tool": "restconf_get_arp_table",
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    warnings: List[str] = []

    # --- Find output block robustly (vendors vary on key naming) ---
    output_key = None
    output = None
    if isinstance(raw, dict):
        if "brocade-arp:output" in raw:
            output_key = "brocade-arp:output"
            output = raw.get(output_key)
        elif "output" in raw:
            output_key = "output"
            output = raw.get(output_key)
        else:
            # first key that ends with ":output"
            for k in raw.keys():
                if isinstance(k, str) and k.endswith(":output"):
                    output_key = k
                    output = raw.get(k)
                    break
            if output is None:
                output_key = "raw"
                output = raw
    else:
        output_key = "raw"
        output = raw

    # --- Extract entries list ---
    entries: List[Dict[str, Any]] = []
    if isinstance(output, dict):
        # common keys
        for k in ("arp-entry", "arp-entries", "entries", "entry", "arp"):
            v = output.get(k)
            if isinstance(v, list):
                entries = [x for x in v if isinstance(x, dict)]
                break
        if not entries:
            # heuristic: single list-valued key
            list_vals = [(k, v) for k, v in output.items() if isinstance(v, list)]
            if len(list_vals) == 1:
                _, v = list_vals[0]
                entries = [x for x in v if isinstance(x, dict)]
    elif isinstance(output, list):
        entries = [x for x in output if isinstance(x, dict)]
    else:
        entries = []

    if not entries:
        warnings.append(f"Unexpected payload shape. output_key={output_key} output_type={type(output).__name__}")
        # still return ok:true because RESTCONF worked, but with 0 entries
        result = {
            "meta": {
                "tool": "restconf_get_arp_table",
                "switch_ip": switch_ip,
                "ok": True,
                "source": "direct_switch_restconf",
            },
            "summary": {
                "signals": {"restconf_ok": True},
                "returned": 0,
                "filtered": bool(ip_filter or mac_filter or interface_name),
                "entries_seen": 0,
            },
            "items": [],
            "warnings": warnings,
        }
        if include_raw:
            result["raw"] = raw
        return result

    # --- Normalize entries ---
    def _get_first(d: Dict[str, Any], keys: Tuple[str, ...]) -> str:
        for k in keys:
            v = d.get(k)
            if v is None:
                continue
            s = _as_str(v)
            if s:
                return s
        return ""

    # normalize interface filter: allow "Ethernet 0/1" -> "0/1"
    iface_filter_raw = interface_name
    iface_filter_norm = interface_name.lower().strip()
    for prefix in ("ethernet", "et", "eth", "port-channel", "po", "vlan", "ve"):
        if iface_filter_norm.startswith(prefix + " "):
            iface_filter_norm = iface_filter_norm.split(" ", 1)[1].strip()
            break

    items: List[Dict[str, Any]] = []
    for e in entries:
        ip = _get_first(e, ("ip-address", "ip", "ip-addr", "ipaddr", "ipv4-address", "address"))
        mac = _get_first(e, ("mac-address", "mac", "mac-addr", "hw-address", "hardware-address"))

        itype = _get_first(e, ("interface-type", "if-type", "intf-type", "port-type"))
        iname = _get_first(e, ("interface-name", "if-name", "port", "port-name", "intf", "interface"))
        # Build a friendly display, but keep the short name too
        iface_short = iname
        iface_display = iname
        if itype and iname:
            # Common casing used elsewhere in your RESTCONF tools
            if itype.lower() == "ethernet":
                iface_display = f"Ethernet {iname}"
            elif itype.lower() in ("port-channel", "portchannel", "lag"):
                iface_display = f"Port-channel {iname}"
            else:
                iface_display = f"{itype} {iname}"

        vlan = _get_first(e, ("vlan", "vlan-id", "vlanid"))
        vrf = _get_first(e, ("vrf", "vrf-name", "vrf_name"))
        age = _get_first(e, ("age", "age-seconds", "age_seconds", "aging", "ageing"))
        typ = _get_first(e, ("type", "arp-type", "state", "flags", "entry-type"))

        # Filters
        if ip_filter and ip_filter not in ip:
            continue
        if mac_filter and mac_filter.lower() not in mac.lower():
            continue
        if iface_filter_raw:
            hay = (iface_display or iface_short or "").lower()
            if iface_filter_norm and iface_filter_norm not in hay and iface_filter_raw.lower() not in hay:
                continue

        items.append(
            {
                "ip_address": ip,
                "mac_address": mac,
                "interface": iface_display,
                "interface_short": iface_short,
                "vlan": vlan,
                "vrf": vrf,
                "age": age,
                "type": typ,
                "details": e,
            }
        )

        if len(items) >= max_items:
            break

    # Basic stats
    unique_ips = len({i.get("ip_address", "") for i in items if i.get("ip_address")})
    unique_macs = len({i.get("mac_address", "") for i in items if i.get("mac_address")})
    unique_ifaces = len({i.get("interface", "") for i in items if i.get("interface")})

    summary = {
        "signals": {"restconf_ok": True},
        "returned": len(items),
        "filtered": bool(ip_filter or mac_filter or interface_name),
        "entries_seen": len(entries),
        "unique_ips": unique_ips,
        "unique_macs": unique_macs,
        "unique_interfaces": unique_ifaces,
    }

    payload = {
        "meta": {"tool": "restconf_get_arp_table", "switch_ip": switch_ip, "ok": True, "source": "direct_switch_restconf"},
        "summary": summary,
        "items": items,
        "warnings": warnings,
    }

    if include_raw:
        payload["raw"] = raw

    return payload

def restconf_get_clock(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2: 'show clock' style summary via RESTCONF RPC:
      POST /restconf/operations/brocade-clock:show-clock

    Normalizes the most common shapes seen on SLX/VSP-style platforms.
    """
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_get_clock", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    include_raw = bool(inputs.get("include_raw") or False)

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    timeout_seconds = inputs.get("timeout_seconds")

    warnings: list[str] = []

    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
            timeout_seconds=timeout_seconds,
        )
        # Prefer explicit helper if present, otherwise fall back to generic POST helpers
        if hasattr(client, "get_clock"):
            raw = client.get_clock()
        elif hasattr(client, "_post_rpc"):
            raw = client._post_rpc("brocade-clock:show-clock")
        elif hasattr(client, "_post_xml"):
            raw = client._post_xml("/operations/brocade-clock:show-clock", "<show-clock></show-clock>")
        else:
            raise RestconfError("Client missing RESTCONF POST helper for brocade-clock:show-clock")
    except RestconfError as e:
        return {
            "meta": {
                "tool": "restconf_get_clock",
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    # --- Most common output shape ---
    # {
    #   "brocade-clock:output": {
    #     "clock-time": [{"current-time":"...","timezone":"..."}]
    #   }
    # }
    root = raw
    if isinstance(raw, dict) and "brocade-clock:output" in raw:
        root = raw.get("brocade-clock:output")

    current_time = ""
    timezone = ""
    ntp = ""
    source = ""

    if isinstance(root, dict):
        ct = root.get("clock-time")
        if isinstance(ct, list) and ct and isinstance(ct[0], dict):
            ct0 = ct[0]
            current_time = _as_str(ct0.get("current-time") or ct0.get("current_time") or "")
            timezone = _as_str(ct0.get("timezone") or ct0.get("time-zone") or ct0.get("tz") or "")
        # Some platforms may expose these at root
        ntp = _as_str(root.get("ntp-status") or root.get("ntp") or root.get("ntp-enabled") or root.get("ntp-synchronized") or root.get("sync-status") or "")
        source = _as_str(root.get("source") or root.get("time-source") or root.get("clock-source") or "")
    else:
        warnings.append(f"Unexpected payload type for clock output: {type(root).__name__}")

    # Fallback deep search if still empty
    if not current_time:
        current_time = _as_str(_deep_find_any(root, ("current-time", "current_time", "current", "clock", "time")))

    if not timezone:
        timezone = _as_str(_deep_find_any(root, ("timezone", "time-zone", "tz")))

    summary = {
        "signals": {"restconf_ok": True},
        "current_time": current_time,
        "timezone": timezone,
        "ntp": ntp,
        "source": source,
    }
    # Remove empty fields (keep signals)
    summary = {k: v for k, v in summary.items() if (k == "signals" or v)}

    payload = {
        "meta": {"tool": "restconf_get_clock", "switch_ip": switch_ip, "ok": True, "source": "direct_switch_restconf"},
        "summary": summary,
        "items": [],
        "warnings": warnings,
    }

    if include_raw:
        payload["raw"] = raw

    return payload

def restconf_get_port_statistics_summary(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """
    Tier-2: Summarize Ethernet port counters (octets/errors) across ports using
    brocade-interface-ext:get-interface-detail RPC.

    Inputs:
      - switch_ip (str, required)
      - max_ports (int, optional, default 64): cap number of ethernet ports considered
      - top_n (int, optional, default 5): number of top ports to show
      - include_raw (bool, optional, default False)
      - username/password/verify_tls/timeout_seconds (optional overrides)
    """
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_get_port_statistics_summary", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    max_ports = _as_int(inputs.get("max_ports"), 64)
    top_n = _as_int(inputs.get("top_n"), 5)
    include_raw = bool(inputs.get("include_raw", False))

    # Optional overrides
    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    timeout_seconds = inputs.get("timeout_seconds")

    warnings: list[str] = []

    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
            timeout_seconds=timeout_seconds,
        )
        raw = client.get_interface_detail(None)
    except RestconfError as e:
        return {
            "meta": {
                "tool": "restconf_get_port_statistics_summary",
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    out = raw.get("brocade-interface-ext:output") or {}
    interfaces = out.get("interface") or []

    if not isinstance(interfaces, list):
        warnings.append("Unexpected RESTCONF payload shape: output.interface is not a list")
        interfaces = []

    def as_int(v):
        try:
            if v is None:
                return 0
            if isinstance(v, bool):
                return int(v)
            if isinstance(v, (int, float)):
                return int(v)
            s = str(v).strip()
            if s == "" or s.lower() == "nil":
                return 0
            return int(float(s))
        except Exception:
            return 0

    items = []
    for it in interfaces:
        if not isinstance(it, dict):
            continue

        if (_as_str(it.get("interface-type"))).lower() != "ethernet":
            continue

        if_name = _as_str(it.get("if-name"))
        iface_short = _as_str(it.get("interface-name"))

        local = if_name or (f"Ethernet {iface_short}" if iface_short else "")

        state = _as_str(it.get("if-state"))
        line = _as_str(it.get("line-protocol-state"))
        speed = _as_str(it.get("actual-line-speed") or it.get("configured-line-speed"))

        in_oct = as_int(it.get("ifHCInOctets"))
        out_oct = as_int(it.get("ifHCOutOctets"))
        in_err = as_int(it.get("ifHCInErrors"))
        out_err = as_int(it.get("ifHCOutErrors"))
        total = in_oct + out_oct

        items.append(
            {
                "port": local,
                "state": state,
                "line_protocol": line,
                "speed": speed,
                "in_octets": in_oct,
                "out_octets": out_oct,
                "in_errors": in_err,
                "out_errors": out_err,
                "total_octets": total,
            }
        )

    items_sorted_by_port = sorted(items, key=lambda x: x.get("port") or "")
    capped = items_sorted_by_port[: (max_ports if max_ports else len(items_sorted_by_port))]

    top = sorted(capped, key=lambda x: x.get("total_octets", 0), reverse=True)[: (top_n if top_n else 0)]
    top_view = [
        {
            "port": t.get("port", ""),
            "total_octets": t.get("total_octets", 0),
            "in_octets": t.get("in_octets", 0),
            "out_octets": t.get("out_octets", 0),
            "errors": (t.get("in_errors", 0) + t.get("out_errors", 0)),
        }
        for t in top
    ]

    total_in = sum(x["in_octets"] for x in capped)
    total_out = sum(x["out_octets"] for x in capped)
    total_err = sum((x["in_errors"] + x["out_errors"]) for x in capped)

    payload = {
        "meta": {
            "tool": "restconf_get_port_statistics_summary",
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_restconf",
        },
        "summary": {
            "signals": {"restconf_ok": True},
            "max_ports": max_ports,
            "top_n": top_n,
            "ports_considered": len(capped),
            "totals": {
                "in_octets": total_in,
                "out_octets": total_out,
                "total_octets": (total_in + total_out),
                "total_errors": total_err,
            },
            "top": top_view,
        },
        "items": capped,
        "warnings": warnings,
    }

    if include_raw:
        payload["raw"] = raw

    return payload




def restconf_get_vrf_summary(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """Read-only: List VRFs via RESTCONF data tree.

    Primary: GET /restconf/data/brocade-vrf:vrf (JSON)
    Fallback: GET /restconf/data/brocade-vrf:vrf (XML) because some SLX builds
    return "application/yang-data+json" that is NOT strict JSON (e.g., trailing commas).
    """
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_get_vrf_summary", "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    name_filter = _as_str(inputs.get("name_filter"))
    max_items = _as_int(inputs.get("max_items"), 200)
    include_raw = bool(inputs.get("include_raw", False))

    # Optional overrides
    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    timeout_seconds = inputs.get("timeout_seconds")

    warnings: list[str] = []

    client = make_client(
        switch_ip,
        username=username,
        password=password,
        verify_tls=verify_tls,
        timeout_seconds=timeout_seconds,
    )

    raw_json = None
    raw_xml = None

    # Try JSON first (may fail if device returns non-strict JSON)
    try:
        raw_json = client.get_vrf_tree()
    except RestconfError as e:
        warnings.append("JSON parse failed for VRF tree; falling back to XML.")
        warnings.append(f"JSON error: {str(e)}")

    items: list[dict] = []

    if raw_json and isinstance(raw_json, dict):
        # SLX may use a fully-qualified key like "urn:brocade.com:mgmt:brocade-vrf:vrf"
        # or "brocade-vrf:vrf". Normalize both.
        root = None
        for k in ("brocade-vrf:vrf", "urn:brocade.com:mgmt:brocade-vrf:vrf"):
            if k in raw_json:
                root = raw_json.get(k)
                break
        if root is None:
            # fallback to common shapes
            root = raw_json.get("vrf") or raw_json

        vrfs = []
        if isinstance(root, list):
            vrfs = root
        elif isinstance(root, dict):
            vrfs = root.get("vrf") or root.get("vrf-entry") or []
        else:
            vrfs = []

        if not isinstance(vrfs, list):
            warnings.append(f"Unexpected VRF JSON shape: {type(vrfs).__name__}")
            vrfs = []

        for it in vrfs:
            if not isinstance(it, dict):
                continue
            name = _as_str(it.get("vrf-name") or it.get("name") or it.get("vrf"))
            if not name:
                continue
            if name_filter and name_filter.lower() not in name.lower():
                continue
            items.append(
                {
                    "name": name,
                    "vrf_id": it.get("vrf-id") or it.get("vrf_id"),
                    "rd": it.get("route-distinguisher") or it.get("rd"),
                    "vni": it.get("vni"),
                    "router_id": it.get("router-id") or it.get("router_id"),
                }
            )

    # If JSON path didn't yield items (or JSON parse failed), do XML fallback
    if not items:
        try:
            status, headers, text = client.get_vrf_tree_xml()
            raw_xml = {"status": status, "content_type": headers.get("Content-Type", ""), "xml": text}
            # Parse: may be a single <vrf> element or a container with multiple
            # The namespace is typically urn:brocade.com:mgmt:brocade-vrf
            # We'll discover namespace from the root tag.
            # Some SLX builds emit an invalid attribute like xmlns:="..." (empty prefix).
            # Strip it so standard XML parsers can handle the payload.
            text_sanitized = re.sub(r"\sxmlns:='[^']*'|\sxmlns:=\"[^\"]*\"", "", text)
            root = ET.fromstring(text_sanitized)
            # Extract namespace
            m = re.match(r"^\{([^}]+)\}", root.tag)
            ns = m.group(1) if m else "urn:brocade.com:mgmt:brocade-vrf"
            def q(tag: str) -> str:
                return f"{{{ns}}}{tag}"

            # Case A: root is <vrf> for one VRF
            if root.tag.endswith("vrf"):
                n_el = root.find(q("vrf-name"))
                if n_el is not None and (n_el.text or "").strip():
                    vrf_names = [(n_el.text or "").strip()]
                else:
                    # maybe multiple children <vrf> ... uncommon, but handle
                    vrf_names = [(el.text or "").strip() for el in root.findall(".//" + q("vrf-name")) if (el.text or "").strip()]
            else:
                vrf_names = [(el.text or "").strip() for el in root.findall(".//" + q("vrf-name")) if (el.text or "").strip()]

            # Deduplicate while keeping order
            seen = set()
            ordered = []
            for n in vrf_names:
                if n not in seen:
                    seen.add(n)
                    ordered.append(n)

            for name in ordered:
                if name_filter and name_filter.lower() not in name.lower():
                    continue
                items.append({"name": name})

        except Exception as e:
            return {
                "meta": {
                    "tool": "restconf_get_vrf_summary",
                    "switch_ip": switch_ip,
                    "ok": False,
                    "source": "direct_switch_restconf",
                    "error": f"XML fallback failed: {str(e)}",
                },
                "summary": {"signals": {"restconf_ok": False}},
                "items": [],
                "warnings": warnings,
            }

    items = sorted(items, key=lambda x: x.get("name") or "")
    if max_items and len(items) > max_items:
        warnings.append(f"Truncated items to max_items={max_items} (from {len(items)}).")
        items = items[:max_items]

    payload = {
        "meta": {
            "tool": "restconf_get_vrf_summary",
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_restconf",
        },
        "summary": {
            "signals": {"restconf_ok": True},
            "vrf_count": len(items),
            "filtered": bool(name_filter),
            "name_filter": name_filter if name_filter else None,
            "example_vrfs": [x.get("name") for x in items[:10] if x.get("name")],
        },
        "items": items,
        "warnings": warnings,
    }

    if include_raw:
        if raw_json is not None:
            payload["raw_json"] = raw_json
        if raw_xml is not None:
            payload["raw_xml"] = raw_xml

    return payload
def restconf_get_ip_interface(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """Tier-2: best-effort L3 IP addressing per interface (IPv4/IPv6).

    Uses RESTCONF data tree:
      GET /restconf/data/brocade-interface:interface?depth=unbounded

    Notes (SLX quirks):
    - Some SLX builds return non-strict JSON; we use XML.
    - XML can contain invalid `xmlns:="..."` (empty prefix); we sanitize it.
    - Some interface nodes containing IP info may not have a direct <name> child,
      so we also accept nodes that contain <ip-address> / IPv6 address leaves.
    """
    tool_name = "restconf_get_ip_interface"
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": tool_name, "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    interface_name = _as_str(inputs.get("interface_name"))
    include_ipv6 = bool(inputs.get("include_ipv6", True))
    max_items = _as_int(inputs.get("max_items"), 200)
    include_raw = bool(inputs.get("include_raw", False))

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    timeout_seconds = inputs.get("timeout_seconds")

    warnings: list[str] = []
    client = make_client(
        switch_ip,
        username=username,
        password=password,
        verify_tls=verify_tls,
        timeout_seconds=timeout_seconds,
    )

    raw_xml = None
    items: list[dict] = []

    # Fetch XML tree
    try:
        status, headers, text = client.get_interface_tree_xml(depth="unbounded")
        raw_xml = {"status": status, "content_type": headers.get("Content-Type", ""), "xml": text}
        if status >= 400:
            return {
                "meta": {
                    "tool": tool_name,
                    "switch_ip": switch_ip,
                    "ok": False,
                    "source": "direct_switch_restconf",
                    "error": f"RESTCONF GET interface tree failed: {status}",
                },
                "summary": {"signals": {"restconf_ok": False}},
                "items": [],
                "warnings": [],
            }
    except Exception as e:
        return {
            "meta": {
                "tool": tool_name,
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    # Parse XML with sanitization
    try:
        xml_text = _sanitize_slx_xml(raw_xml.get("xml", "") if raw_xml else "")
        root = ET.fromstring(xml_text)
    except Exception as e:
        return {
            "meta": {
                "tool": tool_name,
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": f"XML parse failed: {str(e)}",
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": ["Failed parsing interface XML; try include_raw for inspection."],
        }

    def local(tag: str) -> str:
        return tag.split("}", 1)[1] if "}" in tag else tag

    def norm_name(s: str) -> str:
        return s.lower().replace("ethernet", "").replace("eth", "").strip()

    def _best_effort_if_name(el) -> str | None:
        """Try to derive a stable interface name from common leaf tags.

        Order:
        1) direct children: name/interface-name/if-name
        2) any descendant leaf with those tags
        """
        def _valid_name(s: str) -> bool:
            s = (s or "").strip()
            if not s:
                return False
            # Reject purely-numeric or single-character names like '0' that appear as indices.
            if re.fullmatch(r"\d+", s):
                return False
            if len(s) <= 1:
                return False
            # Prefer names that look like real interfaces (letters, '/', '-', or common prefixes).
            if re.search(r"[A-Za-z]", s) or ("/" in s) or ("-" in s):
                return True
            if s.lower() in ("mgmt", "management"):
                return True
            return False

        # 1) direct children
        for ch in list(el):
            lt = local(ch.tag)
            if lt in ("name", "interface-name", "if-name") and (ch.text or "").strip():
                cand = (ch.text or "").strip()
                if _valid_name(cand):
                    return cand

        # 2) descendants
        for leaf in el.iter():
            lt = local(leaf.tag)
            if lt in ("name", "interface-name", "if-name") and (leaf.text or "").strip():
                cand = (leaf.text or "").strip()
                if _valid_name(cand):
                    return cand

        return None

    # Candidate elements: any element named "interface" that has either a name-like child
    # OR contains ip-address / ipv6-address leaves.
    candidates = []
    for el in root.iter():
        if local(el.tag) != "interface":
            continue

        has_name = False
        has_ip_leaf = False

        for ch in list(el):
            lt = local(ch.tag)
            if lt in ("name", "interface-name", "if-name") and (ch.text or "").strip():
                has_name = True
            if lt in ("ip-address", "ipv4-address", "ipv6-address", "ipv6-addr", "address"):
                if (ch.text or "").strip():
                    has_ip_leaf = True

        # Also consider nested leaves (some structures put ip leaves deeper)
        if not has_ip_leaf:
            for leaf in el.iter():
                lt = local(leaf.tag)
                if lt in ("ip-address", "ipv4-address", "ipv6-address", "ipv6-addr"):
                    if (leaf.text or "").strip():
                        has_ip_leaf = True
                        break

        if has_name or has_ip_leaf:
            candidates.append(el)

    # Deduplicate by (name, first_ip)
    seen = set()

    for el in candidates:
        # Find a name, if present (best effort)
        name = _best_effort_if_name(el)

        ipv4 = []
        ipv6 = []
        vrf = None

        for leaf in el.iter():
            t = (leaf.text or "").strip()
            if not t:
                continue
            lt = local(leaf.tag)

            if lt in ("vrf-name", "vrf"):
                if not vrf:
                    vrf = t
                continue

            # Prefer explicit IP leaf names
            if lt in ("ip-address", "ipv4-address") and "." in t:
                if re.match(r"^\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?$", t) and t not in ipv4:
                    ipv4.append(t)

            if include_ipv6 and lt in ("ipv6-address", "ipv6-addr") and ":" in t:
                if re.match(r"^[0-9a-fA-F:]+(/\d{1,3})?$", t) and t not in ipv6:
                    ipv6.append(t)

            # Fallback: any text that looks like an IP
            if "." in t and re.match(r"^\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?$", t) and t not in ipv4:
                ipv4.append(t)
            if include_ipv6 and ":" in t and re.match(r"^[0-9a-fA-F:]+(/\d{1,3})?$", t) and t not in ipv6:
                ipv6.append(t)

        if not ipv4 and not ipv6:
            continue

        if not name:
            # If one of the IPv4s matches the switch_ip, treat as mgmt interface.
            if any((ip.split("/", 1)[0] == switch_ip) for ip in ipv4):
                name = "mgmt"
            else:
                name = "unnamed-interface"

        if interface_name:
            q = norm_name(interface_name)
            if q and q not in name.lower() and q not in norm_name(name):
                continue

        key = (name, ipv4[0] if ipv4 else "", ipv6[0] if ipv6 else "")
        if key in seen:
            continue
        seen.add(key)

        items.append(
            {
                "name": name,
                "vrf": vrf,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "ipv4_count": len(ipv4),
                "ipv6_count": len(ipv6),
            }
        )

    items = sorted(items, key=lambda x: x.get("name") or "")
    if max_items and len(items) > max_items:
        warnings.append(f"Truncated items to max_items={max_items} (from {len(items)}).")
        items = items[:max_items]

    ipv4_total = sum(int(x.get("ipv4_count") or 0) for x in items)
    ipv6_total = sum(int(x.get("ipv6_count") or 0) for x in items)

    if not items:
        warnings.append("No L3 IP addresses found in interface tree (may be expected if L2-only).")

    payload = {
        "meta": {"tool": tool_name, "switch_ip": switch_ip, "ok": True, "source": "direct_switch_restconf"},
        "summary": {
            "signals": {"restconf_ok": True},
            "interface_with_ip_count": len(items),
            "ipv4_address_count": ipv4_total,
            "ipv6_address_count": ipv6_total,
            "filtered": bool(interface_name),
            "interface_name": interface_name if interface_name else None,
        },
        "items": items,
        "warnings": warnings,
    }

    if include_raw:
        payload["raw_xml"] = raw_xml

    return payload
def restconf_get_running_config(
    *,
    inputs: dict,
    registry,
    transport,
    context: dict,
    **kwargs,
) -> dict:
    """Tier-2: Retrieve running configuration snapshot via SLX /rest config datastore.

    SLX exposes running config under:
      GET https://<switch>/rest/config/running  (XML, vendor media type)

    This is NOT a standard /restconf/data tree and NOT an RPC under /restconf/operations.
    We normalize the response into:
      - summary: key identity fields (hostname, chassis), section count
      - items: top-level config sections (tag + y:self path when present)

    Inputs:
      - config_path: optional suffix under /rest/config/running (e.g. "interface")
      - max_bytes: max raw XML bytes to include when include_raw=true
    """
    tool_name = "restconf_get_running_config"
    switch_ip = _as_str(inputs.get("switch_ip"))
    if not switch_ip:
        return {
            "meta": {"tool": tool_name, "ok": False, "error": "Missing switch_ip"},
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    config_path = _as_str(inputs.get("config_path")) or ""
    include_raw = bool(inputs.get("include_raw", False))
    max_bytes = _as_int(inputs.get("max_bytes"), 200_000)

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    timeout_seconds = inputs.get("timeout_seconds")

    warnings: list[str] = []
    client = make_client(
        switch_ip,
        username=username,
        password=password,
        verify_tls=verify_tls,
        timeout_seconds=timeout_seconds,
    )

    # Fetch XML
    raw_xml = None
    try:
        status, headers, text = client.get_running_config_xml(config_path=config_path)
        content_type = headers.get("Content-Type", "")
        raw_xml = {
            "status": status,
            "content_type": content_type,
            "byte_len": len(text or ""),
        }
        if include_raw:
            snippet = (text or "")
            if max_bytes and len(snippet) > max_bytes:
                raw_xml["truncated"] = True
                raw_xml["max_bytes"] = max_bytes
                raw_xml["xml_snippet"] = snippet[:max_bytes]
            else:
                raw_xml["truncated"] = False
                raw_xml["xml_snippet"] = snippet

        if status >= 400:
            return {
                "meta": {
                    "tool": tool_name,
                    "switch_ip": switch_ip,
                    "ok": False,
                    "source": "direct_switch_restconf",
                    "error": f"REST /config/running failed: {status}",
                },
                "summary": {"signals": {"restconf_ok": False}},
                "items": [],
                "warnings": [],
            }
    except Exception as e:
        return {
            "meta": {
                "tool": tool_name,
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": str(e),
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": [],
        }

    # Parse XML (sanitize just in case)
    try:
        xml_text = _sanitize_slx_xml(text or "")
        root = ET.fromstring(xml_text)
    except Exception as e:
        return {
            "meta": {
                "tool": tool_name,
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": f"XML parse failed: {str(e)}",
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": ["Failed parsing running config XML; try include_raw for inspection."],
        }

    def local(tag: str) -> str:
        return tag.split("}", 1)[1] if "}" in tag else tag

    def get_attr_self(el) -> str | None:
        # Attribute is typically y:self where y maps to http://brocade.com/ns/rest
        for k, v in (el.attrib or {}).items():
            if k.endswith("}self") or k == "self":
                return v
        return None

    items: list[dict] = []
    host_name = None
    chassis_name = None

    # Discover host/chassis under switch-attributes (brocade-ras)
    for child in list(root):
        if local(child.tag) == "switch-attributes":
            for leaf in list(child):
                lt = local(leaf.tag)
                if lt == "host-name" and (leaf.text or "").strip():
                    host_name = (leaf.text or "").strip()
                elif lt == "chassis-name" and (leaf.text or "").strip():
                    chassis_name = (leaf.text or "").strip()

    # Top-level sections
    for child in list(root):
        sec = {
            "section": local(child.tag),
            "self": get_attr_self(child),
        }
        items.append(sec)

    # Optional filter by config_path: if user requests a subpath, we still return the top-level view of that subtree
    # (child tags of the returned root element).
    if config_path:
        warnings.append(f"Fetched subtree under /rest/config/running/{config_path.strip('/')}; items represent top-level elements of that subtree.")

    summary = {
        "signals": {"restconf_ok": True},
        "config_path": config_path or None,
        "section_count": len(items),
        "host_name": host_name,
        "chassis_name": chassis_name,
        "example_sections": [it["section"] for it in items[:8]],
    }

    resp = {
        "meta": {
            "tool": tool_name,
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_restconf",
        },
        "summary": summary,
        "items": items,
        "warnings": warnings,
    }
    if include_raw and raw_xml is not None:
        resp["raw_xml"] = raw_xml
    return resp


def restconf_get_user_sessions(
    registry,
    inputs,
    context=None,
    request_id=None,
    correlation_id=None,
    auto_mode=False,
    **kwargs,
):
    """
    Tier-2: Show active user sessions via SLX user-session-info operation (XML).
    inputs: {
      switch_ip, max_items, username_filter, source_ip_filter,
      include_raw, max_bytes,
      username, password, verify_tls, timeout_seconds
    }
    """
    tool_name = "restconf_get_user_sessions"

    switch_ip = (inputs.get("switch_ip") or "").strip()
    max_items = int(inputs.get("max_items", 50))
    username_filter = (inputs.get("username_filter") or "").strip()
    source_ip_filter = (inputs.get("source_ip_filter") or "").strip()

    include_raw = bool(inputs.get("include_raw", False))
    max_bytes = int(inputs.get("max_bytes", 200000))

    username = inputs.get("username")
    password = inputs.get("password")
    verify_tls = inputs.get("verify_tls")
    timeout_seconds = inputs.get("timeout_seconds")

    if not switch_ip:
        return {
            "meta": {
                "tool": tool_name,
                "switch_ip": None,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": "Missing required input: switch_ip",
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": ["Provide switch_ip."],
        }

    # ---- Call switch /rest/operations/user-session-info ----
    try:
        client = make_client(
            switch_ip,
            username=username,
            password=password,
            verify_tls=verify_tls,
            timeout_seconds=timeout_seconds,
        )
        status, headers, text = client.get_user_session_info_xml()
    except Exception as e:
        return {
            "meta": {
                "tool": tool_name,
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": f"REST call failed: {str(e)}",
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": ["REST call failed (connect/auth/TLS). Try include_raw and check credentials/env."],
        }

    content_type = None
    if isinstance(headers, dict):
        content_type = headers.get("content-type") or headers.get("Content-Type")

    raw_xml = None
    if include_raw:
        b = (text or "").encode("utf-8", errors="replace")
        truncated = len(b) > max_bytes
        snippet = b[:max_bytes].decode("utf-8", errors="replace")
        raw_xml = {
            "status": status,
            "content_type": content_type,
            "byte_len": len(b),
            "truncated": truncated,
            "content": snippet,
        }

    if not (200 <= int(status) < 300):
        resp = {
            "meta": {
                "tool": tool_name,
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": f"HTTP {status} from /rest/operations/user-session-info",
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": ["Switch returned non-2xx. Use include_raw to inspect response."],
        }
        if include_raw and raw_xml is not None:
            resp["raw_xml"] = raw_xml
        return resp

    # ---- Parse XML (sanitize just in case) ----
    try:
        xml_text = _sanitize_slx_xml(text or "")
        root = ET.fromstring(xml_text)
    except Exception as e:
        resp = {
            "meta": {
                "tool": tool_name,
                "switch_ip": switch_ip,
                "ok": False,
                "source": "direct_switch_restconf",
                "error": f"XML parse failed: {str(e)}",
            },
            "summary": {"signals": {"restconf_ok": False}},
            "items": [],
            "warnings": ["Failed parsing session XML; try include_raw for inspection."],
        }
        if include_raw and raw_xml is not None:
            resp["raw_xml"] = raw_xml
        return resp

    def local(tag: str) -> str:
        return tag.split("}", 1)[1] if "}" in tag else tag

    def leaf_map(el) -> dict:
        d = {}
        for c in list(el):
            if len(list(c)) == 0 and (c.text or "").strip():
                d[local(c.tag)] = (c.text or "").strip()
        return d

    def norm_key(k: str) -> str:
        return (k or "").strip().replace("-", "_").replace(".", "_")

    def pick(rec: dict, keys: list[str]) -> str | None:
        for k in keys:
            v = rec.get(k)
            if v is not None and str(v).strip() != "":
                return str(v).strip()
        return None

    # Heuristic: collect any element that "looks like" a session record
    candidates = []
    for el in root.iter():
        m = leaf_map(el)
        if not m:
            continue

        ltag = local(el.tag).lower()
        keys_l = {k.lower() for k in m.keys()}

        has_user = any(k in keys_l for k in ["user-name", "username", "login-name", "user", "account", "name"])
        has_ip = any("ip" in k for k in keys_l) or any(k in keys_l for k in ["remote-host", "client-host", "source-host"])

        looks_like_session = ("session" in ltag) or (has_user and has_ip)

        if looks_like_session:
            rec = {norm_key(k): v for k, v in m.items()}
            rec["node"] = local(el.tag)
            candidates.append(rec)

    # If still empty, try root as a single record
    if not candidates:
        m = leaf_map(root)
        if m:
            candidates.append({norm_key(k): v for k, v in m.items()} | {"node": local(root.tag)})

    # Deduplicate
    deduped = []
    seen = set()
    for s in candidates:
        u = pick(s, ["user_name", "username", "login_name", "user", "account", "name"]) or ""
        ip = pick(s, ["source_ip", "src_ip", "remote_ip", "client_ip", "ip_address", "ip"]) or ""
        sid = pick(s, ["session_id", "sid", "id"]) or ""
        tty = pick(s, ["tty", "line", "terminal"]) or ""
        st = pick(s, ["login_time", "start_time"]) or ""
        key = (u, ip, sid, tty, st)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)

    items = deduped

    # Filters
    if username_filter:
        uf = username_filter.lower()
        items = [
            s for s in items
            if uf in (pick(s, ["user_name", "username", "login_name", "user", "account", "name"]) or "").lower()
        ]
    if source_ip_filter:
        sf = source_ip_filter.lower()
        items = [
            s for s in items
            if sf in (pick(s, ["source_ip", "src_ip", "remote_ip", "client_ip", "ip_address", "ip"]) or "").lower()
        ]

    # Truncate
    if max_items > 0:
        items = items[:max_items]

    users = []
    for s in items:
        u = pick(s, ["user_name", "username", "login_name", "user", "account", "name"])
        if u and u not in users:
            users.append(u)

    warnings = []
    if not items:
        warnings.append("No sessions parsed from XML. Try include_raw to inspect, or adjust parser for your SLX build output.")

    summary = {
        "signals": {"restconf_ok": True},
        "session_count": len(items),
        "unique_users": len(users),
        "example_users": users[:8],
        "filters": {
            "username_filter": username_filter or None,
            "source_ip_filter": source_ip_filter or None,
        },
    }

    resp = {
        "meta": {
            "tool": tool_name,
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_restconf",
        },
        "summary": summary,
        "items": items,
        "warnings": warnings,
    }
    if include_raw and raw_xml is not None:
        resp["raw_xml"] = raw_xml
    return resp

