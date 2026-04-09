import asyncio
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from time import monotonic

from app.agents.planning_agent import PlanningCoordinatorAgent
from app.config import Settings
from app.schemas.planning import (
    IntegrationStatus,
    PlanningResponse,
    PlanningTelemetry,
    StageTimingPoint,
    StageTimingStats,
    TripPlanningRequest,
)


@dataclass
class _GenerateCacheEntry:
    response: PlanningResponse
    expires_at: float


class TravelPlannerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.coordinator = PlanningCoordinatorAgent(settings)
        self._generate_cache: OrderedDict[str, _GenerateCacheEntry] = OrderedDict()
        self._inflight_generations: dict[str, asyncio.Task[PlanningResponse]] = {}
        self._cache_lock = asyncio.Lock()

        self._timing_history: dict[str, deque[int]] = {}
        self._timing_point_history: dict[str, deque[tuple[datetime, int]]] = {}
        self._timing_lock = asyncio.Lock()
        self._stats_total_requests = 0
        self._stats_cache_hits = 0
        self._stats_cache_misses = 0
        self._stats_updated_at: datetime | None = None

    async def generate(
        self,
        request: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        started_at = monotonic()

        if not self._generate_cache_enabled():
            response = await self.coordinator.generate(
                request,
                generated_at,
                include_debug=include_debug,
            )
            response = self._append_performance_warnings(response)
            final_response = response.model_copy(update={"generated_at": generated_at}, deep=True)
            await self._record_generation_timing(
                response=final_response,
                request_elapsed_ms=self._elapsed_ms(started_at),
                cache_hit=False,
                include_pipeline_timings=True,
            )
            return final_response

        cache_key = self._request_cache_key(request, include_debug)
        cached = await self._get_cached_response(cache_key)
        if cached is not None:
            final_response = cached.model_copy(update={"generated_at": generated_at}, deep=True)
            await self._record_generation_timing(
                response=final_response,
                request_elapsed_ms=self._elapsed_ms(started_at),
                cache_hit=True,
                include_pipeline_timings=False,
            )
            return final_response

        created_task = False
        async with self._cache_lock:
            cached_again = self._get_cached_response_unlocked(cache_key)
            if cached_again is not None:
                final_response = cached_again.model_copy(update={"generated_at": generated_at}, deep=True)
                await self._record_generation_timing(
                    response=final_response,
                    request_elapsed_ms=self._elapsed_ms(started_at),
                    cache_hit=True,
                    include_pipeline_timings=False,
                )
                return final_response

            inflight_task = self._inflight_generations.get(cache_key)
            if inflight_task is None:
                inflight_task = asyncio.create_task(
                    self.coordinator.generate(
                        request,
                        generated_at,
                        include_debug=include_debug,
                    )
                )
                self._inflight_generations[cache_key] = inflight_task
                created_task = True

        try:
            response = await inflight_task
        finally:
            if created_task:
                async with self._cache_lock:
                    active_task = self._inflight_generations.get(cache_key)
                    if active_task is inflight_task:
                        self._inflight_generations.pop(cache_key, None)

        response = self._append_performance_warnings(response)
        if self._should_cache_response(response):
            await self._put_cached_response(cache_key, response)

        final_response = response.model_copy(update={"generated_at": generated_at}, deep=True)
        await self._record_generation_timing(
            response=final_response,
            request_elapsed_ms=self._elapsed_ms(started_at),
            cache_hit=False,
            include_pipeline_timings=created_task,
        )
        return final_response

    async def diagnose_integrations(self, refresh: bool = False) -> IntegrationStatus:
        return await self.coordinator.diagnose(force_refresh=refresh)

    async def get_telemetry(self) -> PlanningTelemetry:
        if not self._stage_stats_enabled():
            return PlanningTelemetry(
                enabled=False,
                window_size=self._stage_stats_window(),
                warnings=["阶段耗时统计未启用。"],
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

    def _generate_cache_enabled(self) -> bool:
        if not self.settings.planner_generate_cache_enabled:
            return False
        if self.settings.planner_generate_cache_ttl_seconds <= 0:
            return False
        if self.settings.planner_generate_cache_max_entries <= 0:
            return False
        return True

    def _request_cache_key(self, request: TripPlanningRequest, include_debug: bool) -> str:
        request_payload = request.model_dump_json(by_alias=True, exclude_none=False)
        return f"{int(include_debug)}::{request_payload}"

    async def _get_cached_response(self, cache_key: str) -> PlanningResponse | None:
        async with self._cache_lock:
            return self._get_cached_response_unlocked(cache_key)

    def _get_cached_response_unlocked(self, cache_key: str) -> PlanningResponse | None:
        self._evict_expired_unlocked()
        entry = self._generate_cache.get(cache_key)
        if entry is None:
            return None
        self._generate_cache.move_to_end(cache_key)
        return entry.response.model_copy(deep=True)

    async def _put_cached_response(self, cache_key: str, response: PlanningResponse) -> None:
        async with self._cache_lock:
            self._evict_expired_unlocked()
            self._generate_cache[cache_key] = _GenerateCacheEntry(
                response=response.model_copy(deep=True),
                expires_at=monotonic() + float(self.settings.planner_generate_cache_ttl_seconds),
            )
            self._generate_cache.move_to_end(cache_key)
            while len(self._generate_cache) > self.settings.planner_generate_cache_max_entries:
                self._generate_cache.popitem(last=False)

    def _evict_expired_unlocked(self) -> None:
        if not self._generate_cache:
            return
        now = monotonic()
        expired_keys = [
            key
            for key, entry in self._generate_cache.items()
            if entry.expires_at <= now
        ]
        for key in expired_keys:
            self._generate_cache.pop(key, None)

    def _should_cache_response(self, response: PlanningResponse) -> bool:
        # Do not cache degraded partial_success to avoid amplifying transient stage failures.
        return response.status in {"success", "fallback_success"}

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
                if int(value) >= per_stage_threshold:
                    warnings.append(
                        f"性能告警: 阶段 {stage} 耗时 {int(value)}ms，超过阈值 {per_stage_threshold}ms。"
                    )

        total_ms = stage_timings.get("total")
        if total_threshold > 0 and isinstance(total_ms, (int, float)) and int(total_ms) >= total_threshold:
            warnings.append(
                f"性能告警: 总耗时 {int(total_ms)}ms，超过阈值 {total_threshold}ms。"
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

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1000))
