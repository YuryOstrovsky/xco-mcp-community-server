# tools/restconf_slx/mac_address_table.py
"""
restconf_slx_get_mac_address_table — read-only MAC-address-table query
for SLX switches.

Why CLI, not RESTCONF
---------------------
SLX 20.x's RESTCONF surface for the MAC-address-table is config-only:

  POST /restconf/operations/brocade-mac-address-table:get-mac-address-table
       → returns 204 No Content (RPC exists but returns no operational data)
  GET  /restconf/data/brocade-mac-address-table:mac-address-table
       → returns config (static MACs, aging-time, mac-move) NOT learned entries

The DYNAMIC learned MAC table is exposed only via the CLI command
`show mac-address-table`, so this tool uses SSH.  When SLX adds a YANG
model for the learned MAC table, this tool can grow a RESTCONF code
path without renaming.

The tool name keeps the `restconf_` prefix (switch-direct, not via XCO)
matching this server's convention, and the `slx` family marker scopes
it to SLX.

What it does
------------
Queries `show mac-address-table` on one or more switches in parallel,
parses the entries, and returns a list of:

  vlan        (int)        — VLAN ID
  mac         (str)        — normalized colon-separated lowercase MAC
  type        (str)        — Dynamic / Static / EVPN / Internal / Local / Remote
  state       (str)        — typically "Active"
  interface   (str)        — canonical "Ethernet 0/N" form
  interface_short (str)    — short "0/N" form

Optional substring filters: `mac_filter`, `vlan_filter` (exact int),
`interface_filter` — applied server-side before max_items truncation.

switch_ip may be a string (single-switch, original shape) OR an array
of strings (parallel multi-switch fan-out via ThreadPoolExecutor;
cap 16 concurrent SSH sessions).  Non-fatal per-switch failures land in
errors_by_ip; meta.ok stays true if at least one switch returned data.

Side effects: NONE.  Pure show command.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from mcp_runtime.logging import get_logger

logger = get_logger("mcp.restconf_slx.mac_address_table")


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_SSH_TIMEOUT = 20
_DEFAULT_MAX_ITEMS   = 200
_MAX_PARALLEL_SSH    = 16

_DEFAULT_USERNAME = os.environ.get("RESTCONF_USERNAME", "admin")
_DEFAULT_PASSWORD = os.environ.get("RESTCONF_PASSWORD", "")


# ---------------------------------------------------------------------------
# MAC normalisation
# ---------------------------------------------------------------------------

# SLX prints MACs in dotted format (0011.2233.4455).  We normalize to the
# colon form (00:11:22:33:44:55) for downstream consistency with the ARP
# tool's output shape (which is also colon-separated).
_DOTTED_MAC_RE   = re.compile(r"^[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}$")
_COLON_MAC_RE    = re.compile(r"^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
_HYPHEN_MAC_RE   = re.compile(r"^([0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}$")
_BARE_MAC_RE     = re.compile(r"^[0-9a-fA-F]{12}$")


def _normalize_mac(raw: str) -> Optional[str]:
    """Return canonical lowercase colon-form MAC or None if unparseable.
    Accepts SLX dotted form (0011.2233.4455), colon form, hyphen form,
    or bare hex."""
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if _DOTTED_MAC_RE.match(s):
        hex_only = s.replace(".", "")
    elif _COLON_MAC_RE.match(s):
        hex_only = s.replace(":", "")
    elif _HYPHEN_MAC_RE.match(s):
        hex_only = s.replace("-", "")
    elif _BARE_MAC_RE.match(s):
        hex_only = s
    else:
        return None
    return ":".join(hex_only[i:i+2] for i in range(0, 12, 2))


# ---------------------------------------------------------------------------
# Interface name canonicalisation (shared shape with the ARP tool)
# ---------------------------------------------------------------------------

def _canonical_interface(raw: str) -> Tuple[str, str]:
    """Return (display, short) interface names.

    SLX `show mac-address-table` prints interfaces as `Eth 0/51` /
    `Po 100` / `Tu 32769`.  Normalise to the display form used by
    the ARP tool (e.g. `Ethernet 0/51`) AND keep the short form for
    operator copy-paste into other CLI commands.
    """
    if not isinstance(raw, str):
        return ("", "")
    s = raw.strip()
    # Eth 0/N → Ethernet 0/N
    m = re.match(r"^(?:eth|ethernet)\s*(\d+/\d+(?:/\d+)?)$", s, re.IGNORECASE)
    if m:
        return (f"Ethernet {m.group(1)}", m.group(1))
    # Po N → Port-Channel N
    m = re.match(r"^(?:po|port-channel|portchannel)\s*(\d+)$", s, re.IGNORECASE)
    if m:
        return (f"Port-Channel {m.group(1)}", m.group(1))
    # Tu N → Tunnel N
    m = re.match(r"^(?:tu|tunnel)\s*(\d+)$", s, re.IGNORECASE)
    if m:
        return (f"Tunnel {m.group(1)}", m.group(1))
    # Ve N → Ve N
    m = re.match(r"^(?:ve|virtual-ethernet)\s*(\d+)$", s, re.IGNORECASE)
    if m:
        return (f"Ve {m.group(1)}", m.group(1))
    # Unknown — return as-is for both
    return (s, s)


# ---------------------------------------------------------------------------
# Parser — `show mac-address-table`
#
# SLX 20.8.1 EVPN-VXLAN format (ground-truth captured from an SLX leaf
# — the format that the original \d+\s+<mac>
# pattern silently parsed as ZERO entries, so learned EVPN MACs were
# missed):
#
#   Type Code - CCL:Cluster Client Local MAC          <- legend (no leading
#               CCR:Cluster Client Remote MAC            digit → skipped)
#               CR:Cluster Remote MAC
#               ES: Ethernet Segment
#   VlanId/BDId   Mac-address       Type      State    Ports/LIF/PW/T
#   100 (V)       1070.fd17.43c4    Dynamic   Active   Eth 0/51
#   100 (V)       1070.fd17.45cc    EVPN      Active   Tu 32771 (172.31.254.78)
#   Total MAC addresses    :  2
#
# Two format shifts from the older SLX 20.x docs:
#   1. The L2-domain column is `VlanId/BDId` and each row tags the id with
#      `(V)` (VLAN) or `(BD)` (bridge-domain) — e.g. `100 (V)`.  The old
#      regex `(?P<vlan>\d+)\s+<mac>` choked on the `(V)` token and matched
#      nothing.
#   2. EVPN/overlay rows carry the remote VTEP IP after the tunnel token:
#      `Tu 32771 (172.31.254.78)`.  We split that off into `vtep_ip`.
#
# The older un-tagged form (`100  <mac>  Dynamic  Active  Eth 0/51`) is
# still accepted — the `(V)`/`(BD)` tag is optional in the row regex.
#
# Type values observed on SLX 20.x: Dynamic, Static, EVPN, Internal,
# Local, Remote.  State is typically "Active".  Ports column can be
# Eth (access port), Po (port-channel / LAG), or Tu (overlay tunnel,
# for EVPN-learned MACs reachable via VXLAN).
# ---------------------------------------------------------------------------

# Row pattern: VLAN [domain-tag] MAC TYPE STATE PORT-with-space-in-token
# MAC is dotted form (4-4-4 hex.hex.hex).
# The `(V)` / `(BD)` domain tag after the id is OPTIONAL (present on SLX
# 20.8.1, absent on older builds).
# PORT can have a space inside (e.g. "Eth 0/51", "Tu 32771 (1.2.3.4)") so
# we capture greedy and post-split the VTEP IP.
_MAC_ROW_RE = re.compile(
    r"^\s*"
    r"(?P<vlan>\d+)\s*"
    r"(?:\(\s*(?P<domain>[A-Za-z]+)\s*\)\s+)?"
    r"(?P<mac>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"
    r"(?P<type>\S+)\s+"
    r"(?P<state>\S+)\s+"
    r"(?P<port>.+?)\s*$",
)

# A trailing VTEP IP in the Ports column for EVPN-over-VXLAN entries,
# e.g. "Tu 32771 (172.31.254.78)".  Captured separately so `interface`
# stays a clean "Tunnel 32771".
_VTEP_SUFFIX_RE = re.compile(
    r"\(\s*((?:\d{1,3}\.){3}\d{1,3})\s*\)\s*$"
)


def _parse_mac_address_table(text: str) -> Dict[str, Any]:
    """Parse the full output of `show mac-address-table`.  Returns
    a dict with `entries` (full list of normalized records) and
    `summary` (total seen, counts per type)."""
    out: Dict[str, Any] = {
        "entries":          [],
        "total_in_table":   None,    # from the "Total MAC addresses" footer
        "by_type":          {},      # type → count seen
    }
    if not text:
        return out

    entries: List[Dict[str, Any]] = []
    by_type: Dict[str, int] = {}

    for line in text.splitlines():
        # Skip header / divider / footer noise
        if not line.strip():
            continue
        if line.strip().startswith("VlanId"):
            continue
        if line.strip().startswith("-"):
            continue

        m = _MAC_ROW_RE.match(line)
        if not m:
            # Capture the total-MAC footer if present
            tm = re.match(r"^\s*Total MAC addresses\s*:\s*(\d+)\s*$", line)
            if tm:
                try:
                    out["total_in_table"] = int(tm.group(1))
                except ValueError:
                    pass
            continue

        mac_norm = _normalize_mac(m.group("mac"))
        if not mac_norm:
            continue
        try:
            vlan = int(m.group("vlan"))
        except ValueError:
            continue

        # Split a trailing VTEP IP off the Ports column for EVPN/overlay
        # entries ("Tu 32771 (172.31.254.78)") so the interface name stays
        # clean and the VTEP is available for downstream enrichment.
        port_raw = (m.group("port") or "").strip()
        vtep_ip: Optional[str] = None
        vm = _VTEP_SUFFIX_RE.search(port_raw)
        if vm:
            vtep_ip = vm.group(1)
            port_raw = port_raw[:vm.start()].strip()

        # Domain tag: "V" → vlan, "BD" → bridge-domain (None on older
        # builds that don't print the tag).
        domain_tag = (m.group("domain") or "").upper() or None
        domain_kind = {"V": "vlan", "BD": "bridge-domain"}.get(domain_tag)

        iface_display, iface_short = _canonical_interface(port_raw)
        entry = {
            "vlan":            vlan,
            "mac":             mac_norm,
            "mac_dotted":      m.group("mac").lower(),    # SLX-native form for copy-paste
            "type":            m.group("type"),
            "state":           m.group("state"),
            "interface":       iface_display,
            "interface_short": iface_short,
            "domain":          domain_kind,               # "vlan" | "bridge-domain" | None
            "vtep_ip":         vtep_ip,                    # remote VTEP for EVPN/VXLAN entries, else None
        }
        entries.append(entry)
        by_type[entry["type"]] = by_type.get(entry["type"], 0) + 1

    out["entries"] = entries
    out["by_type"] = by_type
    return out


# ---------------------------------------------------------------------------
# SSH primitives for the switch-direct CLI query,
# kept locally to avoid an artificial cross-file dependency for two
# tiny tools.  If a third tool needs them they can be extracted into
# a shared module.
# ---------------------------------------------------------------------------

def _ssh_run_one_command(switch_ip: str, username: str, password: str,
                         command: str, timeout: int) -> Tuple[str, Optional[str]]:
    """Open SSH, run one command, close.  Returns (output, error)."""
    import paramiko
    client = None
    shell = None
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            switch_ip, username=username, password=password,
            timeout=10, look_for_keys=False, allow_agent=False,
            disabled_algorithms={'pubkeys': ['rsa-sha2-512', 'rsa-sha2-256']},
        )
        shell = client.invoke_shell()
        time.sleep(0.5)
        if shell.recv_ready():
            shell.recv(65535)
        # Prelude
        for prelude in ("terminal length 0\n", "terminal width 511\n"):
            shell.send(prelude)
            time.sleep(0.4)
            if shell.recv_ready():
                shell.recv(65535)
        # Run target command
        shell.send(command + "\n")
        buf = b""
        deadline = time.time() + timeout
        idle = 0
        while time.time() < deadline:
            time.sleep(0.4)
            if shell.recv_ready():
                buf += shell.recv(65535)
                idle = 0
            else:
                idle += 1
                if idle >= 4 and buf:
                    break
        text = buf.decode("utf-8", errors="replace")
        # Strip echoed command line + trailing prompt
        lines = text.splitlines()
        stripped: List[str] = []
        saw_first = False
        for ln in lines:
            if not saw_first and command.strip() in ln.strip():
                saw_first = True
                continue
            if re.match(r"^\s*\S+[#>]\s*$", ln):
                continue
            stripped.append(ln)
        return ("\n".join(stripped), None)
    except Exception as e:
        return ("", str(e)[:300])
    finally:
        try:
            if shell is not None:
                shell.send("exit\n")
                time.sleep(0.2)
        except Exception:
            pass
        try:
            if client is not None:
                client.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _filter_entries(
    entries: List[Dict[str, Any]],
    mac_filter: Optional[str],
    vlan_filter: Optional[int],
    interface_filter: Optional[str],
) -> List[Dict[str, Any]]:
    """Apply optional filters; case-insensitive substring on MAC and
    interface; exact match on VLAN.  Order preserved."""
    out = entries
    if vlan_filter is not None:
        out = [e for e in out if e["vlan"] == vlan_filter]
    if mac_filter:
        mf_norm = _normalize_mac(mac_filter)
        if mf_norm:
            # Full-MAC match (normalized)
            out = [e for e in out if e["mac"] == mf_norm]
        else:
            # Substring match (case-insensitive) on either form
            mf = mac_filter.lower().replace(":", "").replace("-", "").replace(".", "")
            def _haystack(e):
                return e["mac"].replace(":", "") + (e.get("mac_dotted") or "").replace(".", "")
            out = [e for e in out if mf in _haystack(e).lower()]
    if interface_filter:
        ifn = interface_filter.lower().strip()
        # Tolerate "Ethernet 0/51", "ethernet 0/51", "0/51"
        for prefix in ("ethernet", "eth", "port-channel", "po", "tunnel", "tu", "ve"):
            if ifn.startswith(prefix + " "):
                ifn = ifn.split(" ", 1)[1].strip()
                break
        out = [
            e for e in out
            if ifn in e.get("interface_short", "").lower()
            or ifn in e.get("interface", "").lower()
        ]
    return out


# ---------------------------------------------------------------------------
# Single-switch probe
# ---------------------------------------------------------------------------

def _probe_single_switch(
    *,
    inputs: Optional[Dict[str, Any]] = None,
    registry=None,
    transport=None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Query one switch's MAC-address-table.  Single-switch response
    shape — original contract."""
    inputs = inputs or {}
    raw_ip = inputs.get("switch_ip")
    switch_ip = raw_ip.strip() if isinstance(raw_ip, str) else ""
    if not switch_ip:
        return {
            "meta": {"tool": "restconf_slx_get_mac_address_table",
                     "ok": False, "error": "Missing required input: switch_ip"},
            "summary": {"returned": 0, "entries_seen": 0, "filtered": False, "by_type": {}},
            "items": [],
            "warnings": [],
        }

    mac_filter       = inputs.get("mac_filter")
    vlan_filter      = inputs.get("vlan_filter")
    iface_filter     = inputs.get("interface_filter")
    max_items        = int(inputs.get("max_items") or _DEFAULT_MAX_ITEMS)
    include_raw      = bool(inputs.get("include_raw") or False)
    ssh_timeout      = int(inputs.get("ssh_timeout") or _DEFAULT_SSH_TIMEOUT)
    username         = inputs.get("username") or _DEFAULT_USERNAME
    password         = inputs.get("password") or _DEFAULT_PASSWORD

    # Coerce vlan_filter to int if a string was passed
    if isinstance(vlan_filter, str) and vlan_filter.isdigit():
        vlan_filter = int(vlan_filter)
    elif vlan_filter is not None and not isinstance(vlan_filter, int):
        vlan_filter = None

    start = time.time()

    # We pick the right CLI command based on vlan_filter: SLX supports
    # `show mac-address-table vlan N` which pre-filters server-side
    # and produces a smaller payload.  Other filters are applied
    # client-side after parsing.
    if vlan_filter is not None:
        cmd = f"show mac-address-table vlan {vlan_filter}"
    else:
        cmd = "show mac-address-table"

    output, err = _ssh_run_one_command(
        switch_ip, username, password, cmd, ssh_timeout,
    )
    elapsed = time.time() - start

    if err:
        return {
            "meta": {
                "tool": "restconf_slx_get_mac_address_table",
                "switch_ip": switch_ip,
                "ok": False,
                "error": f"SSH to {switch_ip} failed: {err}",
                "source": "direct_switch_cli",
                "elapsed_s": round(elapsed, 2),
            },
            "summary": {"returned": 0, "entries_seen": 0, "filtered": False, "by_type": {}},
            "items": [],
            "warnings": [f"Could not reach switch {switch_ip} via SSH."],
        }

    parsed = _parse_mac_address_table(output)
    entries = parsed["entries"]

    # Apply filters
    filtered = _filter_entries(
        entries, mac_filter,
        vlan_filter if vlan_filter is not None else None,
        iface_filter,
    )
    # Tag each entry with switch_ip — important for the multi-switch
    # rollup, useful for single-switch consumers too (consistent with
    # tag per-interface rows).
    for e in filtered:
        e["switch_ip"] = switch_ip

    # Truncate
    truncated = False
    if max_items >= 0 and len(filtered) > max_items:
        filtered = filtered[:max_items]
        truncated = True

    result: Dict[str, Any] = {
        "meta": {
            "tool": "restconf_slx_get_mac_address_table",
            "switch_ip": switch_ip,
            "ok": True,
            "source": "direct_switch_cli",
            "elapsed_s": round(elapsed, 2),
        },
        "summary": {
            "returned":          len(filtered),
            "entries_seen":      len(entries),
            "total_in_table":    parsed["total_in_table"],
            "filtered":          bool(mac_filter or vlan_filter is not None or iface_filter),
            "truncated":         truncated,
            "by_type":           parsed["by_type"],
        },
        "items":    filtered,
        "warnings": [],
    }
    if include_raw:
        result["raw"] = {"show_mac_address_table": output}

    logger.info(
        "restconf_slx_get_mac_address_table: ip=%s entries=%d filtered=%d "
        "truncated=%s elapsed=%.2fs",
        switch_ip, len(entries), len(filtered), truncated, elapsed,
    )
    return result


