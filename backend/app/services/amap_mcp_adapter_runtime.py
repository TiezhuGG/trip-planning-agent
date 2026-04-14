from __future__ import annotations

import time
from typing import Any

from app.schemas.planning import POIRecommendation, ToolCallRecord
from app.services.amap_mcp_circuit import (
    after_tool_call_failure_unlocked,
    after_tool_call_success_unlocked,
    before_tool_call_unlocked,
    is_circuit_breaker_failure,
    open_tool_circuit_unlocked,
    tool_circuit_enabled,
    tool_circuit_key,
    tool_circuit_open_window_seconds,
    tool_circuit_state_item,
    tool_circuit_warning_messages,
)
from app.services.amap_mcp_execution import call_tool_for_purpose as call_tool_for_purpose_runtime
from app.services.amap_mcp_route_runtime import (
    call_route_tool_with_retry as call_route_tool_with_retry_runtime,
    call_route_webservice_with_retry as call_route_webservice_with_retry_runtime,
)
from app.services.amap_mcp_runtime import (
    adaptive_retry_budget,
    adaptive_retry_enabled,
    adaptive_retry_state_item,
    is_rate_limit_error,
    is_rate_limit_text,
    record_adaptive_retry_result,
    retry_delay_seconds,
    suggest_route_parallelism as suggest_route_parallelism_runtime,
)
from app.services.amap_mcp_tools import (
    catalog_is_fresh,
    fetch_tool_catalog,
    purpose_keywords,
    resolve_search_detail_tool_name,
    resolve_tool_name,
)


