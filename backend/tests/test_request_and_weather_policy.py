import asyncio
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.agents.planning_agent import PlanningCoordinatorAgent
from app.config import Settings
from app.schemas.planning import (
    Activity,
    AgentExecution,
    BudgetBreakdown,
    DailyForecast,
    DayPlan,
    InitialPlanDay,
    InitialPlanDraft,
    IntegrationStatus,
    MealRecommendation,
    POIRecommendation,
    RouteSummary,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
    WeatherSummary,
)
from app.services.amap_mcp_adapter import MCPProtocolError
from app.services.ai_client import LLMDiagnosisResult


def test_destination_rejects_non_chinese_city_name() -> None:
    with pytest.raises(ValidationError):
        TripPlanningRequest(
            destination="Shanghai",
            start_date=date(2026, 3, 20),
        )


def test_generate_keeps_working_when_weather_unavailable() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        amap_mcp_command="uvx",
    )
    coordinator = PlanningCoordinatorAgent(settings)
    coordinator.adapter.client = object()

    async def fake_adapter_diagnose(force_refresh: bool = True) -> IntegrationStatus:
        _ = force_refresh
        return IntegrationStatus(
            mcp_enabled=True,
            mcp_connected=True,
            resolved_tools={
                "poi_search": "maps_text_search",
                "weather": "maps_weather",
                "route_plan": "maps_direction_driving_by_address",
            },
            missing_tools=[],
        )

    async def fake_llm_diagnose(check_connection: bool = False) -> LLMDiagnosisResult:
        return LLMDiagnosisResult(
            enabled=True,
            reachable=True,
            model="test-model",
            base_url="",
            warnings=[],
        )

    async def fake_seed_gather(
        _request: TripPlanningRequest,
    ) -> tuple[InitialPlanDraft, AgentExecution, bool, bool, list[str]]:
        draft = InitialPlanDraft(
            summary="seed",
            days=[
                InitialPlanDay(
                    day_number=1,
                    date="2026-03-20",
                    theme="Theme 1",
                    focus="Focus 1",
                    must_visit=[],
                ),
                InitialPlanDay(
                    day_number=2,
                    date="2026-03-21",
                    theme="Theme 2",
                    focus="Focus 2",
                    must_visit=[],
                ),
            ],
        )
        return draft, AgentExecution(agent_name="planner_seed_agent", success=True), True, False, []

    async def fake_sight_gather(
        _request: TripPlanningRequest,
        _trace: list[ToolCallRecord],
    ) -> tuple[list[POIRecommendation], list[POIRecommendation]]:
        attractions = [POIRecommendation(name="Attraction A"), POIRecommendation(name="Attraction B")]
        restaurants = [POIRecommendation(name="Restaurant A"), POIRecommendation(name="Restaurant B")]
        return attractions, restaurants

    async def fake_hotel_gather(
        _request: TripPlanningRequest,
        _attractions: list[POIRecommendation],
        _trace: list[ToolCallRecord],
    ) -> list[POIRecommendation]:
        return [POIRecommendation(name="Hotel A", address="Center")]

    async def fake_weather_gather(
        _request: TripPlanningRequest,
        _trace: list[ToolCallRecord],
    ) -> WeatherSummary:
        raise RuntimeError("No forecast data available")

    def fake_meal_gather(
        _request: TripPlanningRequest,
        _initial_plan: InitialPlanDraft,
        restaurants: list[POIRecommendation],
    ) -> dict[int, list[POIRecommendation]]:
        return {
            1: restaurants[:1],
            2: restaurants[1:2],
        }

    async def fake_route_gather(
        request: TripPlanningRequest,
        plan: TravelPlan,
        context,
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], AgentExecution]:
        _ = (request, plan, context, trace)
        routes = [
            RouteSummary(day_number=1, from_name="Hotel A", to_name="Attraction A"),
            RouteSummary(day_number=2, from_name="Hotel A", to_name="Attraction B"),
        ]
        trace = AgentExecution(agent_name="route_agent", success=True)
        return routes, trace

    async def fake_compose_gather(
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context,
        tool_trace: list[ToolCallRecord],
    ):
        _ = (request, initial_plan, context, tool_trace)
        plan = TravelPlan(
            title="Plan",
            summary="Summary",
            weather_summary="",
            best_booking_tip="Tip",
            estimated_budget=BudgetBreakdown(
                currency="CNY",
                accommodation="¥100-¥200",
                transport="¥100-¥200",
                food="¥100-¥200",
                tickets="¥100-¥200",
                extras="¥100-¥200",
                total_estimate="¥500-¥1000",
            ),
            city_tips=[],
            packing_list=[],
            stay_recommendations=[],
            days=[
                DayPlan(
                    day_number=1,
                    date="2026-03-20",
                    theme="Theme 1",
                    overview="Overview 1",
                    hotel_area="Center",
                    meals=[MealRecommendation(meal_type="lunch", venue_name="Restaurant A")],
                    activities=[
                        Activity(
                            start_time="09:00",
                            end_time="11:00",
                            title="Activity 1",
                            category="sightseeing",
                            description="Desc 1",
                            location_name="Attraction A",
                        )
                    ],
                    route_summary=RouteSummary(day_number=1, from_name="Hotel A", to_name="Attraction A"),
                ),
                DayPlan(
                    day_number=2,
                    date="2026-03-21",
                    theme="Theme 2",
                    overview="Overview 2",
                    hotel_area="Center",
                    meals=[MealRecommendation(meal_type="dinner", venue_name="Restaurant B")],
                    activities=[
                        Activity(
                            start_time="10:00",
                            end_time="12:00",
                            title="Activity 2",
                            category="sightseeing",
                            description="Desc 2",
                            location_name="Attraction B",
                        )
                    ],
                    route_summary=RouteSummary(day_number=2, from_name="Hotel A", to_name="Attraction B"),
                ),
            ],
        )
        trace = AgentExecution(agent_name="itinerary_composer_agent", success=True)
        return plan, trace, True, False, []

    async def fake_bind_daily_stays(
        request: TripPlanningRequest,
        plan: TravelPlan,
        context,
        trace: list[ToolCallRecord],
    ):
        _ = (request, context, trace)
        return plan, [POIRecommendation(name="Hotel A", address="Center")], AgentExecution(agent_name="hotel_binding_agent", success=True)

    async def fake_bind_daily_meals(
        request: TripPlanningRequest,
        plan: TravelPlan,
        context,
        trace: list[ToolCallRecord],
    ):
        _ = (request, context, trace)
        return plan, [POIRecommendation(name="Restaurant A", address="Center")], AgentExecution(agent_name="meal_binding_agent", success=True)

    coordinator.adapter.diagnose = fake_adapter_diagnose
    coordinator.ai_client.diagnose = fake_llm_diagnose
    coordinator.seed_agent.gather = fake_seed_gather
    coordinator.sight_agent.gather = fake_sight_gather
    coordinator.hotel_agent.gather = fake_hotel_gather
    coordinator.hotel_agent.bind_daily_stays = fake_bind_daily_stays
    coordinator.weather_agent.gather = fake_weather_gather
    coordinator.meal_agent.gather = fake_meal_gather
    coordinator.meal_agent.bind_daily_meals = fake_bind_daily_meals
    coordinator.route_agent.gather_for_plan = fake_route_gather
    coordinator.composer_agent.gather = fake_compose_gather

    request = TripPlanningRequest(
        destination="\u4e0a\u6d77",
        start_date=date(2026, 3, 20),
        days=2,
    )
    result = asyncio.run(coordinator.generate(request, generated_at=datetime.now(UTC)))

    assert result.status == "partial_success"
    assert result.plan.days
    assert result.planning_context.weather.daily_forecasts == []
    assert any("weather_agent 调用失败" in item for item in result.meta.warnings)
    assert any(item.stage == "weather" and item.status == "error" for item in result.diagnostics.mcp)
    weather_trace = next(item for item in result.agent_trace if item.agent_name == "weather_agent")
    assert weather_trace.success is False


