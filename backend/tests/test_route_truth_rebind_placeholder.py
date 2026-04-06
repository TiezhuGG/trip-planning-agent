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


def test_bind_plan_truth_rebinds_manual_placeholder_activity_poi() -> None:
    adapter = AmapMCPAdapter(Settings())
    agent = RoutePlanningAgent(adapter)

    async def fake_resolve_location_candidate(
        city: str,
        location_name: str,
        trace,
        anchor_pois=None,
    ):
        _ = (city, trace, anchor_pois)
        if location_name in {"圆明园南门", "圆明园遗址"}:
            return POIRecommendation(
                name="圆明园遗址公园",
                address="清华西路28号",
                district="北京市",
                longitude=116.300451,
                latitude=40.008981,
            )
        return None

    adapter.resolve_location_candidate = fake_resolve_location_candidate

    request = TripPlanningRequest(destination="北京", start_date=date(2026, 4, 12), days=1)
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
                theme="海淀一日",
                overview="圆明园片区",
                hotel_area="海淀",
                stay=DayStayInfo(area="海淀", hotel_name="海淀酒店"),
                activities=[
                    Activity(
                        start_time="09:00",
                        end_time="11:00",
                        title="圆明园遗址漫步",
                        category="sightseeing",
                        description="desc",
                        location_name="圆明园南门",
                        poi=POIRecommendation(
                            name="圆明园南门",
                            address="北京圆明园南门",
                            district="北京",
                            source="manual_placeholder",
                        ),
                    )
                ],
            )
        ],
    )
    context = PlanningContext(
        destination="北京",
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
    assert activity_poi.name == "圆明园遗址公园"
    assert activity_poi.longitude is not None
    assert any(
        item.kind == "activity" and item.poi.name == "圆明园遗址公园"
        for item in rebound_plan.days[0].map_pois
    )
