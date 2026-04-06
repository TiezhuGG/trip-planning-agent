import asyncio
import math

from app.schemas.planning import (
    AgentExecution,
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
        self._segment_concurrency = 1

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
        routes: list[RouteSummary] = []
        fallback_days = 0
        warnings: list[str] = []

        for day in sorted(plan.days, key=lambda item: item.day_number):
            day_routes, day_used_fallback, day_warning = await self._plan_routes_for_day(
                request=request,
                day=day,
                context=context,
                trace=trace,
            )
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
        context: PlanningContext,
        trace: list[ToolCallRecord],
        anchor_points: list[POIRecommendation],
    ) -> POIRecommendation | None:
        matched = self._match_known_point(location_name, context.attractions)
        if matched is not None:
            return self._ensure_route_ready_poi(matched, city)

        matched = self._match_known_point(location_name, context.restaurants)
        if matched is not None:
            return self._ensure_route_ready_poi(matched, city)

        matched = self._match_known_point(location_name, context.hotels, allow_contains=False)
        if matched is not None:
            return self._ensure_route_ready_poi(matched, city)

        return await self._resolve_named_location(
            city=city,
            location_name=location_name,
            known_points=context.attractions,
            trace=trace,
            anchor_points=anchor_points,
        )

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

        resolver = getattr(self.adapter, "resolve_location_candidate", None)
        if resolver is None:
            return None

        resolved = await resolver(
            city=city,
            location_name=location_name,
            trace=trace,
            anchor_pois=anchor_points,
        )
        if resolved is None:
            return None
        return self._ensure_route_ready_poi(resolved, city)

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
