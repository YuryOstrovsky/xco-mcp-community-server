"""HTTP surface smoke (offline) — health, catalog, transport mount, 404 path.

None of these endpoints touch XCO, so they run without a live backend.
"""
import pytest
from fastapi.testclient import TestClient

import api.app as appmod


@pytest.fixture(scope="module")
def client():
    # Context manager runs the app lifespan (MCP transport session manager).
    with TestClient(appmod.app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_tools_and_catalog_version_header(client):
    r = client.get("/tools")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and len(body) > 100
    assert r.headers.get("X-Catalog-Version"), "X-Catalog-Version header missing"


def test_invoke_unknown_tool_is_404(client):
    r = client.post("/invoke", json={"tool": "does_not_exist_xyz", "inputs": {}})
    assert r.status_code == 404


def test_mcp_transport_is_mounted():
    paths = [getattr(r, "path", "") for r in appmod.app.routes]
    assert "/mcp" in paths, "MCP JSON-RPC transport not mounted at /mcp"
