import asyncio
import time

from app.config import Settings
from app.services.amap_mcp_adapter import AmapMCPAdapter


def _tool_catalog() -> list[dict[str, str]]:
    return [
        {"name": "maps_text_search"},
        {"name": "maps_direction_driving_by_address"},
        {"name": "maps_weather"},
    ]


def test_diagnose_cache_hits_when_not_force_refresh() -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_diagnose_cache_seconds=60,
    )
    adapter = AmapMCPAdapter(settings)
    calls = 0

    async def fake_ensure_tool_catalog(force_refresh: bool = False):
        nonlocal calls
        _ = force_refresh
        calls += 1
        catalog = _tool_catalog()
        adapter._tool_catalog = catalog
        return catalog

    async def fake_circuit_warnings() -> list[str]:
        return []

    adapter._ensure_tool_catalog = fake_ensure_tool_catalog  # type: ignore[method-assign]
    adapter._tool_circuit_warning_messages = fake_circuit_warnings  # type: ignore[method-assign]

    first = asyncio.run(adapter.diagnose(force_refresh=False))
    second = asyncio.run(adapter.diagnose(force_refresh=False))

    assert calls == 1
    assert first.mcp_connected is True
    assert second.mcp_connected is True
    assert first.resolved_tools.get("poi_search") == "maps_text_search"


def test_diagnose_force_refresh_bypasses_cache() -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_diagnose_cache_seconds=60,
    )
    adapter = AmapMCPAdapter(settings)
    calls = 0

    async def fake_ensure_tool_catalog(force_refresh: bool = False):
        nonlocal calls
        _ = force_refresh
        calls += 1
        catalog = _tool_catalog()
        adapter._tool_catalog = catalog
        return catalog

    async def fake_circuit_warnings() -> list[str]:
        return []

    adapter._ensure_tool_catalog = fake_ensure_tool_catalog  # type: ignore[method-assign]
    adapter._tool_circuit_warning_messages = fake_circuit_warnings  # type: ignore[method-assign]

    asyncio.run(adapter.diagnose(force_refresh=False))
    asyncio.run(adapter.diagnose(force_refresh=True))

    assert calls == 2


def test_diagnose_cache_expires_by_ttl() -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_diagnose_cache_seconds=0.02,
    )
    adapter = AmapMCPAdapter(settings)
    calls = 0

    async def fake_ensure_tool_catalog(force_refresh: bool = False):
        nonlocal calls
        _ = force_refresh
        calls += 1
        catalog = _tool_catalog()
        adapter._tool_catalog = catalog
        return catalog

    async def fake_circuit_warnings() -> list[str]:
        return []

    adapter._ensure_tool_catalog = fake_ensure_tool_catalog  # type: ignore[method-assign]
    adapter._tool_circuit_warning_messages = fake_circuit_warnings  # type: ignore[method-assign]

    asyncio.run(adapter.diagnose(force_refresh=False))
    time.sleep(0.04)
    asyncio.run(adapter.diagnose(force_refresh=False))

    assert calls == 2


def test_diagnose_cache_disabled_when_ttl_zero() -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_diagnose_cache_seconds=0,
    )
    adapter = AmapMCPAdapter(settings)
    calls = 0

    async def fake_ensure_tool_catalog(force_refresh: bool = False):
        nonlocal calls
        _ = force_refresh
        calls += 1
        catalog = _tool_catalog()
        adapter._tool_catalog = catalog
        return catalog

    async def fake_circuit_warnings() -> list[str]:
        return []

    adapter._ensure_tool_catalog = fake_ensure_tool_catalog  # type: ignore[method-assign]
    adapter._tool_circuit_warning_messages = fake_circuit_warnings  # type: ignore[method-assign]

    asyncio.run(adapter.diagnose(force_refresh=False))
    asyncio.run(adapter.diagnose(force_refresh=False))

    assert calls == 2
