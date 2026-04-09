import asyncio
from datetime import UTC, date, datetime, timedelta

from app.config import Settings
from app.schemas.planning import (
    Activity,
    AgentExecution,
    BudgetBreakdown,
    DayPlan,
    InitialPlanDay,
    InitialPlanDraft,
    IntegrationStatus,
    MapRenderConfig,
    MealRecommendation,
    PlanDiagnostics,
    PlanGenerationMeta,
    PlanningContext,
    PlanningResponse,
    TravelPlan,
    TripPlanningRequest,
    WeatherSummary,
)
from app.services.planner import TravelPlannerService


def _build_response(
    *,
    status: str,
    suffix: str,
    generated_at: datetime,
    request: TripPlanningRequest,
) -> PlanningResponse:
    return PlanningResponse(
        status=status,
        generated_at=generated_at,
        request_echo=request,
        initial_plan=InitialPlanDraft(
            summary=f"seed-{suffix}",
            days=[
                InitialPlanDay(
                    day_number=1,
                    date=request.start_date.isoformat(),
                    theme="主题",
                    focus="核心片区",
                    must_visit=[],
                )
            ],
        ),
        planning_context=PlanningContext(destination=request.destination, weather=WeatherSummary()),
        agent_trace=[AgentExecution(agent_name="planner_seed_agent", success=True)],
        tool_trace=[],
        meta=PlanGenerationMeta(llm_used=True, stage_timings_ms={"total": 10}),
        diagnostics=PlanDiagnostics(),
        map_config=MapRenderConfig(),
        integration_status=IntegrationStatus(),
        plan=TravelPlan(
            title=f"plan-{suffix}",
            summary=f"summary-{suffix}",
            weather_summary="",
            best_booking_tip="",
            estimated_budget=BudgetBreakdown(),
            stay_recommendations=[],
            city_tips=[],
            packing_list=[],
            days=[
                DayPlan(
                    day_number=1,
                    date=request.start_date.isoformat(),
                    theme="主题",
                    overview="概览",
                    hotel_area="市中心",
                    meals=[MealRecommendation(meal_type="lunch", venue_name="本地餐厅")],
                    activities=[
                        Activity(
                            start_time="09:00",
                            end_time="11:00",
                            title="景点活动",
                            category="sightseeing",
                            description="描述",
                            location_name="景点",
                        )
                    ],
                )
            ],
        ),
    )


def test_generate_cache_hit_reuses_recent_response() -> None:
    settings = Settings(
        planner_generate_cache_enabled=True,
        planner_generate_cache_ttl_seconds=60,
        planner_generate_cache_max_entries=8,
    )
    service = TravelPlannerService(settings)
    counter = 0

    async def fake_generate(
        request: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        nonlocal counter
        _ = include_debug
        counter += 1
        return _build_response(
            status="success",
            suffix=str(counter),
            generated_at=generated_at,
            request=request,
        )

    service.coordinator.generate = fake_generate
    request = TripPlanningRequest(destination="北京", start_date=date(2026, 5, 1), days=1)

    first_at = datetime.now(UTC)
    second_at = first_at + timedelta(seconds=5)
    first = asyncio.run(service.generate(request, generated_at=first_at, include_debug=True))
    second = asyncio.run(service.generate(request, generated_at=second_at, include_debug=True))

    assert counter == 1
    assert first.plan.title == "plan-1"
    assert second.plan.title == "plan-1"
    assert second.generated_at == second_at


def test_generate_cache_does_not_store_partial_success() -> None:
    settings = Settings(
        planner_generate_cache_enabled=True,
        planner_generate_cache_ttl_seconds=60,
        planner_generate_cache_max_entries=8,
    )
    service = TravelPlannerService(settings)
    counter = 0

    async def fake_generate(
        request: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        nonlocal counter
        _ = include_debug
        counter += 1
        return _build_response(
            status="partial_success",
            suffix=str(counter),
            generated_at=generated_at,
            request=request,
        )

    service.coordinator.generate = fake_generate
    request = TripPlanningRequest(destination="杭州", start_date=date(2026, 6, 1), days=1)

    first = asyncio.run(service.generate(request, generated_at=datetime.now(UTC), include_debug=True))
    second = asyncio.run(service.generate(request, generated_at=datetime.now(UTC), include_debug=True))

    assert counter == 2
    assert first.plan.title == "plan-1"
    assert second.plan.title == "plan-2"


def test_generate_singleflight_deduplicates_inflight_same_request() -> None:
    settings = Settings(
        planner_generate_cache_enabled=True,
        planner_generate_cache_ttl_seconds=60,
        planner_generate_cache_max_entries=8,
    )
    service = TravelPlannerService(settings)
    counter = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_generate(
        request: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        nonlocal counter
        _ = include_debug
        counter += 1
        started.set()
        await release.wait()
        return _build_response(
            status="success",
            suffix="singleflight",
            generated_at=generated_at,
            request=request,
        )

    service.coordinator.generate = fake_generate
    request = TripPlanningRequest(destination="上海", start_date=date(2026, 7, 1), days=1)

    async def run_case() -> tuple[PlanningResponse, PlanningResponse]:
        first_at = datetime.now(UTC)
        second_at = first_at + timedelta(seconds=2)
        task1 = asyncio.create_task(service.generate(request, generated_at=first_at, include_debug=True))
        await started.wait()
        task2 = asyncio.create_task(service.generate(request, generated_at=second_at, include_debug=True))
        await asyncio.sleep(0)
        release.set()
        return await asyncio.gather(task1, task2)

    first, second = asyncio.run(run_case())

    assert counter == 1
    assert first.plan.title == "plan-singleflight"
    assert second.plan.title == "plan-singleflight"
    assert first.generated_at < second.generated_at
