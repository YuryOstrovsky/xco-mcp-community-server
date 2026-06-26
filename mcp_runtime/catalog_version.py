"""Standalone catalog-version hash.

Kept free of any SDK / transport import so `api.app` can advertise a
stable catalog fingerprint via the `X-Catalog-Version` header without
pulling in the MCP transport just for a hash.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


def compute_catalog_version(catalog: List[Dict[str, Any]]) -> str:
    """Stable short hash over tool names + input schemas + risk, so a client
    can short-circuit re-discovery when the catalog is unchanged.

    16 hex chars of sha256 over, for each tool (sorted by name):
        name | json(input_schema, sort_keys) | policy.risk
    """
    h = hashlib.sha256()
    for e in sorted(catalog, key=lambda x: x.get("name", "")):
        h.update((
            e.get("name", "")
            + "|" + json.dumps(e.get("input_schema", {}), sort_keys=True)
            + "|" + str((e.get("policy") or {}).get("risk", ""))
        ).encode("utf-8"))
    return h.hexdigest()[:16]
