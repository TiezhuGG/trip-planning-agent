import asyncio
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.agents.planning_agent import PlanningCoordinatorAgent
from app.config import Settings
from app.schemas.planning import (
    Activity,
    AgentExecution,
    BudgetBreakdown,
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

    async def fake_adapter_diagnose() -> IntegrationStatus:
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

    async def fake_seed_gather(_request: TripPlanningRequest) -> tuple[InitialPlanDraft, AgentExecution]:
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
        return draft, AgentExecution(agent_name="planner_seed_agent", success=True)

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
        initial_plan: InitialPlanDraft,
        attractions: list[POIRecommendation],
        hotels: list[POIRecommendation],
        day_restaurants: dict[int, list[POIRecommendation]],
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], AgentExecution]:
        _ = (request, initial_plan, attractions, hotels, day_restaurants, trace)
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

    coordinator.adapter.diagnose = fake_adapter_diagnose
    coordinator.ai_client.diagnose = fake_llm_diagnose
    coordinator.seed_agent.gather = fake_seed_gather
    coordinator.sight_agent.gather = fake_sight_gather
    coordinator.hotel_agent.gather = fake_hotel_gather
    coordinator.weather_agent.gather = fake_weather_gather
    coordinator.meal_agent.gather = fake_meal_gather
    coordinator.route_agent.gather = fake_route_gather
    coordinator.composer_agent.gather = fake_compose_gather

    request = TripPlanningRequest(
        destination="\u4e0a\u6d77",
        start_date=date(2026, 3, 20),
        days=2,
    )
    result = asyncio.run(coordinator.generate(request, generated_at=datetime.utcnow()))

    assert result.status == "success"
    assert result.plan.days
    assert result.planning_context.weather.daily_forecasts == []
    assert any("weather_agent 调用失败" in item for item in result.meta.warnings)
    weather_trace = next(item for item in result.agent_trace if item.agent_name == "weather_agent")
    assert weather_trace.success is False
