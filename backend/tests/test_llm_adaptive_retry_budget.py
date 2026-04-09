import asyncio
from datetime import date

import pytest

from app.config import Settings
from app.schemas.planning import InitialPlanDay, InitialPlanDraft, PlanningContext, RouteSummary, TripPlanningRequest, WeatherSummary
from app.services.ai_client import TravelAIClient


def _settings() -> Settings:
    return Settings(
        openai_api_key="",
        openai_base_url="",
        openai_model="test-model",
        openai_backup_api_key="",
        openai_backup_base_url="",
        openai_backup_model="",
        openai_adaptive_retry_enabled=True,
        openai_adaptive_retry_window=6,
        openai_adaptive_retry_min_samples=4,
        openai_adaptive_retry_low_success_rate=0.5,
    )


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


def test_seed_adaptive_retry_reduces_attempts_on_poor_history() -> None:
    client = TravelAIClient(_settings())
    client.client = object()
    request = _request(days=3)
    calls = {"count": 0}

    for _ in range(4):
        asyncio.run(client._record_adaptive_retry_result("seed::test-model", success=False))

    async def fake_request_json_payload(*args, **kwargs):
        _ = (args, kwargs)
        calls["count"] += 1
        raise ValueError("json_object: timed out")

    client._request_json_payload = fake_request_json_payload  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        asyncio.run(client.build_initial_plan(request))

    assert calls["count"] == 3


def test_compose_adaptive_retry_reduces_attempts_on_poor_history() -> None:
    client = TravelAIClient(_settings())
    client.client = object()
    request = _request(days=3)
    initial_plan = _initial_plan(days=3)
    context = _context(days=3)
    calls = {"count": 0}

    for _ in range(4):
        asyncio.run(client._record_adaptive_retry_result("compose::test-model", success=False))

    async def fake_request_json_payload(*args, **kwargs):
        _ = (args, kwargs)
        calls["count"] += 1
        raise ValueError("json_object: timed out")

    client._request_json_payload = fake_request_json_payload  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        asyncio.run(client.compose_plan(request, initial_plan, context, []))

    assert calls["count"] == 1
