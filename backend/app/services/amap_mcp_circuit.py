from __future__ import annotations

import asyncio
import math
from typing import Any

from app.services.mcp_stdio_client import MCPProtocolError


def tool_circuit_key(purpose: str, tool_name: str) -> str:
    return f"{purpose}::{tool_name}"


def tool_circuit_enabled(enabled: bool) -> bool:
    return bool(enabled)


def tool_circuit_open_window_seconds(open_seconds: float) -> float:
    return max(0.01, float(open_seconds))


def tool_circuit_state_item(
    tool_circuit_state: dict[str, dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    existing = tool_circuit_state.get(key)
    if existing is not None:
        return existing
    state = {
        "status": "closed",
        "open_until": 0.0,
        "consecutive_failures": 0,
        "consecutive_slow_calls": 0,
        "trial_in_flight": False,
        "reason": "",
    }
    tool_circuit_state[key] = state
    return state


def open_tool_circuit_unlocked(
    state: dict[str, Any],
    now: float,
    reason: str,
    open_window_seconds: float,
) -> None:
    state["status"] = "open"
    state["open_until"] = now + tool_circuit_open_window_seconds(open_window_seconds)
    state["consecutive_failures"] = 0
    state["consecutive_slow_calls"] = 0
    state["trial_in_flight"] = False
    state["reason"] = reason


def before_tool_call_unlocked(
    *,
    state: dict[str, Any],
    now: float,
    purpose: str,
    tool_name: str,
) -> None:
    status = str(state.get("status", "closed"))
    if status == "open":
        remaining = float(state.get("open_until", 0.0)) - now
        if remaining > 0:
            raise MCPProtocolError(
                f"{tool_name} 熔断中 ({purpose})，约 {int(math.ceil(remaining))}s 后重试。"
            )
        state["status"] = "half_open"
        state["trial_in_flight"] = False
    if str(state.get("status", "closed")) == "half_open":
        if bool(state.get("trial_in_flight", False)):
            raise MCPProtocolError(f"{tool_name} 半开探测中 ({purpose})，请稍后重试。")
        state["trial_in_flight"] = True


def after_tool_call_success_unlocked(
    *,
    state: dict[str, Any],
    now: float,
    elapsed_seconds: float,
    slow_call_seconds: float,
    slow_call_threshold: int,
    open_window_seconds: float,
) -> None:
    status = str(state.get("status", "closed"))
    state["trial_in_flight"] = False
    if status == "half_open":
        state["status"] = "closed"
        state["open_until"] = 0.0
        state["consecutive_failures"] = 0
        state["consecutive_slow_calls"] = 0
        state["reason"] = ""
        return
    if status == "open":
        return
    state["consecutive_failures"] = 0
    if slow_call_seconds <= 0 or slow_call_threshold <= 0:
        state["consecutive_slow_calls"] = 0
        return
    if elapsed_seconds >= slow_call_seconds:
        state["consecutive_slow_calls"] = int(state.get("consecutive_slow_calls", 0)) + 1
        if int(state.get("consecutive_slow_calls", 0)) >= slow_call_threshold:
            open_tool_circuit_unlocked(
                state,
                now,
                reason=f"连续慢调用达到阈值 ({slow_call_threshold})",
                open_window_seconds=open_window_seconds,
            )
        return
    state["consecutive_slow_calls"] = 0


def is_circuit_breaker_failure(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.CancelledError):
        return False
    return True


def after_tool_call_failure_unlocked(
    *,
    state: dict[str, Any],
    now: float,
    exc: BaseException,
    failure_threshold: int,
    open_window_seconds: float,
) -> None:
    status = str(state.get("status", "closed"))
    state["trial_in_flight"] = False
    if status == "half_open":
        open_tool_circuit_unlocked(
            state,
            now,
            reason=f"半开探测失败: {exc.__class__.__name__}",
            open_window_seconds=open_window_seconds,
        )
        return
    if status == "open":
        return
    if not is_circuit_breaker_failure(exc):
        return
    state["consecutive_slow_calls"] = 0
    state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
    if failure_threshold <= 0:
        return
    if int(state.get("consecutive_failures", 0)) >= failure_threshold:
        open_tool_circuit_unlocked(
            state,
            now,
            reason=f"连续失败达到阈值 ({failure_threshold})",
            open_window_seconds=open_window_seconds,
        )


def tool_circuit_warning_messages(
    *,
    tool_circuit_state: dict[str, dict[str, Any]],
    now: float,
) -> list[str]:
    warnings: list[str] = []
    for key, state in tool_circuit_state.items():
        status = str(state.get("status", "closed"))
        if status != "open":
            continue
        remaining = float(state.get("open_until", 0.0)) - now
        if remaining <= 0:
            continue
        purpose, _, tool_name = key.partition("::")
        reason = str(state.get("reason", "")).strip()
        reason_text = f"，原因: {reason}" if reason else ""
        warnings.append(
            f"MCP 工具熔断生效: {tool_name} ({purpose})，约 {int(math.ceil(remaining))}s 后重试{reason_text}。"
        )
    return warnings
