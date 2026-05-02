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
    DailyForecast,
    InitialPlanDay,
    InitialPlanDraft,
    IntegrationStatus,
    MapRenderConfig,
    MealRecommendation,
    PlanDiagnostics,
    PlanGenerationMeta,
    PlanningContext,
    PlanningResponse,
    POIRecommendation,
    PrecheckRefreshRequest,
    ReservationConflictItem,
    ReservationCoverageDiagnostic,
    ReplanRequest,
    ReservationItem,
    RouteSummary,
    TripCreateRequest,
    TripPlanningRequest,
    TripWorkspacePatchRequest,
    TravelPlan,
    WeatherSummary,
)
from app.services.planner import TravelPlannerService
from app.services.trip_workspace_precheck import build_precheck_summary
from app.services.trip_workspace_reservations import build_reservation_coverage_diagnostics
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
    assert workspace.timeline
    assert workspace.timeline[0].kind == "created"
    store_path.unlink(missing_ok=True)


def test_trip_workspace_revoke_share_link_blocks_shared_lookup() -> None:
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
                manual_notes="share control",
            )
        )
    )

    revoked = asyncio.run(service.revoke_share_link(workspace.id))

    assert revoked.share_enabled is False
    assert revoked.version == 2
    assert revoked.timeline[0].kind == "share_revoked"

    try:
        asyncio.run(service.get_trip_by_share_token(workspace.share_token))
    except KeyError as exc:
        assert workspace.share_token in str(exc)
    else:
        raise AssertionError("expected revoked share token to be rejected")
    finally:
        store_path.unlink(missing_ok=True)


def test_trip_workspace_regenerate_share_link_rotates_token_and_records_timeline() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()
    workspace = asyncio.run(service.create_trip(TripCreateRequest(request_brief=request)))

    regenerated = asyncio.run(service.regenerate_share_link(workspace.id))
    shared = asyncio.run(service.get_trip_by_share_token(regenerated.share_token))

    assert regenerated.share_enabled is True
    assert regenerated.share_token != workspace.share_token
    assert regenerated.timeline[0].kind == "share_regenerated"
    assert shared.id == regenerated.id
    store_path.unlink(missing_ok=True)


def test_trip_workspace_list_recent_summaries_orders_by_updated_at() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()

    first = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                manual_notes="first",
            )
        )
    )
    second = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request.model_copy(update={"destination": "北京"}),
                manual_notes="second",
            )
        )
    )
    _ = asyncio.run(
        service.update_trip(
            first.id,
            TripWorkspacePatchRequest(
                manual_notes="first-updated",
            ),
        )
    )

    summaries = asyncio.run(service.list_recent_trips(limit=5))

    assert len(summaries) == 2
    assert summaries[0].id == first.id
    assert summaries[0].title
    assert summaries[0].days == request.days
    assert summaries[1].id == second.id
    store_path.unlink(missing_ok=True)


def test_trip_workspace_calendar_export_includes_reservations_and_itinerary_items() -> None:
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
        suffix="calendar",
    )
    response.plan.days[0].stay.hotel_name = "外滩夜景酒店"
    response.plan.days[0].stay.area = "黄浦江沿线"
    response.plan.days[0].stay.reason = "方便夜游后直接休息"
    response.plan.days[0].activities[0].booking_tip = "建议提前一天预约"
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=response,
                reservations=[
                    ReservationItem(
                        id="river-cruise",
                        type="ticket",
                        title="黄浦江夜游",
                        start_at=datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 20, 30, tzinfo=UTC),
                        location="十六铺码头",
                        confirmation_code="CRUISE-2026",
                    )
                ],
            )
        )
    )

    exported = asyncio.run(service.export_trip_calendar(workspace.id))

    assert exported.filename.endswith(".ics")
    assert "BEGIN:VCALENDAR" in exported.content
    assert "SUMMARY:门票：黄浦江夜游" in exported.content
    assert "LOCATION:十六铺码头" in exported.content
    assert "SUMMARY:住宿：外滩夜景酒店" in exported.content
    assert "SUMMARY:行程活动：活动1-calendar" in exported.content
    assert "CRUISE-2026" in exported.content
    store_path.unlink(missing_ok=True)


def test_trip_workspace_calendar_export_missing_trip_raises_key_error() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)

    try:
        asyncio.run(service.export_trip_calendar("missing-trip"))
    except KeyError as exc:
        assert "missing-trip" in str(exc)
    else:
        raise AssertionError("expected missing trip to raise KeyError")
    finally:
        store_path.unlink(missing_ok=True)


def test_trip_workspace_calendar_export_supports_scope_filters() -> None:
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
        suffix="calendar-scope",
    )
    response.plan.days[0].stay.hotel_name = "外滩夜景酒店"
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=response,
                reservations=[
                    ReservationItem(
                        id="river-cruise",
                        type="ticket",
                        title="黄浦江夜游",
                        start_at=datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 20, 30, tzinfo=UTC),
                        location="十六铺码头",
                        confirmation_code="CRUISE-2026",
                    )
                ],
            )
        )
    )

    reservation_only = asyncio.run(service.export_trip_calendar(workspace.id, scope="reservations"))
    itinerary_only = asyncio.run(service.export_trip_calendar(workspace.id, scope="itinerary"))

    assert reservation_only.filename.endswith("-reservations.ics")
    assert "SUMMARY:门票：黄浦江夜游" in reservation_only.content
    assert "SUMMARY:住宿：外滩夜景酒店" not in reservation_only.content
    assert "SUMMARY:行程活动：活动1-calendar-scope" not in reservation_only.content

    assert itinerary_only.filename.endswith("-itinerary.ics")
    assert "SUMMARY:门票：黄浦江夜游" not in itinerary_only.content
    assert "SUMMARY:住宿：外滩夜景酒店" in itinerary_only.content
    assert "SUMMARY:行程活动：活动1-calendar-scope" in itinerary_only.content
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


