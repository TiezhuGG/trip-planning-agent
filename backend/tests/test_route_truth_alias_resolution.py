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


def test_bind_plan_truth_resolves_activity_from_alias_variants() -> None:
    adapter = AmapMCPAdapter(Settings())
    agent = RoutePlanningAgent(adapter)

    async def fake_resolve_location_candidate(
        city: str,
        location_name: str,
        trace,
        anchor_pois=None,
    ):
        _ = (city, trace, anchor_pois)
        if location_name == "\u5965\u6797\u5339\u514b\u68ee\u6797\u516c\u56ed":
            return POIRecommendation(
                name="\u5965\u6797\u5339\u514b\u68ee\u6797\u516c\u56ed",
                address="\u79d1\u835f\u5357\u8def33\u53f7",
                district="\u5317\u4eac\u5e02",
                longitude=116.392461,
                latitude=40.019226,
            )
        return None

    adapter.resolve_location_candidate = fake_resolve_location_candidate

    request = TripPlanningRequest(
        destination="\u5317\u4eac",
        start_date=date(2026, 4, 12),
        days=1,
    )
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
                theme="Alias Day",
                overview="Olympic Park",
                hotel_area="\u671d\u9633",
                stay=DayStayInfo(area="\u671d\u9633", hotel_name="\u9152\u5e97"),
                activities=[
                    Activity(
                        start_time="08:00",
                        end_time="10:00",
                        title="\u5965\u68ee\u516c\u56ed\u6668\u8dd1",
                        category="sightseeing",
                        description="desc",
                        location_name="\u5965\u6797\u5339\u514b\u68ee\u6797\u516c\u56ed\u5357\u56ed",
                        poi=POIRecommendation(
                            name="\u5965\u6797\u5339\u514b\u68ee\u6797\u516c\u56ed\u5357\u56ed",
                            address="\u5317\u4eac\u5965\u6797\u5339\u514b\u68ee\u6797\u516c\u56ed\u5357\u56ed",
                            district="\u5317\u4eac",
                            source="manual_placeholder",
                        ),
                    )
                ],
            )
        ],
    )
    context = PlanningContext(
        destination="\u5317\u4eac",
        attractions=[],
        restaurants=[],
        hotels=[],
        weather=WeatherSummary(),
    )

    rebound_plan, trace = asyncio.run(
        agent.bind_plan_truth(request=request, plan=plan, context=context, trace=[])
    )

    assert trace.success is True
    activity_poi = rebound_plan.days[0].activities[0].poi
    assert activity_poi is not None
    assert activity_poi.name == "\u5965\u6797\u5339\u514b\u68ee\u6797\u516c\u56ed"
    assert activity_poi.longitude is not None
