from __future__ import annotations

import asyncio

from app.agents.meal_agent_helpers import MealRecommendationAgentHelpersMixin
from app.schemas.planning import (
    AgentExecution,
    POIRecommendation,
    PlanningContext,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)
from app.services.amap_mcp_adapter import AmapMCPAdapter


class MealRecommendationAgent(MealRecommendationAgentHelpersMixin):
    def __init__(self, adapter: AmapMCPAdapter | None = None) -> None:
        self.adapter = adapter
        self._day_concurrency = 3

    def gather(
        self,
        request: TripPlanningRequest,
        initial_plan,
        restaurants: list[POIRecommendation],
    ) -> dict[int, list[POIRecommendation]]:
        _ = request
        if not restaurants:
            return {}

        day_meals: dict[int, list[POIRecommendation]] = {}
        for day_index in range(len(initial_plan.days)):
            start_index = day_index % len(restaurants)
            selected: list[POIRecommendation] = []
            for offset in range(len(restaurants)):
                restaurant = restaurants[(start_index + offset) % len(restaurants)]
                if restaurant in selected:
                    continue
                selected.append(restaurant)
                if len(selected) >= 2:
                    break
            day_meals[day_index + 1] = selected
        return day_meals

    async def bind_daily_meals(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[TravelPlan, list[POIRecommendation], AgentExecution]:
        if self.adapter is None:
            return (
                plan,
                context.restaurants,
                AgentExecution(
                    agent_name="meal_binding_agent",
                    success=True,
                    summary="未配置按天餐饮绑定，保留原餐饮结果。",
                ),
            )

        sorted_days = sorted(plan.days, key=lambda item: item.day_number)
        day_concurrency = min(self._day_concurrency, max(1, len(sorted_days)))
        semaphore = asyncio.Semaphore(day_concurrency)

        async def _bind_day(index: int, day):
            location_names = [activity.location_name for activity in day.activities if activity.location_name][:3]
            stay_hint = day.stay.hotel_name or day.hotel_area
            area_hint = day.hotel_area or day.stay.area
            try:
                async with semaphore:
                    day_restaurants = await self.adapter.fetch_restaurants_for_locations(
                        request=request,
                        trace=trace,
                        location_names=location_names,
                        area_hint=area_hint,
                        stay_hint=stay_hint,
                    )
            except Exception as exc:
                return (
                    index,
                    day,
                    [],
                    f"第 {day.day_number} 天餐饮绑定失败，已保留原餐饮。原因: {exc}",
                    False,
                )

            updated_day = day.model_copy(
                update={
                    "meals": self._build_day_meals(
                        request=request,
                        day=day,
                        restaurants=day_restaurants,
                    ),
                }
            )
            return index, updated_day, day_restaurants[:3], "", bool(day_restaurants)

        day_results = await asyncio.gather(
            *[_bind_day(index, day) for index, day in enumerate(sorted_days)]
        )
        day_results.sort(key=lambda item: item[0])

        updated_days = []
        selected_restaurants: list[POIRecommendation] = []
        warnings: list[str] = []
        rebound_days = 0

        for _, updated_day, day_restaurants, warning, rebound in day_results:
            updated_days.append(updated_day)
            selected_restaurants.extend(day_restaurants)
            if warning:
                warnings.append(warning)
            if rebound:
                rebound_days += 1

        summary = (
            "已按每日活动片区校正餐饮推荐。"
            if rebound_days
            else "未命中需要校正的每日餐饮推荐。"
        )
        return (
            plan.model_copy(update={"days": updated_days}),
            self._merge_unique_restaurants([*selected_restaurants, *context.restaurants]),
            AgentExecution(
                agent_name="meal_binding_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=[],
                warnings=warnings,
            ),
        )