def test_trip_workspace_fill_gap_replan_preserves_existing_non_meal_content() -> None:
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
        suffix="current-meal-gap",
    )
    original.plan.days[0].meals = []
    original.plan.days[0].stay.hotel_name = "Current Stay Hotel"
    original.plan.days[0].activities[0].title = "Current Activity"
    original.plan.days[0].cost_breakdown.food_per_person_cny = 0
    original.plan.days[0].cost_breakdown.total_per_person_cny -= 40

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=request,
            generated_at=datetime.now(UTC),
            suffix="fresh-meal-gap",
        )
        fresh.plan.days[0].stay.hotel_name = "Fresh Stay Hotel"
        fresh.plan.days[0].activities[0].title = "Fresh Activity"
        fresh.plan.days[0].meals[0].venue_name = "Fresh Lunch"
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
            )
        )
    )

    replanned = asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[1],
                repair_mode="fill_gaps",
                repair_gap="meal",
                reason="补齐午餐缺口",
                include_debug=True,
            ),
        )
    )

    assert replanned.response_snapshot is not None
    day = replanned.response_snapshot.plan.days[0]
    assert day.stay.hotel_name == "Current Stay Hotel"
    assert day.activities[0].title == "Current Activity"
    assert day.meals[0].venue_name == "Fresh Lunch"
    assert day.cost_breakdown.food_per_person_cny == 40
    assert day.cost_breakdown.total_per_person_cny == 200
    store_path.unlink(missing_ok=True)


def test_trip_workspace_fill_gap_replan_only_adds_missing_lunch_and_preserves_other_meals() -> None:
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
        suffix="current-lunch-gap",
    )
    original.plan.days[0].meals = [
        MealRecommendation(
            meal_type="breakfast",
            venue_name="Current Breakfast",
            estimated_cost_cny=18,
        ),
        MealRecommendation(
            meal_type="dinner",
            venue_name="Current Dinner",
            estimated_cost_cny=72,
        ),
    ]
    original.plan.days[0].stay.hotel_name = "Current Stay Hotel"
    original.plan.days[0].activities[0].title = "Current Activity"
    original.plan.days[0].cost_breakdown.food_per_person_cny = 90
    original.plan.days[0].cost_breakdown.total_per_person_cny = 250

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=request,
            generated_at=datetime.now(UTC),
            suffix="fresh-lunch-gap",
        )
        fresh.plan.days[0].stay.hotel_name = "Fresh Stay Hotel"
        fresh.plan.days[0].activities[0].title = "Fresh Activity"
        fresh.plan.days[0].meals = [
            MealRecommendation(
                meal_type="breakfast",
                venue_name="Fresh Breakfast",
                estimated_cost_cny=20,
            ),
            MealRecommendation(
                meal_type="lunch",
                venue_name="Fresh Lunch",
                estimated_cost_cny=46,
            ),
            MealRecommendation(
                meal_type="dinner",
                venue_name="Fresh Dinner",
                estimated_cost_cny=68,
            ),
        ]
        fresh.plan.days[0].cost_breakdown.food_per_person_cny = 134
        fresh.plan.days[0].cost_breakdown.total_per_person_cny = 294
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
            )
        )
    )

    replanned = asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[1],
                repair_mode="fill_gaps",
                repair_gap="lunch",
                reason="补齐午餐缺口",
                include_debug=True,
            ),
        )
    )

    assert replanned.response_snapshot is not None
    day = replanned.response_snapshot.plan.days[0]
    assert day.stay.hotel_name == "Current Stay Hotel"
    assert day.activities[0].title == "Current Activity"
    assert [meal.meal_type for meal in day.meals] == ["breakfast", "lunch", "dinner"]
    assert [meal.venue_name for meal in day.meals] == [
        "Current Breakfast",
        "Fresh Lunch",
        "Current Dinner",
    ]
    assert day.cost_breakdown.food_per_person_cny == 136
    assert day.cost_breakdown.total_per_person_cny == 296
    assert replanned.last_replan_summary is not None
    assert replanned.last_replan_summary.title == "第 1 天已完成午餐补齐"
    assert replanned.last_replan_summary.target_days == [1]
    assert replanned.last_replan_summary.items[0].highlights == [
        "新增午餐：Fresh Lunch",
        "人均预算 250 -> 296 元",
    ]
    assert [(change.kind, change.label, change.before, change.after) for change in replanned.last_replan_summary.items[0].changes] == [
        ("meal", "午餐", "", "Fresh Lunch"),
        ("budget", "人均预算", "250 元", "296 元"),
    ]
    store_path.unlink(missing_ok=True)


def test_trip_workspace_fill_gap_replan_only_adds_missing_breakfast_and_preserves_other_meals() -> None:
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
        suffix="current-breakfast-gap",
    )
    original.plan.days[0].meals = [
        MealRecommendation(
            meal_type="lunch",
            venue_name="Current Lunch",
            estimated_cost_cny=42,
        ),
        MealRecommendation(
            meal_type="dinner",
            venue_name="Current Dinner",
            estimated_cost_cny=72,
        ),
    ]
    original.plan.days[0].stay.hotel_name = "Current Stay Hotel"
    original.plan.days[0].activities[0].title = "Current Activity"
    original.plan.days[0].cost_breakdown.food_per_person_cny = 114
    original.plan.days[0].cost_breakdown.total_per_person_cny = 274

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=request,
            generated_at=datetime.now(UTC),
            suffix="fresh-breakfast-gap",
        )
        fresh.plan.days[0].meals = [
            MealRecommendation(
                meal_type="breakfast",
                venue_name="Fresh Breakfast",
                estimated_cost_cny=22,
            ),
            MealRecommendation(
                meal_type="lunch",
                venue_name="Fresh Lunch",
                estimated_cost_cny=46,
            ),
            MealRecommendation(
                meal_type="dinner",
                venue_name="Fresh Dinner",
                estimated_cost_cny=68,
            ),
        ]
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
            )
        )
    )

    replanned = asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[1],
                repair_mode="fill_gaps",
                repair_gap="breakfast",
                reason="补齐早餐缺口",
                include_debug=True,
            ),
        )
    )

    assert replanned.response_snapshot is not None
    day = replanned.response_snapshot.plan.days[0]
    assert [meal.meal_type for meal in day.meals] == ["breakfast", "lunch", "dinner"]
    assert [meal.venue_name for meal in day.meals] == [
        "Fresh Breakfast",
        "Current Lunch",
        "Current Dinner",
    ]
    assert day.cost_breakdown.food_per_person_cny == 136
    assert day.cost_breakdown.total_per_person_cny == 296
    store_path.unlink(missing_ok=True)


