"""Validate the served tool catalog (generated/mcp_tools.json)."""

import json
from pathlib import Path

RAW = Path("generated/mcp_tools.json").read_text()
CATALOG = json.loads(RAW)

VALID_RISKS = {"SAFE_READ"}  # community edition is read-only


def test_catalog_is_nonempty_list():
    assert isinstance(CATALOG, list)
    assert len(CATALOG) > 100


def test_no_duplicate_tool_names():
    names = [t["name"] for t in CATALOG]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplicate tool names: {dupes}"


def test_required_fields_present():
    for t in CATALOG:
        assert t.get("name"), f"entry missing name: {t}"
        assert isinstance(t.get("input_schema"), dict), t["name"]
        assert isinstance(t.get("policy"), dict), t["name"]
        assert t["policy"].get("risk"), t["name"]


def test_input_schema_shape():
    for t in CATALOG:
        s = t["input_schema"]
        assert s.get("type") == "object", t["name"]
        assert isinstance(s.get("properties", {}), dict), t["name"]
        assert isinstance(s.get("required", []), list), t["name"]


def test_read_only_invariant():
    """The community edition must stay read-only: every tool is SAFE_READ."""
    bad = [t["name"] for t in CATALOG if (t.get("policy") or {}).get("risk") not in VALID_RISKS]
    assert not bad, f"non-SAFE_READ tools in a read-only edition: {bad}"


def test_catalog_is_ascii():
    """Catalog is normalized to ensure_ascii=True (clean, portable diffs)."""
    assert RAW.isascii(), "generated/mcp_tools.json must be ASCII-only"
