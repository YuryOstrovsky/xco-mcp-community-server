"""The payload normalizer adds snake_case aliases for hyphenated keys."""
from mcp_runtime.payload_normalize import normalize_result


def test_adds_snake_case_alias_at_top():
    out = normalize_result({"status": 200, "payload": {"fabric-name": "x"}})
    p = out["payload"]
    assert p.get("fabric_name") == "x"
    assert p.get("fabric-name") == "x"  # original key preserved


def test_adds_aliases_in_nested_list():
    out = normalize_result(
        {"status": 200, "payload": {"items": [{"device-id": 1, "ip-address": "1.2.3.4"}]}}
    )
    item = out["payload"]["items"][0]
    assert item.get("device_id") == 1
    assert item.get("ip_address") == "1.2.3.4"


def test_status_preserved():
    out = normalize_result({"status": 404, "payload": {"a-b": 1}})
    assert out["status"] == 404
