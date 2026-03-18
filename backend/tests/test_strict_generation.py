import asyncio
import re
from datetime import date

import pytest

from app.config import Settings
from app.schemas.planning import (
    Activity,
    BudgetBreakdown,
    DayPlan,
    InitialPlanDay,
    InitialPlanDraft,
    MealRecommendation,
    PlanningContext,
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
    return DayPlan(
        day_number=day_number,
        date=day_date,
        theme=f"Day {day_number}",
        overview="overview",
        hotel_area="West Lake",
        transport_tips=["metro first"],
        meals=[
            MealRecommendation(
                meal_type="lunch",
                venue_name=f"Restaurant {day_number}",
                suggestion="nearby",
                estimated_cost="$0",
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


def _parse_range(value: str) -> tuple[int, int]:
    matches = re.findall(r"\d[\d,]*", value)
    assert len(matches) == 2
    low, high = (int(item.replace(",", "")) for item in matches)
    return low, high


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


def test_deterministic_budget_scales_with_days_and_travelers() -> None:
    settings = Settings()
    client = TravelAIClient(settings)

    request_small = _build_request(days=2, adults=1)
    request_large = _build_request(days=5, adults=2, children=1, seniors=1)

    plan_small = client._apply_deterministic_budget(request_small, _build_plan(days=2))
    plan_large = client._apply_deterministic_budget(request_large, _build_plan(days=5))

    total_small = _parse_range(plan_small.estimated_budget.total_estimate)
    total_large = _parse_range(plan_large.estimated_budget.total_estimate)

    assert total_large[0] > total_small[0]
    assert total_large[1] > total_small[1]


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
