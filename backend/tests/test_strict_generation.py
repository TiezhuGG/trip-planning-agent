import asyncio
from datetime import date

import pytest

from app.config import Settings
from app.schemas.planning import (
    Activity,
    BudgetBreakdown,
    DayCostBreakdown,
    DayPlan,
    DayStayInfo,
    InitialPlanDay,
    InitialPlanDraft,
    MealRecommendation,
    POIRecommendation,
    PlanningContext,
    RouteSummary,
    StayRecommendation,
    TravelPlan,
    TripPlanningRequest,
    WeatherSummary,
)
from app.services.ai_client import TravelAIClient


def _build_request(days: int, adults: int, children: int = 0, seniors: int = 0) -> TripPlanningRequest:
    return TripPlanningRequest(
        destination="\u676d\u5dde",
        start_date=date(2026, 3, 10),
        days=days,
        interests=["food", "culture"],
        travelers={"adults": adults, "children": children, "seniors": seniors},
    )


def _build_day(day_number: int, day_date: str) -> DayPlan:
    accommodation = 180 + day_number * 10
    transport = 30 + day_number
    food = 80 + day_number * 5
    tickets = 60 + day_number * 3
    extras = 20
    total = accommodation + transport + food + tickets + extras
    return DayPlan(
        day_number=day_number,
        date=day_date,
        theme=f"Day {day_number}",
        overview="overview",
        hotel_area="West Lake",
        stay=DayStayInfo(
            area="West Lake",
            hotel_name=f"Hotel {day_number}",
            reason="nearby",
            room_nightly_cost_cny=360 + day_number * 20,
        ),
        cost_breakdown=DayCostBreakdown(
            accommodation_per_person_cny=accommodation,
            transport_per_person_cny=transport,
            food_per_person_cny=food,
            tickets_per_person_cny=tickets,
            extras_per_person_cny=extras,
            total_per_person_cny=total,
        ),
        transport_tips=["metro first"],
        meals=[
            MealRecommendation(
                meal_type="lunch",
                venue_name=f"Restaurant {day_number}",
                suggestion="nearby",
                estimated_cost="¥80/人",
                estimated_cost_cny=80,
            )
        ],
        activities=[
            Activity(
                start_time="09:00",
                end_time="11:00",
                title=f"Activity {day_number}",
                category="sightseeing",
                description="desc",
                location_name="spot",
                expected_cost="¥60/人",
                ticket_cost_cny=60,
            )
        ],
        route_summaries=[
            RouteSummary(
                day_number=day_number,
                title=f"Day {day_number} Route",
                from_name="Hotel",
                to_name="Spot",
                estimated_transport_cost_cny=30,
            )
        ],
    )


def _build_plan(days: int) -> TravelPlan:
    return TravelPlan(
        title="Plan",
        summary="Summary",
        weather_summary="Weather",
        best_booking_tip="Tip",
        estimated_budget=BudgetBreakdown(),
        stay_recommendations=[],
        city_tips=[],
        packing_list=[],
        days=[_build_day(index + 1, f"2026-03-{10 + index:02d}") for index in range(days)],
    )


def _parse_amount(value: str) -> int:
    digits = "".join(ch for ch in value if ch.isdigit() or ch == ",")
    return int(digits.replace(",", "")) if digits else 0


def test_final_plan_integrity_rejects_day_count_mismatch() -> None:
    settings = Settings()
    client = TravelAIClient(settings)
    request = _build_request(days=3, adults=2)
    plan = _build_plan(days=2)

    with pytest.raises(ValueError):
        client._ensure_final_plan_integrity(request, plan)


def test_final_plan_integrity_rejects_duplicate_day_number() -> None:
    settings = Settings()
    client = TravelAIClient(settings)
    request = _build_request(days=3, adults=2)
    plan = _build_plan(days=3)
    plan.days[1].day_number = 1

    with pytest.raises(ValueError):
        client._ensure_final_plan_integrity(request, plan)


