import asyncio
from datetime import datetime
from time import monotonic

from app.agents.planning_agent import PlanningCoordinatorAgent
from app.config import Settings
from app.schemas.planning import IntegrationStatus, PlanningResponse, TripPlanningRequest
from app.services.planner_cache import TravelPlannerGenerateCacheMixin
from app.services.planner_telemetry import TravelPlannerTelemetryMixin


class TravelPlannerService(
    TravelPlannerGenerateCacheMixin,
    TravelPlannerTelemetryMixin,
):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.coordinator = PlanningCoordinatorAgent(settings)
        self._init_generate_cache_state()
        self._init_timing_state()

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

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1000))
