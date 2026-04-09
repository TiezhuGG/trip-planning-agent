import asyncio
from datetime import UTC, date, datetime

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
    request: TripPlanningRequest,
    generated_at: datetime,
    stage_timings_ms: dict[str, int],
) -> PlanningResponse:
    return PlanningResponse(
        status="success",
        generated_at=generated_at,
        request_echo=request,
        initial_plan=InitialPlanDraft(
            summary="seed",
            days=[
                InitialPlanDay(
                    day_number=1,
                    date=request.start_date.isoformat(),
                    theme="主题",
                    focus="核心区域",
                    must_visit=[],
                )
            ],
        ),
        planning_context=PlanningContext(destination=request.destination, weather=WeatherSummary()),
        agent_trace=[AgentExecution(agent_name="planner_seed_agent", success=True)],
        tool_trace=[],
        meta=PlanGenerationMeta(
            llm_used=True,
            fallback_used=False,
            model_name="mock",
            warnings=[],
            stage_timings_ms=stage_timings_ms,
        ),
        diagnostics=PlanDiagnostics(),
        map_config=MapRenderConfig(),
        integration_status=IntegrationStatus(),
        plan=TravelPlan(
            title="Plan",
            summary="Summary",
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


def test_planner_telemetry_collects_stage_percentiles() -> None:
    settings = Settings(
        planner_generate_cache_enabled=False,
        planner_stage_stats_enabled=True,
        planner_stage_stats_window=10,
        planner_stage_slow_threshold_ms_per_stage=999999,
        planner_stage_slow_threshold_ms_total=999999,
    )
    service = TravelPlannerService(settings)
    counter = {"idx": 0}

    async def fake_generate(
        request: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = include_debug
        counter["idx"] += 1
        compose = 100 if counter["idx"] == 1 else 300
        total = 200 if counter["idx"] == 1 else 600
        return _build_response(
            request=request,
            generated_at=generated_at,
            stage_timings_ms={"compose": compose, "total": total},
        )

    service.coordinator.generate = fake_generate
    request = TripPlanningRequest(destination="北京", start_date=date(2026, 5, 1), days=1)

    asyncio.run(service.generate(request, generated_at=datetime.now(UTC), include_debug=True))
    asyncio.run(service.generate(request, generated_at=datetime.now(UTC), include_debug=True))
    telemetry = asyncio.run(service.get_telemetry())

    assert telemetry.enabled is True
    assert telemetry.total_requests == 2
    assert telemetry.cache_hits == 0
    assert telemetry.cache_misses == 2
    assert telemetry.stages["compose"].count == 2
    assert telemetry.stages["compose"].p50_ms == 100
    assert telemetry.stages["compose"].p95_ms == 300
    assert telemetry.stages["total"].max_ms == 600
    assert len(telemetry.stages["compose"].recent_points) == 2
    assert telemetry.stages["compose"].recent_points[-1].value_ms == 300


def test_generate_adds_slow_stage_warnings() -> None:
    settings = Settings(
        planner_generate_cache_enabled=False,
        planner_stage_stats_enabled=True,
        planner_stage_slow_threshold_ms_per_stage=100,
        planner_stage_slow_threshold_ms_total=250,
    )
    service = TravelPlannerService(settings)

    async def fake_generate(
        request: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = include_debug
        return _build_response(
            request=request,
            generated_at=generated_at,
            stage_timings_ms={"compose": 180, "total": 320},
        )

    service.coordinator.generate = fake_generate
    request = TripPlanningRequest(destination="上海", start_date=date(2026, 6, 1), days=1)
    result = asyncio.run(service.generate(request, generated_at=datetime.now(UTC), include_debug=True))

    assert any("阶段 compose 耗时 180ms" in item for item in result.meta.warnings)
    assert any("总耗时 320ms" in item for item in result.meta.warnings)


def test_planner_telemetry_counts_cache_hits_without_double_pipeline_stats() -> None:
    settings = Settings(
        planner_generate_cache_enabled=True,
        planner_generate_cache_ttl_seconds=60,
        planner_generate_cache_max_entries=8,
        planner_stage_stats_enabled=True,
    )
    service = TravelPlannerService(settings)
    counter = {"count": 0}

    async def fake_generate(
        request: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = include_debug
        counter["count"] += 1
        return _build_response(
            request=request,
            generated_at=generated_at,
            stage_timings_ms={"compose": 120, "total": 240},
        )

    service.coordinator.generate = fake_generate
    request = TripPlanningRequest(destination="杭州", start_date=date(2026, 7, 1), days=1)

    first = asyncio.run(service.generate(request, generated_at=datetime.now(UTC), include_debug=True))
    second = asyncio.run(service.generate(request, generated_at=datetime.now(UTC), include_debug=True))
    telemetry = asyncio.run(service.get_telemetry())

    assert counter["count"] == 1
    assert first.plan.title == second.plan.title
    assert telemetry.total_requests == 2
    assert telemetry.cache_hits == 1
    assert telemetry.cache_misses == 1
    assert telemetry.stages["compose"].count == 1
    assert telemetry.stages["compose"].recent_points[0].value_ms == 120
