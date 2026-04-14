from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.planning import POIRecommendation, ToolCallRecord

ResolveSearchDetailToolName = Callable[[], str | None]
CallToolForPurpose = Callable[[str, dict[str, Any], list[ToolCallRecord], str | None], Awaitable[Any]]
NormalizePoiDetail = Callable[[Any, POIRecommendation], POIRecommendation]
PoiDetailIsComplete = Callable[[POIRecommendation, str | None], bool]
IsRateLimitError = Callable[[Exception], bool]


async def enrich_pois_with_details(
    *,
    pois: list[POIRecommendation],
    trace: list[ToolCallRecord],
    category: str | None,
    has_client: bool,
    poi_detail_limit: int,
    poi_detail_concurrency: int,
    poi_detail_cache: dict[str, POIRecommendation],
    resolve_search_detail_tool_name_fn: ResolveSearchDetailToolName,
    call_tool_for_purpose_fn: CallToolForPurpose,
    normalize_poi_detail_fn: NormalizePoiDetail,
    poi_detail_is_complete_fn: PoiDetailIsComplete,
    is_rate_limit_error_fn: IsRateLimitError,
) -> list[POIRecommendation]:
    if not has_client or not pois:
        return pois

    detail_tool_name = resolve_search_detail_tool_name_fn()
    if not detail_tool_name:
        return pois

    limit = min(len(pois), poi_detail_limit)
    candidates = pois[:limit]
    semaphore = asyncio.Semaphore(poi_detail_concurrency)
    pending: dict[str, asyncio.Task[POIRecommendation]] = {}

    async def _detail_task(poi: POIRecommendation) -> POIRecommendation:
        assert poi.poi_id is not None
        async with semaphore:
            raw = await call_tool_for_purpose_fn(
                "poi_search",
                {"id": poi.poi_id},
                trace,
                detail_tool_name,
            )
            enriched = normalize_poi_detail_fn(raw, poi)
            poi_detail_cache[poi.poi_id] = enriched
            return enriched

    async def _enrich_one(poi: POIRecommendation) -> POIRecommendation:
        if not poi.poi_id:
            return poi
        if poi_detail_is_complete_fn(poi, category):
            return poi
        cached = poi_detail_cache.get(poi.poi_id)
        if cached is not None:
            return cached

        task = pending.get(poi.poi_id)
        if task is None:
            task = asyncio.create_task(_detail_task(poi))
            pending[poi.poi_id] = task
        return await task

    enriched_prefix: list[POIRecommendation] = []
    for batch_start in range(0, len(candidates), poi_detail_concurrency):
        batch = candidates[batch_start : batch_start + poi_detail_concurrency]
        results = await asyncio.gather(
            *[_enrich_one(poi) for poi in batch],
            return_exceptions=True,
        )
        should_stop = False
        for poi, result in zip(batch, results):
            if isinstance(result, Exception):
                enriched_prefix.append(poi)
                if is_rate_limit_error_fn(result):
                    should_stop = True
                continue
            enriched_prefix.append(result)
        if should_stop:
            enriched_prefix.extend(candidates[batch_start + len(batch) :])
            break
    return enriched_prefix + pois[limit:]