def test_trip_workspace_fill_gap_replan_only_adds_missing_dinner_and_preserves_other_meals() -> None:
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
        suffix="current-dinner-gap",
    )
    original.plan.days[0].meals = [
        MealRecommendation(
            meal_type="breakfast",
            venue_name="Current Breakfast",
            estimated_cost_cny=15,
        ),
        MealRecommendation(
            meal_type="lunch",
            venue_name="Current Lunch",
            estimated_cost_cny=42,
        ),
    ]
    original.plan.days[0].stay.hotel_name = "Current Stay Hotel"
    original.plan.days[0].activities[0].title = "Current Activity"
    original.plan.days[0].cost_breakdown.food_per_person_cny = 57
    original.plan.days[0].cost_breakdown.total_per_person_cny = 217

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=request,
            generated_at=datetime.now(UTC),
            suffix="fresh-dinner-gap",
        )
        fresh.plan.days[0].stay.hotel_name = "Fresh Stay Hotel"
        fresh.plan.days[0].activities[0].title = "Fresh Activity"
        fresh.plan.days[0].meals = [
            MealRecommendation(
                meal_type="breakfast",
                venue_name="Fresh Breakfast",
                estimated_cost_cny=18,
            ),
            MealRecommendation(
                meal_type="lunch",
                venue_name="Fresh Lunch",
                estimated_cost_cny=45,
            ),
            MealRecommendation(
                meal_type="dinner",
                venue_name="Fresh Dinner",
                estimated_cost_cny=78,
            ),
        ]
        fresh.plan.days[0].cost_breakdown.food_per_person_cny = 141
        fresh.plan.days[0].cost_breakdown.total_per_person_cny = 301
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
            )
        )
    )

    replanned = asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[1],
                repair_mode="fill_gaps",
                repair_gap="dinner",
                reason="补齐晚餐缺口",
                include_debug=True,
            ),
        )
    )

    assert replanned.response_snapshot is not None
    day = replanned.response_snapshot.plan.days[0]
    assert day.stay.hotel_name == "Current Stay Hotel"
    assert day.activities[0].title == "Current Activity"
    assert [meal.meal_type for meal in day.meals] == ["breakfast", "lunch", "dinner"]
    assert [meal.venue_name for meal in day.meals] == [
        "Current Breakfast",
        "Current Lunch",
        "Fresh Dinner",
    ]
    assert day.cost_breakdown.food_per_person_cny == 135
    assert day.cost_breakdown.total_per_person_cny == 295
    store_path.unlink(missing_ok=True)


def test_trip_workspace_fill_gap_replan_only_adds_missing_snack_and_preserves_main_meals() -> None:
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
        suffix="current-snack-gap",
    )
    original.plan.days[0].meals = [
        MealRecommendation(
            meal_type="breakfast",
            venue_name="Current Breakfast",
            estimated_cost_cny=18,
        ),
        MealRecommendation(
            meal_type="lunch",
            venue_name="Current Lunch",
            estimated_cost_cny=42,
        ),
        MealRecommendation(
            meal_type="dinner",
            venue_name="Current Dinner",
            estimated_cost_cny=72,
        ),
    ]
    original.plan.days[0].cost_breakdown.food_per_person_cny = 132
    original.plan.days[0].cost_breakdown.total_per_person_cny = 292

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=request,
            generated_at=datetime.now(UTC),
            suffix="fresh-snack-gap",
        )
        fresh.plan.days[0].meals = [
            MealRecommendation(
                meal_type="breakfast",
                venue_name="Fresh Breakfast",
                estimated_cost_cny=20,
            ),
            MealRecommendation(
                meal_type="lunch",
                venue_name="Fresh Lunch",
                estimated_cost_cny=46,
            ),
            MealRecommendation(
                meal_type="dinner",
                venue_name="Fresh Dinner",
                estimated_cost_cny=68,
            ),
            MealRecommendation(
                meal_type="snack",
                venue_name="Fresh Tea Break",
                estimated_cost_cny=25,
            ),
        ]
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
            )
        )
    )

    replanned = asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[1],
                repair_mode="fill_gaps",
                repair_gap="snack",
                reason="补齐加餐缺口",
                include_debug=True,
            ),
        )
    )

    assert replanned.response_snapshot is not None
    day = replanned.response_snapshot.plan.days[0]
    assert [meal.meal_type for meal in day.meals] == ["breakfast", "lunch", "dinner", "snack"]
    assert [meal.venue_name for meal in day.meals] == [
        "Current Breakfast",
        "Current Lunch",
        "Current Dinner",
        "Fresh Tea Break",
    ]
    assert day.cost_breakdown.food_per_person_cny == 157
    assert day.cost_breakdown.total_per_person_cny == 317
    store_path.unlink(missing_ok=True)


