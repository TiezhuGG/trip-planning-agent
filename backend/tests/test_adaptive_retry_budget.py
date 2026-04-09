import asyncio

import pytest

from app.config import Settings
from app.schemas.planning import POIRecommendation, ToolCallRecord
from app.services.amap_mcp_adapter import AmapMCPAdapter, MCPProtocolError


def _build_adapter() -> AmapMCPAdapter:
    settings = Settings(
        amap_mcp_command="uvx",
        amap_mcp_adaptive_retry_enabled=True,
        amap_mcp_adaptive_retry_window=6,
        amap_mcp_adaptive_retry_min_samples=4,
        amap_mcp_adaptive_retry_low_success_rate=0.5,
    )
    return AmapMCPAdapter(settings)


def test_route_tool_retry_budget_reduces_on_low_success_rate() -> None:
    adapter = _build_adapter()
    trace: list[ToolCallRecord] = []
    calls = {"count": 0}

    for _ in range(4):
        asyncio.run(adapter._record_adaptive_retry_result("route_tool", success=False))

    async def fake_call_tool_for_purpose(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, arguments, trace, tool_name_override)
        calls["count"] += 1
        raise MCPProtocolError("CUQPS_HAS_EXCEEDED_THE_LIMIT")

    adapter._call_tool_for_purpose = fake_call_tool_for_purpose  # type: ignore[method-assign]

    with pytest.raises(MCPProtocolError):
        asyncio.run(
            adapter._call_route_tool_with_retry(
                tool_name="maps_direction_driving_by_address",
                arguments={"origin_address": "A", "destination_address": "B"},
                trace=trace,
            )
        )

    assert calls["count"] == 1


def test_route_tool_retry_budget_keeps_base_on_healthy_history() -> None:
    adapter = _build_adapter()
    trace: list[ToolCallRecord] = []
    calls = {"count": 0}

    for _ in range(5):
        asyncio.run(adapter._record_adaptive_retry_result("route_tool", success=True))
    asyncio.run(adapter._record_adaptive_retry_result("route_tool", success=False))

    async def fake_call_tool_for_purpose(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, arguments, trace, tool_name_override)
        calls["count"] += 1
        if calls["count"] <= 2:
            raise MCPProtocolError("QPS_HAS_EXCEEDED_THE_LIMIT")
        return {"route": {"paths": []}}

    adapter._call_tool_for_purpose = fake_call_tool_for_purpose  # type: ignore[method-assign]

    result = asyncio.run(
        adapter._call_route_tool_with_retry(
            tool_name="maps_direction_driving_by_address",
            arguments={"origin_address": "A", "destination_address": "B"},
            trace=trace,
        )
    )

    assert isinstance(result, dict)
    assert calls["count"] == 3


def test_route_webservice_retry_budget_reduces_on_low_success_rate() -> None:
    adapter = _build_adapter()
    trace: list[ToolCallRecord] = []
    calls = {"count": 0}

    for _ in range(4):
        asyncio.run(adapter._record_adaptive_retry_result("route_webservice::driving", success=False))

    async def fake_plan_route_via_web_service(
        mode: str,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> dict:
        _ = (mode, origin, destination, waypoints, trace)
        calls["count"] += 1
        raise MCPProtocolError("OVER_QUERY_LIMIT")

    adapter._plan_route_via_web_service = fake_plan_route_via_web_service  # type: ignore[method-assign]
    origin = POIRecommendation(name="A")
    destination = POIRecommendation(name="B")

    with pytest.raises(MCPProtocolError):
        asyncio.run(
            adapter._call_route_webservice_with_retry(
                mode="driving",
                origin=origin,
                destination=destination,
                waypoints=[],
                trace=trace,
            )
        )

    assert calls["count"] == 1


def test_suggest_route_parallelism_reduces_when_route_health_is_poor() -> None:
    adapter = _build_adapter()

    for _ in range(4):
        asyncio.run(adapter._record_adaptive_retry_result("route_tool", success=False))

    day, segment, warning = asyncio.run(
        adapter.suggest_route_parallelism(day_concurrency=3, segment_concurrency=4)
    )

    assert day == 1
    assert segment == 2
    assert isinstance(warning, str) and "并发已自适应下调" in warning


def test_suggest_route_parallelism_keeps_base_when_route_health_is_good() -> None:
    adapter = _build_adapter()
    for _ in range(5):
        asyncio.run(adapter._record_adaptive_retry_result("route_tool", success=True))
    asyncio.run(adapter._record_adaptive_retry_result("route_tool", success=False))

    day, segment, warning = asyncio.run(
        adapter.suggest_route_parallelism(day_concurrency=3, segment_concurrency=4)
    )

    assert day == 3
    assert segment == 4
    assert warning is None
