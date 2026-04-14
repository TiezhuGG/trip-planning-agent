from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.planning import DayPlan, POIRecommendation, PlanningContext, ToolCallRecord

MatchKnownPoint = Callable[[str, list[POIRecommendation]], POIRecommendation | None]
EnsureRouteReadyPoi = Callable[[POIRecommendation, str], POIRecommendation]
BuildActivityLocationQueries = Callable[[str, str], list[str]]
ResolveNamedLocation = Callable[[str, str, list[POIRecommendation], list[ToolCallRecord], list[POIRecommendation]], Awaitable[POIRecommendation | None]]


async def resolve_named_location(
    *,
    city: str,
    location_name: str,
    known_points: list[POIRecommendation],
    trace: list[ToolCallRecord],
    anchor_points: list[POIRecommendation],
    named_location_cache: dict[str, POIRecommendation | None],
    named_location_cache_key_fn: Callable[[str, str, list[POIRecommendation]], str],
    match_known_point_fn: MatchKnownPoint,
    ensure_route_ready_poi_fn: EnsureRouteReadyPoi,
    adapter: Any,
) -> POIRecommendation | None:
    matched = match_known_point_fn(location_name, known_points)
    if matched is not None:
        return ensure_route_ready_poi_fn(matched, city)

    cache_key = named_location_cache_key_fn(city, location_name, anchor_points)
    if cache_key in named_location_cache:
        cached = named_location_cache[cache_key]
        if cached is None:
            return None
        return ensure_route_ready_poi_fn(cached, city)

    resolver = getattr(adapter, "resolve_location_candidate", None)
    if resolver is None:
        return None

    resolved = await resolver(
        city=city,
        location_name=location_name,
        trace=trace,
        anchor_pois=anchor_points,
    )
    named_location_cache[cache_key] = resolved
    if resolved is None:
        return None
    return ensure_route_ready_poi_fn(resolved, city)


async def resolve_activity_location(
    *,
    city: str,
    location_name: str,
    activity_title: str,
    context: PlanningContext,
    trace: list[ToolCallRecord],
    anchor_points: list[POIRecommendation],
    build_activity_location_queries_fn: BuildActivityLocationQueries,
    match_known_point_fn: MatchKnownPoint,
    ensure_route_ready_poi_fn: EnsureRouteReadyPoi,
    resolve_named_location_fn: ResolveNamedLocation,
) -> POIRecommendation | None:
    for query in build_activity_location_queries_fn(location_name, activity_title):
        matched = match_known_point_fn(query, context.attractions)
        if matched is not None:
            return ensure_route_ready_poi_fn(matched, city)

    for query in build_activity_location_queries_fn(location_name, activity_title):
        resolved = await resolve_named_location_fn(
            city,
            query,
            context.attractions,
            trace,
            anchor_points,
        )
        if resolved is not None:
            return resolved
    return None


async def resolve_activity_points(
    *,
    request_destination: str,
    day: DayPlan,
    context: PlanningContext,
    anchor_points: list[POIRecommendation],
    trace: list[ToolCallRecord],
    activity_resolve_concurrency: int,
    resolve_activity_location_fn: Callable[[str, str, str, PlanningContext, list[ToolCallRecord], list[POIRecommendation]], Awaitable[POIRecommendation | None]],
    ensure_route_ready_poi_fn: EnsureRouteReadyPoi,
) -> list[tuple[POIRecommendation, str]]:
    if not day.activities:
        return []

    semaphore = asyncio.Semaphore(max(1, activity_resolve_concurrency))

    async def _resolve_one(index: int, activity) -> tuple[int, tuple[POIRecommendation, str]]:
        async with semaphore:
            resolved = await resolve_activity_location_fn(
                request_destination,
                activity.location_name,
                activity.title,
                context,
                trace,
                anchor_points,
            )
        if resolved is None:
            resolved = POIRecommendation(
                name=activity.location_name,
                address=f"{request_destination}{activity.location_name}",
                district=request_destination,
                source="activity_fallback",
            )
        point = (
            ensure_route_ready_poi_fn(resolved, request_destination),
            activity.location_name,
        )
        return index, point

    resolved_points = await asyncio.gather(
        *[_resolve_one(index, activity) for index, activity in enumerate(day.activities)]
    )
    resolved_points.sort(key=lambda item: item[0])
    return [point for _, point in resolved_points]
