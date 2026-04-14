from __future__ import annotations

from collections import deque
from typing import Any


def retry_delay_seconds(base_delay_seconds: float, attempt: int) -> float:
    return base_delay_seconds * (attempt + 1)


def adaptive_retry_enabled(enabled: bool) -> bool:
    return bool(enabled)


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


def adaptive_retry_budget(
    *,
    adaptive_retry_stats: dict[str, dict[str, Any]],
    channel: str,
    base_attempts: int,
    window: int,
    min_samples: int,
    low_success_rate: float,
) -> int:
    base = max(1, int(base_attempts))
    state = adaptive_retry_state_item(adaptive_retry_stats, channel, window)
    recent = state["recent"]
    samples = len(recent)
    if samples < min_samples:
        return base
    success_rate = (sum(recent) / samples) if samples else 1.0
    consecutive_failures = int(state.get("consecutive_failures", 0))
    if consecutive_failures >= 3:
        return 1
    if success_rate <= max(0.01, low_success_rate / 2):
        return max(1, base - 2)
    if success_rate <= max(0.01, low_success_rate):
        return max(1, base - 1)
    return base


def record_adaptive_retry_result(
    *,
    adaptive_retry_stats: dict[str, dict[str, Any]],
    channel: str,
    success: bool,
    window: int,
) -> None:
    state = adaptive_retry_state_item(adaptive_retry_stats, channel, window)
    recent = state["recent"]
    recent.append(1 if success else 0)
    state["consecutive_failures"] = 0 if success else int(state.get("consecutive_failures", 0)) + 1


def suggest_route_parallelism(
    *,
    adaptive_retry_stats: dict[str, dict[str, Any]],
    day_concurrency: int,
    segment_concurrency: int,
    window: int,
    min_samples: int,
    low_success_rate: float,
) -> tuple[int, int, str | None]:
    base_day = max(1, int(day_concurrency))
    base_segment = max(1, int(segment_concurrency))

    penalty = 0
    worst_success_rate: float | None = None
    max_consecutive_failures = 0

    for channel, _raw_state in adaptive_retry_stats.items():
        if not str(channel).startswith("route_"):
            continue
        state = adaptive_retry_state_item(adaptive_retry_stats, str(channel), window)
        recent = state.get("recent")
        if isinstance(recent, deque):
            samples = len(recent)
            if samples >= min_samples:
                success_rate = (sum(recent) / samples) if samples else 1.0
                if worst_success_rate is None or success_rate < worst_success_rate:
                    worst_success_rate = success_rate
        max_consecutive_failures = max(
            max_consecutive_failures,
            int(state.get("consecutive_failures", 0)),
        )

    if max_consecutive_failures >= 4:
        penalty = max(penalty, 2)
    elif max_consecutive_failures >= 2:
        penalty = max(penalty, 1)

    if worst_success_rate is not None:
        if worst_success_rate <= max(0.01, low_success_rate / 2):
            penalty = max(penalty, 2)
        elif worst_success_rate <= max(0.01, low_success_rate):
            penalty = max(penalty, 1)

    if penalty <= 0:
        return base_day, base_segment, None

    adjusted_day = max(1, base_day - penalty)
    adjusted_segment = max(1, base_segment - penalty)
    warning = (
        f"route 并发已自适应下调: day {base_day}->{adjusted_day}, "
        f"segment {base_segment}->{adjusted_segment}。"
    )
    return adjusted_day, adjusted_segment, warning


def is_rate_limit_text(text: str) -> bool:
    if not text:
        return False
    upper = text.upper()
    markers = (
        "CUQPS_HAS_EXCEEDED_THE_LIMIT",
        "QPS_HAS_EXCEEDED_THE_LIMIT",
        "OVER_QUERY_LIMIT",
        "DAILY_QUERY_OVER_LIMIT",
    )
    return any(marker in upper for marker in markers)


def is_rate_limit_error(exc: Exception) -> bool:
    if is_rate_limit_text(str(exc)):
        return True
    cause = exc.__cause__ or exc.__context__
    if isinstance(cause, Exception) and cause is not exc:
        return is_rate_limit_error(cause)
    return False
