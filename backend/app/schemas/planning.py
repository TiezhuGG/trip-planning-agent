import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TravelerProfile(BaseModel):
    adults: int = Field(default=2, ge=1, le=10)
    children: int = Field(default=0, ge=0, le=6)
    seniors: int = Field(default=0, ge=0, le=4)


class TripPlanningRequest(BaseModel):
    origin: str | None = Field(default=None, description="出发地")
    destination: str = Field(description="目的地")
    start_date: date = Field(description="出发日期")
    days: int = Field(default=3, ge=1, le=14)
    interests: list[str] = Field(default_factory=list)
    must_visit: list[str] = Field(default_factory=list)
    pace: Literal["relaxed", "balanced", "intense"] = "balanced"
    budget_level: Literal["economy", "comfort", "luxury"] = "comfort"
    transport_preferences: list[str] = Field(default_factory=list)
    hotel_style: str = "市中心舒适型"
    dining_preferences: list[str] = Field(default_factory=list)
    travelers: TravelerProfile = Field(default_factory=TravelerProfile)
    notes: str | None = None
    @field_validator("destination")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[\u4e00-\u9fff]{2,30}", normalized):
            raise ValueError("目的地仅支持中文城市名（例如：上海、北京市）")
        return normalized


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    success: bool = True
    summary: str = ""


class GeoPoint(BaseModel):
    longitude: float
    latitude: float


class POIRecommendation(BaseModel):
    name: str
    poi_id: str | None = None
    address: str = ""
    tags: list[str] = Field(default_factory=list)
    rating: float | None = None
    recommended_duration_minutes: int | None = None
    opening_hours: str | None = None
    district: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    source: str | None = None


class DayPOI(BaseModel):
    kind: Literal["activity", "meal", "stay"]
    label: str = ""
    poi: POIRecommendation


class RouteStep(BaseModel):
    instruction: str
    distance_text: str = ""
    duration_text: str = ""


class RouteSummary(BaseModel):
    day_number: int | None = None
    title: str = ""
    from_name: str
    to_name: str
    waypoints: list[str] = Field(default_factory=list)
    distance_text: str = ""
    duration_text: str = ""
    mode: str = "driving"
    estimated_transport_cost_cny: int = Field(default=0, ge=0)
    steps: list[RouteStep] = Field(default_factory=list)
    polyline: list[GeoPoint] = Field(default_factory=list)


class DailyForecast(BaseModel):
    date: str
    day_weather: str = ""
    night_weather: str = ""
    high_temperature: str = ""
    low_temperature: str = ""
    advice: str = ""


class WeatherSummary(BaseModel):
    overview: str = ""
    temperature_range: str = ""
    suggestions: list[str] = Field(default_factory=list)
    daily_forecasts: list[DailyForecast] = Field(default_factory=list)


class PlanningContext(BaseModel):
    destination: str
    attractions: list[POIRecommendation] = Field(default_factory=list)
    restaurants: list[POIRecommendation] = Field(default_factory=list)
    hotels: list[POIRecommendation] = Field(default_factory=list)
    routes: list[RouteSummary] = Field(default_factory=list)
    weather: WeatherSummary = Field(default_factory=WeatherSummary)


class MealRecommendation(BaseModel):
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    venue_name: str
    cuisine: str = ""
    suggestion: str = ""
    estimated_cost: str = ""
    estimated_cost_cny: int = Field(default=0, ge=0)
    poi: POIRecommendation | None = None


class Activity(BaseModel):
    start_time: str
    end_time: str
    title: str
    category: str
    description: str
    location_name: str
    transport_from_previous: str | None = None
    expected_cost: str | None = None
    ticket_cost_cny: int = Field(default=0, ge=0)
    booking_tip: str | None = None
    poi: POIRecommendation | None = None


class DayStayInfo(BaseModel):
    area: str = ""
    hotel_name: str = ""
    reason: str = ""
    room_nightly_cost_cny: int = Field(default=0, ge=0)
    poi: POIRecommendation | None = None


class DayCostBreakdown(BaseModel):
    accommodation_per_person_cny: int = Field(default=0, ge=0)
    transport_per_person_cny: int = Field(default=0, ge=0)
    food_per_person_cny: int = Field(default=0, ge=0)
    tickets_per_person_cny: int = Field(default=0, ge=0)
    extras_per_person_cny: int = Field(default=0, ge=0)
    total_per_person_cny: int = Field(default=0, ge=0)


