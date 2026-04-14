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
    ReservationItem,
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


def _make_sqlite_store_path() -> Path:
    root = Path(__file__).resolve().parent / "_trip_workspace_testdata"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{uuid.uuid4().hex}.db"


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


def test_trip_workspace_replan_includes_reservations_and_reason() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request().model_copy(update={"notes": "Avoid crowded attractions."})
    original = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="old",
    )
    captured_request: TripPlanningRequest | None = None

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        nonlocal captured_request
        _ = (generated_at, include_debug)
        captured_request = req.model_copy(deep=True)
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
                manual_notes="Prefer indoor activities if the weather changes.",
                reservations=[
                    ReservationItem(
                        id="dinner-anchor",
                        type="restaurant",
                        title="Riverfront Dinner",
                        start_at=datetime(2026, 5, 2, 18, 30, tzinfo=UTC),
                        location="The Bund",
                        notes="Window seat booked.",
                    )
                ],
            )
        )
    )

    replanned = asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[2],
                reason="Rain is expected in the afternoon.",
                include_debug=True,
            ),
        )
    )

    assert captured_request is not None
    assert captured_request.notes is not None
    assert "Avoid crowded attractions." in captured_request.notes
    assert "Prefer indoor activities if the weather changes." in captured_request.notes
    assert "title=Riverfront Dinner" in captured_request.notes
    assert "anchor_days=day2" in captured_request.notes
    assert "requirement=keep_time_window_clear_and_place_anchor_explicitly" in captured_request.notes
    assert "Partial replanning instructions" in captured_request.notes
    assert "regenerate_days=2" in captured_request.notes
    assert "reason=Rain is expected in the afternoon." in captured_request.notes
    assert replanned.response_snapshot is not None
    assert replanned.response_snapshot.request_echo.notes == captured_request.notes
    store_path.unlink(missing_ok=True)


def test_trip_workspace_replan_filters_unrelated_reservations() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request().model_copy(update={"days": 3})
    original = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="old",
    )
    captured_request: TripPlanningRequest | None = None

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        nonlocal captured_request
        _ = (generated_at, include_debug)
        captured_request = req.model_copy(deep=True)
        return _build_response(
            request=req,
            generated_at=datetime.now(UTC),
            suffix="filtered-replan",
        )

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
                reservations=[
                    ReservationItem(
                        id="day-one-ticket",
                        type="ticket",
                        title="Day 1 Museum Entry",
                        start_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
                        location="People's Square",
                    ),
                    ReservationItem(
                        id="day-three-dinner",
                        type="restaurant",
                        title="Day 3 Skyline Dinner",
                        start_at=datetime(2026, 5, 3, 18, 30, tzinfo=UTC),
                        end_at=datetime(2026, 5, 3, 20, 0, tzinfo=UTC),
                        location="Lujiazui",
                    ),
                ],
            )
        )
    )

    asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[3],
                include_debug=True,
            ),
        )
    )

    assert captured_request is not None
    assert captured_request.notes is not None
    assert "Day 3 Skyline Dinner" in captured_request.notes
    assert "anchor_days=day3" in captured_request.notes
    assert "Day 1 Museum Entry" not in captured_request.notes
    assert "anchor_days=day1" not in captured_request.notes
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


def test_trip_workspace_sqlite_store_roundtrip() -> None:
    store_path = _make_sqlite_store_path()
    settings = Settings(
        planner_trip_store_driver="auto",
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()
    response = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="sqlite",
    )

    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=response,
                generate_response=True,
            )
        )
    )
    fetched = asyncio.run(service.get_trip(workspace.id))

    assert fetched.id == workspace.id
    assert fetched.response_snapshot is not None
    assert fetched.response_snapshot.plan.title == "plan-sqlite"
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


def test_trip_workspace_patch_persists_reservations() -> None:
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
                generate_response=False,
            )
        )
    )

    updated = asyncio.run(
        service.update_trip(
            workspace.id,
            TripWorkspacePatchRequest(
                reservations=[
                    ReservationItem(
                        id="hotel-anchor",
                        type="hotel",
                        title="静安寺酒店",
                        location="上海静安区",
                        source="携程",
                        confirmation_code="ABC123",
                    )
                ],
            ),
        )
    )

    assert len(updated.reservations) == 1
    assert updated.reservations[0].title == "静安寺酒店"
    assert updated.reservations[0].confirmation_code == "ABC123"
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