def test_trip_workspace_fill_gap_replan_preserves_existing_stay_and_meals() -> None:
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
        suffix="current-activity-gap",
    )
    original.plan.days[0].stay.hotel_name = "Existing Stay"
    original.plan.days[0].meals[0].venue_name = "Existing Lunch"
    original.plan.days[0].activities = []
    original.plan.days[0].route_summaries = []
    original.plan.days[0].route_segments = []
    original.plan.days[0].cost_breakdown.tickets_per_person_cny = 0
    original.plan.days[0].cost_breakdown.transport_per_person_cny = 0
    original.plan.days[0].cost_breakdown.total_per_person_cny -= 50

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=request,
            generated_at=datetime.now(UTC),
            suffix="fresh-activity-gap",
        )
        fresh.plan.days[0].stay.hotel_name = "Fresh Stay"
        fresh.plan.days[0].meals[0].venue_name = "Fresh Lunch"
        fresh.plan.days[0].activities[0].title = "Fresh Activity"
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
            )
        )
    )

    replanned = asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[1],
                repair_mode="fill_gaps",
                repair_gap="activity",
                reason="补齐主要活动",
                include_debug=True,
            ),
        )
    )

    assert replanned.response_snapshot is not None
    day = replanned.response_snapshot.plan.days[0]
    assert day.stay.hotel_name == "Existing Stay"
    assert day.meals[0].venue_name == "Existing Lunch"
    assert day.activities[0].title == "Fresh Activity"
    assert day.cost_breakdown.tickets_per_person_cny == 30
    assert day.cost_breakdown.transport_per_person_cny == 20
    assert day.cost_breakdown.total_per_person_cny == 200
    store_path.unlink(missing_ok=True)


def test_trip_workspace_fill_gap_replan_requires_gap_type() -> None:
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
        suffix="missing-gap-type",
    )
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=response,
            )
        )
    )

    try:
        asyncio.run(
            service.replan_trip(
                workspace.id,
                ReplanRequest(
                    scope="day",
                    day_numbers=[1],
                    repair_mode="fill_gaps",
                    repair_gap=None,
                    include_debug=True,
                ),
            )
        )
    except ValueError as exc:
        assert "repair_gap" in str(exc)
    else:
        raise AssertionError("expected missing repair_gap to raise ValueError")
    finally:
        store_path.unlink(missing_ok=True)


def test_trip_workspace_fill_gap_replan_rejects_trip_scope() -> None:
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
        suffix="trip-scope-gap",
    )
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=response,
            )
        )
    )

    try:
        asyncio.run(
            service.replan_trip(
                workspace.id,
                ReplanRequest(
                    scope="trip",
                    day_numbers=[],
                    preserve_locked_days=True,
                    repair_mode="fill_gaps",
                    repair_gap="meal",
                    include_debug=True,
                ),
            )
        )
    except ValueError as exc:
        assert "按天" in str(exc) or "day" in str(exc).lower()
    else:
        raise AssertionError("expected trip-scope fill_gaps to raise ValueError")
    finally:
        store_path.unlink(missing_ok=True)


def test_trip_workspace_fill_gap_replan_merges_restaurant_reservation_without_replacing_day() -> None:
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
        suffix="reservation-current",
    )
    original.plan.days[0].stay.hotel_name = "Current Stay"
    original.plan.days[0].activities[0].title = "Current Activity"
    original.plan.days[0].meals[0].venue_name = "Old Lunch"
    original.plan.days[0].cost_breakdown.food_per_person_cny = 40
    original.plan.days[0].cost_breakdown.total_per_person_cny = 200

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=request,
            generated_at=datetime.now(UTC),
            suffix="reservation-fresh",
        )
        fresh.plan.days[0].stay.hotel_name = "Fresh Stay"
        fresh.plan.days[0].activities[0].title = "Fresh Activity"
        fresh.plan.days[0].meals[0].venue_name = "Riverfront Dinner"
        fresh.plan.days[0].meals[0].poi = None
        fresh.plan.days[0].cost_breakdown.food_per_person_cny = 88
        fresh.plan.days[0].cost_breakdown.total_per_person_cny = 248
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
                reservations=[
                    ReservationItem(
                        id="riverfront-dinner",
                        type="restaurant",
                        title="Riverfront Dinner",
                        start_at=datetime(2026, 5, 1, 18, 30, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
                        location="The Bund",
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
                day_numbers=[1],
                repair_mode="fill_gaps",
                repair_gap="reservation",
                reason="落地晚餐预约",
                include_debug=True,
            ),
        )
    )

    assert replanned.response_snapshot is not None
    day = replanned.response_snapshot.plan.days[0]
    assert day.stay.hotel_name == "Current Stay"
    assert day.activities[0].title == "Current Activity"
    assert day.meals[0].venue_name == "Riverfront Dinner"
    assert day.cost_breakdown.food_per_person_cny == 88
    assert day.cost_breakdown.total_per_person_cny == 248
    assert replanned.last_replan_summary is not None
    assert replanned.last_replan_summary.items[0].highlights[0] == "餐厅预约已落地：Riverfront Dinner"
    assert replanned.last_replan_summary.items[0].changes[0].kind == "reservation"
    assert replanned.last_replan_summary.items[0].changes[0].label == "餐厅预约"
    assert replanned.last_replan_summary.items[0].changes[0].before == "未落地"
    assert replanned.last_replan_summary.items[0].changes[0].after == "Riverfront Dinner"
    store_path.unlink(missing_ok=True)


def test_trip_workspace_fill_gap_replan_merges_ticket_reservation_without_replacing_stay_and_meals() -> None:
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
        suffix="ticket-current",
    )
    original.plan.days[0].stay.hotel_name = "Existing Stay"
    original.plan.days[0].meals[0].venue_name = "Existing Lunch"
    original.plan.days[0].activities[0].title = "Old Activity"
    original.plan.days[0].cost_breakdown.transport_per_person_cny = 20
    original.plan.days[0].cost_breakdown.tickets_per_person_cny = 30
    original.plan.days[0].cost_breakdown.total_per_person_cny = 200

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=request,
            generated_at=datetime.now(UTC),
            suffix="ticket-fresh",
        )
        fresh.plan.days[0].stay.hotel_name = "Fresh Stay"
        fresh.plan.days[0].meals[0].venue_name = "Fresh Lunch"
        fresh.plan.days[0].activities[0].title = "Museum Entry"
        fresh.plan.days[0].activities[0].location_name = "People's Square"
        fresh.plan.days[0].cost_breakdown.transport_per_person_cny = 55
        fresh.plan.days[0].cost_breakdown.tickets_per_person_cny = 120
        fresh.plan.days[0].cost_breakdown.total_per_person_cny = 325
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
                reservations=[
                    ReservationItem(
                        id="museum-entry",
                        type="ticket",
                        title="Museum Entry",
                        start_at=datetime(2026, 5, 1, 9, 30, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
                        location="People's Square",
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
                day_numbers=[1],
                repair_mode="fill_gaps",
                repair_gap="reservation",
                reason="落地门票预约",
                include_debug=True,
            ),
        )
    )

    assert replanned.response_snapshot is not None
    day = replanned.response_snapshot.plan.days[0]
    assert day.stay.hotel_name == "Existing Stay"
    assert day.meals[0].venue_name == "Existing Lunch"
    assert day.activities[0].title == "Museum Entry"
    assert day.cost_breakdown.transport_per_person_cny == 55
    assert day.cost_breakdown.tickets_per_person_cny == 120
    assert day.cost_breakdown.total_per_person_cny == 325
    assert replanned.last_replan_summary is not None
    assert replanned.last_replan_summary.items[0].changes[0].kind == "reservation"
    assert replanned.last_replan_summary.items[0].changes[0].label == "门票预约"
    assert replanned.last_replan_summary.items[0].changes[0].after == "Museum Entry"
    store_path.unlink(missing_ok=True)


