from __future__ import annotations

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

