# Copyright 2025 Extreme Networks, Inc.
# SPDX-License-Identifier: Apache-2.0
# mcp_runtime/payload_normalize.py
"""
Global response-payload normaliser (Nova contract, 02-nova-target-spec §3.1/§5).

Applied at the HTTP response boundary (the `/invoke` route and the MCP
`tools/call` result) so the data a *client* consumes is snake_case-clean —
without touching the payloads internal callers (plan executor, composites) see
from `mcp.invoke()`.

Three rules, all additive / non-breaking:

  1. **snake_case aliases.** For every dict key that is hyphenated or camelCase,
     ADD a snake_case sibling with the same value (the original is KEPT, so the
     legacy demo client is unaffected).  `fabric-name` → also `fabric_name`;
     `switchId` → also `switch_id`.
  2. **No null identifiers.** A key that denotes an id (`*_id` / `*-id` / `id` /
     `*_uuid`) whose value is exactly `null` is dropped — "either populate it or
     omit it, never null for an identifier" (Brendan, Q2).
  3. **`raw` is the escape hatch.** Anything under a key named `raw` is left
     verbatim (it is the unchanged XCO passthrough by contract, §5).

Tuple-record fields (`top_resources: [[s,n]…]`) are intentionally NOT rewritten
here — the alarms tool already ships an object-form companion
(`top_resources_objects`), and a blind list-of-pairs heuristic would risk
mangling legitimate data.

Gate: `MCP_NORMALIZE_PAYLOADS` (default on); set false to return raw payloads.
"""
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
#   inputs / body /     — REQUEST bodies, esp. plan-builder step bodies, which
#   rollback / arguments  round-trip straight back to XCO. XCO does strict field
#                         validation, so an added snake_case alias (e.g.
#                         `int_type` beside XCO's `int-type`) makes it reject the
#                         whole call with HTTP 400 "unknown field". These must
#                         keep XCO's exact (hyphenated) field names.
_OPAQUE_KEYS = {"raw", "inputs", "body", "rollback", "arguments"}


def to_snake(key: str) -> str:
    """'fabric-name' / 'switchId' / 'TopResources' → snake_case."""
    s = key.replace("-", "_")
    s = _CAMEL_RE.sub(r"_\1", s).lower()
    return re.sub(r"__+", "_", s)


def _is_null_id(key: str, val: Any) -> bool:
    return val is None and isinstance(key, str) and bool(_ID_KEY_RE.search(key))


def _norm(obj: Any, opaque: bool) -> Any:
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


# ---------------------------------------------------------------------------
# Inverse of rule 1, applied to XCO-bound REQUEST bodies (defence in depth).
#
# The boundary normaliser ADDS a snake_case sibling to every hyphenated/camel
# read key (e.g. `int-type` → also `int_type`).  That is correct for data a
# client *displays*.  But XCO config objects (tenants, endpoint-groups, …) are
# simultaneously read OUTPUT and valid write INPUT, and XCO does strict field
# validation — it rejects the extra alias with HTTP 400 code 1728
# ("unknown field 'int_type'").  So if a client (or a plan persisted by a
# pre-fix write path) round-trips a normalised object straight back into a
# write tool, the call 400s.
#
# `heal_redundant_snake_aliases` is the single choke-point cure: applied to the
# body of every XCO request in `transport.request`, it drops a snake_case key
# *only* when a distinct sibling maps to the same snake form (i.e. it is one of
# our added aliases), keeping XCO's native (hyphenated/camel) key.  It NEVER
# touches a lone snake_case field — that may be a legitimate XCO field, not our
# alias.  Pure + identity-stable: a body with no doubled keys is returned
# unchanged (same object), so the normal write path is byte-for-byte unaffected.
# Deliberately NOT gated on NORMALIZE_ENABLED — a doubled body baked into a
# stored plan must heal even if the live normaliser is later switched off.
# ---------------------------------------------------------------------------
def _redundant_snake_keys(d: dict) -> set:
    """Snake_case keys in ``d`` that are a redundant alias of a differently
    spelled sibling (hyphenated/camel) mapping to the same snake form."""
    groups: dict = {}
    for k in d:
        if isinstance(k, str):
            groups.setdefault(to_snake(k), []).append(k)
    drop = set()
    for snake, origs in groups.items():
        # the literal snake key is present AND a non-snake sibling produced it
        if snake in d and any(o != snake for o in origs):
            drop.add(snake)
    return drop


def _heal(obj: Any) -> Any:
    if isinstance(obj, dict):
        drop = _redundant_snake_keys(obj)
        changed = bool(drop)
        out = {}
        for k, v in obj.items():
            if k in drop:
                continue
            hv = _heal(v)
            if hv is not v:
                changed = True
            out[k] = hv
        return out if changed else obj
    if isinstance(obj, list):
        new = [_heal(x) for x in obj]
        if len(new) == len(obj) and all(n is o for n, o in zip(new, obj)):
            return obj
        return new
    return obj


def heal_redundant_snake_aliases(obj: Any) -> Any:
    """Drop normaliser-added snake_case alias keys from an XCO-bound request
    body so a round-tripped (read→write) object is accepted by XCO's strict
    field validation.  Pure + identity-stable (same object when nothing to
    heal)."""
    return _heal(obj)