def test_trip_workspace_generation_includes_workspace_constraints() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request().model_copy(update={"notes": "Original brief note"})
    captured_request: TripPlanningRequest | None = None

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        nonlocal captured_request
        _ = (generated_at, include_debug)
        captured_request = req.model_copy(deep=True)
        return _build_response(
            request=req,
            generated_at=datetime.now(UTC),
            suffix="workspace-constraints",
        )

    planner.generate = fake_generate  # type: ignore[method-assign]

    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                manual_notes="Keep the hotel near a metro station.",
                reservations=[
                    ReservationItem(
                        id="hotel-anchor",
                        type="hotel",
                        title="Jingan Hotel",
                        start_at=datetime(2026, 5, 1, 14, 0, tzinfo=UTC),
                        end_at=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
                        location="Jingan District",
                        notes="Late check-in confirmed.",
                        confirmation_code="ABC123",
                    )
                ],
                generate_response=True,
                include_debug=True,
            )
        )
    )

    assert captured_request is not None
    assert captured_request.notes is not None
    assert "Original brief note" in captured_request.notes
    assert "Workspace notes that must be considered" in captured_request.notes
    assert "Keep the hotel near a metro station." in captured_request.notes
    assert "Fixed reservations and anchors" in captured_request.notes
    assert "title=Jingan Hotel" in captured_request.notes
    assert "trip_days=day1,day2" in captured_request.notes
    assert "confirmation=ABC123" in captured_request.notes
    assert "Reservation scheduling directives:" in captured_request.notes
    assert "stay_anchor_days=day1,day2" in captured_request.notes
    assert "requirement=keep_stay_aligned_with_reserved_hotel" in captured_request.notes
    assert "Scheduling rules:" in captured_request.notes
    assert workspace.request_brief.notes == "Original brief note"
    assert workspace.response_snapshot is not None
    assert workspace.response_snapshot.request_echo.notes == captured_request.notes
    store_path.unlink(missing_ok=True)


def test_trip_workspace_rejects_reservation_with_invalid_time_range() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()

    try:
        asyncio.run(
            service.create_trip(
                TripCreateRequest(
                    request_brief=request,
                    reservations=[
                        ReservationItem(
                            id="bad-range",
                            type="restaurant",
                            title="Late Dinner",
                            start_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
                            end_at=datetime(2026, 5, 1, 18, 0, tzinfo=UTC),
                        )
                    ],
                    generate_response=False,
                )
            )
        )
    except ValueError as exc:
        assert "结束时间不能早于开始时间" in str(exc)
    else:
        raise AssertionError("expected invalid reservation time range to raise ValueError")
    finally:
        store_path.unlink(missing_ok=True)


def test_trip_workspace_rejects_reservation_outside_trip_range() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()

    try:
        asyncio.run(
            service.create_trip(
                TripCreateRequest(
                    request_brief=request,
                    reservations=[
                        ReservationItem(
                            id="outside-range",
                            type="hotel",
                            title="Outside Hotel",
                            start_at=datetime(2026, 5, 5, 14, 0, tzinfo=UTC),
                            end_at=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
                        )
                    ],
                    generate_response=False,
                )
            )
        )
    except ValueError as exc:
        assert "不在本次行程日期范围内" in str(exc)
    else:
        raise AssertionError("expected out-of-range reservation to raise ValueError")
    finally:
        store_path.unlink(missing_ok=True)


def test_trip_workspace_rejects_overlapping_non_hotel_reservations() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()

    try:
        asyncio.run(
            service.create_trip(
                TripCreateRequest(
                    request_brief=request,
                    reservations=[
                        ReservationItem(
                            id="museum-ticket",
                            type="ticket",
                            title="Museum Entry",
                            start_at=datetime(2026, 5, 1, 14, 0, tzinfo=UTC),
                            end_at=datetime(2026, 5, 1, 15, 30, tzinfo=UTC),
                        ),
                        ReservationItem(
                            id="dinner-booking",
                            type="restaurant",
                            title="Dinner Booking",
                            start_at=datetime(2026, 5, 1, 15, 0, tzinfo=UTC),
                            end_at=datetime(2026, 5, 1, 16, 0, tzinfo=UTC),
                        ),
                    ],
                    generate_response=False,
                )
            )
        )
    except ValueError as exc:
        assert "时间重叠" in str(exc)
    else:
        raise AssertionError("expected overlapping reservations to raise ValueError")
    finally:
        store_path.unlink(missing_ok=True)


def test_trip_workspace_generation_adds_reservation_audit_warning() -> None:
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
            suffix="audit-warning",
        )

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                reservations=[
                    ReservationItem(
                        id="river-cruise",
                        type="ticket",
                        title="Night River Cruise",
                        start_at=datetime(2026, 5, 2, 19, 0, tzinfo=UTC),
                        location="North Bund Pier",
                    )
                ],
                generate_response=True,
                include_debug=True,
            )
        )
    )

    assert workspace.response_snapshot is not None
    warnings = workspace.response_snapshot.diagnostics.warnings
    assert any("Reservation audit:" in item for item in warnings)
    assert any("Night River Cruise" in item for item in warnings)
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
