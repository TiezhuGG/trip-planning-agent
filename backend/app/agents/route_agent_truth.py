from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.schemas.planning import (
    DayPOI,
    DayPlan,
    POIRecommendation,
    PlanningContext,
    ToolCallRecord,
    TripPlanningRequest,
)

ShouldRebindNamedPoi = Callable[[str, POIRecommendation | None, str], bool]
ResolveOriginForDay = Callable[
    [TripPlanningRequest, DayPlan, PlanningContext, list[POIRecommendation], list[ToolCallRecord]],
    Awaitable[POIRecommendation | None],
]
ResolveActivityLocation = Callable[
    [str, str, str, PlanningContext, list[ToolCallRecord], list[POIRecommendation]],
    Awaitable[POIRecommendation | None],
]
ResolveNamedLocation = Callable[
    [str, str, list[POIRecommendation], list[ToolCallRecord], list[POIRecommendation]],
    Awaitable[POIRecommendation | None],
]
EnsureRouteReadyPoi = Callable[[POIRecommendation, str], POIRecommendation]
BuildUniqueDayPois = Callable[[list[DayPOI]], list[DayPOI]]


async def bind_truth_for_day(
    *,
    request: TripPlanningRequest,
    day: DayPlan,
    context: PlanningContext,
    trace: list[ToolCallRecord],
    should_rebind_named_poi_fn: ShouldRebindNamedPoi,
    resolve_origin_for_day_fn: ResolveOriginForDay,
    resolve_activity_location_fn: ResolveActivityLocation,
    resolve_named_location_fn: ResolveNamedLocation,
    ensure_route_ready_poi_fn: EnsureRouteReadyPoi,
    build_unique_day_pois_fn: BuildUniqueDayPois,
) -> tuple[DayPlan, list[str]]:
    anchor_points = [*context.attractions, *context.hotels]
    day_fallbacks = list(day.fallbacks)
    map_pois: list[DayPOI] = []
    day_warnings: list[str] = []
    route_segments = list(day.route_segments or day.route_summaries)
    if not route_segments and day.route_summary is not None:
        route_segments = [day.route_summary]

    stay_poi = day.stay.poi
    if should_rebind_named_poi_fn(day.stay.hotel_name or day.hotel_area, stay_poi, ""):
        try:
            stay_poi = await resolve_origin_for_day_fn(
                request=request,
                day=day,
                context=context,
                anchor_points=anchor_points,
                trace=trace,
            )
        except Exception as exc:
            day_warnings.append(
                f"第 {day.day_number} 天住宿点位校正失败，已保留原住宿信息。原因: {exc}"
            )
            day_fallbacks.append("stay_poi_binding_failed")
    if stay_poi is not None:
        stay_poi = ensure_route_ready_poi_fn(stay_poi, request.destination)
    updated_stay = day.stay.model_copy(update={"poi": stay_poi})
    if stay_poi is not None and updated_stay.hotel_name:
        map_pois.append(DayPOI(kind="stay", label=updated_stay.hotel_name, poi=stay_poi))
    elif updated_stay.hotel_name:
        day_fallbacks.append("stay_poi_unresolved")

    updated_activities = []
    for activity in day.activities:
        resolved = activity.poi
        if should_rebind_named_poi_fn(
            activity.location_name or activity.title,
            resolved,
            activity.title,
        ):
            try:
                resolved = await resolve_activity_location_fn(
                    city=request.destination,
                    location_name=activity.location_name,
                    activity_title=activity.title,
                    context=context,
                    trace=trace,
                    anchor_points=anchor_points,
                ) or resolved
            except Exception as exc:
                day_warnings.append(
                    "第 "
                    f"{day.day_number} 天活动点位校正失败，已保留原活动信息。"
                    f"活动: {activity.location_name or activity.title}；原因: {exc}"
                )
                day_fallbacks.append(
                    f"activity_poi_binding_failed:{activity.location_name}"
                )
        if resolved is not None:
            resolved = ensure_route_ready_poi_fn(resolved, request.destination)
        updated_activity = activity.model_copy(update={"poi": resolved})
        updated_activities.append(updated_activity)
        if resolved is not None:
            map_pois.append(
                DayPOI(
                    kind="activity",
                    label=activity.title or activity.location_name,
                    poi=resolved,
                )
            )
        elif activity.location_name:
            day_fallbacks.append(f"activity_poi_unresolved:{activity.location_name}")

    updated_meals = []
    for meal in day.meals:
        resolved_meal = meal.poi
        if (
            should_rebind_named_poi_fn(meal.venue_name, resolved_meal, "")
            and meal.venue_name
        ):
            try:
                resolved_meal = await resolve_named_location_fn(
                    city=request.destination,
                    location_name=meal.venue_name,
                    known_points=context.restaurants,
                    trace=trace,
                    anchor_points=context.restaurants or anchor_points,
                ) or resolved_meal
            except Exception as exc:
                day_warnings.append(
                    "第 "
                    f"{day.day_number} 天餐饮点位校正失败，已保留原餐饮信息。"
                    f"餐厅: {meal.venue_name}；原因: {exc}"
                )
                day_fallbacks.append(f"meal_poi_binding_failed:{meal.venue_name}")
        if resolved_meal is None and meal.meal_type == "breakfast":
            resolved_meal = updated_stay.poi
        if resolved_meal is not None:
            resolved_meal = ensure_route_ready_poi_fn(
                resolved_meal,
                request.destination,
            )
        updated_meal = meal.model_copy(update={"poi": resolved_meal})
        updated_meals.append(updated_meal)
        if resolved_meal is not None:
            map_pois.append(
                DayPOI(
                    kind="meal",
                    label=meal.meal_type,
                    poi=resolved_meal,
                )
            )
        elif meal.venue_name:
            day_fallbacks.append(f"meal_poi_unresolved:{meal.venue_name}")

    if updated_activities and not any(
        item.poi.longitude is not None and item.poi.latitude is not None
        for item in map_pois
        if item.kind == "activity"
    ):
        day_warnings.append(
            f"第 {day.day_number} 天活动点位仍缺少坐标，地图仅展示已成功定位的点位。"
        )
        day_fallbacks.append("activity_coordinates_unresolved")

    return (
        day.model_copy(
            update={
                "stay": updated_stay,
                "activities": updated_activities,
                "meals": updated_meals,
                "map_pois": build_unique_day_pois_fn(map_pois),
                "route_segments": route_segments,
                "fallbacks": sorted(set(day_fallbacks)),
            }
        ),
        day_warnings,
    )
