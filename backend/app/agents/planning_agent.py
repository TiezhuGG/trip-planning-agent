from datetime import datetime

import asyncio
from time import perf_counter

from app.agents.hotel_agent import HotelRecommendationAgent
from app.agents.itinerary_composer_agent import ItineraryComposerAgent
from app.agents.meal_agent import MealRecommendationAgent
from app.agents.planner_seed_agent import PlannerSeedAgent
from app.agents.poi_agent import SightseeingAgent
from app.agents.route_agent import RoutePlanningAgent
from app.agents.weather_agent import WeatherAgent
from app.config import Settings
from app.schemas.planning import (
    AgentExecution,
    GeoPoint,
    IntegrationStatus,
    MapRenderConfig,
    PlanDiagnostics,
    PlanGenerationMeta,
    PlanningContext,
    PlanningResponse,
    StageDiagnostic,
    TripPlanningRequest,
    WeatherSummary,
)
from app.services.ai_client import TravelAIClient
from app.services.amap_mcp_adapter import AmapMCPAdapter


class PlanningCoordinatorAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.adapter = AmapMCPAdapter(settings)
        self.ai_client = TravelAIClient(settings)
        self.seed_agent = PlannerSeedAgent(self.ai_client)
        self.sight_agent = SightseeingAgent(self.adapter)
        self.weather_agent = WeatherAgent(self.adapter)
        self.hotel_agent = HotelRecommendationAgent(self.adapter)
        self.meal_agent = MealRecommendationAgent(self.adapter)
        self.route_agent = RoutePlanningAgent(self.adapter)
        self.composer_agent = ItineraryComposerAgent(self.ai_client)

    async def diagnose(self) -> IntegrationStatus:
        integration_status = await self.adapter.diagnose()
        llm_status = await self.ai_client.diagnose(check_connection=True)
        integration_status.llm_enabled = llm_status.enabled
        integration_status.llm_reachable = llm_status.reachable
        integration_status.llm_model = llm_status.model
        integration_status.llm_base_url = llm_status.base_url
        integration_status.warnings.extend(llm_status.warnings)
        return integration_status

    async def generate(
        self,
        request: TripPlanningRequest,
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
            integration_status.llm_enabled = llm_status.enabled
            integration_status.llm_reachable = llm_status.reachable
            integration_status.llm_model = llm_status.model
            integration_status.llm_base_url = llm_status.base_url
            integration_status.warnings.extend(llm_status.warnings)
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
            weather_task = asyncio.create_task(self.weather_agent.gather(request, tool_trace))
            poi_tool_trace_start = len(tool_trace)
            poi_started = perf_counter()
            try:
                attractions, restaurants = await self.sight_agent.gather(request, tool_trace)
                context.attractions = attractions[:12]
                context.restaurants = restaurants[:12]
                poi_stage_warnings = self._collect_stage_tool_warnings(
                    tool_trace[poi_tool_trace_start:],
                    fallback_message="景点或餐饮数据部分受限，已使用当前可用候选继续生成。",
                )
                warnings.extend(poi_stage_warnings)
                poi_trace = AgentExecution(
                    agent_name="poi_agent",
                    success=True,
                    summary=f"已获取 {len(context.attractions)} 个景点和 {len(context.restaurants)} 个餐饮候选。",
                    used_llm=False,
                    used_tools=[integration_status.resolved_tools.get("poi_search", self.adapter.settings.amap_mcp_tool_poi_search)],
                    warnings=poi_stage_warnings,
                )
            except Exception as exc:
                poi_warning = f"poi_agent 调用失败: {exc}"
                warnings.append(poi_warning)
                poi_trace = AgentExecution(
                    agent_name="poi_agent",
                    success=False,
                    summary="景点与餐饮候选不可用，已在缺少 POI 上下文条件下继续生成行程。",
                    used_llm=False,
                    used_tools=[integration_status.resolved_tools.get("poi_search", self.adapter.settings.amap_mcp_tool_poi_search)],
                    warnings=[str(exc)],
                )
            stage_timings_ms["poi_collection"] = self._elapsed_ms(poi_started)
            agent_trace.append(poi_trace)

            hotel_tool_trace_start = len(tool_trace)
            hotel_started = perf_counter()
            hotel_task = asyncio.create_task(
                self.hotel_agent.gather(request, context.attractions, tool_trace)
            )
            try:
                hotels = await hotel_task
                context.hotels = hotels[:8]
                hotel_stage_warnings = self._collect_stage_tool_warnings(
                    tool_trace[hotel_tool_trace_start:],
                    fallback_message="酒店候选部分受限，已使用当前可用候选继续生成。",
                )
                warnings.extend(hotel_stage_warnings)
                hotel_trace = AgentExecution(
                    agent_name="hotel_agent",
                    success=True,
                    summary=f"已获取 {len(context.hotels)} 个酒店候选。",
                    used_llm=False,
                    used_tools=[integration_status.resolved_tools.get("poi_search", self.adapter.settings.amap_mcp_tool_poi_search)],
                    warnings=hotel_stage_warnings,
                )
            except Exception as exc:
                hotel_warning = f"hotel_agent 调用失败: {exc}"
                warnings.append(hotel_warning)
                hotel_trace = AgentExecution(
                    agent_name="hotel_agent",
                    success=False,
                    summary="酒店候选不可用，已在缺少酒店推荐条件下继续生成行程。",
                    used_llm=False,
                    used_tools=[integration_status.resolved_tools.get("poi_search", self.adapter.settings.amap_mcp_tool_poi_search)],
                    warnings=[str(exc)],
                )
            stage_timings_ms["hotel_candidates"] = self._elapsed_ms(hotel_started)
            agent_trace.append(hotel_trace)

            try:
                context.weather = await weather_task
                weather_trace = AgentExecution(
                    agent_name="weather_agent",
                    success=True,
                    summary=f"已获取 {len(context.weather.daily_forecasts)} 天天气信息。",
                    used_llm=False,
                    used_tools=[integration_status.resolved_tools.get("weather", self.adapter.settings.amap_mcp_tool_weather)],
                )
                agent_trace.append(weather_trace)
            except Exception as exc:
                weather_warning = f"weather_agent 调用失败: {exc}"
                warnings.append(weather_warning)
                weather_trace = AgentExecution(
                    agent_name="weather_agent",
                    success=False,
                    summary="天气数据不可用，已在无天气详情条件下继续生成行程。",
                    used_llm=False,
                    used_tools=[integration_status.resolved_tools.get("weather", self.adapter.settings.amap_mcp_tool_weather)],
                    warnings=[str(exc)],
                )
                agent_trace.append(weather_trace)
            stage_timings_ms["weather"] = self._elapsed_ms(weather_started)

            meal_candidates_started = perf_counter()
            day_restaurants = self.meal_agent.gather(request, initial_plan, context.restaurants)
            stage_timings_ms["meal_candidates"] = self._elapsed_ms(meal_candidates_started)
            meal_candidate_trace = AgentExecution(
                agent_name="meal_agent",
                success=True,
                summary=f"已为 {len(day_restaurants)} 天行程匹配餐饮候选。",
                used_llm=False,
                used_tools=[],
            )
            agent_trace.append(meal_candidate_trace)

            compose_started = perf_counter()
            plan, compose_trace, compose_llm_used, compose_fallback_used, compose_warnings = await self.composer_agent.gather(
                request=request,
                initial_plan=initial_plan,
                context=context,
                tool_trace=tool_trace,
            )
            stage_timings_ms["compose"] = self._elapsed_ms(compose_started)
            agent_trace.append(compose_trace)
            warnings.extend(compose_warnings)

            hotel_binding_started = perf_counter()
            plan, rebound_hotels, hotel_binding_trace = await self.hotel_agent.bind_daily_stays(
                request=request,
                plan=plan,
                context=context,
                trace=tool_trace,
            )
            stage_timings_ms["hotel_binding"] = self._elapsed_ms(hotel_binding_started)
            if rebound_hotels:
                context.hotels = rebound_hotels[:8]
            agent_trace.append(hotel_binding_trace)
            warnings.extend(hotel_binding_trace.warnings)

            meal_binding_started = perf_counter()
            plan, rebound_restaurants, meal_binding_trace = await self.meal_agent.bind_daily_meals(
                request=request,
                plan=plan,
                context=context,
                trace=tool_trace,
            )
            stage_timings_ms["meal_binding"] = self._elapsed_ms(meal_binding_started)
            if rebound_restaurants:
                context.restaurants = rebound_restaurants[:12]
            agent_trace.append(meal_binding_trace)
            warnings.extend(meal_binding_trace.warnings)

            route_generation_started = perf_counter()
            routes, route_trace = await self.route_agent.gather_for_plan(
                request=request,
                plan=plan,
                context=context,
                trace=tool_trace,
            )
            stage_timings_ms["route_generation"] = self._elapsed_ms(route_generation_started)
            context.routes = routes
            route_finalize_started = perf_counter()
            plan = self.ai_client.finalize_plan_with_routes(
                request=request,
                plan=plan,
                context=context,
            )
            stage_timings_ms["route_finalize"] = self._elapsed_ms(route_finalize_started)
            agent_trace.append(route_trace)
            warnings.extend(route_trace.warnings)
            truth_binding_started = perf_counter()
            try:
                plan, truth_trace = await self.route_agent.bind_plan_truth(
                    request=request,
                    plan=plan,
                    context=context,
                    trace=tool_trace,
                )
            except Exception as exc:
                warning = f"plan_truth_agent 调用失败: {exc}"
                warnings.append(warning)
                truth_trace = AgentExecution(
                    agent_name="plan_truth_agent",
                    success=False,
                    summary="最终点位校正失败，已保留基础行程结果继续返回。",
                    used_llm=False,
                    used_tools=[],
                    warnings=[str(exc)],
                )
            stage_timings_ms["truth_binding"] = self._elapsed_ms(truth_binding_started)
            agent_trace.append(truth_trace)
            warnings.extend(truth_trace.warnings)

            llm_used = seed_llm_used or compose_llm_used
            fallback_used = seed_fallback_used or compose_fallback_used
            integration_status.llm_reachable = integration_status.llm_reachable or llm_used
            diagnostics_started = perf_counter()
            diagnostics = self._build_diagnostics(
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
            response_status = self._resolve_response_status(
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

    def _resolve_response_status(
        self,
        fallback_used: bool,
        diagnostics: PlanDiagnostics,
    ) -> str:
        if fallback_used:
            return "fallback_success"
        if any(item.status == "error" for item in [*diagnostics.llm, *diagnostics.mcp]):
            return "partial_success"
        return "success"

    def _build_diagnostics(
        self,
        integration_status: IntegrationStatus,
        warnings: list[str],
        seed_trace: AgentExecution,
        seed_fallback_used: bool,
        seed_llm_used: bool,
        compose_trace: AgentExecution,
        compose_fallback_used: bool,
        compose_llm_used: bool,
        weather_trace: AgentExecution,
        poi_trace: AgentExecution,
        hotel_trace: AgentExecution,
        hotel_binding_trace: AgentExecution,
        meal_candidate_trace: AgentExecution,
        meal_binding_trace: AgentExecution,
        route_trace: AgentExecution,
        truth_trace: AgentExecution,
        plan,
    ) -> PlanDiagnostics:
        llm_diagnostics = [
            StageDiagnostic(
                stage="initial_planning",
                status="fallback" if seed_fallback_used else ("warning" if seed_trace.warnings else "ok"),
                summary=seed_trace.summary,
                warnings=seed_trace.warnings,
                fallback_used=seed_fallback_used,
                used_llm=seed_llm_used,
                provider=integration_status.llm_model,
            ),
            StageDiagnostic(
                stage="final_composition",
                status="fallback" if compose_fallback_used else ("warning" if compose_trace.warnings else "ok"),
                summary=compose_trace.summary,
                warnings=compose_trace.warnings,
                fallback_used=compose_fallback_used,
                used_llm=compose_llm_used,
                provider=integration_status.llm_model,
            ),
        ]
        mcp_diagnostics = [
            self._trace_to_stage("poi_collection", poi_trace),
            self._trace_to_stage("hotel_candidates", hotel_trace),
            self._trace_to_stage("weather", weather_trace),
            self._trace_to_stage("meal_candidates", meal_candidate_trace),
            self._trace_to_stage("daily_hotel_binding", hotel_binding_trace),
            self._trace_to_stage("daily_meal_binding", meal_binding_trace),
            self._trace_to_stage("route_generation", route_trace),
            self._trace_to_stage("plan_truth_binding", truth_trace),
        ]
        fallback_sources = [
            item.stage
            for item in llm_diagnostics
            if item.fallback_used
        ]
        fallback_sources.extend(
            fallback
            for day in getattr(plan, "days", [])
            for fallback in getattr(day, "fallbacks", [])
        )
        return PlanDiagnostics(
            llm=llm_diagnostics,
            mcp=mcp_diagnostics,
            warnings=list(dict.fromkeys(item for item in warnings if item)),
            fallbacks_used=list(dict.fromkeys(fallback_sources)),
            error_code="LLM_TEMPLATE_FALLBACK" if (seed_fallback_used or compose_fallback_used) else "",
        )

    def _trace_to_stage(self, stage: str, trace: AgentExecution) -> StageDiagnostic:
        status = "ok"
        if not trace.success:
            status = "error"
        elif trace.warnings:
            status = "warning"
        return StageDiagnostic(
            stage=stage,
            status=status,
            summary=trace.summary,
            warnings=trace.warnings,
            fallback_used=False,
            used_llm=trace.used_llm,
        )

    def _collect_stage_tool_warnings(
        self,
        stage_trace: list,
        fallback_message: str,
    ) -> list[str]:
        if not stage_trace:
            return []

        warnings: list[str] = []
        rate_limited = False
        for item in stage_trace:
            if getattr(item, "success", True):
                continue
            summary = getattr(item, "summary", "")
            if not summary:
                continue
            if self.adapter._is_rate_limit_text(summary):
                rate_limited = True
                continue
            warnings.append(summary)

        if rate_limited:
            warnings.append(fallback_message)
        return list(dict.fromkeys(warnings))

