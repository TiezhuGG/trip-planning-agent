import asyncio

from app.config import Settings
from app.schemas.planning import POIRecommendation, ToolCallRecord
from app.services.amap_mcp_adapter import AmapMCPAdapter, MCPProtocolError


def _adapter() -> AmapMCPAdapter:
    adapter = AmapMCPAdapter(Settings(amap_mcp_command="uvx"))
    adapter.client = object()
    adapter._tool_catalog = [{"name": "maps_search_detail"}]
    return adapter


def _detail_payload(poi_id: str) -> dict:
    offset = sum(ord(ch) for ch in poi_id) % 10
    return {
        "pois": [
            {
                "id": poi_id,
                "name": f"poi-{poi_id}",
                "location": f"121.4{offset},31.2{offset}",
                "adname": "test-district",
                "type": "050100",
            }
        ]
    }


def test_detail_calls_are_limited_and_cached_between_requests() -> None:
    adapter = _adapter()
    calls: list[str] = []

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, trace, tool_name_override)
        poi_id = str(arguments["id"])
        calls.append(poi_id)
        return _detail_payload(poi_id)

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]
    pois = [POIRecommendation(name=f"A{i}", poi_id=f"id{i}") for i in range(12)]

    first = asyncio.run(adapter._enrich_pois_with_details(pois, [], category="attraction"))
    second = asyncio.run(adapter._enrich_pois_with_details(pois, [], category="attraction"))

    assert len(calls) == 4
    assert sum(1 for item in first if item.longitude is not None and item.latitude is not None) == 4
    assert sum(1 for item in second if item.longitude is not None and item.latitude is not None) == 4


def test_detail_calls_deduplicate_same_poi_id_within_single_request() -> None:
    adapter = _adapter()
    calls: list[str] = []

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, trace, tool_name_override)
        poi_id = str(arguments["id"])
        calls.append(poi_id)
        return _detail_payload(poi_id)

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]
    pois = [
        POIRecommendation(name="R1", poi_id="dup"),
        POIRecommendation(name="R2", poi_id="dup"),
        POIRecommendation(name="R3", poi_id="id3"),
    ]

    enriched = asyncio.run(adapter._enrich_pois_with_details(pois, [], category="restaurant"))

    assert calls.count("dup") == 1
    assert calls.count("id3") == 1
    assert all(item.longitude is not None and item.latitude is not None for item in enriched)


def test_restaurant_with_complete_fields_skips_detail_call() -> None:
    adapter = _adapter()
    calls = {"count": 0}

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, arguments, trace, tool_name_override)
        calls["count"] += 1
        return _detail_payload(str(arguments["id"]))

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]
    poi = POIRecommendation(
        name="Complete Restaurant",
        poi_id="full",
        district="test-district",
        tags=["050100"],
        longitude=121.47,
        latitude=31.23,
    )

    enriched = asyncio.run(adapter._enrich_pois_with_details([poi], [], category="restaurant"))

    assert calls["count"] == 0
    assert enriched[0].longitude == 121.47
    assert enriched[0].latitude == 31.23


def test_detail_calls_stop_after_rate_limit_and_keep_remaining_pois() -> None:
    adapter = _adapter()
    calls: list[str] = []

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, trace, tool_name_override)
        poi_id = str(arguments["id"])
        calls.append(poi_id)
        if poi_id == "id1":
            raise MCPProtocolError("Get poi detail failed: CUQPS_HAS_EXCEEDED_THE_LIMIT")
        return _detail_payload(poi_id)

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]
    pois = [POIRecommendation(name=f"A{i}", poi_id=f"id{i}") for i in range(6)]

    enriched = asyncio.run(adapter._enrich_pois_with_details(pois, [], category="attraction"))

    assert calls == ["id0", "id1"]
    assert enriched[0].longitude is not None
    assert enriched[1].longitude is None
    assert all(item.longitude is None for item in enriched[2:])