def test_deterministic_budget_aggregates_daily_breakdown() -> None:
    settings = Settings()
    client = TravelAIClient(settings)

    request_small = _build_request(days=2, adults=1)
    request_large = _build_request(days=5, adults=2, children=1, seniors=1)
    source_small = _build_plan(days=2)
    source_large = _build_plan(days=5)

    expected_small = sum(day.cost_breakdown.total_per_person_cny for day in source_small.days)
    expected_large = sum(day.cost_breakdown.total_per_person_cny for day in source_large.days)

    plan_small = client._apply_deterministic_budget(request_small, source_small)
    plan_large = client._apply_deterministic_budget(request_large, source_large)

    total_small = _parse_amount(plan_small.estimated_budget.total_estimate)
    total_large = _parse_amount(plan_large.estimated_budget.total_estimate)

    assert total_small == expected_small
    assert total_large == expected_large


def test_build_initial_plan_requires_llm_configuration() -> None:
    settings = Settings(openai_api_key="", openai_model="", openai_base_url="")
    client = TravelAIClient(settings)
    request = _build_request(days=2, adults=2)

    with pytest.raises(RuntimeError):
        asyncio.run(client.build_initial_plan(request))


def test_compose_plan_requires_llm_configuration() -> None:
    settings = Settings(openai_api_key="", openai_model="", openai_base_url="")
    client = TravelAIClient(settings)
    request = _build_request(days=2, adults=2)
    initial_plan = InitialPlanDraft(
        summary="summary",
        days=[
            InitialPlanDay(
                day_number=1,
                date="2026-03-10",
                theme="Theme 1",
                focus="Focus 1",
                must_visit=[],
            ),
            InitialPlanDay(
                day_number=2,
                date="2026-03-11",
                theme="Theme 2",
                focus="Focus 2",
                must_visit=[],
            ),
        ],
    )
    context = PlanningContext(destination="\u676d\u5dde", weather=WeatherSummary())

    with pytest.raises(RuntimeError):
        asyncio.run(client.compose_plan(request, initial_plan, context, []))


def test_normalize_plan_days_enforces_three_meals_and_recomputes_daily_food_cost() -> None:
    settings = Settings()
    client = TravelAIClient(settings)
    request = _build_request(days=1, adults=2)
    source = _build_plan(days=1)
    context = PlanningContext(
        destination="杭州",
        restaurants=[
            POIRecommendation(name="餐厅A", tags=["杭帮菜"]),
            POIRecommendation(name="餐厅B", tags=["本帮菜"]),
        ],
        weather=WeatherSummary(),
    )

    normalized = client._normalize_plan_days(request, source, context)
    day = normalized.days[0]
    meal_types = [meal.meal_type for meal in day.meals]

    assert meal_types[:3] == ["breakfast", "lunch", "dinner"]
    assert set(meal_types) >= {"breakfast", "lunch", "dinner"}
    assert day.cost_breakdown.food_per_person_cny == sum(item.estimated_cost_cny for item in day.meals)
    assert day.cost_breakdown.total_per_person_cny == (
        day.cost_breakdown.accommodation_per_person_cny
        + day.cost_breakdown.transport_per_person_cny
        + day.cost_breakdown.food_per_person_cny
        + day.cost_breakdown.tickets_per_person_cny
        + day.cost_breakdown.extras_per_person_cny
    )


def test_finalize_plan_with_routes_syncs_route_summaries_and_activity_transport() -> None:
    settings = Settings()
    client = TravelAIClient(settings)
    request = _build_request(days=1, adults=2)
    source = _build_plan(days=1)
    source.days[0].activities = [
        Activity(
            start_time="09:00",
            end_time="10:00",
            title="West Lake",
            category="sightseeing",
            description="desc",
            location_name="West Lake",
        ),
        Activity(
            start_time="10:30",
            end_time="12:00",
            title="Lingyin",
            category="sightseeing",
            description="desc",
            location_name="Lingyin Temple",
        ),
    ]
    context = PlanningContext(
        destination="\u676d\u5dde",
        routes=[
            RouteSummary(
                day_number=1,
                title="Route 1",
                from_name="Hotel 1",
                to_name="West Lake",
                mode="walking",
                duration_text="15分钟",
                distance_text="1.2公里",
                estimated_transport_cost_cny=0,
            ),
            RouteSummary(
                day_number=1,
                title="Route 2",
                from_name="West Lake",
                to_name="Lingyin Temple",
                mode="transit",
                duration_text="25分钟",
                distance_text="6.0公里",
                estimated_transport_cost_cny=8,
            ),
        ],
        weather=WeatherSummary(),
    )

    finalized = client.finalize_plan_with_routes(request, source, context)
    day = finalized.days[0]

    assert [(route.from_name, route.to_name) for route in day.route_summaries] == [
        ("Hotel 1", "West Lake"),
        ("West Lake", "Lingyin Temple"),
    ]
    assert day.activities[0].transport_from_previous == "从 Hotel 1 前往 West Lake，建议步行，15分钟，1.2公里"
    assert day.activities[1].transport_from_previous == "从 West Lake 前往 Lingyin Temple，建议公共交通，25分钟，6.0公里"
    assert day.transport_tips[-1] == "从 West Lake 前往 Lingyin Temple，建议公共交通，25分钟，6.0公里"


