"""Integration-style tests for composite tools with a MOCKED XCO backend.

These exercise the real handler code (parsing, snake_case shaping, tier-1 error
surfacing) without any network by faking the registry + transport.
"""

from tools.discovery.list_ids import inventory_list_device_ids, tenant_list_ids
from tools.fabric.list_names import fabric_get_fabric_names


class FakeTransport:
    """Stands in for XCOTransport — records calls, returns a canned response."""

    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status
        self.calls = []

    def request(self, method, path, params=None, port=None, context=None, **kwargs):
        self.calls.append((method, path))
        return {"status": self._status, "payload": self._payload}


class FakeRegistry:
    def __init__(self, defs):
        self._defs = defs

    def get(self, name):
        return self._defs.get(name)


def test_fabric_get_fabric_names_parses_mocked_xco():
    reg = FakeRegistry(
        {"fabric_get_fabrics": {"method": "GET", "endpoint": {"path": "/v1/fabrics"}}}
    )
    tx = FakeTransport(
        {"items": [{"fabric-name": "default", "fabric-id": 1, "fabric-type": "clos"}]}
    )

    out = fabric_get_fabric_names(inputs={}, registry=reg, transport=tx, context={})

    assert out["status"] == 200
    p = out["payload"]
    assert p["fabric_names"] == ["default"]
    assert p["fabrics"][0] == {"fabric_name": "default", "fabric_id": 1, "fabric_type": "clos"}
    assert p["count"] == 1
    assert tx.calls == [("GET", "/v1/fabrics")]


def test_inventory_list_device_ids_parses_mocked_xco():
    reg = FakeRegistry(
        {"inventory_getswitches": {"method": "GET", "endpoint": {"path": "/v1/inventory/switches"}}}
    )
    tx = FakeTransport(
        {"items": [{"device-id": 15, "ip-address": "10.0.0.1", "host-name": "leaf1"}]}
    )

    out = inventory_list_device_ids(inputs={}, registry=reg, transport=tx, context={})

    assert out["status"] == 200
    assert out["payload"]["device_ids"] == [15]
    assert out["payload"]["devices"][0] == {"device_id": 15, "ip": "10.0.0.1", "hostname": "leaf1"}


def test_tenant_list_ids_parses_mocked_xco():
    reg = FakeRegistry(
        {"tenant_get_tenants": {"method": "GET", "endpoint": {"path": "/v1/tenants"}}}
    )
    tx = FakeTransport({"items": [{"tenant-id": 3, "name": "DC-East"}]})

    out = tenant_list_ids(inputs={}, registry=reg, transport=tx, context={})

    assert out["status"] == 200
    assert out["payload"]["tenants"][0] == {"tenant_id": 3, "tenant_name": "DC-East"}


def test_discovery_surfaces_tier1_failure():
    reg = FakeRegistry(
        {"fabric_get_fabrics": {"method": "GET", "endpoint": {"path": "/v1/fabrics"}}}
    )
    tx = FakeTransport({"items": []}, status=502)

    out = fabric_get_fabric_names(inputs={}, registry=reg, transport=tx, context={})

    assert out["status"] == 502
    assert "warning" in out["payload"]