class DayPlan(BaseModel):
    day_number: int
    date: str
    theme: str
    overview: str
    hotel_area: str
    stay: DayStayInfo = Field(default_factory=DayStayInfo)
    cost_breakdown: DayCostBreakdown = Field(default_factory=DayCostBreakdown)
    transport_tips: list[str] = Field(default_factory=list)
    meals: list[MealRecommendation] = Field(default_factory=list)
    activities: list[Activity] = Field(default_factory=list)
    weather: DailyForecast | None = None
    route_summary: RouteSummary | None = None
    route_summaries: list[RouteSummary] = Field(default_factory=list)
    route_segments: list[RouteSummary] = Field(default_factory=list)
    map_pois: list[DayPOI] = Field(default_factory=list)
    fallbacks: list[str] = Field(default_factory=list)


class StayRecommendation(BaseModel):
    area: str
    hotel_name: str
    reason: str
    nightly_budget: str


class BudgetBreakdown(BaseModel):
    currency: str = "CNY"
    accommodation: str = ""
    transport: str = ""
    food: str = ""
    tickets: str = ""
    extras: str = ""
    total_estimate: str = ""


class TravelPlan(BaseModel):
    title: str
    summary: str
    weather_summary: str
    best_booking_tip: str
    estimated_budget: BudgetBreakdown
    stay_recommendations: list[StayRecommendation] = Field(default_factory=list)
    city_tips: list[str] = Field(default_factory=list)
    packing_list: list[str] = Field(default_factory=list)
    days: list[DayPlan] = Field(default_factory=list)


class InitialPlanDay(BaseModel):
    day_number: int
    date: str
    theme: str
    focus: str
    must_visit: list[str] = Field(default_factory=list)
    poi_query: str = ""
    dining_query: str = ""


class InitialPlanDraft(BaseModel):
    summary: str
    days: list[InitialPlanDay] = Field(default_factory=list)


class AgentExecution(BaseModel):
    agent_name: str
    success: bool = True
    summary: str = ""
    used_llm: bool = False
    used_tools: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlanGenerationMeta(BaseModel):
    llm_used: bool = False
    fallback_used: bool = False
    model_name: str = ""
    warnings: list[str] = Field(default_factory=list)
    stage_timings_ms: dict[str, int] = Field(default_factory=dict)


class StageDiagnostic(BaseModel):
    stage: str
    status: Literal["ok", "warning", "fallback", "error"] = "ok"
    summary: str = ""
    code: str = ""
    warnings: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    used_llm: bool = False
    provider: str = ""


class ReservationConflictItem(BaseModel):
    day_number: int
    kind: Literal["activity", "meal", "stay"]
    label: str = ""
    time_text: str = ""
    summary: str = ""


class ReservationCoverageDiagnostic(BaseModel):
    reservation_id: str = ""
    title: str
    status: Literal["covered", "unresolved", "pending"] = "pending"
    target_days: list[int] = Field(default_factory=list)
    matched_days: list[int] = Field(default_factory=list)
    auto_anchored_days: list[int] = Field(default_factory=list)
    coordinated_days: list[int] = Field(default_factory=list)
    coordination_tip: str = ""
    reason_code: Literal[
        "generated_match",
        "runtime_fallback",
        "missing_time_window",
        "day_conflict",
        "no_explicit_match",
    ] = "generated_match"
    reason_summary: str = ""
    conflict_items: list[ReservationConflictItem] = Field(default_factory=list)
    detail: str = ""


class PlanDiagnostics(BaseModel):
    llm: list[StageDiagnostic] = Field(default_factory=list)
    mcp: list[StageDiagnostic] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    fallbacks_used: list[str] = Field(default_factory=list)
    reservation_coverage: list[ReservationCoverageDiagnostic] = Field(default_factory=list)
    error_code: str = ""


class MapRenderConfig(BaseModel):
    provider: Literal["amap"] = "amap"
    enabled: bool = False
    js_api_key: str | None = None
    security_js_code: str | None = None
    center: GeoPoint | None = None


class IntegrationStatus(BaseModel):
    mcp_enabled: bool = False
    mcp_connected: bool = False
    mcp_command: str = ""
    llm_enabled: bool = False
    llm_reachable: bool = False
    llm_model: str = ""
    llm_base_url: str = ""
    available_tools: list[str] = Field(default_factory=list)
    resolved_tools: dict[str, str] = Field(default_factory=dict)
    missing_tools: list[str] = Field(default_factory=list)
    map_rendering_enabled: bool = False
    map_js_key_configured: bool = False
    security_js_code_configured: bool = False
    warnings: list[str] = Field(default_factory=list)