def test_trip_workspace_full_day_replan_records_last_replan_summary() -> None:
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
        suffix="replace-current",
    )

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=request,
            generated_at=datetime.now(UTC),
            suffix="replace-fresh",
        )
        fresh.plan.days[0].stay.hotel_name = "Updated Stay"
        fresh.plan.days[0].activities[0].title = "Updated Activity"
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
            )
        )
    )

    replanned = asyncio.run(
        service.replan_trip(
            workspace.id,
            ReplanRequest(
                scope="day",
                day_numbers=[1],
                repair_mode="replace",
                reason="重新调整当天安排",
                include_debug=True,
            ),
        )
    )

    assert replanned.last_replan_summary is not None
    assert replanned.last_replan_summary.title == "第 1 天已重新生成"
    assert replanned.last_replan_summary.repair_mode == "replace"
    assert replanned.last_replan_summary.target_days == [1]
    assert replanned.last_replan_summary.items[0].day_number == 1
    assert "住宿更新为：Updated Stay" in replanned.last_replan_summary.items[0].highlights
    assert "活动更新为：Updated Activity" in replanned.last_replan_summary.items[0].highlights
    assert [(change.kind, change.label) for change in replanned.last_replan_summary.items[0].changes] == [
        ("stay", "住宿"),
        ("meal", "午餐"),
        ("activity", "活动"),
    ]
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
    assert "check_in_slot=afternoon" in captured_request.notes
    assert "check_out_slot=lunch" in captured_request.notes
    assert "requirement=keep_stay_aligned_with_reserved_hotel" in captured_request.notes
    assert "Scheduling rules:" in captured_request.notes
    assert workspace.request_brief.notes == "Original brief note"
    assert workspace.response_snapshot is not None
    assert workspace.response_snapshot.request_echo.notes == captured_request.notes
    coverage = workspace.response_snapshot.diagnostics.reservation_coverage
    assert len(coverage) == 1
    assert coverage[0].reservation_id == "hotel-anchor"
    assert coverage[0].status == "covered"
    assert coverage[0].target_days == [1, 2]
    assert coverage[0].matched_days == [1, 2]
    assert coverage[0].auto_anchored_days == [1, 2]
    store_path.unlink(missing_ok=True)


def test_trip_workspace_generation_includes_restaurant_slot_directives() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()
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
            suffix="restaurant-slot-directives",
        )

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                reservations=[
                    ReservationItem(
                        id="reserved-dinner",
                        type="restaurant",
                        title="Skyline Dinner",
                        start_at=datetime(2026, 5, 1, 18, 30, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
                        location="Lujiazui",
                    )
                ],
                generate_response=True,
                include_debug=True,
            )
        )
    )

    assert captured_request is not None
    assert captured_request.notes is not None
    assert "anchor_slot=dinner" in captured_request.notes
    assert "meal_slot=dinner" in captured_request.notes
    assert "requirement=place_the_reserved_restaurant_into_that_meal_slot" in captured_request.notes
    assert workspace.response_snapshot is not None
    store_path.unlink(missing_ok=True)


def test_trip_workspace_generation_includes_daily_multi_anchor_coordination_rules() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()
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
            suffix="multi-anchor-directives",
        )

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                reservations=[
                    ReservationItem(
                        id="museum-entry",
                        type="ticket",
                        title="Museum Entry",
                        start_at=datetime(2026, 5, 1, 9, 30, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
                        location="People's Square",
                    ),
                    ReservationItem(
                        id="skyline-dinner",
                        type="restaurant",
                        title="Skyline Dinner",
                        start_at=datetime(2026, 5, 1, 18, 30, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
                        location="Lujiazui",
                    ),
                ],
                generate_response=True,
                include_debug=True,
            )
        )
    )

    assert captured_request is not None
    assert captured_request.notes is not None
    assert "day_anchor_plan=day1" in captured_request.notes
    assert "anchor_count=2" in captured_request.notes
    assert "ticket:Museum Entry@morning[2026-05-01 09:30 -> 2026-05-01 11:00]" in captured_request.notes
    assert "restaurant:Skyline Dinner@dinner[2026-05-01 18:30 -> 2026-05-01 20:00]" in captured_request.notes
    assert "requirements=sequence_the_day_around_all_anchor_windows" in captured_request.notes
    assert "preserve_transfer_buffers_between_anchor_windows" in captured_request.notes
    assert "compress_flexible_activities_into_the_remaining_gaps" in captured_request.notes
    assert "avoid_scheduling_other_meals_inside_reserved_time_windows" in captured_request.notes
    assert workspace.response_snapshot is not None
    store_path.unlink(missing_ok=True)


