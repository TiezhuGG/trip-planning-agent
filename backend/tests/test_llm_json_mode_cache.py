import asyncio
from types import SimpleNamespace
from typing import Any

from app.config import Settings
from app.services.ai_client import TravelAIClient


class _DummyCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs) -> Any:
        self.calls.append(kwargs)
        if "response_format" in kwargs:
            raise ValueError("invalid_request_error: response_format json_object is not supported")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"status":"ok"}'))]
        )


class _DummyClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_DummyCompletions())


def test_json_object_unsupported_mode_is_cached_and_skipped() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
    )
    ai_client = TravelAIClient(settings)
    dummy = _DummyClient()

    async def _run() -> None:
        first = await ai_client._request_json_payload(
            system_prompt="test",
            user_payload={"task": "ping"},
            temperature=0,
            client=dummy,
            model="m1",
        )
        second = await ai_client._request_json_payload(
            system_prompt="test",
            user_payload={"task": "ping"},
            temperature=0,
            client=dummy,
            model="m1",
        )
        assert first.get("status") == "ok"
        assert second.get("status") == "ok"

    asyncio.run(_run())

    # First request: json_object fails + plain_text_json success => 2 calls.
    # Second request: skip cached unsupported json_object => 1 call.
    assert len(dummy.chat.completions.calls) == 3
    assert "response_format" in dummy.chat.completions.calls[0]
    assert "response_format" not in dummy.chat.completions.calls[2]
