import asyncio
import time
from typing import Any

import pytest

from app.config import Settings
from app.schemas.planning import ToolCallRecord
from app.services.amap_mcp_adapter import AmapMCPAdapter, MCPProtocolError


class _FailingClient:
    def __init__(self) -> None:
        self.calls = 0

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        _ = (tool_name, arguments)
        self.calls += 1
        raise MCPProtocolError("upstream unavailable")


class _SequenceClient:
    def __init__(self) -> None:
        self.calls = 0

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        _ = (tool_name, arguments)
        self.calls += 1
        if self.calls <= 2:
            raise MCPProtocolError("timeout")
        return {"pois": [{"name": "ok"}]}


class _SlowClient:
    def __init__(self, sleep_seconds: float) -> None:
        self.calls = 0
        self.sleep_seconds = sleep_seconds

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        _ = (tool_name, arguments)
        self.calls += 1
        await asyncio.sleep(self.sleep_seconds)
        return {"pois": [{"name": "slow-ok"}]}


def _build_adapter() -> AmapMCPAdapter:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_circuit_enabled=True,
        amap_mcp_circuit_failure_threshold=2,
        amap_mcp_circuit_open_seconds=0.05,
        amap_mcp_circuit_slow_call_seconds=0.02,
        amap_mcp_circuit_slow_call_threshold=2,
    )
    adapter = AmapMCPAdapter(settings)
    adapter._tool_catalog = [{"name": "maps_text_search"}]
    adapter._tool_catalog_cached_at = time.monotonic()
    return adapter


def test_tool_circuit_opens_after_consecutive_failures() -> None:
    adapter = _build_adapter()
    client = _FailingClient()
    adapter.client = client
    trace: list[ToolCallRecord] = []

    with pytest.raises(MCPProtocolError):
        asyncio.run(adapter._call_tool_for_purpose("poi_search", {"city": "北京", "keywords": "景点"}, trace))
    with pytest.raises(MCPProtocolError):
        asyncio.run(adapter._call_tool_for_purpose("poi_search", {"city": "北京", "keywords": "景点"}, trace))

    assert client.calls == 2
    with pytest.raises(MCPProtocolError) as exc_info:
        asyncio.run(adapter._call_tool_for_purpose("poi_search", {"city": "北京", "keywords": "景点"}, trace))
    assert "熔断中" in str(exc_info.value)
    assert client.calls == 2


def test_tool_circuit_half_open_recovers_after_open_window() -> None:
    adapter = _build_adapter()
    client = _SequenceClient()
    adapter.client = client
    trace: list[ToolCallRecord] = []

    with pytest.raises(MCPProtocolError):
        asyncio.run(adapter._call_tool_for_purpose("poi_search", {"city": "上海", "keywords": "美食"}, trace))
    with pytest.raises(MCPProtocolError):
        asyncio.run(adapter._call_tool_for_purpose("poi_search", {"city": "上海", "keywords": "美食"}, trace))

    with pytest.raises(MCPProtocolError):
        asyncio.run(adapter._call_tool_for_purpose("poi_search", {"city": "上海", "keywords": "美食"}, trace))
    assert client.calls == 2

    time.sleep(0.07)
    first_recovery = asyncio.run(
        adapter._call_tool_for_purpose("poi_search", {"city": "上海", "keywords": "美食"}, trace)
    )
    second_recovery = asyncio.run(
        adapter._call_tool_for_purpose("poi_search", {"city": "上海", "keywords": "美食"}, trace)
    )

    assert client.calls == 4
    assert isinstance(first_recovery, dict)
    assert isinstance(second_recovery, dict)


def test_tool_circuit_opens_on_consecutive_slow_calls() -> None:
    adapter = _build_adapter()
    client = _SlowClient(sleep_seconds=0.03)
    adapter.client = client
    trace: list[ToolCallRecord] = []

    first = asyncio.run(
        adapter._call_tool_for_purpose("poi_search", {"city": "杭州", "keywords": "餐厅"}, trace)
    )
    second = asyncio.run(
        adapter._call_tool_for_purpose("poi_search", {"city": "杭州", "keywords": "餐厅"}, trace)
    )

    assert isinstance(first, dict)
    assert isinstance(second, dict)
    assert client.calls == 2

    with pytest.raises(MCPProtocolError) as exc_info:
        asyncio.run(
            adapter._call_tool_for_purpose("poi_search", {"city": "杭州", "keywords": "餐厅"}, trace)
        )
    assert "熔断中" in str(exc_info.value)
    assert client.calls == 2
