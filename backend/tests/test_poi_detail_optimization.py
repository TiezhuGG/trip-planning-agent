import asyncio

from app.config import Settings
from app.schemas.planning import POIRecommendation, ToolCallRecord
from app.services.amap_mcp_adapter import AmapMCPAdapter


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

    assert len(calls) == 8
    assert sum(1 for item in first if item.longitude is not None and item.latitude is not None) == 8
    assert sum(1 for item in second if item.longitude is not None and item.latitude is not None) == 8


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
