import asyncio
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from app.config import Settings
from app.schemas.planning import (
    Activity,
    AgentExecution,
    BudgetBreakdown,
    DayCostBreakdown,
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
    ReplanRequest,
    TripCreateRequest,
    TripPlanningRequest,
    TripWorkspacePatchRequest,
    TravelPlan,
    WeatherSummary,
)
from app.services.planner import TravelPlannerService
from app.services.trip_workspace import TripWorkspaceService


def _make_store_path() -> Path:
    root = Path(__file__).resolve().parent / "_trip_workspace_testdata"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{uuid.uuid4().hex}.json"


def _build_request() -> TripPlanningRequest:
    return TripPlanningRequest(
        destination="上海",
        start_date=date(2026, 5, 1),
        days=2,
        interests=["自然风光"],
    )


def _build_response(
    *,
    request: TripPlanningRequest,
    generated_at: datetime,
    suffix: str,
) -> PlanningResponse:
    return PlanningResponse(
        status="success",
        generated_at=generated_at,
        request_echo=request,
        initial_plan=InitialPlanDraft(
            summary=f"seed-{suffix}",
            days=[
                InitialPlanDay(
                    day_number=1,
                    date=request.start_date.isoformat(),
                    theme=f"主题1-{suffix}",
                    focus="外滩",
                    must_visit=[],
                ),
                InitialPlanDay(
                    day_number=2,
                    date=(request.start_date.replace(day=request.start_date.day + 1)).isoformat(),
                    theme=f"主题2-{suffix}",
                    focus="徐汇",
                    must_visit=[],
                ),
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
            stage_timings_ms={"total": 20},
        ),
        diagnostics=PlanDiagnostics(),
        map_config=MapRenderConfig(),
        integration_status=IntegrationStatus(),
        plan=TravelPlan(
            title=f"plan-{suffix}",
            summary=f"summary-{suffix}",
            weather_summary="",
            best_booking_tip="tip",
            estimated_budget=BudgetBreakdown(),
            stay_recommendations=[],
            city_tips=[],
            packing_list=[],
            days=[
                DayPlan(
                    day_number=1,
                    date=request.start_date.isoformat(),
                    theme=f"第1天-{suffix}",
                    overview=f"overview-1-{suffix}",
                    hotel_area="黄浦",
                    cost_breakdown=DayCostBreakdown(
                        accommodation_per_person_cny=100,
                        transport_per_person_cny=20,
                        food_per_person_cny=40,
                        tickets_per_person_cny=30,
                        extras_per_person_cny=10,
                        total_per_person_cny=200,
                    ),
                    meals=[MealRecommendation(meal_type="lunch", venue_name=f"餐厅1-{suffix}", estimated_cost_cny=40)],
                    activities=[
                        Activity(
                            start_time="09:00",
                            end_time="10:30",
                            title=f"活动1-{suffix}",
                            category="sightseeing",
                            description="desc",
                            location_name="外滩",
                            ticket_cost_cny=30,
                        )
                    ],
                ),
                DayPlan(
                    day_number=2,
                    date="2026-05-02",
                    theme=f"第2天-{suffix}",
                    overview=f"overview-2-{suffix}",
                    hotel_area="徐汇",
                    cost_breakdown=DayCostBreakdown(
                        accommodation_per_person_cny=110,
                        transport_per_person_cny=25,
                        food_per_person_cny=45,
                        tickets_per_person_cny=35,
                        extras_per_person_cny=10,
                        total_per_person_cny=225,
                    ),
                    meals=[MealRecommendation(meal_type="dinner", venue_name=f"餐厅2-{suffix}", estimated_cost_cny=45)],
                    activities=[
                        Activity(
                            start_time="14:00",
                            end_time="16:00",
                            title=f"活动2-{suffix}",
                            category="explore",
                            description="desc",
                            location_name="徐汇",
                            ticket_cost_cny=35,
                        )
                    ],
                ),
            ],
        ),
    )


def test_trip_workspace_create_and_lookup_by_share_token() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()
    response = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="saved",
    )

    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=response,
                manual_notes="初始备注",
            )
        )
    )
    fetched = asyncio.run(service.get_trip(workspace.id))
    shared = asyncio.run(service.get_trip_by_share_token(workspace.share_token))

    assert fetched.id == workspace.id
    assert shared.id == workspace.id
    assert shared.manual_notes == "初始备注"
    store_path.unlink(missing_ok=True)


def test_trip_workspace_can_be_saved_as_draft_without_response() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()

    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                manual_notes="仅保存草稿",
                generate_response=False,
            )
        )
    )

    assert workspace.status == "draft"
    assert workspace.response_snapshot is None
    assert workspace.manual_notes == "仅保存草稿"
    store_path.unlink(missing_ok=True)


def test_trip_workspace_patch_updates_notes_and_locked_days() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=_build_response(
                    request=request,
                    generated_at=datetime.now(UTC),
                    suffix="base",
                ),
            )
        )
    )

    updated = asyncio.run(
        service.update_trip(
            workspace.id,
            TripWorkspacePatchRequest(
                manual_notes="更新后的备注",
                locked_day_numbers=[2, 1, 99],
            ),
        )
    )

    assert updated.version == 2
    assert updated.manual_notes == "更新后的备注"
    assert updated.locked_day_numbers == [1, 2]
    store_path.unlink(missing_ok=True)


def test_trip_workspace_patch_can_generate_from_draft() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (generated_at, include_debug)
        return _build_response(
            request=req,
            generated_at=datetime.now(UTC),
            suffix="draft-to-ready",
        )

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                generate_response=False,
            )
        )
    )

    updated = asyncio.run(
        service.update_trip(
            workspace.id,
            TripWorkspacePatchRequest(
                manual_notes="现在生成",
                generate_response=True,
                include_debug=True,
            ),
        )
    )

    assert updated.status == "ready"
    assert updated.response_snapshot is not None
    assert updated.response_snapshot.plan.title == "plan-draft-to-ready"
    store_path.unlink(missing_ok=True)


def test_trip_workspace_replan_replaces_only_target_day() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()
    original = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="old",
    )

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (generated_at, include_debug)
        return _build_response(
            request=req,
            generated_at=datetime.now(UTC),
            suffix="new",
        )

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
                locked_day_numbers=[1],
            )
        )
    )

    replanned = asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[2],
                include_debug=True,
            ),
        )
    )

    assert replanned.version == 2
    assert replanned.response_snapshot.plan.days[0].theme == "第1天-old"
    assert replanned.response_snapshot.plan.days[1].theme == "第2天-new"
    assert any("第 2 天" in item for item in replanned.response_snapshot.meta.warnings)
    store_path.unlink(missing_ok=True)