class AmapMCPAdapterRuntimeMixin:
    def _amap_web_service_key(self) -> str:
        return str(self.settings.amap_mcp_env.get("AMAP_MAPS_API_KEY", "")).strip()

    async def _call_route_tool_with_retry(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        trace: list[ToolCallRecord],
    ) -> Any:
        return await call_route_tool_with_retry_runtime(
            tool_name=tool_name,
            arguments=arguments,
            trace=trace,
            route_retry_attempts=self._route_retry_attempts,
            adaptive_retry_budget=self._adaptive_retry_budget,
            call_tool_for_purpose=self._call_tool_for_purpose,
            record_adaptive_retry_result=self._record_adaptive_retry_result,
            is_rate_limit_error=self._is_rate_limit_error,
            retry_delay_seconds=self._retry_delay_seconds,
        )

    async def _call_route_webservice_with_retry(
        self,
        mode: str,
        origin: POIRecommendation,
        destination: POIRecommendation,
        waypoints: list[POIRecommendation],
        trace: list[ToolCallRecord],
    ) -> dict[str, Any]:
        return await call_route_webservice_with_retry_runtime(
            mode=mode,
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            trace=trace,
            route_retry_attempts=self._route_retry_attempts,
            adaptive_retry_budget=self._adaptive_retry_budget,
            plan_route_via_web_service=self._plan_route_via_web_service,
            record_adaptive_retry_result=self._record_adaptive_retry_result,
            is_rate_limit_error=self._is_rate_limit_error,
            retry_delay_seconds=self._retry_delay_seconds,
        )

    def _retry_delay_seconds(self, attempt: int) -> float:
        return retry_delay_seconds(self._route_retry_base_delay_seconds, attempt)

    async def _adaptive_retry_budget(self, channel: str, base_attempts: int) -> int:
        base = max(1, int(base_attempts))
        if not adaptive_retry_enabled(self.settings.amap_mcp_adaptive_retry_enabled):
            return base

        window = max(1, int(self.settings.amap_mcp_adaptive_retry_window))
        min_samples = max(1, int(self.settings.amap_mcp_adaptive_retry_min_samples))
        low_success_rate = float(self.settings.amap_mcp_adaptive_retry_low_success_rate)
        async with self._adaptive_retry_lock:
            return adaptive_retry_budget(
                adaptive_retry_stats=self._adaptive_retry_stats,
                channel=channel,
                base_attempts=base,
                window=window,
                min_samples=min_samples,
                low_success_rate=low_success_rate,
            )

    async def _record_adaptive_retry_result(self, channel: str, success: bool) -> None:
        if not adaptive_retry_enabled(self.settings.amap_mcp_adaptive_retry_enabled):
            return
        window = max(1, int(self.settings.amap_mcp_adaptive_retry_window))
        async with self._adaptive_retry_lock:
            record_adaptive_retry_result(
                adaptive_retry_stats=self._adaptive_retry_stats,
                channel=channel,
                success=success,
                window=window,
            )

    async def suggest_route_parallelism(
        self,
        day_concurrency: int,
        segment_concurrency: int,
    ) -> tuple[int, int, str | None]:
        base_day = max(1, int(day_concurrency))
        base_segment = max(1, int(segment_concurrency))
        if not adaptive_retry_enabled(self.settings.amap_mcp_adaptive_retry_enabled):
            return base_day, base_segment, None

        window = max(1, int(self.settings.amap_mcp_adaptive_retry_window))
        min_samples = max(1, int(self.settings.amap_mcp_adaptive_retry_min_samples))
        low_success_rate = float(self.settings.amap_mcp_adaptive_retry_low_success_rate)

        async with self._adaptive_retry_lock:
            return suggest_route_parallelism_runtime(
                adaptive_retry_stats=self._adaptive_retry_stats,
                day_concurrency=base_day,
                segment_concurrency=base_segment,
                window=window,
                min_samples=min_samples,
                low_success_rate=low_success_rate,
            )

    def _adaptive_retry_enabled(self) -> bool:
        return adaptive_retry_enabled(self.settings.amap_mcp_adaptive_retry_enabled)

    def _adaptive_retry_state_item(self, channel: str, window: int) -> dict[str, Any]:
        return adaptive_retry_state_item(self._adaptive_retry_stats, channel, window)

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        return is_rate_limit_error(exc)

    def _is_rate_limit_text(self, text: str) -> bool:
        return is_rate_limit_text(text)

    async def _call_tool_for_purpose(
        self,
        purpose: str,
        arguments: dict[str, Any],
        trace: list[ToolCallRecord],
        tool_name_override: str | None = None,
    ) -> Any:
        assert self.client is not None
        return await call_tool_for_purpose_runtime(
            client=self.client,
            purpose=purpose,
            arguments=arguments,
            trace=trace,
            timeout_seconds=self.settings.amap_mcp_timeout_seconds,
            ensure_tool_catalog=self._ensure_tool_catalog,
            get_tool_catalog=lambda: self._tool_catalog or [],
            resolve_tool_name=lambda requested_purpose: self._resolve_tool_name(requested_purpose),
            tool_circuit_key=self._tool_circuit_key,
            before_tool_call=self._before_tool_call,
            after_tool_call_success=self._after_tool_call_success,
            after_tool_call_failure=self._after_tool_call_failure,
            unwrap_tool_result=self._unwrap_tool_result,
            raise_on_tool_error=self._raise_on_tool_error,
            summarize_tool_payload=self._summarize_tool_payload,
            tool_name_override=tool_name_override,
        )

    def _tool_circuit_key(self, purpose: str, tool_name: str) -> str:
        return tool_circuit_key(purpose, tool_name)

    def _tool_circuit_enabled(self) -> bool:
        return tool_circuit_enabled(self.settings.amap_mcp_circuit_enabled)

    def _tool_circuit_open_window_seconds(self) -> float:
        return tool_circuit_open_window_seconds(self.settings.amap_mcp_circuit_open_seconds)

    def _tool_circuit_state_item(self, key: str) -> dict[str, Any]:
        return tool_circuit_state_item(self._tool_circuit_state, key)

    def _open_tool_circuit_unlocked(self, state: dict[str, Any], now: float, reason: str) -> None:
        open_tool_circuit_unlocked(
            state=state,
            now=now,
            reason=reason,
            open_window_seconds=self.settings.amap_mcp_circuit_open_seconds,
        )

    async def _before_tool_call(self, key: str, purpose: str, tool_name: str) -> None:
        if not self._tool_circuit_enabled():
            return
        now = time.monotonic()
        async with self._tool_circuit_lock:
            state = self._tool_circuit_state_item(key)
            before_tool_call_unlocked(
                state=state,
                now=now,
                purpose=purpose,
                tool_name=tool_name,
            )

    async def _after_tool_call_success(self, key: str, elapsed_seconds: float) -> None:
        if not self._tool_circuit_enabled():
            return
        now = time.monotonic()
        async with self._tool_circuit_lock:
            state = self._tool_circuit_state_item(key)
            after_tool_call_success_unlocked(
                state=state,
                now=now,
                elapsed_seconds=elapsed_seconds,
                slow_call_seconds=float(self.settings.amap_mcp_circuit_slow_call_seconds),
                slow_call_threshold=int(self.settings.amap_mcp_circuit_slow_call_threshold),
                open_window_seconds=self.settings.amap_mcp_circuit_open_seconds,
            )

    async def _after_tool_call_failure(
        self,
        key: str,
        exc: BaseException,
        elapsed_seconds: float,
    ) -> None:
        _ = elapsed_seconds
        if not self._tool_circuit_enabled():
            return
        now = time.monotonic()
        async with self._tool_circuit_lock:
            state = self._tool_circuit_state_item(key)
            after_tool_call_failure_unlocked(
                state=state,
                now=now,
                exc=exc,
                failure_threshold=int(self.settings.amap_mcp_circuit_failure_threshold),
                open_window_seconds=self.settings.amap_mcp_circuit_open_seconds,
            )

    def _is_circuit_breaker_failure(self, exc: BaseException) -> bool:
        return is_circuit_breaker_failure(exc)

    async def _tool_circuit_warning_messages(self) -> list[str]:
        if not self._tool_circuit_enabled():
            return []
        now = time.monotonic()
        async with self._tool_circuit_lock:
            return tool_circuit_warning_messages(
                tool_circuit_state=self._tool_circuit_state,
                now=now,
            )

    async def _ensure_tool_catalog(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        if self.client is None:
            return []
        now = time.monotonic()
        if catalog_is_fresh(
            self._tool_catalog,
            self._tool_catalog_cached_at,
            self._tool_catalog_ttl_seconds,
            now,
            force_refresh,
        ):
            return self._tool_catalog

        async with self._tool_catalog_lock:
            now = time.monotonic()
            if catalog_is_fresh(
                self._tool_catalog,
                self._tool_catalog_cached_at,
                self._tool_catalog_ttl_seconds,
                now,
                force_refresh,
            ):
                return self._tool_catalog

            self._tool_catalog = await fetch_tool_catalog(
                self.client,
                self.settings.amap_mcp_timeout_seconds,
            )
            self._tool_catalog_cached_at = now
            self._resolved_tools = {}
            return self._tool_catalog

    def _resolve_tool_name(self, purpose: str, strict: bool = True) -> str | None:
        configured_name = {
            "poi_search": self.settings.amap_mcp_tool_poi_search,
            "route_plan": self.settings.amap_mcp_tool_route_plan,
            "weather": self.settings.amap_mcp_tool_weather,
        }[purpose]
        return resolve_tool_name(
            purpose=purpose,
            configured_name=configured_name,
            catalog=self._tool_catalog or [],
            resolved_tools=self._resolved_tools,
            strict=strict,
        )

    def _purpose_keywords(self, purpose: str) -> list[str]:
        return purpose_keywords(purpose)

    def _resolve_search_detail_tool_name(self) -> str | None:
        return resolve_search_detail_tool_name(self._tool_catalog or [])
