from __future__ import annotations

import asyncio
from datetime import datetime
from time import perf_counter

from app.schemas.planning import (
    AgentExecution,
    GeoPoint,
    IntegrationStatus,
    MapRenderConfig,
    PlanGenerationMeta,
    PlanningContext,
    PlanningResponse,
    WeatherSummary,
)
from app.agents.planning_agent_diagnostics import (
    apply_llm_status_to_integration,
    build_plan_diagnostics,
    resolve_response_status,
)
from app.agents.planning_agent_postprocess import (
    run_post_compose_pipeline as run_post_compose_pipeline_runtime,
)
from app.agents.planning_agent_stage_runtime import (
    build_meal_candidate_trace,
    gather_hotel_stage,
    gather_poi_stage,
    gather_weather_stage,
)


class PlanningCoordinatorRuntimeMixin:
    async def diagnose(self, force_refresh: bool = False) -> IntegrationStatus:
        integration_status = await self.adapter.diagnose(force_refresh=force_refresh)
        llm_status = await self.ai_client.diagnose(check_connection=True)
        return apply_llm_status_to_integration(integration_status, llm_status)

    async def generate(
        self,
        request,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        agent_trace: list[AgentExecution] = []
        tool_trace = []
        warnings: list[str] = []
        stage_timings_ms: dict[str, int] = {}
        total_started = perf_counter()
        async with self.adapter.request_scope():
            diagnose_started = perf_counter()
            integration_status, llm_status = await asyncio.gather(
                self.adapter.diagnose(force_refresh=False),
                self.ai_client.diagnose(check_connection=False),
            )
            stage_timings_ms["diagnose"] = self._elapsed_ms(diagnose_started)
            apply_llm_status_to_integration(integration_status, llm_status)
            warnings.extend(integration_status.warnings)

            if not self.adapter.has_client:
                raise RuntimeError("未配置高德 MCP，无法生成稳定可验证的行程结果。")
            if not llm_status.enabled:
                raise RuntimeError("未配置大模型，无法生成最终行程。")
            if integration_status.missing_tools:
                raise RuntimeError(f"MCP 工具映射不完整: {', '.join(integration_status.missing_tools)}")

            seed_started = perf_counter()
            (
                initial_plan,
                seed_trace,
                seed_llm_used,
                seed_fallback_used,
                seed_warnings,
            ) = await self.seed_agent.gather(request)
            stage_timings_ms["seed"] = self._elapsed_ms(seed_started)
            agent_trace.append(seed_trace)
            warnings.extend(seed_warnings)

            context = PlanningContext(
                destination=request.destination,
                attractions=[],
                restaurants=[],
                hotels=[],
                routes=[],
                weather=WeatherSummary(),
            )
            weather_started = perf_counter()
            resolved_poi_search_tool = integration_status.resolved_tools.get(
                "poi_search",
                self.adapter.settings.amap_mcp_tool_poi_search,
            )
            resolved_weather_tool = integration_status.resolved_tools.get(
                "weather",
                self.adapter.settings.amap_mcp_tool_weather,
            )
            weather_task = asyncio.create_task(
                gather_weather_stage(
                    request=request,
                    weather_agent=self.weather_agent,
                    tool_trace=tool_trace,
                    resolved_weather_tool=resolved_weather_tool,
                )
            )
            poi_started = perf_counter()
            (
                context.attractions,
                context.restaurants,
                poi_trace,
                poi_stage_warnings,
            ) = await gather_poi_stage(
                request=request,
                sight_agent=self.sight_agent,
                tool_trace=tool_trace,
                resolved_poi_search_tool=resolved_poi_search_tool,
                is_rate_limit_text=self.adapter._is_rate_limit_text,
            )
            warnings.extend(poi_stage_warnings)
            stage_timings_ms["poi_collection"] = self._elapsed_ms(poi_started)
            agent_trace.append(poi_trace)

            hotel_started = perf_counter()
            hotel_task = asyncio.create_task(
                gather_hotel_stage(
                    request=request,
                    attractions=context.attractions,
                    hotel_agent=self.hotel_agent,
                    tool_trace=tool_trace,
                    resolved_poi_search_tool=resolved_poi_search_tool,
                    is_rate_limit_text=self.adapter._is_rate_limit_text,
                )
            )
            context.hotels, hotel_trace, hotel_stage_warnings = await hotel_task
            warnings.extend(hotel_stage_warnings)
            stage_timings_ms["hotel_candidates"] = self._elapsed_ms(hotel_started)
            agent_trace.append(hotel_trace)

            context.weather, weather_trace, weather_warnings = await weather_task
            warnings.extend(weather_warnings)
            agent_trace.append(weather_trace)
            stage_timings_ms["weather"] = self._elapsed_ms(weather_started)

            meal_candidates_started = perf_counter()
            day_restaurants = self.meal_agent.gather(request, initial_plan, context.restaurants)
            stage_timings_ms["meal_candidates"] = self._elapsed_ms(meal_candidates_started)
            meal_candidate_trace = build_meal_candidate_trace(day_restaurants)
            agent_trace.append(meal_candidate_trace)

            compose_started = perf_counter()
            plan, compose_trace, compose_llm_used, compose_fallback_used, compose_warnings = (
                await self.composer_agent.gather(
                    request=request,
                    initial_plan=initial_plan,
                    context=context,
                    tool_trace=tool_trace,
                )
            )
            stage_timings_ms["compose"] = self._elapsed_ms(compose_started)
            agent_trace.append(compose_trace)
            warnings.extend(compose_warnings)

            (
                plan,
                context,
                hotel_binding_trace,
                meal_binding_trace,
                route_trace,
                truth_trace,
                postprocess_warnings,
                postprocess_timings,
            ) = await run_post_compose_pipeline_runtime(
                request=request,
                plan=plan,
                context=context,
                tool_trace=tool_trace,
                resolved_poi_search_tool=integration_status.resolved_tools.get(
                    "poi_search",
                    self.adapter.settings.amap_mcp_tool_poi_search,
                ),
                resolved_route_plan_tool=integration_status.resolved_tools.get(
                    "route_plan",
                    self.adapter.settings.amap_mcp_tool_route_plan,
                ),
                hotel_binding_timeout=self.settings.planner_hotel_binding_timeout_seconds,
                meal_binding_timeout=self.settings.planner_meal_binding_timeout_seconds,
                route_generation_timeout=self.settings.planner_route_generation_timeout_seconds,
                truth_binding_timeout=self.settings.planner_truth_binding_timeout_seconds,
                bind_daily_stays_fn=self.hotel_agent.bind_daily_stays,
                bind_daily_meals_fn=self.meal_agent.bind_daily_meals,
                gather_routes_fn=self.route_agent.gather_for_plan,
                finalize_plan_with_routes_fn=self.ai_client.finalize_plan_with_routes,
                bind_plan_truth_fn=self.route_agent.bind_plan_truth,
                await_with_optional_timeout_fn=self._await_with_optional_timeout,
                format_timeout_seconds_fn=self._format_timeout_seconds,
                elapsed_ms_fn=self._elapsed_ms,
            )
            stage_timings_ms.update(postprocess_timings)
            agent_trace.append(hotel_binding_trace)
            agent_trace.append(meal_binding_trace)
            agent_trace.append(route_trace)
            agent_trace.append(truth_trace)
            warnings.extend(postprocess_warnings)

            llm_used = seed_llm_used or compose_llm_used
            fallback_used = seed_fallback_used or compose_fallback_used
            integration_status.llm_reachable = integration_status.llm_reachable or llm_used
            diagnostics_started = perf_counter()
            diagnostics = build_plan_diagnostics(
                integration_status=integration_status,
                warnings=warnings,
                seed_trace=seed_trace,
                seed_fallback_used=seed_fallback_used,
                seed_llm_used=seed_llm_used,
                compose_trace=compose_trace,
                compose_fallback_used=compose_fallback_used,
                compose_llm_used=compose_llm_used,
                weather_trace=weather_trace,
                poi_trace=poi_trace,
                hotel_trace=hotel_trace,
                hotel_binding_trace=hotel_binding_trace,
                meal_candidate_trace=meal_candidate_trace,
                meal_binding_trace=meal_binding_trace,
                route_trace=route_trace,
                truth_trace=truth_trace,
                plan=plan,
            )
            stage_timings_ms["diagnostics"] = self._elapsed_ms(diagnostics_started)
            response_status = resolve_response_status(
                fallback_used=fallback_used,
                diagnostics=diagnostics,
            )
            stage_timings_ms["total"] = self._elapsed_ms(total_started)

            response = PlanningResponse(
                status=response_status,
                generated_at=generated_at,
                request_echo=request,
                initial_plan=initial_plan,
                planning_context=context,
                agent_trace=agent_trace,
                tool_trace=tool_trace,
                meta=PlanGenerationMeta(
                    llm_used=llm_used,
                    fallback_used=fallback_used,
                    model_name=integration_status.llm_model or self.settings.openai_model,
                    warnings=warnings,
                    stage_timings_ms=stage_timings_ms,
                ),
                diagnostics=diagnostics,
                map_config=MapRenderConfig(
                    enabled=self.settings.has_map_rendering,
                    js_api_key=self.settings.amap_api_key or None,
                    security_js_code=self.settings.amap_security_js_code or None,
                    center=self._resolve_center(context, plan),
                ),
                integration_status=integration_status,
                plan=plan,
            )
            if include_debug:
                return response
            return self._compact_response(response)

    async def _await_with_optional_timeout(self, awaitable, timeout_seconds: float) -> object:
        if timeout_seconds and timeout_seconds > 0:
            return await asyncio.wait_for(awaitable, timeout=float(timeout_seconds))
        return await awaitable

    def _format_timeout_seconds(self, timeout_seconds: float) -> str:
        seconds = float(timeout_seconds)
        if seconds.is_integer():
            return str(int(seconds))
        return f"{seconds:.1f}".rstrip("0").rstrip(".")

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((perf_counter() - started_at) * 1000))

    def _compact_response(self, response: PlanningResponse) -> PlanningResponse:
        return response.model_copy(
            update={
                "planning_context": PlanningContext(
                    destination=response.planning_context.destination,
                    weather=response.planning_context.weather,
                ),
                "agent_trace": [],
                "tool_trace": [],
            }
        )

    def _resolve_center(self, context: PlanningContext, plan=None) -> GeoPoint | None:
        if plan is not None:
            for day in getattr(plan, "days", []):
                for item in getattr(day, "map_pois", []):
                    poi = getattr(item, "poi", None)
                    if getattr(poi, "longitude", None) is None or getattr(poi, "latitude", None) is None:
                        continue
                    return GeoPoint(longitude=poi.longitude, latitude=poi.latitude)
        for poi in [*context.attractions, *context.hotels, *context.restaurants]:
            if poi.longitude is None or poi.latitude is None:
                continue
            return GeoPoint(longitude=poi.longitude, latitude=poi.latitude)
        return None
