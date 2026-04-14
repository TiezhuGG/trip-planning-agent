from __future__ import annotations

from collections import deque
from typing import Any


def extract_message_content(completion: Any) -> str:
    choices = getattr(completion, "choices", None) or []
    if not choices:
        return "{}"
    message = getattr(choices[0], "message", None)
    if message is None:
        return "{}"
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                fragments.append(str(item.get("text", "")))
        return "\n".join(fragment for fragment in fragments if fragment)
    return str(content or "{}")


def normalize_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions", "/responses"):
        if normalized.lower().endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def format_exception(exc: Exception) -> str:
    parts = [f"{exc.__class__.__name__}: {exc}"] if str(exc) else [exc.__class__.__name__]
    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc:
        if str(cause):
            parts.append(f"cause={cause.__class__.__name__}: {cause}")
        else:
            parts.append(f"cause={cause.__class__.__name__}")
    return " | ".join(parts)


def request_mode_order(
    model: str | None,
    preferred_modes_by_model: dict[str, str],
    unsupported_modes_by_model: dict[str, set[str]],
) -> list[str]:
    default_modes = ["json_object", "plain_text_json", "minimal"]
    key = str(model or "")
    unsupported = unsupported_modes_by_model.get(key, set())
    available_modes = [mode for mode in default_modes if mode not in unsupported]
    if not available_modes:
        return ["minimal"]
    preferred = preferred_modes_by_model.get(key)
    if not preferred or preferred not in available_modes:
        return available_modes
    return [preferred] + [mode for mode in available_modes if mode != preferred]


def mark_json_mode_unsupported(
    model: str | None,
    mode: str,
    preferred_modes_by_model: dict[str, str],
    unsupported_modes_by_model: dict[str, set[str]],
) -> None:
    key = str(model or "")
    if not key:
        return
    unsupported = unsupported_modes_by_model.get(key)
    if unsupported is None:
        unsupported = set()
        unsupported_modes_by_model[key] = unsupported
    unsupported.add(mode)
    preferred = preferred_modes_by_model.get(key)
    if preferred == mode:
        preferred_modes_by_model.pop(key, None)


def is_unsupported_json_mode_error(exc: Exception, mode: str) -> bool:
    if mode != "json_object":
        return False
    message = str(exc).lower()
    response_format_markers = (
        "response_format",
        "json_object",
        "json schema",
        "json_schema",
    )
    unsupported_markers = (
        "not support",
        "unsupported",
        "invalid",
        "invalid_request_error",
        "badrequesterror",
        "not allowed",
    )
    return any(marker in message for marker in response_format_markers) and any(
        marker in message for marker in unsupported_markers
    )


def is_terminal_request_error(
    exc: Exception,
    should_fallback_to_template: Any,
) -> bool:
    if should_fallback_to_template(exc):
        return True
    message = str(exc).lower()
    terminal_keywords = (
        "unauthorized",
        "authentication",
        "invalid api key",
        "permission denied",
        "forbidden",
        "error code: 401",
        "error code: 403",
        "invalid_request_error",
    )
    return any(keyword in message for keyword in terminal_keywords)


def compose_retry_specs(fast_mode: bool) -> list[tuple[float, int]]:
    if fast_mode:
        return [
            (0.25, 7168),
            (0.0, 8192),
        ]
    return [
        (0.35, 8192),
        (0.15, 9216),
        (0.0, 10240),
    ]


def seed_retry_specs(fast_mode: bool) -> list[tuple[float, int]]:
    if fast_mode:
        return [
            (0.3, 2048),
            (0.1, 3072),
        ]
    return [
        (0.4, 2048),
        (0.2, 3072),
        (0.1, 3072),
        (0.0, 4096),
        (0.0, 4096),
    ]


def retry_backoff_seconds(fast_mode: bool, attempt: int) -> float:
    if fast_mode:
        return min(0.3, 0.1 * attempt)
    return min(2.0, 0.4 * attempt)


def trim_adaptive_retry_specs(
    retry_specs: list[tuple[float, int]],
    adaptive_retry_stats: dict[str, dict[str, Any]],
    channel: str,
    window: int,
    min_samples: int,
    low_success_rate: float,
) -> list[tuple[float, int]]:
    specs = list(retry_specs)
    state = adaptive_retry_state_item(adaptive_retry_stats, channel, window)
    recent = state["recent"]
    samples = len(recent)
    if samples < min_samples:
        return specs

    success_rate = (sum(recent) / samples) if samples else 1.0
    consecutive_failures = int(state.get("consecutive_failures", 0))
    trim = 0
    if consecutive_failures >= 3:
        trim = max(trim, 2)
    elif consecutive_failures >= 2:
        trim = max(trim, 1)
    if success_rate <= max(0.01, low_success_rate / 2):
        trim = max(trim, 2)
    elif success_rate <= max(0.01, low_success_rate):
        trim = max(trim, 1)
    if trim <= 0:
        return specs
    return specs[: max(1, len(specs) - trim)]


def record_adaptive_retry_result(
    adaptive_retry_stats: dict[str, dict[str, Any]],
    channel: str,
    success: bool,
    window: int,
) -> None:
    state = adaptive_retry_state_item(adaptive_retry_stats, channel, window)
    recent = state["recent"]
    recent.append(1 if success else 0)
    state["consecutive_failures"] = 0 if success else int(state.get("consecutive_failures", 0)) + 1


def adaptive_retry_state_item(
    adaptive_retry_stats: dict[str, dict[str, Any]],
    channel: str,
    window: int,
) -> dict[str, Any]:
    state = adaptive_retry_stats.get(channel)
    if state is None:
        state = {
            "recent": deque(maxlen=window),
            "consecutive_failures": 0,
        }
        adaptive_retry_stats[channel] = state
        return state

    recent = state.get("recent")
    if not isinstance(recent, deque):
        recent = deque(recent or [], maxlen=window)
        state["recent"] = recent
    if recent.maxlen != window:
        state["recent"] = deque(list(recent), maxlen=window)
    return state
