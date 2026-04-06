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
        updated_days = []
        selected_hotels: list[POIRecommendation] = []
        rebound_days = 0
        warnings: list[str] = []

        for day in sorted(plan.days, key=lambda item: item.day_number):
            location_names = [activity.location_name for activity in day.activities if activity.location_name][:3]
            area_hint = day.hotel_area or day.stay.area
            if not location_names and not area_hint:
                updated_days.append(day)
                continue

            try:
                day_hotels = await self.adapter.fetch_hotels_for_locations(
                    request=request,
                    trace=trace,
                    location_names=location_names,
                    area_hint=area_hint,
                )
            except Exception as exc:
                warnings.append(f"第 {day.day_number} 天酒店绑定失败，已保留原住宿。原因: {exc}")
                updated_days.append(day)
                continue

            if not day_hotels:
                updated_days.append(day)
                continue

            selected = day_hotels[0]
            selected_hotels.append(selected)
            rebound_days += 1
            resolved_area = selected.district or selected.address or day.hotel_area or day.stay.area
            focus = location_names[0] if location_names else resolved_area or request.destination
            updated_days.append(
                day.model_copy(
                    update={
                        "hotel_area": resolved_area,
                        "stay": day.stay.model_copy(
                            update={
                                "area": resolved_area,
                                "hotel_name": selected.name,
                                "reason": f"更贴近{focus}等当日活动区域，往返更省时。",
                            }
                        ),
                    }
                )
            )

        summary = "已按每日活动区域校正住宿推荐。" if rebound_days else "未命中需要校正的每日住宿推荐。"
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
