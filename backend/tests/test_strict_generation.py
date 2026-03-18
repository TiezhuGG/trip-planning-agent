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
