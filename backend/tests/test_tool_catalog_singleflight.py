import asyncio
from typing import Any

from app.config import Settings
from app.services.amap_mcp_adapter import AmapMCPAdapter


class _CatalogClient:
    def __init__(self) -> None:
        self.list_calls = 0

    async def list_tools(self) -> dict[str, Any]:
        self.list_calls += 1
        await asyncio.sleep(0.03)
        return {
            "tools": [
                {"name": "maps_text_search"},
                {"name": "maps_direction_driving_by_address"},
                {"name": "maps_weather"},
            ]
        }


def test_tool_catalog_load_is_singleflight() -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_tool_catalog_cache_seconds=60,
    )
    adapter = AmapMCPAdapter(settings)
    client = _CatalogClient()
    adapter.client = client

    async def _run() -> None:
        await asyncio.gather(*[adapter._ensure_tool_catalog(force_refresh=False) for _ in range(8)])

    asyncio.run(_run())
    assert client.list_calls == 1


def test_tool_catalog_force_refresh_still_refreshes() -> None:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_tool_catalog_cache_seconds=60,
    )
    adapter = AmapMCPAdapter(settings)
    client = _CatalogClient()
    adapter.client = client

    async def _run() -> None:
        await adapter._ensure_tool_catalog(force_refresh=False)
        await adapter._ensure_tool_catalog(force_refresh=True)

    asyncio.run(_run())
    assert client.list_calls == 2