def test_generate_keeps_working_when_poi_unavailable() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        amap_mcp_command="uvx",
    )
    coordinator = PlanningCoordinatorAgent(settings)
    coordinator.adapter.client = object()

    async def fake_adapter_diagnose(force_refresh: bool = True) -> IntegrationStatus:
        _ = force_refresh
        return IntegrationStatus(
            mcp_enabled=True,
            mcp_connected=True,
            resolved_tools={
                "poi_search": "maps_text_search",
                "weather": "maps_weather",
                "route_plan": "maps_direction_driving_by_address",
            },
            missing_tools=[],
        )

    async def fake_llm_diagnose(check_connection: bool = False) -> LLMDiagnosisResult:
        _ = check_connection
        return LLMDiagnosisResult(
            enabled=True,
            reachable=True,
            model="test-model",
            base_url="",
            warnings=[],
        )

    async def fake_seed_gather(
        _request: TripPlanningRequest,
    ) -> tuple[InitialPlanDraft, AgentExecution, bool, bool, list[str]]:
        draft = InitialPlanDraft(
            summary="seed",
            days=[
                InitialPlanDay(
                    day_number=1,
                    date="2026-03-20",
                    theme="Theme 1",
                    focus="Focus 1",
                    must_visit=[],
                )
            ],
        )
        return draft, AgentExecution(agent_name="planner_seed_agent", success=True), True, False, []

    async def fake_sight_gather(
        _request: TripPlanningRequest,
        _trace: list[ToolCallRecord],
    ) -> tuple[list[POIRecommendation], list[POIRecommendation]]:
        raise MCPProtocolError("maps_text_search 返回错误: Text Search failed: CUQPS_HAS_EXCEEDED_THE_LIMIT")

    async def fake_hotel_gather(
        _request: TripPlanningRequest,
        _attractions: list[POIRecommendation],
        _trace: list[ToolCallRecord],
    ) -> list[POIRecommendation]:
        return []

    async def fake_weather_gather(
        _request: TripPlanningRequest,
        _trace: list[ToolCallRecord],
    ) -> WeatherSummary:
        return WeatherSummary()

    def fake_meal_gather(
        _request: TripPlanningRequest,
        _initial_plan: InitialPlanDraft,
        restaurants: list[POIRecommendation],
    ) -> dict[int, list[POIRecommendation]]:
        _ = restaurants
        return {}

    async def fake_route_gather(
        request: TripPlanningRequest,
        plan: TravelPlan,
        context,
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], AgentExecution]:
        _ = (request, plan, context, trace)
        return (
            [RouteSummary(day_number=1, from_name="Start", to_name="End")],
            AgentExecution(agent_name="route_agent", success=True),
        )

    async def fake_compose_gather(
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context,
        tool_trace: list[ToolCallRecord],
    ):
        _ = (request, initial_plan, context, tool_trace)
        plan = TravelPlan(
            title="Plan",
            summary="Summary",
            weather_summary="",
            best_booking_tip="Tip",
            estimated_budget=BudgetBreakdown(),
            city_tips=[],
            packing_list=[],
            stay_recommendations=[],
            days=[
                DayPlan(
                    day_number=1,
                    date="2026-03-20",
                    theme="Theme 1",
                    overview="Overview 1",
                    hotel_area="Center",
                    meals=[MealRecommendation(meal_type="lunch", venue_name="Fallback Meal")],
                    activities=[
                        Activity(
                            start_time="09:00",
                            end_time="10:00",
                            title="Fallback Activity",
                            category="sightseeing",
                            description="Desc",
                            location_name="Fallback Location",
                        )
                    ],
                    route_summaries=[RouteSummary(day_number=1, from_name="Start", to_name="End")],
                )
            ],
        )
        trace = AgentExecution(agent_name="itinerary_composer_agent", success=True)
        return plan, trace, True, False, []

    async def fake_bind_daily_stays(
        request: TripPlanningRequest,
        plan: TravelPlan,
        context,
        trace: list[ToolCallRecord],
    ):
        _ = (request, context, trace)
        return plan, [], AgentExecution(agent_name="hotel_binding_agent", success=True)

    async def fake_bind_daily_meals(
        request: TripPlanningRequest,
        plan: TravelPlan,
        context,
        trace: list[ToolCallRecord],
    ):
        _ = (request, context, trace)
        return plan, [], AgentExecution(agent_name="meal_binding_agent", success=True)

    coordinator.adapter.diagnose = fake_adapter_diagnose
    coordinator.ai_client.diagnose = fake_llm_diagnose
    coordinator.seed_agent.gather = fake_seed_gather
    coordinator.sight_agent.gather = fake_sight_gather
    coordinator.hotel_agent.gather = fake_hotel_gather
    coordinator.hotel_agent.bind_daily_stays = fake_bind_daily_stays
    coordinator.weather_agent.gather = fake_weather_gather
    coordinator.meal_agent.gather = fake_meal_gather
    coordinator.meal_agent.bind_daily_meals = fake_bind_daily_meals
    coordinator.route_agent.gather_for_plan = fake_route_gather
    coordinator.composer_agent.gather = fake_compose_gather

    request = TripPlanningRequest(
        destination="上海",
        start_date=date(2026, 3, 20),
        days=1,
    )
    result = asyncio.run(coordinator.generate(request, generated_at=datetime.now(UTC)))

    assert result.status == "partial_success"
    assert result.plan.days
    assert any("poi_agent 调用失败" in item for item in result.meta.warnings)
    assert any(item.stage == "poi_collection" and item.status == "error" for item in result.diagnostics.mcp)
    poi_trace = next(item for item in result.agent_trace if item.agent_name == "poi_agent")
    assert poi_trace.success is False


