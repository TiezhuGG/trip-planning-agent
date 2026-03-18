import asyncio
from datetime import date

import pytest

from app.config import Settings
from app.schemas.planning import (
    InitialPlanDay,
    InitialPlanDraft,
    PlanningContext,
    RouteSummary,
    TripPlanningRequest,
    WeatherSummary,
)
from app.services.ai_client import TravelAIClient


def _request(days: int = 3) -> TripPlanningRequest:
    return TripPlanningRequest(
        destination="上海",
        start_date=date(2026, 3, 20),
        days=days,
        interests=["美食", "文化"],
    )


def _initial_plan(days: int = 3) -> InitialPlanDraft:
    return InitialPlanDraft(
        summary="seed",
        days=[
            InitialPlanDay(
                day_number=index + 1,
                date=f"2026-03-{20 + index:02d}",
                theme=f"Theme {index + 1}",
                focus=f"Focus {index + 1}",
                must_visit=[],
            )
            for index in range(days)
        ],
    )


def _context(days: int = 3) -> PlanningContext:
    return PlanningContext(
        destination="上海",
        routes=[
            RouteSummary(
                day_number=index + 1,
                title=f"Route {index + 1}",
                from_name="Hotel",
                to_name=f"Spot {index + 1}",
            )
            for index in range(days)
        ],
        weather=WeatherSummary(),
    )


def _plan_payload(days: int) -> dict:
    return {
        "title": "Plan",
        "summary": "Summary",
        "weather_summary": "Weather",
        "best_booking_tip": "Tip",
        "estimated_budget": {
            "currency": "CNY",
            "accommodation": "",
            "transport": "",
            "food": "",
            "tickets": "",
            "extras": "",
            "total_estimate": "",
        },
        "stay_recommendations": [],
        "city_tips": [],
        "packing_list": [],
        "days": [
            {
                "day_number": index + 1,
                "date": f"2026-03-{20 + index:02d}",
                "theme": f"Theme {index + 1}",
                "overview": "overview",
                "hotel_area": "center",
                "transport_tips": [],
                "meals": [
                    {
                        "meal_type": "lunch",
                        "venue_name": f"Meal {index + 1}",
                        "cuisine": "",
                        "suggestion": "",
                        "estimated_cost": "¥50/人",
                    }
                ],
                "activities": [
                    {
                        "start_time": "09:00",
                        "end_time": "10:00",
                        "title": f"Act {index + 1}",
                        "category": "sightseeing",
                        "description": "desc",
                        "location_name": "spot",
                    }
                ],
            }
            for index in range(days)
        ],
    }


def test_compose_retries_on_day_mismatch_and_succeeds_with_repair() -> None:
    client = TravelAIClient(Settings())
    client.client = object()
    request = _request(days=3)
    initial_plan = _initial_plan(days=3)
    context = _context(days=3)

    calls = {"count": 0}

    async def fake_request_json_payload(*args, **kwargs):
        _ = (args, kwargs)
        calls["count"] += 1
        if calls["count"] == 1:
            return _plan_payload(days=1)
        return _plan_payload(days=3)

    client._request_json_payload = fake_request_json_payload  # type: ignore[method-assign]

    result = asyncio.run(client.compose_plan(request, initial_plan, context, []))

    assert len(result.plan.days) == 3
    assert calls["count"] >= 2
    assert any("补全修复并成功" in message for message in result.warnings)


def test_compose_retries_on_unparseable_json_error_and_succeeds() -> None:
    client = TravelAIClient(Settings())
    client.client = object()
    request = _request(days=3)
    initial_plan = _initial_plan(days=3)
    context = _context(days=3)

    calls = {"count": 0}

    async def fake_request_json_payload(*args, **kwargs):
        _ = (args, kwargs)
        calls["count"] += 1
        if calls["count"] == 1:
            raise ValueError("json_object: 返回了不可解析的内容")
        return _plan_payload(days=3)

    client._request_json_payload = fake_request_json_payload  # type: ignore[method-assign]

    result = asyncio.run(client.compose_plan(request, initial_plan, context, []))

    assert len(result.plan.days) == 3
    assert calls["count"] >= 2
    assert any("第 1 次失败" in message for message in result.warnings)


def test_compose_fails_after_exhausting_retries() -> None:
    client = TravelAIClient(Settings())
    client.client = object()
    request = _request(days=3)
    initial_plan = _initial_plan(days=3)
    context = _context(days=3)

    async def fake_request_json_payload(*args, **kwargs):
        _ = (args, kwargs)
        return _plan_payload(days=1)

    client._request_json_payload = fake_request_json_payload  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        asyncio.run(client.compose_plan(request, initial_plan, context, []))
