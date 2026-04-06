from datetime import date

from app.agents.meal_agent import MealRecommendationAgent
from app.config import Settings
from app.schemas.planning import (
    BudgetBreakdown,
    DayPlan,
    DayStayInfo,
    MealRecommendation,
    PlanningContext,
    POIRecommendation,
    TravelPlan,
    TripPlanningRequest,
    WeatherSummary,
)
from app.services.ai_client import TravelAIClient
from app.services.amap_mcp_adapter import AmapMCPAdapter


def test_meal_agent_prefers_local_restaurant_over_chain() -> None:
    agent = MealRecommendationAgent()
    local_restaurant = POIRecommendation(
        name="老泉州面线糊",
        tags=["小吃", "闽南风味"],
        longitude=118.67,
        latitude=24.91,
    )
    chain_restaurant = POIRecommendation(
        name="肯德基(西街店)",
        tags=["050301"],
        longitude=118.6701,
        latitude=24.9101,
    )

    picked = agent._pick_restaurant(
        [chain_restaurant, local_restaurant],
        preferred_kind="lunch",
    )

    assert picked is not None
    assert picked.name == "老泉州面线糊"


def test_meal_agent_prefers_city_signature_food_for_quanzhou() -> None:
    agent = MealRecommendationAgent()
    signature_restaurant = POIRecommendation(
        name="国仔面线糊",
        tags=["泉州小吃"],
        longitude=118.67,
        latitude=24.91,
    )
    generic_restaurant = POIRecommendation(
        name="西街风味小馆",
        tags=["小吃", "地方菜"],
        longitude=118.6701,
        latitude=24.9101,
    )

    picked = agent._pick_restaurant(
        [generic_restaurant, signature_restaurant],
        preferred_kind="breakfast",
        city="泉州",
    )

    assert picked is not None
    assert picked.name == "国仔面线糊"


def test_amap_adapter_prefers_city_signature_restaurant_in_sorting() -> None:
    adapter = AmapMCPAdapter(Settings())
    signature_restaurant = POIRecommendation(
        name="国仔面线糊",
        tags=["泉州小吃"],
        district="鲤城区",
    )
    generic_restaurant = POIRecommendation(
        name="西街风味小馆",
        tags=["小吃", "地方菜"],
        district="鲤城区",
    )

    sorted_restaurants = adapter._sort_restaurants_for_route(
        restaurants=[generic_restaurant, signature_restaurant],
        city="泉州",
        anchor_pois=[],
    )

    assert sorted_restaurants[0].name == "国仔面线糊"


def test_meal_agent_uses_budget_level_for_daily_meal_costs() -> None:
    agent = MealRecommendationAgent()
    request = TripPlanningRequest(
        destination="泉州",
        start_date=date(2026, 4, 7),
        days=1,
        budget_level="luxury",
    )
    day = DayPlan(
        day_number=1,
        date="2026-04-07",
        theme="西街美食",
        overview="overview",
        hotel_area="西街",
        stay=DayStayInfo(area="西街", hotel_name="西街酒店"),
    )

    meals = agent._build_day_meals(request=request, day=day, restaurants=[])

    assert [meal.estimated_cost_cny for meal in meals] == [45, 120, 180]


def test_normalize_plan_days_uses_budget_level_for_missing_room_cost() -> None:
    client = TravelAIClient(Settings())
    request = TripPlanningRequest(
        destination="泉州",
        start_date=date(2026, 4, 7),
        days=1,
        budget_level="economy",
    )
    context = PlanningContext(destination="泉州", weather=WeatherSummary())
    plan = TravelPlan(
        title="Plan",
        summary="Summary",
        weather_summary="",
        best_booking_tip="",
        estimated_budget=BudgetBreakdown(),
        stay_recommendations=[],
        city_tips=[],
        packing_list=[],
        days=[
            DayPlan(
                day_number=1,
                date="2026-04-07",
                theme="Theme",
                overview="Overview",
                hotel_area="西街",
                stay=DayStayInfo(area="西街", hotel_name="西街酒店", room_nightly_cost_cny=0),
            )
        ],
    )

    normalized = client._normalize_plan_days(
        request=request,
        plan=plan,
        context=context,
    )

    assert normalized.days[0].stay.room_nightly_cost_cny == 360


def test_normalize_plan_days_estimates_room_cost_from_hotel_poi() -> None:
    client = TravelAIClient(Settings())
    request = TripPlanningRequest(
        destination="泉州",
        start_date=date(2026, 4, 7),
        days=1,
        budget_level="comfort",
    )
    context = PlanningContext(
        destination="泉州",
        hotels=[
            POIRecommendation(
                name="泉州西街海景温泉度假酒店",
                tags=["100100"],
                rating=4.8,
                district="鲤城区",
            )
        ],
        weather=WeatherSummary(),
    )
    plan = TravelPlan(
        title="Plan",
        summary="Summary",
        weather_summary="",
        best_booking_tip="",
        estimated_budget=BudgetBreakdown(),
        stay_recommendations=[],
        city_tips=[],
        packing_list=[],
        days=[
            DayPlan(
                day_number=1,
                date="2026-04-07",
                theme="西街漫游",
                overview="Overview",
                hotel_area="西街",
                stay=DayStayInfo(area="西街", hotel_name="泉州西街海景温泉度假酒店", room_nightly_cost_cny=0),
            )
        ],
    )

    normalized = client._normalize_plan_days(
        request=request,
        plan=plan,
        context=context,
    )

    assert normalized.days[0].stay.room_nightly_cost_cny == 1000


def test_normalize_plan_days_uses_restaurant_poi_to_correct_meal_cost() -> None:
    client = TravelAIClient(Settings())
    request = TripPlanningRequest(
        destination="泉州",
        start_date=date(2026, 4, 7),
        days=1,
        budget_level="comfort",
    )
    context = PlanningContext(
        destination="泉州",
        restaurants=[
            POIRecommendation(
                name="西街海鲜馆",
                tags=["海鲜", "地方菜"],
                rating=4.8,
                district="鲤城区",
            )
        ],
        weather=WeatherSummary(),
    )
    plan = TravelPlan(
        title="Plan",
        summary="Summary",
        weather_summary="",
        best_booking_tip="",
        estimated_budget=BudgetBreakdown(),
        stay_recommendations=[],
        city_tips=[],
        packing_list=[],
        days=[
            DayPlan(
                day_number=1,
                date="2026-04-07",
                theme="西街美食",
                overview="Overview",
                hotel_area="西街",
                stay=DayStayInfo(area="西街", hotel_name="西街酒店"),
                meals=[
                    MealRecommendation(
                        meal_type="lunch",
                        venue_name="西街海鲜馆",
                        estimated_cost_cny=10,
                    )
                ],
            )
        ],
    )

    normalized = client._normalize_plan_days(
        request=request,
        plan=plan,
        context=context,
    )

    lunch = next(meal for meal in normalized.days[0].meals if meal.meal_type == "lunch")
    assert lunch.estimated_cost_cny == 90