def test_normalize_plan_days_replaces_far_hotel_with_activity_area_hotel() -> None:
    settings = Settings()
    client = TravelAIClient(settings)
    request = _build_request(days=1, adults=2)
    source = _build_plan(days=1)
    source.days[0].hotel_area = "西街片区"
    source.days[0].stay = DayStayInfo(
        area="崇武片区",
        hotel_name="崇武海景湾度假酒店",
        reason="海景资源丰富",
        room_nightly_cost_cny=520,
    )
    source.days[0].activities = [
        Activity(
            start_time="09:00",
            end_time="10:30",
            title="开元寺",
            category="sightseeing",
            description="desc",
            location_name="开元寺",
        ),
        Activity(
            start_time="11:00",
            end_time="13:00",
            title="西街",
            category="explore",
            description="desc",
            location_name="西街",
        ),
    ]
    context = PlanningContext(
        destination="泉州",
        hotels=[
            POIRecommendation(name="泉州西街行舍(开元寺店)", address="鲤中街道通政社区会通巷57-2号"),
            POIRecommendation(name="锦江之星(泉州西街开元寺店)", address="新华北路373-391号"),
        ],
        weather=WeatherSummary(),
    )

    normalized = client._normalize_plan_days(request, source, context)
    day = normalized.days[0]

    assert day.hotel_area == "西街片区"
    assert day.stay.hotel_name == "泉州西街行舍(开元寺店)"
    assert day.stay.area == "西街片区"
    assert "开元寺" in day.stay.reason


def test_normalize_plan_days_rebuilds_stay_recommendations_from_daily_stays() -> None:
    settings = Settings()
    client = TravelAIClient(settings)
    request = _build_request(days=2, adults=2)
    source = _build_plan(days=2)
    source.stay_recommendations = [
        StayRecommendation(
            area="崇武片区",
            hotel_name="崇武海景湾度假酒店",
            reason="海景资源丰富",
            nightly_budget="¥680/晚",
        )
    ]
    source.days[0].hotel_area = "西街片区"
    source.days[0].stay = DayStayInfo(
        area="西街片区",
        hotel_name="泉州西街行舍(开元寺店)",
        reason="步行可达开元寺和西街",
        room_nightly_cost_cny=500,
    )
    source.days[1].hotel_area = "钟楼区域"
    source.days[1].stay = DayStayInfo(
        area="钟楼区域",
        hotel_name="汉庭酒店(泉州古城西街店)",
        reason="靠近第二天活动区域",
        room_nightly_cost_cny=400,
    )
    context = PlanningContext(destination="泉州", weather=WeatherSummary())

    normalized = client._normalize_plan_days(request, source, context)

    assert [(item.hotel_name, item.area) for item in normalized.stay_recommendations] == [
        ("泉州西街行舍(开元寺店)", "西街片区"),
        ("汉庭酒店(泉州古城西街店)", "钟楼区域"),
    ]
    assert normalized.stay_recommendations[0].nightly_budget == "¥500/晚"


def test_normalize_plan_days_adds_supplemental_activity_when_day_ends_too_early() -> None:
    settings = Settings()
    client = TravelAIClient(settings)
    request = _build_request(days=1, adults=2)
    source = _build_plan(days=1)
    source.days[0].hotel_area = "清源山片区"
    source.days[0].activities = [
        Activity(
            start_time="09:00",
            end_time="12:00",
            title="清源山登山",
            category="sightseeing",
            description="desc",
            location_name="清源山君岩景区",
        )
    ]
    context = PlanningContext(
        destination="泉州",
        attractions=[POIRecommendation(name="清源山老君岩", address="清源山片区")],
        weather=WeatherSummary(),
    )

    normalized = client._normalize_plan_days(request, source, context)
    day = normalized.days[0]

    assert len(day.activities) >= 2
    assert day.activities[-1].start_time >= "14:00"
