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

        for day_index, day in enumerate(initial_plan.days):
            day_attractions = self._select_day_attractions(attractions, day_index, day.must_visit)
            meal_points = day_restaurants.get(day.day_number, [])
            route_points = [*day_attractions[:2], *meal_points[:2]]
            if not route_points:
                continue

            origin = hotels[0] if hotels else route_points[0]
            destination = meal_points[-1] if meal_points else route_points[-1]
            waypoints = route_points[:-1] if destination == route_points[-1] else route_points
            if waypoints and waypoints[0] == origin:
                waypoints = waypoints[1:]
            if destination in waypoints:
                waypoints = [item for item in waypoints if item != destination]

            try:
                route = await self.adapter.plan_route(
                    day_number=day.day_number,
                    origin=origin,
                    destination=destination,
                    waypoints=waypoints,
                    mode=self._preferred_mode(request),
                    trace=trace,
                )
                routes.append(route)
            except Exception as exc:
                warnings.append(f"第 {day.day_number} 天路线规划失败: {exc}")

        summary = f"已生成 {len(routes)} 条每日路线。" if routes else "暂无可用的每日路线结果。"
        return (
            routes,
            AgentExecution(
                agent_name="route_agent",
                success=not warnings,
                summary=summary,
                used_llm=False,
                used_tools=[self.adapter.settings.amap_mcp_tool_route_plan] if self.adapter.has_client else [],
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
