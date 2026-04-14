from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.utils.json_extract import extract_json_payload


def request_json_payload(
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    temperature: float,
    max_tokens: int | None,
    client: Any,
    model: str | None,
    errors: list[str],
    mode_order: list[str],
    extract_message_content_fn: Callable[[Any], str],
    format_exception_fn: Callable[[Exception], str],
    is_unsupported_json_mode_error_fn: Callable[[Exception, str], bool],
    mark_json_mode_unsupported_fn: Callable[[str | None, str], None],
    is_terminal_request_error_fn: Callable[[Exception], bool],
    set_preferred_json_mode_fn: Callable[[str | None, str], None],
) -> Any:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
    ]

    async def _run() -> dict[str, Any]:
        for mode in mode_order:
            try:
                request_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                }
                if mode != "minimal":
                    request_kwargs["temperature"] = temperature
                if max_tokens is not None:
                    request_kwargs["max_tokens"] = max_tokens
                if mode == "json_object":
                    request_kwargs["response_format"] = {"type": "json_object"}

                completion = await client.chat.completions.create(**request_kwargs)
                content = extract_message_content_fn(completion)
                payload = extract_json_payload(content)
                if isinstance(payload, dict):
                    set_preferred_json_mode_fn(model, mode)
                    return payload
                errors.append(f"{mode}: 返回了不可解析的内容")
            except Exception as exc:
                errors.append(f"{mode}: {format_exception_fn(exc)}")
                if is_unsupported_json_mode_error_fn(exc, mode):
                    mark_json_mode_unsupported_fn(model, mode)
                    continue
                if is_terminal_request_error_fn(exc):
                    break

        raise ValueError("；".join(errors))

    return _run()
