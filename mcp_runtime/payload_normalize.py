# mcp_runtime/payload_normalize.py
"""
Global response-payload normaliser.

Applied at the HTTP response boundary (the `/invoke` route and the MCP
`tools/call` result) so the data a *client* consumes is snake_case-clean —
without touching the payloads internal callers (composites) see from
`mcp.invoke()`.

Three rules, all additive / non-breaking:

  1. **snake_case aliases.** For every dict key that is hyphenated or camelCase,
     ADD a snake_case sibling with the same value (the original is KEPT, so
     existing clients are unaffected).  `fabric-name` → also `fabric_name`;
     `switchId` → also `switch_id`.
  2. **No null identifiers.** A key that denotes an id (`*_id` / `*-id` / `id` /
     `*_uuid`) whose value is exactly `null` is dropped — either populate it or
     omit it, never null for an identifier.
  3. **`raw` is the escape hatch.** Anything under a key named `raw` is left
     verbatim (it is the unchanged XCO passthrough).

Tuple-record fields (`top_resources: [[s,n]…]`) are intentionally NOT rewritten
here — the alarms tool already ships an object-form companion
(`top_resources_objects`), and a blind list-of-pairs heuristic would risk
mangling legitimate data.

Gate: `MCP_NORMALIZE_PAYLOADS` (default on); set false to return raw payloads.
"""
import base64
import os
import re
from typing import Any

NORMALIZE_ENABLED = os.environ.get("MCP_NORMALIZE_PAYLOADS", "true").lower() \
    not in ("0", "false", "no", "off")

# camelCase boundary: a lowercase/digit followed by an uppercase letter.
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])([A-Z])")
# identifier key: ends in id/uuid, preceded by start-of-string, '_' or '-'
# (so "grid"/"valid"/"pid" are NOT treated as identifiers).
_ID_KEY_RE = re.compile(r"(?:^|[_-])(?:id|uuid)$", re.IGNORECASE)
# Subtrees left VERBATIM (no aliasing, no null-id drop):
#   raw                 — the documented XCO escape hatch
#   inputs / body /     — request-shaped bodies that may round-trip back to XCO.
#   rollback / arguments  XCO does strict field validation, so an added
#                         snake_case alias (e.g. `int_type` beside XCO's
#                         `int-type`) would make it reject the call with HTTP 400
#                         "unknown field". These keep XCO's exact (hyphenated)
#                         field names.
_OPAQUE_KEYS = {"raw", "inputs", "body", "rollback", "arguments"}


def to_snake(key: str) -> str:
    """'fabric-name' / 'switchId' / 'TopResources' → snake_case."""
    s = key.replace("-", "_")
    s = _CAMEL_RE.sub(r"_\1", s).lower()
    return re.sub(r"__+", "_", s)


def _is_null_id(key: str, val: Any) -> bool:
    return val is None and isinstance(key, str) and bool(_ID_KEY_RE.search(key))


def _norm(obj: Any, opaque: bool) -> Any:
    if isinstance(obj, (bytes, bytearray)):
        # Binary payloads (e.g. XLSX/ZIP exports) are not JSON-serializable and
        # would crash the HTTP encoder (UnicodeDecodeError); expose as base64.
        return base64.b64encode(bytes(obj)).decode("ascii")
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            child_opaque = opaque or (isinstance(k, str) and k in _OPAQUE_KEYS)
            out[k] = v if child_opaque else _norm(v, False)
        if opaque:
            return out
        # 1. additive snake_case aliases (never clobber an existing key)
        for k in list(out.keys()):
            if isinstance(k, str):
                sk = to_snake(k)
                if sk != k and sk not in out:
                    out[sk] = out[k]
        # 2. drop null identifier keys (original + any alias just added)
        for k in list(out.keys()):
            if _is_null_id(k, out.get(k)):
                del out[k]
        return out
    if isinstance(obj, list):
        return [_norm(x, opaque) for x in obj]
    return obj


def normalize_payload(obj: Any) -> Any:
    """Return a snake_case-aliased, null-id-pruned copy of ``obj`` (or ``obj``
    unchanged when disabled). Pure — does not mutate the input."""
    if not NORMALIZE_ENABLED:
        return obj
    return _norm(obj, opaque=False)


def normalize_result(result: Any) -> Any:
    """Normalise the ``payload`` field of an `mcp.invoke()` result envelope at
    the HTTP boundary, returning a shallow copy (never mutates the input, so
    internal callers of `mcp.invoke()` are unaffected)."""
    if (NORMALIZE_ENABLED and isinstance(result, dict)
            and isinstance(result.get("payload"), (dict, list))):
        return {**result, "payload": normalize_payload(result["payload"])}
    return result