class StageTimingPoint(BaseModel):
    at: datetime
    value_ms: int = 0


class StageTimingStats(BaseModel):
    count: int = 0
    p50_ms: int = 0
    p95_ms: int = 0
    max_ms: int = 0
    last_ms: int = 0
    recent_ms: list[int] = Field(default_factory=list)
    recent_points: list[StageTimingPoint] = Field(default_factory=list)


class PlanningTelemetry(BaseModel):
    enabled: bool = False
    window_size: int = 0
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    stages: dict[str, StageTimingStats] = Field(default_factory=dict)
    updated_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class PlanningResponse(BaseModel):
    status: Literal["success", "partial_success", "fallback_success"] = "success"
    generated_at: datetime
    request_echo: TripPlanningRequest
    initial_plan: InitialPlanDraft
    planning_context: PlanningContext
    agent_trace: list[AgentExecution] = Field(default_factory=list)
    tool_trace: list[ToolCallRecord] = Field(default_factory=list)
    meta: PlanGenerationMeta = Field(default_factory=PlanGenerationMeta)
    diagnostics: PlanDiagnostics = Field(default_factory=PlanDiagnostics)
    map_config: MapRenderConfig = Field(default_factory=MapRenderConfig)
    integration_status: IntegrationStatus = Field(default_factory=IntegrationStatus)
    plan: TravelPlan


class ReservationItem(BaseModel):
    id: str = ""
    type: Literal["flight", "train", "hotel", "restaurant", "ticket", "other"] = "other"
    title: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str = ""
    notes: str = ""
    source: str = ""
    confirmation_code: str = ""


class ReplanChange(BaseModel):
    kind: Literal["stay", "meal", "activity", "route", "budget", "reservation"]
    label: str
    before: str = ""
    after: str = ""


class ReplanDaySummary(BaseModel):
    day_number: int
    highlights: list[str] = Field(default_factory=list)
    changes: list[ReplanChange] = Field(default_factory=list)


class ReplanSummary(BaseModel):
    created_at: datetime
    scope: Literal["trip", "day"] = "day"
    repair_mode: Literal["replace", "fill_gaps"] = "replace"
    repair_gap: str | None = None
    target_days: list[int] = Field(default_factory=list)
    title: str = ""
    items: list[ReplanDaySummary] = Field(default_factory=list)


class PrecheckRepairAction(BaseModel):
    gap: Literal["stay", "meal", "breakfast", "lunch", "dinner", "snack", "activity", "reservation", "day-plan"]
    label: str = ""
    reason: str = ""
    day_numbers: list[int] = Field(default_factory=list)


class PrecheckSummaryItem(BaseModel):
    key: str
    title: str
    before_status: Literal["ok", "warning", "pending"] = "pending"
    after_status: Literal["ok", "warning", "pending"] = "pending"
    before_days: list[int] = Field(default_factory=list)
    after_days: list[int] = Field(default_factory=list)
    recommended_gap: Literal["stay", "meal", "breakfast", "lunch", "dinner", "snack", "activity", "reservation", "day-plan"] | None = None
    action_label: str = ""
    action_reason: str = ""
    actions: list[PrecheckRepairAction] = Field(default_factory=list)
    before_summary: str = ""
    after_summary: str = ""
    conflict_items: list[ReservationConflictItem] = Field(default_factory=list)


class PrecheckSummary(BaseModel):
    created_at: datetime
    title: str = ""
    items: list[PrecheckSummaryItem] = Field(default_factory=list)


class WorkspaceTimelineEvent(BaseModel):
    id: str = ""
    created_at: datetime
    kind: Literal[
        "created",
        "updated",
        "generated",
        "snapshot",
        "replanned",
        "prechecked",
        "restored",
        "share_revoked",
        "share_regenerated",
    ]
    title: str
    summary: str = ""
    version: int = Field(default=1, ge=1)
    target_days: list[int] = Field(default_factory=list)


class TripSummary(BaseModel):
    id: str
    share_token: str
    share_enabled: bool = True
    status: Literal["draft", "ready", "action_required", "generating", "error"] = "ready"
    version: int = Field(default=1, ge=1)
    destination: str
    start_date: date
    days: int = Field(default=1, ge=1)
    updated_at: datetime
    created_at: datetime
    reservations_count: int = 0
    locked_day_count: int = 0
    has_result: bool = False
    title: str = ""


