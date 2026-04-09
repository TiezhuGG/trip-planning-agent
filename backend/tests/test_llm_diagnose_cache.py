import asyncio
import time

from app.config import Settings
from app.services.ai_client import TravelAIClient


def test_llm_diagnose_cache_hits_within_ttl() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        openai_diagnose_cache_seconds=60,
    )
    client = TravelAIClient(settings)
    client.client = object()

    calls = 0

    async def fake_request_json_payload(*args, **kwargs):
        nonlocal calls
        _ = (args, kwargs)
        calls += 1
        return {"status": "ok"}

    client._request_json_payload = fake_request_json_payload  # type: ignore[method-assign]

    first = asyncio.run(client.diagnose(check_connection=True))
    second = asyncio.run(client.diagnose(check_connection=True))

    assert first.reachable is True
    assert second.reachable is True
    assert calls == 1


def test_llm_diagnose_cache_expires() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        openai_diagnose_cache_seconds=0.02,
    )
    client = TravelAIClient(settings)
    client.client = object()

    calls = 0

    async def fake_request_json_payload(*args, **kwargs):
        nonlocal calls
        _ = (args, kwargs)
        calls += 1
        return {"status": "ok"}

    client._request_json_payload = fake_request_json_payload  # type: ignore[method-assign]

    asyncio.run(client.diagnose(check_connection=True))
    time.sleep(0.04)
    asyncio.run(client.diagnose(check_connection=True))

    assert calls == 2
