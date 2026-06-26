"""compute_catalog_version is a stable, order-independent 16-hex fingerprint."""
import re

from mcp_runtime.catalog_version import compute_catalog_version

SAMPLE = [
    {"name": "b_tool", "input_schema": {"type": "object"},
     "policy": {"risk": "SAFE_READ"}},
    {"name": "a_tool",
     "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}},
     "policy": {"risk": "SAFE_READ"}},
]


def test_format_is_16_hex():
    assert re.fullmatch(r"[0-9a-f]{16}", compute_catalog_version(SAMPLE))


def test_deterministic():
    assert compute_catalog_version(SAMPLE) == compute_catalog_version(SAMPLE)


def test_order_independent():
    assert compute_catalog_version(SAMPLE) == compute_catalog_version(list(reversed(SAMPLE)))


def test_changes_when_schema_changes():
    before = compute_catalog_version(SAMPLE)
    mutated = [
        dict(SAMPLE[0]),
        {**SAMPLE[1], "input_schema": {"type": "object",
                                       "properties": {"y": {"type": "string"}}}},
    ]
    assert compute_catalog_version(mutated) != before


def test_empty_catalog_is_stable():
    assert re.fullmatch(r"[0-9a-f]{16}", compute_catalog_version([]))
