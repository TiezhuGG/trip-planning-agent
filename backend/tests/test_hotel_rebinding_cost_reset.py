import asyncio
from datetime import date

from app.agents.hotel_agent import HotelRecommendationAgent
from app.schemas.planning import (
    Activity,
    BudgetBreakdown,
    DayPlan,
    POIRecommendation,
    PlanningContext,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)


def test_hotel_agent_clears_stale_room_cost_when_rebinding_hotel() -> None:
    class FakeAdapter:
        async def fetch_hotels_for_locations(
            self,
            request: TripPlanningRequest,
            trace: list[ToolCallRecord],
            location_names: list[str],
            area_hint: str = "",
        ):
            _ = (request, trace, location_names, area_hint)
            return [
                POIRecommendation(
                    name="清源山脚精品酒店",
                    district="清源山景区入口",
                )
            ]

    agent = HotelRecommendationAgent(FakeAdapter())  # type: ignore[arg-type]
    request = TripPlanningRequest(
        destination="泉州",
        start_date=date(2026, 3, 20),
        days=1,
        transport_preferences=["步行"],
    )
    plan = TravelPlan(
        title="Plan",
        summary="Summary",
        weather_summary="",
        best_booking_tip="Tip",
        estimated_budget=BudgetBreakdown(),
        stay_recommendations=[],
        city_tips=[],
        packing_list=[],
        days=[
            DayPlan(
                day_number=1,
                date="2026-03-20",
                theme="Day 1",
                overview="Overview",
                hotel_area="崇武镇",
                stay={
                    "area": "崇武镇",
                    "hotel_name": "崇武海景湾度假酒店",
                    "reason": "旧推荐",
                    "room_nightly_cost_cny": 500,
                },
                meals=[],
                activities=[
                    Activity(
                        start_time="09:00",
                        end_time="12:00",
                        title="清源山",
                        category="sightseeing",
                        description="desc",
                        location_name="清源山君岩景区",
                    )
                ],
                route_summaries=[],
            )
        ],
    )
    context = PlanningContext(destination="泉州", hotels=[])

    rebound_plan, _, execution = asyncio.run(agent.bind_daily_stays(request, plan, context, []))

    assert rebound_plan.days[0].stay.hotel_name == "清源山脚精品酒店"
    assert rebound_plan.days[0].stay.room_nightly_cost_cny == 0
    assert execution.success is True
