import asyncio
from datetime import date

import pytest

from app.config import Settings
from app.schemas.planning import TripPlanningRequest
from app.services.ai_client import TravelAIClient


def _request(days: int = 3) -> TripPlanningRequest:
    return TripPlanningRequest(
        destination="上海",
        start_date=date(2026, 3, 20),
        days=days,
        interests=["美食", "文化"],
    )


def _initial_payload(days: int) -> dict:
    return {
        "summary": "seed summary",
        "days": [
            {
                "day_number": index + 1,
                "date": f"2026-03-{20 + index:02d}",
                "theme": f"Theme {index + 1}",
                "focus": f"Focus {index + 1}",
                "must_visit": [],
                "poi_query": "上海 景点",
                "dining_query": "上海 美食",
            }
            for index in range(days)
        ],
    }


def test_seed_retries_on_provider_400_and_succeeds() -> None:
    client = TravelAIClient(Settings())
    client.client = object()
    request = _request(days=3)
    calls = {"count": 0}

    async def fake_request_json_payload(*args, **kwargs):
        _ = (args, kwargs)
        calls["count"] += 1
        if calls["count"] == 1:
            raise ValueError(
                "json_object: BadRequestError: Error code: 400 - "
                "{'error': {'message': 'Output data may contain inappropriate content.'}}"
            )
        return _initial_payload(days=3)

    client._request_json_payload = fake_request_json_payload  # type: ignore[method-assign]

    result = asyncio.run(client.build_initial_plan(request))

    assert len(result.draft.days) == 3
    assert calls["count"] >= 2
    assert any("seed 第 1 次失败" in warning for warning in result.warnings)


def test_seed_fails_after_exhausting_retries() -> None:
    client = TravelAIClient(Settings())
    client.client = object()
    request = _request(days=3)
    calls = {"count": 0}

    async def fake_request_json_payload(*args, **kwargs):
        _ = (args, kwargs)
        calls["count"] += 1
        raise ValueError("json_object: timed out")

    client._request_json_payload = fake_request_json_payload  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        asyncio.run(client.build_initial_plan(request))

    assert calls["count"] == 5
