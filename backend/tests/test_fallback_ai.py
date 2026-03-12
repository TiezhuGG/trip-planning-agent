from datetime import date

from app.config import Settings
from app.schemas.planning import PlanningContext, TripPlanningRequest, WeatherSummary
from app.services.ai_client import TravelAIClient


def test_fallback_initial_plan_matches_requested_days() -> None:
    settings = Settings()
    client = TravelAIClient(settings)

    request = TripPlanningRequest(
        destination="杭州",
        start_date=date(2026, 3, 10),
        days=4,
        interests=["美食", "文化"],
    )

    draft = client._fallback_initial_plan(request)

    assert len(draft.days) == 4
    assert draft.days[0].poi_query.startswith("杭州")


def test_fallback_planner_generates_requested_days() -> None:
    settings = Settings()
    client = TravelAIClient(settings)

    request = TripPlanningRequest(
        destination="杭州",
        start_date=date(2026, 3, 10),
        days=4,
        interests=["美食", "文化"],
    )
    initial_plan = client._fallback_initial_plan(request)
    context = PlanningContext(
        destination="杭州",
        weather=WeatherSummary(
            overview="天气稳定，适合出游",
            temperature_range="18-26°C",
        ),
    )

    plan = client._fallback_plan(request, initial_plan, context)

    assert len(plan.days) == 4
    assert "杭州" in plan.title
    assert plan.days[0].theme