class TripWorkspaceVersionSummary(BaseModel):
    trip_id: str
    version: int = Field(default=1, ge=1)
    status: Literal["draft", "ready", "action_required", "generating", "error"] = "ready"
    updated_at: datetime
    created_at: datetime
    has_result: bool = False
    title: str = ""
    version_label: str = ""
    is_starred: bool = False
    is_archived: bool = False
    is_current: bool = False
    version_origin_kind: Literal[
        "created",
        "updated",
        "generated",
        "snapshot",
        "replanned",
        "prechecked",
        "restored",
        "share_revoked",
        "share_regenerated",
    ] | None = None
    restored_from_version: int | None = Field(default=None, ge=1)


class TripWorkspaceVersionListResponse(BaseModel):
    items: list[TripWorkspaceVersionSummary]
    total: int = Field(default=0, ge=0)
    has_more: bool = False


class PlanningJob(BaseModel):
    id: str
    kind: Literal["generate_plan", "update_trip", "replan_trip", "precheck_trip"]
    status: Literal["queued", "running", "succeeded", "failed"] = "queued"
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    trip_id: str | None = None
    progress_message: str = ""
    error_code: str = ""
    error_message: str = ""
    planning_response: PlanningResponse | None = None
    trip_workspace: "TripWorkspace | None" = None


class PlanningJobSummary(BaseModel):
    id: str
    kind: Literal["generate_plan", "update_trip", "replan_trip", "precheck_trip"]
    status: Literal["queued", "running", "succeeded", "failed"] = "queued"
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    trip_id: str | None = None
    progress_message: str = ""
    error_code: str = ""
    error_message: str = ""


class TripWorkspace(BaseModel):
    id: str
    share_token: str
    share_enabled: bool = True
    status: Literal["draft", "ready", "action_required", "generating", "error"] = "ready"
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime
    request_brief: TripPlanningRequest
    manual_notes: str = ""
    version_label: str = ""
    is_starred: bool = False
    is_archived: bool = False
    version_origin_kind: Literal[
        "created",
        "updated",
        "generated",
        "snapshot",
        "replanned",
        "prechecked",
        "restored",
        "share_revoked",
        "share_regenerated",
    ] | None = None
    restored_from_version: int | None = Field(default=None, ge=1)
    locked_day_numbers: list[int] = Field(default_factory=list)
    reservations: list[ReservationItem] = Field(default_factory=list)
    last_replan_summary: ReplanSummary | None = None
    last_precheck_summary: PrecheckSummary | None = None
    timeline: list[WorkspaceTimelineEvent] = Field(default_factory=list)
    response_snapshot: PlanningResponse | None = None


class TripCreateRequest(BaseModel):
    request_brief: TripPlanningRequest
    response_snapshot: PlanningResponse | None = None
    manual_notes: str = ""
    locked_day_numbers: list[int] = Field(default_factory=list)
    reservations: list[ReservationItem] = Field(default_factory=list)
    generate_response: bool = False
    include_debug: bool = False


class TripWorkspacePatchRequest(BaseModel):
    request_brief: TripPlanningRequest | None = None
    manual_notes: str | None = None
    locked_day_numbers: list[int] | None = None
    reservations: list[ReservationItem] | None = None
    generate_response: bool = False
    include_debug: bool = False


class TripWorkspaceVersion(BaseModel):
    trip_id: str
    version: int = Field(default=1, ge=1)
    captured_at: datetime
    is_current: bool = False
    workspace: TripWorkspace


class TripWorkspaceVersionLabelUpdateRequest(BaseModel):
    version_label: str = ""


class TripWorkspaceVersionCreateRequest(BaseModel):
    version_label: str = ""


class TripWorkspaceVersionMetaUpdateRequest(BaseModel):
    version_label: str = ""
    is_starred: bool = False
    is_archived: bool = False


class PrecheckRefreshRequest(BaseModel):
    include_debug: bool = False


class ReplanRequest(BaseModel):
    scope: Literal["trip", "day"] = "day"
    day_numbers: list[int] = Field(default_factory=list)
    preserve_locked_days: bool = True
    repair_mode: Literal["replace", "fill_gaps"] = "replace"
    repair_gap: Literal["stay", "meal", "breakfast", "lunch", "dinner", "snack", "activity", "reservation", "day-plan"] | None = None
    reason: str | None = None
    include_debug: bool = False


PlanningJob.model_rebuild()
