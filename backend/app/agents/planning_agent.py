from datetime import datetime

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
    PlanGenerationMeta,
    PlanningContext,
    PlanningResponse,
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
        self.meal_agent = MealRecommendationAgent()
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
        self, request: TripPlanningRequest, generated_at: datetime
    ) -> PlanningResponse:
        agent_trace: list[AgentExecution] = []
        warnings: list[str] = []
        integration_status = await self.adapter.diagnose()
        llm_status = await self.ai_client.diagnose(check_connection=False)
        integration_status.llm_enabled = llm_status.enabled
        integration_status.llm_reachable = llm_status.reachable
        integration_status.llm_model = llm_status.model
        integration_status.llm_base_url = llm_status.base_url
        integration_status.warnings.extend(llm_status.warnings)
        warnings.extend(integration_status.warnings)

        initial_plan, seed_trace = await self.seed_agent.gather(request)
        agent_trace.append(seed_trace)
        warnings.extend(seed_trace.warnings)

        if not self.adapter.has_client and self.settings.enable_mock_mcp:
            context, tool_trace = self.adapter.mock_context(request)
            agent_trace.extend(
                [
                    AgentExecution(
                        agent_name="poi_agent",
                        success=True,
                        summary="未配置高德 MCP，已使用 Mock 景点与餐饮数据。",
                        used_llm=False,
                        used_tools=[],
                    ),
                    AgentExecution(
                        agent_name="hotel_agent",
                        success=True,
                        summary="未配置高德 MCP，已使用 Mock 酒店数据。",
                        used_llm=False,
                        used_tools=[],
                    ),
                    AgentExecution(
                        agent_name="weather_agent",
                        success=True,
                        summary="未配置高德 MCP，已使用 Mock 天气数据。",
                        used_llm=False,
                        used_tools=[],
                    ),
                ]
            )
        else:
            tool_trace = []
            context = PlanningContext(
                destination=request.destination,
                attractions=[],
                restaurants=[],
                hotels=[],
                routes=[],
                weather=WeatherSummary(),
            )
            try:
                attractions, restaurants = await self.sight_agent.gather(request, tool_trace)
                context.attractions = attractions[:12]
                context.restaurants = restaurants[:12]
                agent_trace.append(
                    AgentExecution(
                        agent_name="poi_agent",
                        success=True,
                        summary=f"已获取 {len(context.attractions)} 个景点和 {len(context.restaurants)} 个餐饮候选。",
                        used_llm=False,
                        used_tools=[integration_status.resolved_tools.get("poi_search", self.adapter.settings.amap_mcp_tool_poi_search)],
                    )
                )
            except Exception as exc:
                warnings.append(f"poi_agent 调用失败: {exc}")
                agent_trace.append(
                    AgentExecution(
                        agent_name="poi_agent",
                        success=False,
                        summary="景点与餐饮检索失败，已保留空结果继续生成行程。",
                        used_llm=False,
                        used_tools=[integration_status.resolved_tools.get("poi_search", self.adapter.settings.amap_mcp_tool_poi_search)],
                        warnings=[str(exc)],
                    )
                )

            try:
                hotels = await self.hotel_agent.gather(request, tool_trace)
                context.hotels = hotels[:8]
                agent_trace.append(
                    AgentExecution(
                        agent_name="hotel_agent",
                        success=True,
                        summary=f"已获取 {len(context.hotels)} 个酒店候选。",
                        used_llm=False,
                        used_tools=[integration_status.resolved_tools.get("poi_search", self.adapter.settings.amap_mcp_tool_poi_search)],
                    )
                )
            except Exception as exc:
                warnings.append(f"hotel_agent 调用失败: {exc}")
                agent_trace.append(
                    AgentExecution(
                        agent_name="hotel_agent",
                        success=False,
                        summary="酒店检索失败，已保留空结果继续生成行程。",
                        used_llm=False,
                        used_tools=[integration_status.resolved_tools.get("poi_search", self.adapter.settings.amap_mcp_tool_poi_search)],
                        warnings=[str(exc)],
                    )
                )

            try:
                context.weather = await self.weather_agent.gather(request, tool_trace)
                agent_trace.append(
                    AgentExecution(
                        agent_name="weather_agent",
                        success=True,
                        summary=f"已获取 {len(context.weather.daily_forecasts)} 天天气信息。",
                        used_llm=False,
                        used_tools=[integration_status.resolved_tools.get("weather", self.adapter.settings.amap_mcp_tool_weather)],
                    )
                )
            except Exception as exc:
                warnings.append(f"weather_agent 调用失败: {exc}")
                agent_trace.append(
                    AgentExecution(
                        agent_name="weather_agent",
                        success=False,
                        summary="天气检索失败，已保留空结果继续生成行程。",
                        used_llm=False,
                        used_tools=[integration_status.resolved_tools.get("weather", self.adapter.settings.amap_mcp_tool_weather)],
                        warnings=[str(exc)],
                    )
                )

        day_restaurants = self.meal_agent.gather(request, initial_plan, context.restaurants)
        agent_trace.append(
            AgentExecution(
                agent_name="meal_agent",
                success=True,
                summary=f"已为 {len(day_restaurants)} 天行程匹配餐饮候选。",
                used_llm=False,
                used_tools=[],
            )
        )

        routes, route_trace = await self.route_agent.gather(
            request=request,
            initial_plan=initial_plan,
            attractions=context.attractions,
            hotels=context.hotels,
            day_restaurants=day_restaurants,
            trace=tool_trace,
        )
        context.routes = routes
        agent_trace.append(route_trace)
        warnings.extend(route_trace.warnings)

        plan, compose_trace, compose_llm_used, compose_fallback_used, compose_warnings = await self.composer_agent.gather(
            request=request,
            initial_plan=initial_plan,
            context=context,
            tool_trace=tool_trace,
        )
        agent_trace.append(compose_trace)
        warnings.extend(compose_warnings)

        llm_used = seed_trace.used_llm or compose_llm_used
        fallback_used = bool(seed_trace.warnings or compose_fallback_used)
        integration_status.llm_reachable = integration_status.llm_reachable or llm_used

        return PlanningResponse(
            generated_at=generated_at,
            request_echo=request,
            initial_plan=initial_plan,
            planning_context=context,
            agent_trace=agent_trace,
            tool_trace=tool_trace,
            meta=PlanGenerationMeta(
                llm_used=llm_used,
                fallback_used=fallback_used,
                model_name=self.settings.openai_model,
                warnings=warnings,
            ),
            map_config=MapRenderConfig(
                enabled=self.settings.has_map_rendering,
                js_api_key=self.settings.amap_api_key or None,
                security_js_code=self.settings.amap_security_js_code or None,
                center=self._resolve_center(context),
            ),
            integration_status=integration_status,
            plan=plan,
        )

    def _resolve_center(self, context: PlanningContext) -> GeoPoint | None:
        for poi in [*context.attractions, *context.hotels, *context.restaurants]:
            if poi.longitude is None or poi.latitude is None:
                continue
            return GeoPoint(longitude=poi.longitude, latitude=poi.latitude)
        return None
