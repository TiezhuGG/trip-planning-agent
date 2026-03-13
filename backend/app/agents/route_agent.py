import math

from app.schemas.planning import (
    AgentExecution,
    InitialPlanDraft,
    POIRecommendation,
    RouteSummary,
    ToolCallRecord,
    TripPlanningRequest,
)
from app.services.amap_mcp_adapter import AmapMCPAdapter


class RoutePlanningAgent:
    def __init__(self, adapter: AmapMCPAdapter) -> None:
        self.adapter = adapter

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
        warnings: list[str] = []
        used_tools: set[str] = set()
        fallback_days = 0

        for day_index, day in enumerate(initial_plan.days):
            day_attractions = self._select_day_attractions(attractions, day_index, day.must_visit)
            meal_points = day_restaurants.get(day.day_number, [])
            route_points = [*day_attractions[:2], *meal_points[:2]]
            if not route_points:
                continue

            origin = self._select_origin(hotels, route_points)
            destination = meal_points[-1] if meal_points else route_points[-1]
            waypoints = route_points[:-1] if destination == route_points[-1] else route_points
            if waypoints and waypoints[0] == origin:
                waypoints = waypoints[1:]
            if destination in waypoints:
                waypoints = [item for item in waypoints if item != destination]

            trace_start = len(trace)
            preferred_mode = self._preferred_mode(request)
            try:
                route = await self.adapter.plan_route(
                    day_number=day.day_number,
                    origin=origin,
                    destination=destination,
                    waypoints=waypoints,
                    mode=preferred_mode,
                    trace=trace,
                )
                routes.append(route)

                day_tools = {
                    item.tool_name
                    for item in trace[trace_start:]
                    if item.tool_name.startswith("maps_direction")
                    or item.tool_name.startswith("maps_bicycling")
                    or item.tool_name.startswith("amap_webservice_transit")
                }
                used_tools.update(day_tools)
                if route.mode != preferred_mode:
                    fallback_days += 1
            except Exception as exc:
                warnings.append(f"第 {day.day_number} 天路线规划失败: {exc}")

        summary = f"已生成 {len(routes)} 条每日路线。" if routes else "暂无可用的每日路线结果。"
        if fallback_days:
            summary = f"{summary} 其中 {fallback_days} 天已自动降级到可用路线模式。"

        return (
            routes,
            AgentExecution(
                agent_name="route_agent",
                success=not warnings,
                summary=summary,
                used_llm=False,
                used_tools=sorted(used_tools),
                warnings=warnings,
            ),
        )

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
        # Equirectangular approximation is sufficient for same-city ranking.
        lat_scale = 111.0
        lon_scale = 111.0 * max(0.1, math.cos(math.radians((lat1 + lat2) / 2)))
        lat_distance = (lat1 - lat2) * lat_scale
        lon_distance = (lon1 - lon2) * lon_scale
        return math.sqrt(lat_distance * lat_distance + lon_distance * lon_distance)