def test_search_poi_candidates_returns_partial_results_on_rate_limit() -> None:
    adapter = AmapMCPAdapter(Settings(amap_mcp_command="uvx"))
    adapter.client = object()
    adapter._tool_catalog = [{"name": "maps_text_search"}]
    trace: list[ToolCallRecord] = []

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, tool_name_override)
        keyword = str(arguments["keywords"])
        if keyword == "热门景点":
            raise MCPProtocolError("Text Search failed: CUQPS_HAS_EXCEEDED_THE_LIMIT")
        trace.append(
            ToolCallRecord(
                tool_name="maps_text_search",
                arguments=arguments,
                success=True,
                summary="ok",
            )
        )
        return {
            "pois": [
                {
                    "id": keyword,
                    "name": keyword,
                    "address": f"{keyword} 地址",
                }
            ]
        }

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]

    result = asyncio.run(
        adapter._search_poi_candidates(
            city="上海",
            queries=["外滩", "热门景点", "景区"],
            trace=trace,
            fallback_kind="景点",
            target_count=10,
        )
    )

    assert [item.name for item in result] == ["外滩"]


def test_search_poi_candidates_caps_query_attempts_on_empty_results() -> None:
    adapter = AmapMCPAdapter(Settings(amap_mcp_command="uvx"))
    adapter.client = object()
    adapter._tool_catalog = [{"name": "maps_text_search"}]
    trace: list[ToolCallRecord] = []
    calls = {"count": 0}

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, trace, tool_name_override)
        calls["count"] += 1
        return {"pois": []}

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]
    queries = [f"query-{idx}" for idx in range(20)]

    result = asyncio.run(
        adapter._search_poi_candidates(
            city="上海",
            queries=queries,
            trace=trace,
            fallback_kind="景点",
            target_count=10,
        )
    )

    assert result == []
    # query budget for target_count=10 is capped at 12, and empty-stop halves each pass -> 6 + 6 calls.
    assert calls["count"] == 12


def test_search_poi_candidates_adaptive_budget_reduces_attempts_on_poor_history() -> None:
    adapter = AmapMCPAdapter(
        Settings(
            amap_mcp_command="uvx",
            amap_mcp_adaptive_retry_enabled=True,
            amap_mcp_adaptive_retry_window=6,
            amap_mcp_adaptive_retry_min_samples=4,
            amap_mcp_adaptive_retry_low_success_rate=0.5,
        )
    )
    adapter.client = object()
    adapter._tool_catalog = [{"name": "maps_text_search"}]
    trace: list[ToolCallRecord] = []
    calls = {"count": 0}

    for _ in range(4):
        asyncio.run(adapter._record_adaptive_retry_result("poi_search", success=False))

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, arguments, trace, tool_name_override)
        calls["count"] += 1
        return {"pois": []}

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]
    queries = [f"query-{idx}" for idx in range(20)]

    result = asyncio.run(
        adapter._search_poi_candidates(
            city="上海",
            queries=queries,
            trace=trace,
            fallback_kind="景点",
            target_count=10,
        )
    )

    assert result == []
    assert calls["count"] == 3


def test_search_poi_candidates_adaptive_budget_keeps_base_when_history_healthy() -> None:
    adapter = AmapMCPAdapter(
        Settings(
            amap_mcp_command="uvx",
            amap_mcp_adaptive_retry_enabled=True,
            amap_mcp_adaptive_retry_window=8,
            amap_mcp_adaptive_retry_min_samples=4,
            amap_mcp_adaptive_retry_low_success_rate=0.5,
        )
    )
    adapter.client = object()
    adapter._tool_catalog = [{"name": "maps_text_search"}]
    trace: list[ToolCallRecord] = []
    calls = {"count": 0}

    for _ in range(6):
        asyncio.run(adapter._record_adaptive_retry_result("poi_search", success=True))

    async def fake_call_tool(
        purpose: str,
        arguments: dict,
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ):
        _ = (purpose, arguments, trace, tool_name_override)
        calls["count"] += 1
        return {"pois": []}

    adapter._call_tool_for_purpose = fake_call_tool  # type: ignore[method-assign]
    queries = [f"query-{idx}" for idx in range(20)]

    result = asyncio.run(
        adapter._search_poi_candidates(
            city="上海",
            queries=queries,
            trace=trace,
            fallback_kind="景点",
            target_count=10,
        )
    )

    assert result == []
    # Healthy history keeps default budget behavior: 12 attempts (6 for citylimit=true + 6 for false).
    assert calls["count"] == 12