def test_generate_keeps_working_when_hotels_unavailable() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        amap_mcp_command="uvx",
    )
    coordinator = PlanningCoordinatorAgent(settings)
    coordinator.adapter.client = object()

    async def fake_adapter_diagnose(force_refresh: bool = True) -> IntegrationStatus:
        _ = force_refresh
        return IntegrationStatus(
            mcp_enabled=True,
            mcp_connected=True,
            resolved_tools={
                "poi_search": "maps_text_search",
                "weather": "maps_weather",
                "route_plan": "maps_direction_driving_by_address",
            },
            missing_tools=[],
        )

    async def fake_llm_diagnose(check_connection: bool = False) -> LLMDiagnosisResult:
        _ = check_connection
        return LLMDiagnosisResult(
            enabled=True,
            reachable=True,
            model="test-model",
            base_url="",
            warnings=[],
        )

    async def fake_seed_gather(
        _request: TripPlanningRequest,
    ) -> tuple[InitialPlanDraft, AgentExecution, bool, bool, list[str]]:
        draft = InitialPlanDraft(
            summary="seed",
            days=[
                InitialPlanDay(
                    day_number=1,
                    date="2026-03-20",
                    theme="Theme 1",
                    focus="Focus 1",
                    must_visit=[],
                )
            ],
        )
        return draft, AgentExecution(agent_name="planner_seed_agent", success=True), True, False, []

    async def fake_sight_gather(
        _request: TripPlanningRequest,
        _trace: list[ToolCallRecord],
    ) -> tuple[list[POIRecommendation], list[POIRecommendation]]:
        return [POIRecommendation(name="Attraction A")], [POIRecommendation(name="Restaurant A")]

    async def fake_hotel_gather(
        _request: TripPlanningRequest,
        _attractions: list[POIRecommendation],
        _trace: list[ToolCallRecord],
    ) -> list[POIRecommendation]:
        raise MCPProtocolError("maps_text_search 返回错误: Text Search failed: CUQPS_HAS_EXCEEDED_THE_LIMIT")

    async def fake_weather_gather(
        _request: TripPlanningRequest,
        _trace: list[ToolCallRecord],
    ) -> WeatherSummary:
        return WeatherSummary(
            daily_forecasts=[DailyForecast(date="2026-03-20")]
        )

    def fake_meal_gather(
        _request: TripPlanningRequest,
        _initial_plan: InitialPlanDraft,
        restaurants: list[POIRecommendation],
    ) -> dict[int, list[POIRecommendation]]:
        return {1: restaurants}

    async def fake_route_gather(
        request: TripPlanningRequest,
        plan: TravelPlan,
        context,
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], AgentExecution]:
        _ = (request, plan, context, trace)
        return (
            [RouteSummary(day_number=1, from_name="Hotel", to_name="Attraction A")],
            AgentExecution(agent_name="route_agent", success=True),
        )

    async def fake_compose_gather(
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context,
        tool_trace: list[ToolCallRecord],
    ):
        _ = (request, initial_plan, context, tool_trace)
        plan = TravelPlan(
            title="Plan",
            summary="Summary",
            weather_summary="",
            best_booking_tip="Tip",
            estimated_budget=BudgetBreakdown(),
            city_tips=[],
            packing_list=[],
            stay_recommendations=[],
            days=[
                DayPlan(
                    day_number=1,
                    date="2026-03-20",
                    theme="Theme 1",
                    overview="Overview 1",
                    hotel_area="Center",
                    meals=[MealRecommendation(meal_type="lunch", venue_name="Restaurant A")],
                    activities=[
                        Activity(
                            start_time="09:00",
                            end_time="11:00",
                            title="Activity 1",
                            category="sightseeing",
                            description="Desc 1",
                            location_name="Attraction A",
                        )
                    ],
                    route_summaries=[RouteSummary(day_number=1, from_name="Hotel", to_name="Attraction A")],
                )
            ],
        )
        trace = AgentExecution(agent_name="itinerary_composer_agent", success=True)
        return plan, trace, True, False, []

    async def fake_bind_daily_stays(
        request: TripPlanningRequest,
        plan: TravelPlan,
        context,
        trace: list[ToolCallRecord],
    ):
        _ = (request, context, trace)
        return plan, [], AgentExecution(agent_name="hotel_binding_agent", success=True)

    async def fake_bind_daily_meals(
        request: TripPlanningRequest,
        plan: TravelPlan,
        context,
        trace: list[ToolCallRecord],
    ):
        _ = (request, context, trace)
        return plan, context.restaurants, AgentExecution(agent_name="meal_binding_agent", success=True)

    coordinator.adapter.diagnose = fake_adapter_diagnose
    coordinator.ai_client.diagnose = fake_llm_diagnose
    coordinator.seed_agent.gather = fake_seed_gather
    coordinator.sight_agent.gather = fake_sight_gather
    coordinator.hotel_agent.gather = fake_hotel_gather
    coordinator.hotel_agent.bind_daily_stays = fake_bind_daily_stays
    coordinator.weather_agent.gather = fake_weather_gather
    coordinator.meal_agent.gather = fake_meal_gather
    coordinator.meal_agent.bind_daily_meals = fake_bind_daily_meals
    coordinator.route_agent.gather_for_plan = fake_route_gather
    coordinator.composer_agent.gather = fake_compose_gather

    request = TripPlanningRequest(
        destination="上海",
        start_date=date(2026, 3, 20),
        days=1,
    )
    result = asyncio.run(coordinator.generate(request, generated_at=datetime.now(UTC)))

    assert result.status == "partial_success"
    assert result.plan.days
    assert any("hotel_agent 调用失败" in item for item in result.meta.warnings)
    assert any(item.stage == "hotel_candidates" and item.status == "error" for item in result.diagnostics.mcp)
    weather_trace = next(item for item in result.agent_trace if item.agent_name == "weather_agent")
    hotel_trace = next(item for item in result.agent_trace if item.agent_name == "hotel_agent")
    assert weather_trace.success is True
    assert hotel_trace.success is False
