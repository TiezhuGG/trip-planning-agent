from __future__ import annotations

import asyncio

from app.schemas.planning import (
    AgentExecution,
    POIRecommendation,
    PlanningContext,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)
from app.services.amap_mcp_adapter import AmapMCPAdapter


class HotelRecommendationAgent:
    def __init__(self, adapter: AmapMCPAdapter) -> None:
        self.adapter = adapter
        self._day_concurrency = 3

    async def gather(
        self,
        request: TripPlanningRequest,
        attractions: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> list[POIRecommendation]:
        return await self.adapter.fetch_hotels(request, trace, anchor_pois=attractions)

    async def bind_daily_stays(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
        trace: list[ToolCallRecord],
    ) -> tuple[TravelPlan, list[POIRecommendation], AgentExecution]:
        sorted_days = sorted(plan.days, key=lambda item: item.day_number)
        day_concurrency = min(self._day_concurrency, max(1, len(sorted_days)))
        semaphore = asyncio.Semaphore(day_concurrency)

        async def _bind_day(index: int, day):
            location_names = [activity.location_name for activity in day.activities if activity.location_name][:3]
            area_hint = day.hotel_area or day.stay.area
            if not location_names and not area_hint:
                return index, day, None, "", False

            try:
                async with semaphore:
                    day_hotels = await self.adapter.fetch_hotels_for_locations(
                        request=request,
                        trace=trace,
                        location_names=location_names,
                        area_hint=area_hint,
                    )
            except Exception as exc:
                return (
                    index,
                    day,
                    None,
                    f"第 {day.day_number} 天酒店绑定失败，已保留原住宿。原因: {exc}",
                    False,
                )

            if not day_hotels:
                return index, day, None, "", False

            selected = day_hotels[0]
            resolved_area = selected.district or selected.address or day.hotel_area or day.stay.area
            focus = location_names[0] if location_names else resolved_area or request.destination
            hotel_changed = not self._same_hotel_name(day.stay.hotel_name, selected.name)
            updated_day = day.model_copy(
                update={
                    "hotel_area": resolved_area,
                    "stay": day.stay.model_copy(
                        update={
                            "area": resolved_area,
                            "hotel_name": selected.name,
                            "reason": f"更贴近{focus}等当日活动区域，往返更省时。",
                            "room_nightly_cost_cny": 0 if hotel_changed else day.stay.room_nightly_cost_cny,
                        }
                    ),
                }
            )
            return index, updated_day, selected, "", True

        day_results = await asyncio.gather(
            *[_bind_day(index, day) for index, day in enumerate(sorted_days)]
        )
        day_results.sort(key=lambda item: item[0])

        updated_days = []
        selected_hotels: list[POIRecommendation] = []
        rebound_days = 0
        warnings: list[str] = []
        for _, updated_day, selected_hotel, warning, rebound in day_results:
            updated_days.append(updated_day)
            if selected_hotel is not None:
                selected_hotels.append(selected_hotel)
            if warning:
                warnings.append(warning)
            if rebound:
                rebound_days += 1

        summary = (
            "已按每日活动区域校正住宿推荐。"
            if rebound_days
            else "未命中需要校正的每日住宿推荐。"
        )
        return (
            plan.model_copy(update={"days": updated_days}),
            self._merge_unique_hotels([*selected_hotels, *context.hotels]),
            AgentExecution(
                agent_name="hotel_binding_agent",
                success=True,
                summary=summary,
                used_llm=False,
                used_tools=[],
                warnings=warnings,
            ),
        )

    def _same_hotel_name(
        self,
        current_name: str,
        selected_name: str,
    ) -> bool:
        return self._normalize_hotel_name(current_name) == self._normalize_hotel_name(selected_name)

    def _normalize_hotel_name(
        self,
        value: str,
    ) -> str:
        return (value or "").strip().lower()

    def _merge_unique_hotels(
        self,
        hotels: list[POIRecommendation],
    ) -> list[POIRecommendation]:
        merged: list[POIRecommendation] = []
        seen: set[str] = set()
        for hotel in hotels:
            key = hotel.poi_id or hotel.name
            if key in seen:
                continue
            seen.add(key)
            merged.append(hotel)
        return merged