# ---------------------------------------------------------------------------
# Multi-switch fan-out (switch_ip string OR list; single-element list also
# ---------------------------------------------------------------------------

def _multi_switch_fanout(
    switch_ips: List[str],
    inputs: Dict[str, Any],
    registry=None,
    transport=None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Parallel per-switch probe via ThreadPoolExecutor.  Returns the
    multi-switch response shape (items flat, per-switch context keyed
    by IP, errors per IP).  Never raises — per-switch failures become
    rows in errors_by_ip."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    start = time.time()
    valid_ips: List[str] = []
    bad_ips: List[Any] = []
    for ip in switch_ips:
        if isinstance(ip, str) and ip.strip():
            valid_ips.append(ip.strip())
        else:
            bad_ips.append(ip)

    if not valid_ips:
        return {
            "meta": {
                "tool": "restconf_slx_get_mac_address_table",
                "ok": False, "switches": [],
                "error": (
                    f"switch_ip[] is empty or contained only non-string "
                    f"entries.  Got: {switch_ips!r}"
                ),
            },
            "summary": {"switches_probed": 0, "switches_errored": 0,
                        "returned": 0, "entries_seen": 0,
                        "filtered": False, "by_type": {}},
            "items":                  [],
            "switch_level_data_by_ip": {},
            "errors_by_ip":            {},
            "warnings":                [],
        }

    per_switch_inputs: Dict[str, Dict[str, Any]] = {}
    for ip in valid_ips:
        per_switch_inputs[ip] = dict(inputs)
        per_switch_inputs[ip]["switch_ip"] = ip

    n_workers = min(_MAX_PARALLEL_SSH, len(valid_ips))
    per_switch_results: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(
        max_workers=n_workers,
        thread_name_prefix="mac_address_table",
    ) as pool:
        fut_to_ip = {
            pool.submit(
                _probe_single_switch,
                inputs=per_switch_inputs[ip],
                registry=registry,
                transport=transport,
                context=context,
                **kwargs,
            ): ip
            for ip in valid_ips
        }
        for fut in as_completed(fut_to_ip):
            ip = fut_to_ip[fut]
            try:
                per_switch_results[ip] = fut.result()
            except Exception as e:
                logger.exception(
                    "restconf_slx_get_mac_address_table: per-switch probe raised "
                    "for ip=%s", ip,
                )
                per_switch_results[ip] = {
                    "meta": {"switch_ip": ip, "ok": False,
                             "error": f"unexpected error: {str(e)[:200]}"},
                    "items": [], "warnings": [],
                }

    # Aggregate
    items_out: List[Dict[str, Any]] = []
    switch_level_data_by_ip: Dict[str, Any] = {}
    errors_by_ip: Dict[str, str] = {}
    aggregated_warnings: List[str] = []
    n_errored = 0
    entries_seen_total = 0
    by_type_total: Dict[str, int] = {}

    for i, bad in enumerate(bad_ips):
        errors_by_ip[f"<invalid#{i}>"] = (
            f"switch_ip entry was not a non-empty string: {bad!r}"
        )
        n_errored += 1

    for ip in valid_ips:
        per_sw = per_switch_results.get(ip, {})
        meta = per_sw.get("meta", {})
        if not meta.get("ok", False):
            errors_by_ip[ip] = meta.get("error", "unknown error")
            n_errored += 1
            continue
        for it in per_sw.get("items", []) or []:
            items_out.append(it)
        summ = per_sw.get("summary", {}) or {}
        entries_seen_total += int(summ.get("entries_seen") or 0)
        for t, c in (summ.get("by_type") or {}).items():
            by_type_total[t] = by_type_total.get(t, 0) + int(c)
        switch_level_data_by_ip[ip] = {
            "total_in_table":     summ.get("total_in_table"),
            "entries_seen":       summ.get("entries_seen", 0),
            "returned_this_switch": summ.get("returned", 0),
            "by_type":            summ.get("by_type", {}),
            "truncated":          bool(summ.get("truncated")),
        }
        for w in per_sw.get("warnings", []) or []:
            aggregated_warnings.append(f"[{ip}] {w}")

    elapsed = time.time() - start
    ok = (n_errored < len(valid_ips) + len(bad_ips))

    result: Dict[str, Any] = {
        "meta": {
            "tool":              "restconf_slx_get_mac_address_table",
            "ok":                ok,
            "switches":          valid_ips,
            "source":            "direct_switch_cli",
            "elapsed_s":         round(elapsed, 2),
            "multi_switch":      True,
            "max_parallel_ssh":  n_workers,
        },
        "summary": {
            "switches_probed":  len(valid_ips) + len(bad_ips),
            "switches_errored": n_errored,
            "returned":         len(items_out),
            "entries_seen":     entries_seen_total,
            "filtered":         bool(
                inputs.get("mac_filter")
                or inputs.get("vlan_filter") is not None
                or inputs.get("interface_filter")
            ),
            "by_type":          by_type_total,
        },
        "items":                  items_out,
        "switch_level_data_by_ip": switch_level_data_by_ip,
        "errors_by_ip":            errors_by_ip,
        "warnings":                aggregated_warnings,
    }

    logger.info(
        "restconf_slx_get_mac_address_table: multi-switch n=%d errored=%d "
        "returned=%d entries_seen=%d elapsed=%.2fs",
        len(valid_ips), n_errored, len(items_out), entries_seen_total, elapsed,
    )
    return result


# ---------------------------------------------------------------------------
# Top-level handler — dispatches single vs multi
# ---------------------------------------------------------------------------

def restconf_slx_get_mac_address_table(
    *,
    inputs: Optional[Dict[str, Any]] = None,
    registry=None,
    transport=None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Tier-2 read-only MAC-address-table query for SLX switches.

    switch_ip may be:
      - a string  → single-switch probe (original shape)
      - a list of strings → multi-switch parallel fan-out (v2 shape:
        meta.multi_switch=true, switch_level_data_by_ip, errors_by_ip)

    Single-element list also returns the multi-switch shape so the
    client can pass an array unconditionally.

    Composes with restconf_get_arp_table for the "where is this IP /
    MAC?" search flow: ARP gives IP → MAC + (Ve N | Eth 0/N); this
    tool resolves MAC → access port when ARP gave you the SVI.

    Underlying transport is SSH+CLI (SLX 20.x's RESTCONF surface for
    the learned MAC table is config-only over RESTCONF).
    Side-effect free.
    """
    inputs = inputs or {}
    sw = inputs.get("switch_ip")
    if isinstance(sw, list):
        return _multi_switch_fanout(
            sw, inputs,
            registry=registry, transport=transport, context=context, **kwargs,
        )
    return _probe_single_switch(
        inputs=inputs, registry=registry, transport=transport,
        context=context, **kwargs,
    )
