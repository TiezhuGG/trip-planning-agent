import asyncio
import math

from app.schemas.planning import (
    AgentExecution,
    DayPOI,
    DayPlan,
    InitialPlanDraft,
    POIRecommendation,
    PlanningContext,
    RouteSummary,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)
from app.services.amap_mcp_adapter import AmapMCPAdapter


class RoutePlanningAgent:
    def __init__(self, adapter: AmapMCPAdapter) -> None:
        self.adapter = adapter
        # Keep low concurrency to balance latency and upstream rate-limit pressure.
        self._segment_concurrency = 2
        self._named_location_cache: dict[str, POIRecommendation | None] = {}

    async def gather(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        attractions: list[POIRecommendation],
        hotels: list[POIRecommendation],
        day_restaurants: dict[int, list[POIRecommendation]],
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], AgentExecution]:
        routes: list[RouteSummary] = []
        fallback_days = 0

        for day_index, day in enumerate(initial_plan.days):
            day_attractions = self._select_day_attractions(attractions, day_index, day.must_visit)
            meal_points = day_restaurants.get(day.day_number, [])
            attraction_pool = [*day_attractions, *attractions]
            route_points = [
                *self._take_coordinate_points(attraction_pool, 2),
                *self._take_coordinate_points(meal_points, 2),
            ]
            if not route_points:
                raise ValueError(f"第 {day.day_number} 天缺少可用于路线规划的景点或餐饮节点。")

            origin = self._select_origin(hotels, route_points)
            preferred_mode = self._preferred_mode(request)
            daily_had_fallback = False
            ordered_points = self._dedupe_points([origin, *route_points])
            if len(ordered_points) < 2:
                raise ValueError(f"第 {day.day_number} 天路线节点不足，无法拆分多段路线。")

            segment_jobs: list[tuple[int, POIRecommendation, POIRecommendation]] = []
            for segment_index in range(len(ordered_points) - 1):
                segment_origin = ordered_points[segment_index]
                segment_destination = ordered_points[segment_index + 1]
                if segment_origin == segment_destination:
                    continue
                segment_jobs.append((segment_index, segment_origin, segment_destination))

            async def _plan_segment(
                segment_index: int,
                segment_origin: POIRecommendation,
                segment_destination: POIRecommendation,
            ) -> tuple[int, RouteSummary]:
                async with semaphore:
                    route = await self.adapter.plan_route(
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
                    }
                )

            semaphore = asyncio.Semaphore(max(1, self._segment_concurrency))
            segment_results = await asyncio.gather(
                *[
                    _plan_segment(segment_index, segment_origin, segment_destination)
                    for segment_index, segment_origin, segment_destination in segment_jobs
                ]
            )
            segment_results.sort(key=lambda item: item[0])
            for _, route in segment_results:
                routes.append(route)
                if route.mode != preferred_mode:
                    daily_had_fallback = True

            if daily_had_fallback:
                fallback_days += 1

        used_tools = {
            item.tool_name
            for item in trace
            if item.tool_name.startswith("maps_direction")
            or item.tool_name.startswith("maps_bicycling")
            or item.tool_name.startswith("amap_webservice_")
        }

        summary = f"已生成 {len(routes)} 条分段路线。" if routes else "暂无可用的每日路线结果。"
        if fallback_days:
            summary = f"{summary} 其中 {fallback_days} 天因路况数据限制切换为其他交通方式。"

        return (
            routes,
            AgentExecution(
                agent_name="route_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=sorted(used_tools),
                warnings=[],
            ),
        )

    async def gather_for_plan(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], AgentExecution]:
        self._named_location_cache.clear()
        routes: list[RouteSummary] = []
        fallback_days = 0
        warnings: list[str] = []
        sorted_days = sorted(plan.days, key=lambda item: item.day_number)
        day_concurrency = min(2, max(1, len(sorted_days)))
        semaphore = asyncio.Semaphore(day_concurrency)

        async def _plan_day(index: int, day: DayPlan):
            async with semaphore:
                day_routes, day_used_fallback, day_warning = await self._plan_routes_for_day(
                    request=request,
                    day=day,
                    context=context,
                    trace=trace,
                )
            return index, day_routes, day_used_fallback, day_warning

        day_results = await asyncio.gather(
            *[_plan_day(index, day) for index, day in enumerate(sorted_days)]
        )
        day_results.sort(key=lambda item: item[0])
        for _, day_routes, day_used_fallback, day_warning in day_results:
            routes.extend(day_routes)
            if day_used_fallback:
                fallback_days += 1
            if day_warning:
                warnings.append(day_warning)

        used_tools = {
            item.tool_name
            for item in trace
            if item.tool_name.startswith("maps_direction")
            or item.tool_name.startswith("maps_bicycling")
            or item.tool_name.startswith("amap_webservice_")
        }
        summary = f"已基于最终行程生成 {len(routes)} 条分段路线。" if routes else "暂无可用的每日路线结果。"
        if fallback_days:
            summary = f"{summary} 其中 {fallback_days} 天使用了规则路线摘要。"

        return (
            routes,
            AgentExecution(
                agent_name="route_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=sorted(used_tools),
                warnings=warnings,
            ),
        )

    async def _legacy_bind_plan_truth(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[TravelPlan, AgentExecution]:
        updated_days: list[DayPlan] = []
        warnings: list[str] = []

        for day in sorted(plan.days, key=lambda item: item.day_number):
            anchor_points = [*context.attractions, *context.hotels]
            day_fallbacks = list(day.fallbacks)
            map_pois: list[DayPOI] = []

            stay_poi = day.stay.poi
            if self._should_rebind_poi(stay_poi):
                try:
                    stay_poi = await self._resolve_origin_for_day(
                        request=request,
                        day=day,
                        context=context,
                        anchor_points=anchor_points,
                        trace=trace,
                    )
                except Exception as exc:
                    warnings.append(f"第 {day.day_number} 天住宿点位校正失败: {exc}")
                    day_fallbacks.append("stay_poi_binding_failed")
            updated_stay = day.stay.model_copy(update={"poi": stay_poi})
            if stay_poi is not None and updated_stay.hotel_name:
                map_pois.append(
                    DayPOI(kind="stay", label=updated_stay.hotel_name, poi=stay_poi)
                )
            elif updated_stay.hotel_name:
                day_fallbacks.append("stay_poi_unresolved")

            updated_activities = []
            for activity in day.activities:
                resolved = activity.poi
                if self._should_rebind_poi(resolved):
                    try:
                        resolved = await self._resolve_activity_location(
                            city=request.destination,
                            location_name=activity.location_name,
                            activity_title=activity.title,
                            context=context,
                            trace=trace,
                            anchor_points=anchor_points,
                        ) or resolved
                    except Exception as exc:
                        warnings.append(
                            f"第 {day.day_number} 天活动点位校正失败: {activity.location_name} | {exc}"
                        )
                        day_fallbacks.append(
                            f"activity_poi_binding_failed:{activity.location_name}"
                        )
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
                if self._should_rebind_poi(resolved_meal) and meal.venue_name:
                    try:
                        resolved_meal = await self._resolve_named_location(
                            city=request.destination,
                            location_name=meal.venue_name,
                            known_points=context.restaurants,
                            trace=trace,
                            anchor_points=context.restaurants or anchor_points,
                        ) or resolved_meal
                    except Exception as exc:
                        warnings.append(
                            f"第 {day.day_number} 天餐饮点位校正失败: {meal.venue_name} | {exc}"
                        )
                        day_fallbacks.append(f"meal_poi_binding_failed:{meal.venue_name}")
                    if resolved_meal is None and meal.meal_type == "breakfast":
                        resolved_meal = updated_stay.poi
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

            route_segments = list(day.route_segments or day.route_summaries)
            if not route_segments and day.route_summary is not None:
                route_segments = [day.route_summary]
            if updated_activities and not any(
                item.poi.longitude is not None and item.poi.latitude is not None
                for item in map_pois
                if item.kind == "activity"
            ):
                warnings.append(f"第 {day.day_number} 天活动点位未解析出坐标，地图将只显示已确认位置。")

            updated_days.append(
                day.model_copy(
                    update={
                        "stay": updated_stay,
                        "activities": updated_activities,
                        "meals": updated_meals,
                        "map_pois": self._build_unique_day_pois(map_pois),
                        "route_segments": route_segments,
                        "fallbacks": sorted(set(day_fallbacks)),
                    }
                )
            )

        summary = "已完成最终日程点位校正。"
        if warnings:
            summary = "已完成最终日程点位校正，部分活动点位未能解析精确坐标。"
        return (
            plan.model_copy(update={"days": updated_days}),
            AgentExecution(
                agent_name="plan_truth_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=[],
                warnings=warnings,
            ),
        )

    async def bind_plan_truth(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[TravelPlan, AgentExecution]:
        self._named_location_cache.clear()
        updated_days: list[DayPlan] = []
        warnings: list[str] = []

        for day in sorted(plan.days, key=lambda item: item.day_number):
            anchor_points = [*context.attractions, *context.hotels]
            day_fallbacks = list(day.fallbacks)
            map_pois: list[DayPOI] = []
            route_segments = list(day.route_segments or day.route_summaries)
            if not route_segments and day.route_summary is not None:
                route_segments = [day.route_summary]

            stay_poi = day.stay.poi
            if self._should_rebind_poi(stay_poi):
                try:
                    stay_poi = await self._resolve_origin_for_day(
                        request=request,
                        day=day,
                        context=context,
                        anchor_points=anchor_points,
                        trace=trace,
                    )
                except Exception as exc:
                    warnings.append(
                        f"第 {day.day_number} 天住宿点位校正失败，已保留原住宿信息。原因: {exc}"
                    )
                    day_fallbacks.append("stay_poi_binding_failed")
            if stay_poi is not None:
                stay_poi = self._ensure_route_ready_poi(stay_poi, request.destination)
            updated_stay = day.stay.model_copy(update={"poi": stay_poi})
            if stay_poi is not None and updated_stay.hotel_name:
                map_pois.append(
                    DayPOI(kind="stay", label=updated_stay.hotel_name, poi=stay_poi)
                )
            elif updated_stay.hotel_name:
                day_fallbacks.append("stay_poi_unresolved")

            updated_activities = []
            for activity in day.activities:
                resolved = activity.poi
                if self._should_rebind_poi(resolved):
                    try:
                        resolved = await self._resolve_activity_location(
                            city=request.destination,
                            location_name=activity.location_name,
                            activity_title=activity.title,
                            context=context,
                            trace=trace,
                            anchor_points=anchor_points,
                        ) or resolved
                    except Exception as exc:
                        warnings.append(
                            f"第 {day.day_number} 天活动点位校正失败，已保留原活动信息。"
                            f"活动: {activity.location_name or activity.title}；原因: {exc}"
                        )
                        day_fallbacks.append(
                            f"activity_poi_binding_failed:{activity.location_name}"
                        )
                if resolved is not None:
                    resolved = self._ensure_route_ready_poi(resolved, request.destination)
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
                    day_fallbacks.append(
                        f"activity_poi_unresolved:{activity.location_name}"
                    )

            updated_meals = []
            for meal in day.meals:
                resolved_meal = meal.poi
                if self._should_rebind_poi(resolved_meal) and meal.venue_name:
                    try:
                        resolved_meal = await self._resolve_named_location(
                            city=request.destination,
                            location_name=meal.venue_name,
                            known_points=context.restaurants,
                            trace=trace,
                            anchor_points=context.restaurants or anchor_points,
                        ) or resolved_meal
                    except Exception as exc:
                        warnings.append(
                            f"第 {day.day_number} 天餐饮点位校正失败，已保留原餐饮信息。"
                            f"餐厅: {meal.venue_name}；原因: {exc}"
                        )
                        day_fallbacks.append(
                            f"meal_poi_binding_failed:{meal.venue_name}"
                        )
                if resolved_meal is None and meal.meal_type == "breakfast":
                    resolved_meal = updated_stay.poi
                if resolved_meal is not None:
                    resolved_meal = self._ensure_route_ready_poi(
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
                warnings.append(
                    f"第 {day.day_number} 天活动点位仍缺少坐标，地图仅展示已成功定位的点位。"
                )
                day_fallbacks.append("activity_coordinates_unresolved")

            updated_days.append(
                day.model_copy(
                    update={
                        "stay": updated_stay,
                        "activities": updated_activities,
                        "meals": updated_meals,
                        "map_pois": self._build_unique_day_pois(map_pois),
                        "route_segments": route_segments,
                        "fallbacks": sorted(set(day_fallbacks)),
                    }
                )
            )

        summary = "已完成最终点位校正。"
        if warnings:
            summary = "已完成最终点位校正，部分点位未能精确定位。"
        return (
            plan.model_copy(update={"days": updated_days}),
            AgentExecution(
                agent_name="plan_truth_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=[],
                warnings=warnings,
            ),
        )

    def _take_coordinate_points(
        self,
        points: list[POIRecommendation],
        limit: int,
    ) -> list[POIRecommendation]:
        selected: list[POIRecommendation] = []
        for poi in points:
            if poi.longitude is None or poi.latitude is None:
                continue
            selected.append(poi)
            if len(selected) >= limit:
                break
        return selected

    def _dedupe_points(self, points: list[POIRecommendation]) -> list[POIRecommendation]:
        deduped: list[POIRecommendation] = []
        seen: set[str] = set()
        for poi in points:
            key = poi.poi_id or poi.name
            if key in seen:
                continue
            seen.add(key)
            deduped.append(poi)
        return deduped

    def _select_day_attractions(
        self,
        attractions: list[POIRecommendation],
        day_index: int,
        must_visit: list[str],
    ) -> list[POIRecommendation]:
        if not attractions:
            return []

        selected: list[POIRecommendation] = []
        for keyword in must_visit:
            matched = next((poi for poi in attractions if keyword in poi.name), None)
            if matched and matched not in selected:
                selected.append(matched)

        start_index = day_index % len(attractions)
        for offset in range(len(attractions)):
            poi = attractions[(start_index + offset) % len(attractions)]
            if poi in selected:
                continue
            selected.append(poi)
            if len(selected) >= 2:
                break
        return selected

    def _preferred_mode(self, request: TripPlanningRequest) -> str:
        preferences = request.transport_preferences
        if "步行" in preferences:
            return "walking"
        if "公共交通" in preferences:
            return "transit"
        if "骑行" in preferences:
            return "bicycling"
        if "自驾" in preferences:
            return "driving"
        return "driving"

    def _select_origin(
        self,
        hotels: list[POIRecommendation],
        route_points: list[POIRecommendation],
    ) -> POIRecommendation:
        if not hotels:
            return route_points[0]

        scored: list[tuple[float, POIRecommendation]] = []
        for hotel in hotels:
            distance = self._average_distance_km(hotel, route_points)
            scored.append((distance, hotel))

        scored.sort(key=lambda item: item[0])
        best_distance, best_hotel = scored[0]
        if best_distance == float("inf") or best_distance > 25:
            return route_points[0]
        return best_hotel

    def _average_distance_km(
        self,
        origin: POIRecommendation,
        targets: list[POIRecommendation],
    ) -> float:
        if origin.longitude is None or origin.latitude is None:
            return float("inf")

        distances: list[float] = []
        for target in targets[:3]:
            if target.longitude is None or target.latitude is None:
                continue
            distances.append(
                self._distance_km(
                    origin.latitude,
                    origin.longitude,
                    target.latitude,
                    target.longitude,
                )
            )

        if not distances:
            return float("inf")
        return sum(distances) / len(distances)

    def _distance_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat_scale = 111.0
        lon_scale = 111.0 * max(0.1, math.cos(math.radians((lat1 + lat2) / 2)))
        lat_distance = (lat1 - lat2) * lat_scale
        lon_distance = (lon1 - lon2) * lon_scale
        return math.sqrt(lat_distance * lat_distance + lon_distance * lon_distance)

    async def _plan_routes_for_day(
        self,
        request: TripPlanningRequest,
        day: DayPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], bool, str | None]:
        anchor_points = [*context.attractions, *context.hotels]
        preferred_mode = self._preferred_mode(request)
        origin_label = day.stay.hotel_name or (context.hotels[0].name if context.hotels else "") or day.hotel_area or request.hotel_style

        origin = await self._resolve_origin_for_day(
            request=request,
            day=day,
            context=context,
            anchor_points=anchor_points,
            trace=trace,
        )
        activity_nodes = await self._resolve_activity_points(
            request=request,
            day=day,
            context=context,
            anchor_points=anchor_points,
            trace=trace,
        )

        if not activity_nodes:
            return [self._fallback_day_route(day, request, origin)], True, f"第 {day.day_number} 天未解析出可规划的活动点位。"

        ordered_nodes = (
            self._dedupe_route_nodes([(origin, origin_label), *activity_nodes])
            if origin
            else self._dedupe_route_nodes(activity_nodes)
        )
        if len(ordered_nodes) < 2:
            ordered_nodes = self._dedupe_route_nodes(
                [(self._build_synthetic_origin(request, day), origin_label), *activity_nodes]
            )

        if len(ordered_nodes) < 2:
            return [self._fallback_day_route(day, request, origin)], True, f"第 {day.day_number} 天路线节点不足，已改用规则摘要。"

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
            return [self._fallback_day_route(day, request, origin)], True, f"第 {day.day_number} 天路线节点重复，已改用规则摘要。"

        async def _plan_segment(
            segment_index: int,
            segment_origin: POIRecommendation,
            segment_origin_label: str,
            segment_destination: POIRecommendation,
            segment_destination_label: str,
        ) -> tuple[int, RouteSummary]:
            async with semaphore:
                route = await self.adapter.plan_route(
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

        semaphore = asyncio.Semaphore(max(1, self._segment_concurrency))
        try:
            segment_results = await asyncio.gather(
                *[
                    _plan_segment(
                        segment_index,
                        segment_origin,
                        segment_origin_label,
                        segment_destination,
                        segment_destination_label,
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
            return [self._fallback_day_route(day, request, origin)], True, warning

        segment_results.sort(key=lambda item: item[0])
        return [route for _, route in segment_results], False, None

    async def _resolve_origin_for_day(
        self,
        request: TripPlanningRequest,
        day: DayPlan,
        context: PlanningContext,
        anchor_points: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> POIRecommendation | None:
        if day.stay.hotel_name:
            resolved = await self._resolve_named_location(
                city=request.destination,
                location_name=day.stay.hotel_name,
                known_points=context.hotels,
                trace=trace,
                anchor_points=context.hotels or anchor_points,
            )
            if resolved is not None:
                return resolved

        if context.hotels:
            return self._ensure_route_ready_poi(context.hotels[0], request.destination)

        if day.hotel_area:
            resolved = await self._resolve_named_location(
                city=request.destination,
                location_name=day.hotel_area,
                known_points=context.hotels,
                trace=trace,
                anchor_points=anchor_points,
            )
            if resolved is not None:
                return resolved
        return None

    async def _resolve_activity_points(
        self,
        request: TripPlanningRequest,
        day: DayPlan,
        context: PlanningContext,
        anchor_points: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> list[tuple[POIRecommendation, str]]:
        activity_points: list[tuple[POIRecommendation, str]] = []
        for activity in day.activities:
            resolved = await self._resolve_activity_location(
                city=request.destination,
                location_name=activity.location_name,
                activity_title=activity.title,
                context=context,
                trace=trace,
                anchor_points=anchor_points,
            )
            if resolved is None:
                resolved = POIRecommendation(
                    name=activity.location_name,
                    address=f"{request.destination}{activity.location_name}",
                    district=request.destination,
                    source="activity_fallback",
                )
            activity_points.append(
                (
                    self._ensure_route_ready_poi(resolved, request.destination),
                    activity.location_name,
                )
            )
        return activity_points

    async def _resolve_activity_location(
        self,
        city: str,
        location_name: str,
        activity_title: str,
        context: PlanningContext,
        trace: list[ToolCallRecord],
        anchor_points: list[POIRecommendation],
    ) -> POIRecommendation | None:
        for query in self._build_activity_location_queries(location_name, activity_title):
            matched = self._match_known_point(query, context.attractions)
            if matched is not None:
                return self._ensure_route_ready_poi(matched, city)

        for query in self._build_activity_location_queries(location_name, activity_title):
            resolved = await self._resolve_named_location(
                city=city,
                location_name=query,
                known_points=context.attractions,
                trace=trace,
                anchor_points=anchor_points,
            )
            if resolved is not None:
                return resolved
        return None

    async def _resolve_named_location(
        self,
        city: str,
        location_name: str,
        known_points: list[POIRecommendation],
        trace: list[ToolCallRecord],
        anchor_points: list[POIRecommendation],
    ) -> POIRecommendation | None:
        matched = self._match_known_point(location_name, known_points)
        if matched is not None:
            return self._ensure_route_ready_poi(matched, city)

        cache_key = self._named_location_cache_key(city, location_name, anchor_points)
        if cache_key in self._named_location_cache:
            cached = self._named_location_cache[cache_key]
            if cached is None:
                return None
            return self._ensure_route_ready_poi(cached, city)

        resolver = getattr(self.adapter, "resolve_location_candidate", None)
        if resolver is None:
            return None

        resolved = await resolver(
            city=city,
            location_name=location_name,
            trace=trace,
            anchor_pois=anchor_points,
        )
        self._named_location_cache[cache_key] = resolved
        if resolved is None:
            return None
        return self._ensure_route_ready_poi(resolved, city)

    def _named_location_cache_key(
        self,
        city: str,
        location_name: str,
        anchor_points: list[POIRecommendation],
    ) -> str:
        normalized_city = self._normalize_location_name(city)
        normalized_location = self._normalize_location_name(location_name)
        anchor_tokens = [
            self._normalize_location_name(poi.poi_id or poi.name or "")
            for poi in anchor_points[:3]
        ]
        anchor_key = "|".join(token for token in anchor_tokens if token)
        return f"{normalized_city}::{normalized_location}::{anchor_key}"

    def _match_known_point(
        self,
        location_name: str,
        candidates: list[POIRecommendation],
        allow_contains: bool = True,
    ) -> POIRecommendation | None:
        normalized_target = self._normalize_location_name(location_name)
        if not normalized_target:
            return None

        scored: list[tuple[int, int, int, POIRecommendation]] = []
        for poi in candidates:
            normalized_name = self._normalize_location_name(poi.name)
            if not normalized_name:
                continue
            exact_penalty = 0 if normalized_name == normalized_target else 1
            contains_penalty = 0 if normalized_target in normalized_name or normalized_name in normalized_target else 1
            coordinate_penalty = 0 if poi.longitude is not None and poi.latitude is not None else 1
            if exact_penalty and (contains_penalty or not allow_contains):
                continue
            scored.append((exact_penalty, contains_penalty, coordinate_penalty, poi))

        if not scored:
            return None
        scored.sort(key=lambda item: item[:3])
        return scored[0][3]

    def _dedupe_route_nodes(
        self,
        nodes: list[tuple[POIRecommendation, str]],
    ) -> list[tuple[POIRecommendation, str]]:
        deduped: list[tuple[POIRecommendation, str]] = []
        seen: set[str] = set()
        for poi, label in nodes:
            key = poi.poi_id or label or poi.name
            if key in seen:
                continue
            seen.add(key)
            deduped.append((poi, label))
        return deduped

    def _build_unique_day_pois(
        self,
        pois: list[DayPOI],
    ) -> list[DayPOI]:
        deduped: list[DayPOI] = []
        seen: set[str] = set()
        for item in pois:
            key = item.poi.poi_id or f"{item.kind}:{item.poi.name}:{item.poi.address}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _should_rebind_poi(self, poi: POIRecommendation | None) -> bool:
        if poi is None:
            return True
        if poi.longitude is None or poi.latitude is None:
            return True
        return (poi.source or "").lower() in {
            "manual_placeholder",
            "activity_fallback",
            "stay_fallback",
        }

    def _build_activity_location_queries(
        self,
        location_name: str,
        activity_title: str,
    ) -> list[str]:
        variants: list[str] = []
        for candidate in (location_name, activity_title):
            self._append_activity_variants(variants, candidate)
        place_suffixes = (
            "\u5357\u95e8",
            "\u5317\u95e8",
            "\u4e1c\u95e8",
            "\u897f\u95e8",
            "\u6b63\u95e8",
            "\u5357\u56ed",
            "\u5317\u56ed",
            "\u4e1c\u56ed",
            "\u897f\u56ed",
            "\u5916\u56f4",
            "\u5916\u5708",
            "\u5165\u53e3",
            "\u51fa\u53e3",
            "\u6e38\u5ba2\u4e2d\u5fc3",
            "\u6e29\u5ba4",
            "\u957f\u5eca",
            "\u9057\u5740",
        )
        for base in list(variants):
            for suffix in place_suffixes:
                if base.endswith(suffix) and len(base) > len(suffix):
                    self._add_location_variant(variants, base[: -len(suffix)].strip())
        return variants

    def _append_activity_variants(
        self,
        variants: list[str],
        value: str,
    ) -> None:
        for item in self._expand_location_variants(value):
            if item and item not in variants:
                variants.append(item)
            for alias in self._activity_alias_variants(item):
                if alias and alias not in variants:
                    variants.append(alias)

    def _expand_location_variants(self, value: str) -> list[str]:
        text = value.strip()
        if not text:
            return []

        variants: list[str] = []
        self._add_location_variant(variants, text)
        trimmed = text
        suffixes = (
            "外景拍摄",
            "温室参观",
            "长廊游览",
            "遗址漫步",
            "桃花林徒步",
            "晨跑",
            "徒步",
            "漫步",
            "游览",
            "参观",
            "拍摄",
            "打卡",
            "观景",
            "登山",
            "夜游",
        )
        for suffix in suffixes:
            if trimmed.endswith(suffix) and len(trimmed) > len(suffix):
                trimmed = trimmed[: -len(suffix)].strip()
                self._add_location_variant(variants, trimmed)
        if "外围" in trimmed:
            simplified = trimmed.replace("外围", "").strip()
            self._add_location_variant(variants, simplified)
        return variants

    def _activity_alias_variants(self, value: str) -> list[str]:
        alias_map = {
            "\u5965\u68ee": "\u5965\u6797\u5339\u514b\u68ee\u6797\u516c\u56ed",
            "\u5965\u68ee\u516c\u56ed": "\u5965\u6797\u5339\u514b\u68ee\u6797\u516c\u56ed",
            "\u9e1f\u5de2": "\u56fd\u5bb6\u4f53\u80b2\u573a",
            "\u6c34\u7acb\u65b9": "\u56fd\u5bb6\u6e38\u6cf3\u4e2d\u5fc3",
            "\u5706\u660e\u56ed\u9057\u5740": "\u5706\u660e\u56ed",
            "\u56fd\u5bb6\u690d\u7269\u56ed\u6e29\u5ba4": "\u56fd\u5bb6\u690d\u7269\u56ed",
        }
        expanded: list[str] = []
        for alias, canonical in alias_map.items():
            if alias in value and canonical != value:
                expanded.append(canonical)
        return expanded

    def _add_location_variant(
        self,
        variants: list[str],
        value: str,
    ) -> None:
        candidate = value.strip()
        if not candidate or candidate in variants:
            return
        variants.append(candidate)

    def _ensure_route_ready_poi(
        self,
        poi: POIRecommendation,
        city: str,
    ) -> POIRecommendation:
        district = poi.district or city
        address = poi.address or f"{district}{poi.name}"
        return poi.model_copy(
            update={
                "district": district,
                "address": address,
            }
        )

    def _build_synthetic_origin(
        self,
        request: TripPlanningRequest,
        day: DayPlan,
    ) -> POIRecommendation:
        name = day.stay.hotel_name or day.hotel_area or request.hotel_style
        address = day.stay.area or day.hotel_area or request.destination
        return POIRecommendation(
            name=name,
            address=f"{request.destination}{address}",
            district=request.destination,
            source="stay_fallback",
        )

    def _fallback_day_route(
        self,
        day: DayPlan,
        request: TripPlanningRequest,
        origin: POIRecommendation | None,
    ) -> RouteSummary:
        destination_name = day.activities[-1].location_name if day.activities else request.destination
        waypoints = [activity.location_name for activity in day.activities[:-1]]
        from_name = (
            (origin.name if origin is not None else "")
            or day.stay.hotel_name
            or day.hotel_area
            or request.hotel_style
        )
        return RouteSummary(
            day_number=day.day_number,
            title=f"第 {day.day_number} 天路线 1",
            from_name=from_name,
            to_name=destination_name,
            waypoints=waypoints,
            duration_text="约 30-45 分钟",
            mode=self._preferred_mode(request),
            estimated_transport_cost_cny=20,
            steps=[],
        )

    def _normalize_location_name(self, value: str) -> str:
        return "".join(ch for ch in value.strip().lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
