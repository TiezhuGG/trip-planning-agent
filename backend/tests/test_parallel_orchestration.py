import asyncio
from datetime import date

from app.agents.hotel_agent import HotelRecommendationAgent
from app.agents.poi_agent import SightseeingAgent
from app.agents.route_agent import RoutePlanningAgent
from app.schemas.planning import (
    Activity,
    BudgetBreakdown,
    DayPlan,
    InitialPlanDay,
    InitialPlanDraft,
    MealRecommendation,
    POIRecommendation,
    PlanningContext,
    RouteSummary,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)


def _request(days: int = 1) -> TripPlanningRequest:
    return TripPlanningRequest(
        destination="上海",
        start_date=date(2026, 3, 20),
        days=days,
        transport_preferences=["步行"],
    )


def test_poi_agent_fetches_restaurants_with_attraction_anchors() -> None:
    class FakeAdapter:
        def __init__(self) -> None:
            self.received_anchors: list[POIRecommendation] | None = None

        async def fetch_attractions(self, request: TripPlanningRequest, trace: list[ToolCallRecord]):
            _ = (request, trace)
            return [
                POIRecommendation(name="外滩", district="黄浦区"),
                POIRecommendation(name="豫园", district="黄浦区"),
            ]

        async def fetch_restaurants(
            self,
            request: TripPlanningRequest,
            trace: list[ToolCallRecord],
            anchor_pois: list[POIRecommendation] | None = None,
        ):
            _ = (request, trace)
            self.received_anchors = anchor_pois
            return [POIRecommendation(name="本帮菜馆")]

    adapter = FakeAdapter()
    agent = SightseeingAgent(adapter)  # type: ignore[arg-type]

    attractions, restaurants = asyncio.run(agent.gather(_request(), []))

    assert [item.name for item in attractions] == ["外滩", "豫园"]
    assert [item.name for item in restaurants] == ["本帮菜馆"]
    assert adapter.received_anchors is not None
    assert [item.name for item in adapter.received_anchors] == ["外滩", "豫园"]


def test_route_agent_keeps_segment_order_when_planning_in_parallel() -> None:
    class FakeAdapter:
        async def plan_route(
            self,
            day_number: int,
            origin: POIRecommendation,
            destination: POIRecommendation,
            waypoints: list[POIRecommendation],
            mode: str,
            trace: list[ToolCallRecord],
        ) -> RouteSummary:
            _ = waypoints
            if destination.name.endswith("2"):
                await asyncio.sleep(0.08)
            elif destination.name.endswith("3"):
                await asyncio.sleep(0.02)
            else:
                await asyncio.sleep(0.05)
            trace.append(
                ToolCallRecord(
                    tool_name="maps_direction_walking_by_coordinates",
                    arguments={"origin": origin.name, "destination": destination.name},
                    success=True,
                    summary="ok",
                )
            )
            return RouteSummary(
                day_number=day_number,
                title="route",
                from_name=origin.name,
                to_name=destination.name,
                mode=mode,
            )

    agent = RoutePlanningAgent(FakeAdapter())  # type: ignore[arg-type]
    request = _request(days=1)
    initial_plan = InitialPlanDraft(
        summary="seed",
        days=[
            InitialPlanDay(
                day_number=1,
                date="2026-03-20",
                theme="D1",
                focus="focus",
                must_visit=[],
            )
        ],
    )
    attractions = [
        POIRecommendation(name="景点1", longitude=121.47, latitude=31.23),
        POIRecommendation(name="景点2", longitude=121.48, latitude=31.24),
    ]
    hotels = [POIRecommendation(name="酒店", longitude=121.46, latitude=31.22)]
    day_restaurants = {
        1: [
            POIRecommendation(name="餐厅3", longitude=121.49, latitude=31.25),
            POIRecommendation(name="餐厅4", longitude=121.50, latitude=31.26),
        ]
    }
    trace: list[ToolCallRecord] = []

    routes, execution = asyncio.run(
        agent.gather(
            request=request,
            initial_plan=initial_plan,
            attractions=attractions,
            hotels=hotels,
            day_restaurants=day_restaurants,
            trace=trace,
        )
    )

    assert [route.title for route in routes] == [
        "第 1 天路线 1",
        "第 1 天路线 2",
        "第 1 天路线 3",
        "第 1 天路线 4",
    ]
    assert execution.success is True
    assert len(routes) == 4


def test_hotel_agent_rebinds_daily_stay_around_day_activities() -> None:
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
                POIRecommendation(name="清源山脚精品酒店", address="清源山景区入口"),
                POIRecommendation(name="西街行舍", address="西街"),
            ]

    agent = HotelRecommendationAgent(FakeAdapter())  # type: ignore[arg-type]
    request = _request(days=1)
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
                stay={"area": "崇武镇", "hotel_name": "崇武海景湾度假酒店", "reason": "旧推荐"},
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

    rebound_plan, rebound_hotels, execution = asyncio.run(agent.bind_daily_stays(request, plan, context, []))

    assert rebound_plan.days[0].stay.hotel_name == "清源山脚精品酒店"
    assert rebound_plan.days[0].hotel_area == "清源山景区入口"
    assert rebound_hotels[0].name == "清源山脚精品酒店"
    assert execution.success is True


def test_meal_agent_rebinds_daily_meals_around_day_activities() -> None:
    class FakeAdapter:
        async def fetch_restaurants_for_locations(
            self,
            request: TripPlanningRequest,
            trace: list[ToolCallRecord],
            location_names: list[str],
            area_hint: str = "",
            stay_hint: str = "",
        ):
            _ = (request, trace, location_names, area_hint, stay_hint)
            return [
                POIRecommendation(name="清源山早餐铺", tags=["早餐"]),
                POIRecommendation(name="清源山景区餐厅", tags=["餐厅"]),
                POIRecommendation(name="西街海鲜馆", tags=["海鲜", "餐厅"]),
            ]

    from app.agents.meal_agent import MealRecommendationAgent

    agent = MealRecommendationAgent(FakeAdapter())  # type: ignore[arg-type]
    request = _request(days=1)
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
                stay={"area": "清源山片区", "hotel_name": "清源山脚精品酒店", "reason": "nearby"},
                meals=[MealRecommendation(meal_type="lunch", venue_name="崇武镇餐厅")],
                activities=[
                    Activity(
                        start_time="09:00",
                        end_time="12:00",
                        title="清源山",
                        category="sightseeing",
                        description="desc",
                        location_name="清源山君岩景区",
                    ),
                    Activity(
                        start_time="14:00",
                        end_time="16:00",
                        title="凉亭观景",
                        category="explore",
                        description="desc",
                        location_name="清源山凉亭观景台",
                    ),
                ],
                route_summaries=[],
            )
        ],
    )
    context = PlanningContext(destination="泉州", restaurants=[])

    rebound_plan, rebound_restaurants, execution = asyncio.run(agent.bind_daily_meals(request, plan, context, []))

    assert [meal.venue_name for meal in rebound_plan.days[0].meals[:3]] == [
        "清源山早餐铺",
        "清源山景区餐厅",
        "西街海鲜馆",
    ]
    assert rebound_restaurants[0].name == "清源山早餐铺"
    assert execution.success is True