def test_trip_workspace_generation_includes_hotel_anchor_coordination_rule_for_shared_day() -> None:
    store_path = _make_store_path()
    settings = Settings(
        planner_trip_store_path=str(store_path),
        planner_generate_cache_enabled=False,
    )
    planner = TravelPlannerService(settings)
    service = TripWorkspaceService(settings, planner)
    request = _build_request()
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
            suffix="hotel-anchor-coordination",
        )

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                reservations=[
                    ReservationItem(
                        id="bund-hotel",
                        type="hotel",
                        title="Bund Riverside Hotel",
                        start_at=datetime(2026, 5, 1, 15, 0, tzinfo=UTC),
                        end_at=datetime(2026, 5, 2, 11, 0, tzinfo=UTC),
                        location="The Bund",
                    ),
                    ReservationItem(
                        id="river-cruise",
                        type="ticket",
                        title="Night River Cruise",
                        start_at=datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 20, 30, tzinfo=UTC),
                        location="Shiliupu Wharf",
                    ),
                ],
                generate_response=True,
                include_debug=True,
            )
        )
    )

    assert captured_request is not None
    assert captured_request.notes is not None
    assert "day_anchor_plan=day1" in captured_request.notes
    assert "hotel:Bund Riverside Hotel@afternoon[2026-05-01 15:00 -> 2026-05-02 11:00]" in captured_request.notes
    assert "ticket:Night River Cruise@dinner[2026-05-01 19:00 -> 2026-05-01 20:30]" in captured_request.notes
    assert "align_departure_and_return_with_the_reserved_hotel_anchor" in captured_request.notes
    assert workspace.response_snapshot is not None
    store_path.unlink(missing_ok=True)


def test_trip_workspace_refresh_precheck_regenerates_workspace_snapshot() -> None:
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
        suffix="precheck-old",
    )
    original.plan.days[0].activities[0].poi = POIRecommendation(
        name="Bund Walk",
        source="amap",
    )
    original.plan.days[1].activities[0].poi = POIRecommendation(
        name="Xuhui Walk",
        source="amap",
    )
    captured_request: TripPlanningRequest | None = None

    async def fake_generate(
        req: TripPlanningRequest,
        generated_at: datetime,
        include_debug: bool = True,
    ) -> PlanningResponse:
        nonlocal captured_request
        _ = generated_at
        assert include_debug is True
        captured_request = req.model_copy(deep=True)
        refreshed_response = _build_response(
            request=req,
            generated_at=datetime.now(UTC),
            suffix="precheck-new",
        )
        refreshed_response.plan.days[0].weather = DailyForecast(
            date=req.start_date.isoformat(),
            day_weather="晴",
            night_weather="多云",
            high_temperature="26",
            low_temperature="18",
            advice="注意补水",
        )
        refreshed_response.plan.days[0].route_summary = RouteSummary(
            day_number=1,
            title="Metro to Bund",
            from_name="Hotel",
            to_name="Bund",
            waypoints=[],
            distance_text="4 km",
            duration_text="25 min",
            mode="metro",
            estimated_transport_cost_cny=4,
            steps=[],
            polyline=[],
        )
        refreshed_response.plan.days[0].activities[0].poi = POIRecommendation(
            name="Bund Walk",
            source="amap",
            opening_hours="09:00-18:00",
        )
        refreshed_response.plan.days[1].activities[0].poi = POIRecommendation(
            name="Xuhui Walk",
            source="amap",
        )
        return refreshed_response

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                response_snapshot=original,
                manual_notes="Refresh weather and route checks before departure.",
            )
        )
    )

    refreshed = asyncio.run(
        service.refresh_precheck(
            workspace.id,
            PrecheckRefreshRequest(include_debug=True),
        )
    )

    assert captured_request is not None
    assert captured_request.notes is not None
    assert "Refresh weather and route checks before departure." in captured_request.notes
    assert refreshed.version == workspace.version + 1
    assert refreshed.response_snapshot is not None
    assert refreshed.response_snapshot.plan.title == "plan-precheck-new"
    assert refreshed.last_replan_summary == workspace.last_replan_summary
    assert refreshed.last_precheck_summary is not None
    assert "出发前校验已刷新" in refreshed.last_precheck_summary.title
    weather_item = next(item for item in refreshed.last_precheck_summary.items if item.key == "weather")
    route_item = next(item for item in refreshed.last_precheck_summary.items if item.key == "route")
    opening_hours_item = next(
        item for item in refreshed.last_precheck_summary.items if item.key == "opening-hours"
    )
    assert weather_item.before_days == [1, 2]
    assert weather_item.after_days == [2]
    assert weather_item.recommended_gap == "activity"
    assert weather_item.action_label == "改室内活动"
    assert "室内" in weather_item.action_reason
    assert [action.label for action in weather_item.actions] == ["改室内活动", "调整出发时段"]
    assert weather_item.actions[0].gap == "activity"
    assert weather_item.actions[1].gap == "day-plan"
    assert "时间窗" in weather_item.actions[1].reason
    assert route_item.before_days == [1, 2]
    assert route_item.after_days == [2]
    assert route_item.recommended_gap == "day-plan"
    assert route_item.action_label == "重排路线影响日"
    assert "路线衔接" in route_item.action_reason
    assert [action.label for action in route_item.actions] == ["重排路线影响日", "压缩跨区往返"]
    assert "跨区往返" in route_item.actions[1].reason
    assert opening_hours_item.before_days == [1, 2]
    assert opening_hours_item.after_days == [2]
    assert opening_hours_item.recommended_gap == "activity"
    assert opening_hours_item.action_label == "替换活动"
    assert [action.label for action in opening_hours_item.actions] == ["替换活动", "调整游玩时段"]
    assert opening_hours_item.actions[1].gap == "day-plan"
    assert "营业时间" in opening_hours_item.actions[1].reason
    store_path.unlink(missing_ok=True)


