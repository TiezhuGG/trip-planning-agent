import asyncio
from datetime import date

from app.agents.route_agent import RoutePlanningAgent
from app.config import Settings
from app.schemas.planning import (
    Activity,
    DayPlan,
    DayStayInfo,
    PlanningContext,
    POIRecommendation,
    TravelPlan,
    TripPlanningRequest,
    WeatherSummary,
)
from app.services.amap_mcp_adapter import AmapMCPAdapter


def test_bind_plan_truth_resolves_activity_pois_for_map_markers() -> None:
    adapter = AmapMCPAdapter(Settings())
    agent = RoutePlanningAgent(adapter)

    async def fake_resolve_location_candidate(
        city: str,
        location_name: str,
        trace,
        anchor_pois=None,
    ):
        _ = (city, trace, anchor_pois)
        if location_name == "西湖":
            return POIRecommendation(
                name="杭州西湖名胜区",
                address="西湖区龙井路1号",
                district="西湖区",
                longitude=120.1551,
                latitude=30.2376,
            )
        return None

    adapter.resolve_location_candidate = fake_resolve_location_candidate

    request = TripPlanningRequest(destination="杭州", start_date=date(2026, 4, 12), days=1)
    plan = TravelPlan(
        title="Plan",
        summary="Summary",
        weather_summary="",
        best_booking_tip="",
        estimated_budget={},
        stay_recommendations=[],
        city_tips=[],
        packing_list=[],
        days=[
            DayPlan(
                day_number=1,
                date="2026-04-12",
                theme="西湖慢游",
                overview="西湖片区",
                hotel_area="西湖片区",
                stay=DayStayInfo(area="西湖片区", hotel_name="西湖酒店"),
                activities=[
                    Activity(
                        start_time="09:00",
                        end_time="11:00",
                        title="西湖漫步",
                        category="sightseeing",
                        description="desc",
                        location_name="西湖",
                    )
                ],
            )
        ],
    )
    context = PlanningContext(
        destination="杭州",
        attractions=[],
        restaurants=[],
        hotels=[
            POIRecommendation(
                name="西湖酒店",
                address="西湖区",
                district="西湖区",
                longitude=120.1500,
                latitude=30.2400,
            )
        ],
        weather=WeatherSummary(),
    )

    rebound_plan, trace = asyncio.run(
        agent.bind_plan_truth(request=request, plan=plan, context=context, trace=[])
    )

    assert trace.success is True
    assert rebound_plan.days[0].activities[0].poi is not None
    assert rebound_plan.days[0].activities[0].poi.name == "杭州西湖名胜区"
    assert any(item.kind == "activity" for item in rebound_plan.days[0].map_pois)
