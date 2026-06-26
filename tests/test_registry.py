"""The registry loads and its handler map is consistent with the catalog."""
from mcp_runtime.registry import MCPRegistry


def _reg():
    return MCPRegistry().load()


def test_registry_loads():
    reg = _reg()
    assert len(reg.tools) > 100


def test_handlers_reference_known_tools():
    reg = _reg()
    unknown = [n for n in reg.handlers if n not in reg.tools]
    assert not unknown, f"handlers for tools not in catalog: {unknown}"


def test_handlers_are_callable_or_tier1():
    reg = _reg()
    # Tier-1 tools map to None (generic HTTP executor); Tier-2 to a callable.
    for name, h in reg.handlers.items():
        assert h is None or callable(h), f"handler {name} is neither None nor callable"


def test_discovery_tools_registered():
    reg = _reg()
    for name in ("inventory_list_device_ids", "tenant_list_ids", "fabric_get_fabric_names"):
        assert name in reg.tools, f"{name} missing from catalog"
        assert callable(reg.handlers.get(name)), f"{name} has no callable handler"
