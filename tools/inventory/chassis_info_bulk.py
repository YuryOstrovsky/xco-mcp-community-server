# tools/inventory/chassis_info_bulk.py
"""
inventory_get_chassis_info_bulk — fleet-wide chassis identity export.

Returns one row per switch with hostname / IP / site / OS version /
**serial number** / **part number**, sourced from XCO's own bulk-export
endpoint (the same data the "Download Inventory" button in the XCO UI
gives operators).

Why this exists
---------------
The client team's Fleet Inventory widget needs serial numbers, but the
existing inventory tool surface doesn't expose them:

- `inventory_switch_inventory_summary` returns `{}` (broken in XCO
  4.0.0 / Lab-B).
- `inventory_switch_inventory_info` returns all-null sub-fields.
- `inventory_get_device_inventory_export` returns per-device hardware
  tree (slots/fans/PSUs) without serial.
- `/v1/inventory/switches` returns 30+ fields per switch — chassis_name
  yes, serial NO.

Lab investigation (2026-05-27) found the actual endpoint XCO's "Download
Inventory" UI button uses: `POST /v1/inventory/switches/
inventory-bulk-export` with `{"device_ids": [...]}`.  Returns a ZIP-
wrapped XLSX whose single sheet has exactly the columns we need.

Architectural notes
-------------------
- One XCO call returns the whole fleet — no per-switch SSH or
  RESTCONF roundtrips.
- No new dependencies: outer ZIP and inner XLSX are both parsed with
  stdlib `zipfile` + `xml.etree.ElementTree`.  We deliberately don't
  pull in `openpyxl` for one tool's parser.
- We do NOT attempt to merge this with other inventory data — that's
  a client-side concern (join by `ip_address`).
- Side effects: none.  Read-only against XCO.
"""

from __future__ import annotations

import io
import time
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional

from mcp_runtime.logging import get_logger

logger = get_logger("mcp.inventory.chassis_info_bulk")


# XCO endpoints we hit
_LIST_SWITCHES_PATH = "/v1/inventory/switches"
_BULK_EXPORT_PATH = "/v1/inventory/switches/inventory-bulk-export"

# Default cap so a misconfigured caller doesn't ask for 10k switches at once
_DEFAULT_MAX_DEVICES = 500

# XML namespace used in XLSX sheets and shared strings
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# The header row XCO emits (used to detect malformed responses).  We
# tolerate column order changes by matching on header name, not position.
_EXPECTED_HEADERS = {
    "Host Name":     "hostname",
    "IP Address":    "ip_address",
    "Site Name":     "site_name",
    "OS Version":    "os_version",
    "Serial Number": "serial_number",
    "Part Number":   "part_number",
}


# ---------------------------------------------------------------------------
# XLSX parser — stdlib only
# ---------------------------------------------------------------------------