def test_precheck_summary_mentions_coordinated_auto_anchored_reservations() -> None:
    request = _build_request()
    previous = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="precheck-before-reservation-summary",
    )
    current = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="precheck-after-reservation-summary",
    )
    current.diagnostics = current.diagnostics.model_copy(
        update={
            "reservation_coverage": [
                ReservationCoverageDiagnostic(
                    reservation_id="museum-entry",
                    title="Museum Entry",
                    status="covered",
                    target_days=[1],
                    matched_days=[1],
                    auto_anchored_days=[1],
                    coordinated_days=[1],
                    coordination_tip=(
                        "固定预约顺序：09:30 Museum Entry -> 19:00 Night River Cruise；"
                        "请预留预约之间的通勤与候场缓冲，将可调整活动压缩到剩余空档。"
                    ),
                    reason_code="runtime_fallback",
                    reason_summary="系统已在第 1 天按预约信息保底注入，并对同日多预约顺序做了协调。",
                    detail="Covered on day 1 with runtime fallback anchoring on day 1.",
                ),
                ReservationCoverageDiagnostic(
                    reservation_id="night-cruise",
                    title="Night River Cruise",
                    status="covered",
                    target_days=[1],
                    matched_days=[1],
                    auto_anchored_days=[1],
                    coordinated_days=[1],
                    coordination_tip=(
                        "固定预约顺序：09:30 Museum Entry -> 19:00 Night River Cruise；"
                        "请预留预约之间的通勤与候场缓冲，将可调整活动压缩到剩余空档。"
                    ),
                    reason_code="runtime_fallback",
                    reason_summary="系统已在第 1 天按预约信息保底注入，并对同日多预约顺序做了协调。",
                    detail="Covered on day 1 with runtime fallback anchoring on day 1.",
                ),
            ]
        },
        deep=True,
    )

    summary = build_precheck_summary(
        previous=previous,
        current=current,
        created_at=datetime.now(UTC),
    )

    reservation_item = next(item for item in summary.items if item.key == "reservation")
    assert reservation_item.after_status == "warning"
    assert reservation_item.after_days == [1]
    assert reservation_item.after_summary == "2 条预约由系统保底注入，其中 2 条涉及多预约顺序协调"


def test_precheck_summary_exposes_reservation_conflict_items() -> None:
    request = _build_request()
    previous = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="precheck-before-reservation-conflicts",
    )
    current = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="precheck-after-reservation-conflicts",
    )
    current.diagnostics = current.diagnostics.model_copy(
        update={
            "reservation_coverage": [
                ReservationCoverageDiagnostic(
                    reservation_id="reserved-lunch",
                    title="Reserved Lunch",
                    status="unresolved",
                    target_days=[1],
                    matched_days=[],
                    auto_anchored_days=[],
                    coordinated_days=[],
                    coordination_tip="",
                    reason_code="day_conflict",
                    reason_summary=(
                        "目标日期内未找到与该预约匹配的明确行程内容，且当前日程存在明显冲突："
                        "第 1 天午餐档已安排“餐厅1-precheck-after-reservation-conflicts”。"
                    ),
                    conflict_items=[
                        ReservationConflictItem(
                            day_number=1,
                            kind="meal",
                            label="餐厅1-precheck-after-reservation-conflicts",
                            time_text="午餐",
                            summary="第 1 天午餐档已安排“餐厅1-precheck-after-reservation-conflicts”",
                        )
                    ],
                    detail="Expected on day 1, but no explicit match was found.",
                )
            ]
        },
        deep=True,
    )

    summary = build_precheck_summary(
        previous=previous,
        current=current,
        created_at=datetime.now(UTC),
    )

    reservation_item = next(item for item in summary.items if item.key == "reservation")
    assert reservation_item.after_status == "warning"
    assert reservation_item.after_days == [1]
    assert len(reservation_item.conflict_items) == 1
    assert reservation_item.conflict_items[0].kind == "meal"
    assert reservation_item.conflict_items[0].label == "餐厅1-precheck-after-reservation-conflicts"
    assert "当前已识别冲突" in reservation_item.actions[0].reason
    assert "午餐档已安排" in reservation_item.actions[0].reason


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


def test_trip_workspace_generation_auto_anchors_ticket_reservation_into_day_plan() -> None:
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
    day = workspace.response_snapshot.plan.days[1]
    assert any(item.title == "Night River Cruise" for item in day.activities)
    assert any("固定预约锚点" in (item.booking_tip or "") for item in day.activities)
    warnings = workspace.response_snapshot.diagnostics.warnings
    coverage = workspace.response_snapshot.diagnostics.reservation_coverage
    assert len(coverage) == 1
    assert coverage[0].reservation_id == "river-cruise"
    assert coverage[0].status == "covered"
    assert coverage[0].target_days == [2]
    assert coverage[0].matched_days == [2]
    assert coverage[0].auto_anchored_days == [2]
    assert coverage[0].coordinated_days == []
    assert coverage[0].coordination_tip == ""
    assert coverage[0].reason_code == "runtime_fallback"
    assert "保底注入" in coverage[0].reason_summary
    assert any("Reservation fallback:" in item for item in warnings)
    assert any("Night River Cruise" in item for item in warnings)
    assert not any("Reservation audit:" in item for item in warnings)
    store_path.unlink(missing_ok=True)


def test_trip_workspace_generation_auto_anchors_restaurant_reservation_into_meal_slot() -> None:
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
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=req,
            generated_at=datetime.now(UTC),
            suffix="restaurant-anchor",
        )
        fresh.plan.days[0].meals = []
        fresh.plan.days[0].cost_breakdown.food_per_person_cny = 0
        fresh.plan.days[0].cost_breakdown.total_per_person_cny = 160
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                reservations=[
                    ReservationItem(
                        id="reserved-lunch",
                        type="restaurant",
                        title="Reserved Lunch",
                        start_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
                        location="The Bund",
                    )
                ],
                generate_response=True,
                include_debug=True,
            )
        )
    )

    assert workspace.response_snapshot is not None
    day = workspace.response_snapshot.plan.days[0]
    assert [meal.meal_type for meal in day.meals] == ["lunch"]
    assert day.meals[0].venue_name == "Reserved Lunch"
    warnings = workspace.response_snapshot.diagnostics.warnings
    coverage = workspace.response_snapshot.diagnostics.reservation_coverage
    assert len(coverage) == 1
    assert coverage[0].reservation_id == "reserved-lunch"
    assert coverage[0].status == "covered"
    assert coverage[0].target_days == [1]
    assert coverage[0].matched_days == [1]
    assert coverage[0].auto_anchored_days == [1]
    assert coverage[0].coordinated_days == []
    assert coverage[0].coordination_tip == ""
    assert coverage[0].reason_code == "runtime_fallback"
    assert "保底注入" in coverage[0].reason_summary
    assert any("Reservation fallback:" in item for item in warnings)
    assert not any("Reservation audit:" in item for item in warnings)
    store_path.unlink(missing_ok=True)


