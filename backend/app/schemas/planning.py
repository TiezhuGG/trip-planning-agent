from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class Activity(BaseModel):
    start_time: str
    end_time: str
    title: str
    category: str
    description: str
    location_name: str
    transport_from_previous: str | None = None
    expected_cost: str | None = None
    booking_tip: str | None = None


class DayPlan(BaseModel):
    day_number: int
    date: str
    theme: str
    overview: str
    hotel_area: str
    transport_tips: list[str] = Field(default_factory=list)
    meals: list[MealRecommendation] = Field(default_factory=list)
    activities: list[Activity] = Field(default_factory=list)
    weather: DailyForecast | None = None
    route_summary: RouteSummary | None = None


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


class MapRenderConfig(BaseModel):
    provider: Literal["amap"] = "amap"
    enabled: bool = False
    js_api_key: str | None = None
    security_js_code: str | None = None
    center: GeoPoint | None = None


class PlanningResponse(BaseModel):
    status: Literal["success"] = "success"
    generated_at: datetime
    request_echo: TripPlanningRequest
    initial_plan: InitialPlanDraft
    planning_context: PlanningContext
    agent_trace: list[AgentExecution] = Field(default_factory=list)
    tool_trace: list[ToolCallRecord] = Field(default_factory=list)
    meta: PlanGenerationMeta = Field(default_factory=PlanGenerationMeta)
    map_config: MapRenderConfig = Field(default_factory=MapRenderConfig)
    plan: TravelPlan