def _parse_inner_xlsx(blob: bytes) -> List[List[str]]:
    """Parse an XLSX bytes blob into a list-of-lists (one inner list
    per row, in document order).  Returns raw cell text — no header
    mapping yet.  Uses stdlib zipfile + xml.etree, no openpyxl
    dependency.

    Handles:
      - shared strings (the common case for text cells)
      - inline strings (used when XCO emits cell text directly)
      - number-typed cells (cell @t="n" or absent)
    """
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()

        # Shared strings table — pool of unique text values that cells
        # reference by index when @t="s".
        strings: List[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.iter(f"{_NS}si"):
                # Concatenate all <t> children (may be multiple under
                # <r> formatting runs).
                strings.append("".join(
                    t.text or "" for t in si.iter() if t.tag.endswith("}t")
                ))

        # Iterate every worksheet — bulk-export currently has one
        # sheet, but tolerate multiple just in case.
        rows: List[List[str]] = []
        sheet_names = sorted(n for n in names
                             if n.startswith("xl/worksheets/sheet")
                             and n.endswith(".xml"))
        for sn in sheet_names:
            root = ET.fromstring(z.read(sn))
            for row in root.iter(f"{_NS}row"):
                cells: List[str] = []
                for c in row.findall(f"{_NS}c"):
                    t = c.get("t", "")
                    v = c.find(f"{_NS}v")
                    inline = c.find(f"{_NS}is")
                    if t == "s" and v is not None and strings:
                        try:
                            cells.append(strings[int(v.text or "0")])
                        except (ValueError, IndexError):
                            cells.append("")
                    elif inline is not None:
                        cells.append("".join(
                            (t.text or "") for t in inline.iter()
                            if t.tag.endswith("}t")
                        ))
                    elif v is not None:
                        cells.append(v.text or "")
                    else:
                        cells.append("")
                rows.append(cells)
        return rows


def _unwrap_outer_zip_and_parse(blob: bytes) -> List[List[str]]:
    """XCO's bulk-export returns a ZIP that contains ONE .xlsx file
    inside.  Unwrap the outer ZIP, then parse the inner XLSX.

    If the response is NOT a ZIP (e.g. XCO returned JSON error directly),
    raises ValueError so the caller can return a structured error.
    """
    if not blob or len(blob) < 4 or blob[:2] != b"PK":
        raise ValueError(
            f"Response does not look like a ZIP archive "
            f"(first bytes: {blob[:8]!r})"
        )

    with zipfile.ZipFile(io.BytesIO(blob)) as outer:
        inner_names = [n for n in outer.namelist()
                       if n.lower().endswith(".xlsx")]
        if not inner_names:
            raise ValueError(
                "Outer ZIP did not contain any .xlsx file "
                f"(contains: {outer.namelist()})"
            )
        # Take the first .xlsx — XCO emits exactly one per response
        return _parse_inner_xlsx(outer.read(inner_names[0]))


def _rows_to_items(rows: List[List[str]]) -> List[Dict[str, Any]]:
    """Map rows-with-headers into a list of structured dicts.  The
    header row is identified by matching against _EXPECTED_HEADERS;
    column order doesn't matter."""
    if not rows:
        return []

    # Find the header row (usually row 0)
    header_idx = -1
    headers: List[str] = []
    for i, row in enumerate(rows):
        if any(h in _EXPECTED_HEADERS for h in row):
            header_idx = i
            headers = list(row)
            break

    if header_idx < 0:
        # No recognisable header — return rows as-is keyed by column index
        return [
            {"_col_{}".format(j): v for j, v in enumerate(row)}
            for row in rows if any(c.strip() for c in row)
        ]

    # Map header position → canonical field name
    col_to_field: Dict[int, str] = {}
    for j, h in enumerate(headers):
        if h in _EXPECTED_HEADERS:
            col_to_field[j] = _EXPECTED_HEADERS[h]

    items: List[Dict[str, Any]] = []
    for row in rows[header_idx + 1:]:
        if not any((c or "").strip() for c in row):
            continue  # skip blank rows
        item: Dict[str, Any] = {}
        for j, val in enumerate(row):
            field = col_to_field.get(j)
            if field:
                item[field] = (val or "").strip() or None
        # Always ensure all expected fields are present (None when blank)
        for field in _EXPECTED_HEADERS.values():
            item.setdefault(field, None)
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------

def _error(status: int, msg: str, **extra: Any) -> Dict[str, Any]:
    payload = {"error": msg}
    payload.update(extra)
    return {"status": status, "payload": payload}


def inventory_get_chassis_info_bulk(
    *,
    inputs: Optional[Dict[str, Any]] = None,
    registry=None,
    transport=None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Return chassis identity (hostname, IP, site, OS, serial, part
    number) for every switch in the bound XCO site, sourced from XCO's
    `inventory-bulk-export` endpoint.

    Inputs:
      device_ids   (optional) list of integer device IDs to scope the
                              export.  Omit to auto-expand to all
                              switches XCO knows about.
      max_devices  (optional) safety cap on auto-expansion (default 500).

    Returns:
      { status: 200,
        payload: {
          items: [ {hostname, ip_address, site_name, os_version,
                    serial_number, part_number}, ... ],
          item_count: int,
          meta: { source, fetched_at, elapsed_s, device_ids_requested }
        } }
    """
    inputs = inputs or {}

    if transport is None:
        return _error(500, "No XCO transport available.")

    device_ids: Optional[List[int]] = inputs.get("device_ids")
    max_devices = int(inputs.get("max_devices") or _DEFAULT_MAX_DEVICES)
    start = time.time()

    # --- Step 1: resolve device_ids (auto-expand if omitted) ---
    if device_ids is None:
        try:
            resp = transport.request(method="GET", path=_LIST_SWITCHES_PATH,
                                     timeout=15)
        except Exception as e:
            logger.warning("chassis_info_bulk: failed to list switches: %s",
                           str(e)[:200])
            return _error(502,
                          f"Failed to enumerate switches for auto-expansion: "
                          f"{str(e)[:200]}")

        if not isinstance(resp, dict) or resp.get("status", 0) >= 400:
            return _error(502,
                          "Failed to enumerate switches for auto-expansion "
                          "(non-2xx from XCO)")

        payload = resp.get("payload") or {}
        items = payload.get("items") or []
        device_ids = []
        for sw in items:
            sid = sw.get("id") if isinstance(sw, dict) else None
            if isinstance(sid, int):
                device_ids.append(sid)
        if not device_ids:
            return {
                "status": 200,
                "payload": {
                    "items": [], "item_count": 0,
                    "meta": {
                        "source": "xco-bulk-export",
                        "elapsed_s": round(time.time() - start, 3),
                        "fetched_at": int(time.time()),
                        "device_ids_requested": 0,
                        "note": (
                            "XCO returned an empty switch list; nothing "
                            "to export."
                        ),
                    },
                },
            }
        if len(device_ids) > max_devices:
            return _error(
                400,
                f"Auto-expanded device list has {len(device_ids)} entries, "
                f"which exceeds max_devices={max_devices}. Pass an explicit "
                f"device_ids list to scope the call.",
                device_ids_count=len(device_ids),
                max_devices=max_devices,
            )
    else:
        # Validate caller-supplied list — must be a non-empty list of ints.
        if (not isinstance(device_ids, list) or not device_ids
                or not all(isinstance(d, int) for d in device_ids)):
            return _error(400,
                          "device_ids must be a non-empty list of integers "
                          "(XCO's bulk-export endpoint requires int32 IDs).")
        if len(device_ids) > max_devices:
            return _error(
                400,
                f"device_ids has {len(device_ids)} entries, exceeds "
                f"max_devices={max_devices}.",
            )

    # --- Step 2: POST the bulk-export request ---
    try:
        resp = transport.request(
            method="POST", path=_BULK_EXPORT_PATH,
            body={"device_ids": device_ids},
            timeout=30,
        )
    except Exception as e:
        logger.warning("chassis_info_bulk: bulk-export call failed: %s",
                       str(e)[:200])
        return _error(502,
                      f"XCO bulk-export call failed: {str(e)[:200]}")

    status_code = resp.get("status", 0) if isinstance(resp, dict) else 0
    payload = resp.get("payload") if isinstance(resp, dict) else None

    if status_code >= 400:
        # Try to surface XCO's own error message
        msg = ""
        if isinstance(payload, dict):
            msg = str(payload.get("message") or payload.get("error") or "")
        elif isinstance(payload, str):
            msg = payload
        return _error(
            502,
            f"XCO returned HTTP {status_code} for bulk-export"
            + (f": {msg[:200]}" if msg else ""),
            xco_status=status_code,
            xco_body=msg[:300] if msg else None,
        )

    # XCO returns application/octet-stream for this endpoint.  The
    # framework transport wraps non-JSON responses as
    # `{"_raw": str, "_raw_bytes": bytes, "_content_type": str}` —
    # we want `_raw_bytes` because the text decoding in `_raw` mangles
    # binary data with U+FFFD replacement characters.
    raw_bytes: Optional[bytes] = None
    if isinstance(payload, (bytes, bytearray)):
        raw_bytes = bytes(payload)
    elif isinstance(payload, dict):
        v = payload.get("_raw_bytes")
        if isinstance(v, (bytes, bytearray)):
            raw_bytes = bytes(v)

    if raw_bytes is None:
        return _error(
            502,
            "XCO bulk-export response did not include binary bytes "
            "(`_raw_bytes` field). This is a transport-layer encoding "
            "issue — confirm the server is running a build that includes "
            "the _raw_bytes wrapper in mcp_runtime/transport.py.",
            payload_type=type(payload).__name__,
            payload_keys=(list(payload.keys()) if isinstance(payload, dict)
                          else None),
        )

    # --- Step 3: unwrap + parse ---
    try:
        rows = _unwrap_outer_zip_and_parse(raw_bytes)
    except Exception as e:
        logger.warning("chassis_info_bulk: parse failed: %s", str(e)[:200])
        return _error(502,
                      f"Could not parse XCO bulk-export response: "
                      f"{str(e)[:200]}",
                      response_size_bytes=len(raw_bytes))

    items = _rows_to_items(rows)
    elapsed = time.time() - start

    logger.info(
        "chassis_info_bulk: returned %d items in %.2fs (device_ids=%d)",
        len(items), elapsed, len(device_ids),
    )

    return {
        "status": 200,
        "payload": {
            "items": items,
            "item_count": len(items),
            "meta": {
                "source": "xco-bulk-export",
                "endpoint": _BULK_EXPORT_PATH,
                "elapsed_s": round(elapsed, 3),
                "fetched_at": int(time.time()),
                "device_ids_requested": len(device_ids),
                "fields_per_item": list(_EXPECTED_HEADERS.values()),
            },
        },
    }
