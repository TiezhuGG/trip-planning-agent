from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.schemas.planning import (
    DayPlan,
    POIRecommendation,
    PlanningContext,
    RouteSummary,
    ToolCallRecord,
    TripPlanningRequest,
)

ResolveOriginForDay = Callable[
    [TripPlanningRequest, DayPlan, PlanningContext, list[POIRecommendation], list[ToolCallRecord]],
    Awaitable[POIRecommendation | None],
]
ResolveActivityPoints = Callable[
    [TripPlanningRequest, DayPlan, PlanningContext, list[POIRecommendation], list[ToolCallRecord]],
    Awaitable[list[tuple[POIRecommendation, str]]],
]
DedupeRouteNodes = Callable[
    [list[tuple[POIRecommendation, str]]],
    list[tuple[POIRecommendation, str]],
]
BuildSyntheticOrigin = Callable[[TripPlanningRequest, DayPlan], POIRecommendation]
FallbackDayRoute = Callable[[DayPlan, TripPlanningRequest, POIRecommendation | None], RouteSummary]
PreferredMode = Callable[[TripPlanningRequest], str]


async def plan_routes_for_day(
    *,
    request: TripPlanningRequest,
    day: DayPlan,
    context: PlanningContext,
    trace: list[ToolCallRecord],
    segment_concurrency: int | None,
    default_segment_concurrency: int,
    adapter,
    preferred_mode_fn: PreferredMode,
    resolve_origin_for_day_fn: ResolveOriginForDay,
    resolve_activity_points_fn: ResolveActivityPoints,
    dedupe_route_nodes_fn: DedupeRouteNodes,
    build_synthetic_origin_fn: BuildSyntheticOrigin,
    fallback_day_route_fn: FallbackDayRoute,
) -> tuple[list[RouteSummary], bool, str | None]:
    anchor_points = [*context.attractions, *context.hotels]
    preferred_mode = preferred_mode_fn(request)
    origin_label = (
        day.stay.hotel_name
        or (context.hotels[0].name if context.hotels else "")
        or day.hotel_area
        or request.hotel_style
    )

    origin = await resolve_origin_for_day_fn(
        request=request,
        day=day,
        context=context,
        anchor_points=anchor_points,
        trace=trace,
    )
    activity_nodes = await resolve_activity_points_fn(
        request=request,
        day=day,
        context=context,
        anchor_points=anchor_points,
        trace=trace,
    )

    if not activity_nodes:
        warning = f"第 {day.day_number} 天未解析出可规划的活动点位。"
        return [fallback_day_route_fn(day, request, origin)], True, warning

    ordered_nodes = (
        dedupe_route_nodes_fn([(origin, origin_label), *activity_nodes])
        if origin
        else dedupe_route_nodes_fn(activity_nodes)
    )
    if len(ordered_nodes) < 2:
        ordered_nodes = dedupe_route_nodes_fn(
            [(build_synthetic_origin_fn(request, day), origin_label), *activity_nodes]
        )

    if len(ordered_nodes) < 2:
        warning = f"第 {day.day_number} 天路线节点不足，已改用规则摘要。"
        return [fallback_day_route_fn(day, request, origin)], True, warning

    segment_jobs: list[tuple[int, POIRecommendation, str, POIRecommendation, str]] = []
    for segment_index in range(len(ordered_nodes) - 1):
        segment_origin, segment_origin_label = ordered_nodes[segment_index]
        segment_destination, segment_destination_label = ordered_nodes[segment_index + 1]
        if segment_origin == segment_destination:
            continue
        segment_jobs.append(
            (
                segment_index,
                segment_origin,
                segment_origin_label,
                segment_destination,
                segment_destination_label,
            )
        )

    if not segment_jobs:
        warning = f"第 {day.day_number} 天路线节点重复，已改用规则摘要。"
        return [fallback_day_route_fn(day, request, origin)], True, warning

    async def _plan_segment(
        segment_index: int,
        segment_origin: POIRecommendation,
        segment_origin_label: str,
        segment_destination: POIRecommendation,
        segment_destination_label: str,
        semaphore: asyncio.Semaphore,
    ) -> tuple[int, RouteSummary]:
        async with semaphore:
            route = await adapter.plan_route(
                day_number=day.day_number,
                origin=segment_origin,
                destination=segment_destination,
                waypoints=[],
                mode=preferred_mode,
                trace=trace,
            )
        return segment_index, route.model_copy(
            update={
                "title": f"第 {day.day_number} 天路线 {segment_index + 1}",
                "day_number": day.day_number,
                "from_name": segment_origin_label,
                "to_name": segment_destination_label,
            }
        )

    semaphore = asyncio.Semaphore(
        max(1, int(segment_concurrency or default_segment_concurrency))
    )
    try:
        segment_results = await asyncio.gather(
            *[
                _plan_segment(
                    segment_index,
                    segment_origin,
                    segment_origin_label,
                    segment_destination,
                    segment_destination_label,
                    semaphore,
                )
                for (
                    segment_index,
                    segment_origin,
                    segment_origin_label,
                    segment_destination,
                    segment_destination_label,
                ) in segment_jobs
            ]
        )
    except Exception as exc:
        warning = f"第 {day.day_number} 天路线规划失败，已改用规则摘要。原因: {exc}"
        return [fallback_day_route_fn(day, request, origin)], True, warning

    segment_results.sort(key=lambda item: item[0])
    return [route for _, route in segment_results], False, None
