from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from math import ceil

from app.schemas.planning import (
    PlanningResponse,
    PlanningTelemetry,
    StageTimingPoint,
    StageTimingStats,
)

_DISABLED_WARNING = "\u9636\u6bb5\u8017\u65f6\u7edf\u8ba1\u672a\u542f\u7528\u3002"
_STAGE_WARNING_TEMPLATE = (
    "\u6027\u80fd\u544a\u8b66: \u9636\u6bb5 {stage} \u8017\u65f6 {value}ms\uff0c"
    "\u8d85\u8fc7\u9608\u503c {threshold}ms\u3002"
)
_TOTAL_WARNING_TEMPLATE = (
    "\u6027\u80fd\u544a\u8b66: \u603b\u8017\u65f6 {value}ms\uff0c"
    "\u8d85\u8fc7\u9608\u503c {threshold}ms\u3002"
)


class TravelPlannerTelemetryMixin:
    def _init_timing_state(self) -> None:
        self._timing_history: dict[str, deque[int]] = {}
        self._timing_point_history: dict[str, deque[tuple[datetime, int]]] = {}
        self._timing_lock = asyncio.Lock()
        self._stats_total_requests = 0
        self._stats_cache_hits = 0
        self._stats_cache_misses = 0
        self._stats_updated_at: datetime | None = None

    async def get_telemetry(self) -> PlanningTelemetry:
        if not self._stage_stats_enabled():
            return PlanningTelemetry(
                enabled=False,
                window_size=self._stage_stats_window(),
                warnings=[_DISABLED_WARNING],
            )

        async with self._timing_lock:
            snapshot = {
                stage: list(values)
                for stage, values in self._timing_history.items()
            }
            point_snapshot = {
                stage: list(values)
                for stage, values in self._timing_point_history.items()
            }
            total_requests = self._stats_total_requests
            cache_hits = self._stats_cache_hits
            cache_misses = self._stats_cache_misses
            updated_at = self._stats_updated_at

        stages = {
            stage: self._build_stage_timing_stats(
                values,
                points=point_snapshot.get(stage, []),
                series_points=self._stage_stats_series_points(),
            )
            for stage, values in sorted(snapshot.items())
        }
        return PlanningTelemetry(
            enabled=True,
            window_size=self._stage_stats_window(),
            total_requests=total_requests,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            stages=stages,
            updated_at=updated_at,
            warnings=[],
        )

    async def _record_generation_timing(
        self,
        response: PlanningResponse,
        request_elapsed_ms: int,
        cache_hit: bool,
        include_pipeline_timings: bool,
    ) -> None:
        if not self._stage_stats_enabled():
            return

        async with self._timing_lock:
            self._stats_total_requests += 1
            if cache_hit:
                self._stats_cache_hits += 1
            else:
                self._stats_cache_misses += 1

            window = self._stage_stats_window()
            sampled_at = datetime.now(timezone.utc)
            self._append_stage_timing_unlocked(
                "request_total",
                request_elapsed_ms,
                window,
                sampled_at=sampled_at,
            )
            if include_pipeline_timings:
                for stage, value in (response.meta.stage_timings_ms or {}).items():
                    if not isinstance(value, (int, float)):
                        continue
                    self._append_stage_timing_unlocked(
                        stage,
                        int(max(0, value)),
                        window,
                        sampled_at=sampled_at,
                    )
            self._stats_updated_at = sampled_at

    def _append_stage_timing_unlocked(
        self,
        stage: str,
        value: int,
        window: int,
        sampled_at: datetime,
    ) -> None:
        history = self._timing_history.get(stage)
        if history is None:
            history = deque(maxlen=window)
            self._timing_history[stage] = history
        elif history.maxlen != window:
            history = deque(list(history), maxlen=window)
            self._timing_history[stage] = history
        normalized = int(max(0, value))
        history.append(normalized)

        point_history = self._timing_point_history.get(stage)
        if point_history is None:
            point_history = deque(maxlen=window)
            self._timing_point_history[stage] = point_history
        elif point_history.maxlen != window:
            point_history = deque(list(point_history), maxlen=window)
            self._timing_point_history[stage] = point_history
        point_history.append((sampled_at, normalized))

    def _stage_stats_enabled(self) -> bool:
        return bool(self.settings.planner_stage_stats_enabled)

    def _stage_stats_window(self) -> int:
        return max(1, int(self.settings.planner_stage_stats_window))

    def _stage_stats_series_points(self) -> int:
        return max(1, int(self.settings.planner_stage_stats_series_points))

    def _build_stage_timing_stats(
        self,
        values: list[int],
        points: list[tuple[datetime, int]],
        series_points: int,
    ) -> StageTimingStats:
        if not values:
            return StageTimingStats()
        sorted_values = sorted(values)
        max_points = max(1, series_points)
        tail = values[-max_points:]
        point_tail = points[-max_points:]
        return StageTimingStats(
            count=len(values),
            p50_ms=self._percentile(sorted_values, 0.50),
            p95_ms=self._percentile(sorted_values, 0.95),
            max_ms=sorted_values[-1],
            last_ms=values[-1],
            recent_ms=[int(max(0, item)) for item in tail],
            recent_points=[
                StageTimingPoint(at=at, value_ms=int(max(0, value_ms)))
                for at, value_ms in point_tail
            ],
        )

    def _percentile(self, sorted_values: list[int], ratio: float) -> int:
        if not sorted_values:
            return 0
        clamped = min(1.0, max(0.0, ratio))
        rank = max(1, ceil(len(sorted_values) * clamped))
        index = min(len(sorted_values) - 1, rank - 1)
        return int(sorted_values[index])

    def _append_performance_warnings(self, response: PlanningResponse) -> PlanningResponse:
        if not self._stage_stats_enabled():
            return response

        stage_timings = response.meta.stage_timings_ms or {}
        if not stage_timings:
            return response

        warnings = list(response.meta.warnings)
        per_stage_threshold = int(self.settings.planner_stage_slow_threshold_ms_per_stage)
        total_threshold = int(self.settings.planner_stage_slow_threshold_ms_total)

        if per_stage_threshold > 0:
            for stage, value in stage_timings.items():
                if stage in {"total", "diagnose", "diagnostics"}:
                    continue
                if not isinstance(value, (int, float)):
                    continue
                numeric_value = int(value)
                if numeric_value >= per_stage_threshold:
                    warnings.append(
                        _STAGE_WARNING_TEMPLATE.format(
                            stage=stage,
                            value=numeric_value,
                            threshold=per_stage_threshold,
                        )
                    )

        total_ms = stage_timings.get("total")
        if total_threshold > 0 and isinstance(total_ms, (int, float)):
            numeric_total = int(total_ms)
            if numeric_total >= total_threshold:
                warnings.append(
                    _TOTAL_WARNING_TEMPLATE.format(
                        value=numeric_total,
                        threshold=total_threshold,
                    )
                )

        deduped = list(dict.fromkeys(item for item in warnings if item))
        if deduped == response.meta.warnings:
            return response
        return response.model_copy(
            update={
                "meta": response.meta.model_copy(update={"warnings": deduped}),
            },
            deep=True,
        )
