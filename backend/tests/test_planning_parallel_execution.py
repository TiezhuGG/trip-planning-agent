import asyncio
from datetime import date, datetime

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


def test_generate_runs_hotel_and_weather_in_parallel() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        amap_mcp_command="uvx",
    )
    coordinator = PlanningCoordinatorAgent(settings)
    coordinator.adapter.client = object()

    hotel_started = asyncio.Event()
    weather_started = asyncio.Event()

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
                )
            ],
        )
        return draft, AgentExecution(agent_name="planner_seed_agent", success=True)

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
        hotel_started.set()
        await weather_started.wait()
        return [POIRecommendation(name="Hotel A", address="Center")]

    async def fake_weather_gather(
        _request: TripPlanningRequest,
        _trace: list[ToolCallRecord],
    ) -> WeatherSummary:
        weather_started.set()
        await hotel_started.wait()
        return WeatherSummary()

    def fake_meal_gather(
        _request: TripPlanningRequest,
        _initial_plan: InitialPlanDraft,
        restaurants: list[POIRecommendation],
    ) -> dict[int, list[POIRecommendation]]:
        return {1: restaurants}

    async def fake_route_gather(
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        attractions: list[POIRecommendation],
        hotels: list[POIRecommendation],
        day_restaurants: dict[int, list[POIRecommendation]],
        trace: list[ToolCallRecord],
    ) -> tuple[list[RouteSummary], AgentExecution]:
        _ = (request, initial_plan, attractions, hotels, day_restaurants, trace)
        return (
            [RouteSummary(day_number=1, from_name="Hotel A", to_name="Attraction A")],
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
                    route_summaries=[RouteSummary(day_number=1, from_name="Hotel A", to_name="Attraction A")],
                )
            ],
        )
        return plan, AgentExecution(agent_name="itinerary_composer_agent", success=True), True, False, []

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
        destination="上海",
        start_date=date(2026, 3, 20),
        days=1,
    )
    result = asyncio.run(
        asyncio.wait_for(
            coordinator.generate(request, generated_at=datetime.utcnow()),
            timeout=1.0,
        )
    )
    assert result.status == "success"
