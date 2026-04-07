import asyncio

from app.config import Settings
from app.schemas.planning import POIRecommendation, ToolCallRecord
from app.services.amap_mcp_adapter import AmapMCPAdapter


def _adapter() -> AmapMCPAdapter:
    adapter = AmapMCPAdapter(Settings(amap_mcp_command="uvx"))
    adapter.client = object()
    adapter._tool_catalog = [{"name": "maps_text_search"}, {"name": "maps_search_detail"}]
    return adapter


def test_resolve_location_candidate_reuses_cache_for_same_query() -> None:
    adapter = _adapter()
    calls = {"search": 0}
    trace: list[ToolCallRecord] = []

    async def fake_search_poi_candidates(
        city: str,
        queries: list[str],
        trace: list[ToolCallRecord],
        fallback_kind: str,
        target_count: int,
    ) -> list[POIRecommendation]:
        _ = (city, queries, trace, fallback_kind, target_count)
        calls["search"] += 1
        return [
            POIRecommendation(
                name="清源山",
                district="泉州市",
                tags=["110201"],
                longitude=118.67,
                latitude=24.93,
            )
        ]

    adapter._search_poi_candidates = fake_search_poi_candidates  # type: ignore[method-assign]

    first = asyncio.run(
        adapter.resolve_location_candidate(
            city="泉州",
            location_name="清源山",
            trace=trace,
            anchor_pois=[],
        )
    )
    second = asyncio.run(
        adapter.resolve_location_candidate(
            city="泉州",
            location_name="清源山",
            trace=trace,
            anchor_pois=[],
        )
    )

    assert calls["search"] == 1
    assert first is not None
    assert second is not None
    assert first.name == "清源山"
    assert second.name == "清源山"


def test_resolve_location_candidate_enriches_top_two_candidates_only() -> None:
    adapter = _adapter()
    trace: list[ToolCallRecord] = []
    calls = {"enrich_count": 0}

    async def fake_search_poi_candidates(
        city: str,
        queries: list[str],
        trace: list[ToolCallRecord],
        fallback_kind: str,
        target_count: int,
    ) -> list[POIRecommendation]:
        _ = (city, queries, trace, fallback_kind, target_count)
        return [
            POIRecommendation(name="清源山景区", district="泉州市"),
            POIRecommendation(name="清源山君岩", district="泉州市"),
            POIRecommendation(name="清源山风景名胜区", district="泉州市"),
            POIRecommendation(name="清源山游客中心", district="泉州市"),
        ]

    async def fake_enrich_pois_with_details(
        pois: list[POIRecommendation],
        trace: list[ToolCallRecord],
        category: str | None = None,
    ) -> list[POIRecommendation]:
        _ = (trace, category)
        calls["enrich_count"] = len(pois)
        return [
            poi.model_copy(update={"longitude": 118.67, "latitude": 24.93, "tags": ["110201"]})
            for poi in pois
        ]

    adapter._search_poi_candidates = fake_search_poi_candidates  # type: ignore[method-assign]
    adapter._enrich_pois_with_details = fake_enrich_pois_with_details  # type: ignore[method-assign]

    resolved = asyncio.run(
        adapter.resolve_location_candidate(
            city="泉州",
            location_name="清源山",
            trace=trace,
            anchor_pois=[],
        )
    )

    assert calls["enrich_count"] == 2
    assert resolved is not None
    assert resolved.longitude is not None
    assert resolved.latitude is not None


def test_resolve_location_candidate_reuses_simple_cache_across_anchor_variants() -> None:
    adapter = _adapter()
    calls = {"search": 0}
    trace: list[ToolCallRecord] = []

    async def fake_search_poi_candidates(
        city: str,
        queries: list[str],
        trace: list[ToolCallRecord],
        fallback_kind: str,
        target_count: int,
    ) -> list[POIRecommendation]:
        _ = (city, queries, trace, fallback_kind, target_count)
        calls["search"] += 1
        return [
            POIRecommendation(
                name="清源山",
                district="泉州市",
                tags=["110201"],
                longitude=118.67,
                latitude=24.93,
            )
        ]

    adapter._search_poi_candidates = fake_search_poi_candidates  # type: ignore[method-assign]

    first = asyncio.run(
        adapter.resolve_location_candidate(
            city="泉州",
            location_name="清源山",
            trace=trace,
            anchor_pois=[],
        )
    )
    second = asyncio.run(
        adapter.resolve_location_candidate(
            city="泉州",
            location_name="清源山",
            trace=trace,
            anchor_pois=[
                POIRecommendation(
                    name="西街",
                    district="泉州市",
                    longitude=118.68,
                    latitude=24.92,
                )
            ],
        )
    )

    assert calls["search"] == 1
    assert first is not None
    assert second is not None
    assert second.name == "清源山"


def test_resolve_location_candidate_skips_simple_cache_when_anchor_out_of_scope() -> None:
    adapter = _adapter()
    calls = {"search": 0}
    trace: list[ToolCallRecord] = []

    async def fake_search_poi_candidates(
        city: str,
        queries: list[str],
        trace: list[ToolCallRecord],
        fallback_kind: str,
        target_count: int,
    ) -> list[POIRecommendation]:
        _ = (city, queries, trace, fallback_kind, target_count)
        calls["search"] += 1
        return [
            POIRecommendation(
                name="测试点位",
                district="泉州市",
                tags=["110201"],
                longitude=100.0,
                latitude=10.0,
            )
        ]

    adapter._search_poi_candidates = fake_search_poi_candidates  # type: ignore[method-assign]

    first = asyncio.run(
        adapter.resolve_location_candidate(
            city="泉州",
            location_name="测试点位",
            trace=trace,
            anchor_pois=[],
        )
    )
    second = asyncio.run(
        adapter.resolve_location_candidate(
            city="泉州",
            location_name="测试点位",
            trace=trace,
            anchor_pois=[
                POIRecommendation(
                    name="西街",
                    district="泉州市",
                    longitude=118.67,
                    latitude=24.92,
                )
            ],
        )
    )

    assert calls["search"] == 2
    assert first is not None
    assert second is not None
    assert second.name == "测试点位"