def test_trip_workspace_generation_marks_reservation_without_time_as_pending_with_reason() -> None:
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
        _ = (req, generated_at, include_debug)
        return _build_response(
            request=req,
            generated_at=datetime.now(UTC),
            suffix="pending-reservation",
        )

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                reservations=[
                    ReservationItem(
                        id="floating-reservation",
                        type="other",
                        title="待补时间的预约",
                        location="静安寺",
                    )
                ],
                generate_response=True,
                include_debug=True,
            )
        )
    )

    assert workspace.response_snapshot is not None
    coverage = workspace.response_snapshot.diagnostics.reservation_coverage
    assert len(coverage) == 1
    assert coverage[0].reservation_id == "floating-reservation"
    assert coverage[0].status == "pending"
    assert coverage[0].reason_code == "missing_time_window"
    assert "时间窗" in coverage[0].reason_summary
    assert coverage[0].coordinated_days == []
    assert coverage[0].coordination_tip == ""
    store_path.unlink(missing_ok=True)


def test_build_reservation_coverage_diagnostics_describes_meal_slot_conflict() -> None:
    request = _build_request()
    response = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="meal-conflict",
    )

    coverage = build_reservation_coverage_diagnostics(
        request=request,
        reservations=[
            ReservationItem(
                id="reserved-lunch",
                type="restaurant",
                title="Reserved Lunch",
                start_at=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
                end_at=datetime(2026, 5, 1, 13, 30, tzinfo=UTC),
                location="The Bund",
            )
        ],
        response=response,
    )

    assert len(coverage) == 1
    assert coverage[0].status == "unresolved"
    assert coverage[0].reason_code == "day_conflict"
    assert "午餐档已安排" in coverage[0].reason_summary
    assert "餐厅1-meal-conflict" in coverage[0].reason_summary
    assert len(coverage[0].conflict_items) == 1
    assert coverage[0].conflict_items[0].day_number == 1
    assert coverage[0].conflict_items[0].kind == "meal"
    assert coverage[0].conflict_items[0].label == "餐厅1-meal-conflict"
    assert coverage[0].conflict_items[0].time_text == "午餐"


def test_build_reservation_coverage_diagnostics_describes_activity_time_conflict() -> None:
    request = _build_request()
    response = _build_response(
        request=request,
        generated_at=datetime.now(UTC),
        suffix="activity-conflict",
    )

    coverage = build_reservation_coverage_diagnostics(
        request=request,
        reservations=[
            ReservationItem(
                id="museum-entry",
                type="ticket",
                title="Museum Entry",
                start_at=datetime(2026, 5, 1, 9, 30, tzinfo=UTC),
                end_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
                location="People's Square",
            )
        ],
        response=response,
    )

    assert len(coverage) == 1
    assert coverage[0].status == "unresolved"
    assert coverage[0].reason_code == "day_conflict"
    assert "已有活动占用预约时段" in coverage[0].reason_summary
    assert "09:00-10:30“活动1-activity-conflict”" in coverage[0].reason_summary
    assert len(coverage[0].conflict_items) == 1
    assert coverage[0].conflict_items[0].day_number == 1
    assert coverage[0].conflict_items[0].kind == "activity"
    assert coverage[0].conflict_items[0].label == "活动1-activity-conflict"
    assert coverage[0].conflict_items[0].time_text == "09:00-10:30"


def test_trip_workspace_generation_multi_reservation_fallback_adds_coordination_tip() -> None:
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
        _ = (req, generated_at, include_debug)
        fresh = _build_response(
            request=req,
            generated_at=datetime.now(UTC),
            suffix="multi-anchor-fallback",
        )
        fresh.plan.days[0].activities = []
        fresh.plan.days[0].transport_tips = []
        return fresh

    planner.generate = fake_generate  # type: ignore[method-assign]
    workspace = asyncio.run(
        service.create_trip(
            TripCreateRequest(
                request_brief=request,
                reservations=[
                    ReservationItem(
                        id="museum-entry",
                        type="ticket",
                        title="Museum Entry",
                        start_at=datetime(2026, 5, 1, 9, 30, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
                        location="People's Square",
                    ),
                    ReservationItem(
                        id="night-cruise",
                        type="ticket",
                        title="Night River Cruise",
                        start_at=datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
                        end_at=datetime(2026, 5, 1, 20, 30, tzinfo=UTC),
                        location="Shiliupu Wharf",
                    ),
                ],
                generate_response=True,
                include_debug=True,
            )
        )
    )

    assert workspace.response_snapshot is not None
    day = workspace.response_snapshot.plan.days[0]
    assert [item.title for item in day.activities[:2]] == [
        "Museum Entry",
        "Night River Cruise",
    ]
    assert any(
        "固定预约顺序：09:30 Museum Entry -> 19:00 Night River Cruise" in tip
        for tip in day.transport_tips
    )
    assert "reservation_multi_anchor_coordinated" in day.fallbacks
    coverage = workspace.response_snapshot.diagnostics.reservation_coverage
    assert len(coverage) == 2
    assert all(item.status == "covered" for item in coverage)
    assert all(item.reason_code == "runtime_fallback" for item in coverage)
    assert all(item.coordinated_days == [1] for item in coverage)
    assert all(
        "固定预约顺序：09:30 Museum Entry -> 19:00 Night River Cruise" in item.coordination_tip
        for item in coverage
    )
    assert all("同日多预约顺序做了协调" in item.reason_summary for item in coverage)
    warnings = workspace.response_snapshot.diagnostics.warnings
    assert sum("Reservation fallback:" in item for item in warnings) == 2
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
