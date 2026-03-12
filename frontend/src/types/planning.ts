export type Pace = 'relaxed' | 'balanced' | 'intense'
export type BudgetLevel = 'economy' | 'comfort' | 'luxury'

export interface TravelerProfile {
  adults: number
  children: number
  seniors: number
}

export interface TripPlanningRequest {
  origin: string | null
  destination: string
  start_date: string
  days: number
  interests: string[]
  must_visit: string[]
  pace: Pace
  budget_level: BudgetLevel
  transport_preferences: string[]
  hotel_style: string
  dining_preferences: string[]
  travelers: TravelerProfile
  notes: string | null
}

export interface ToolCallRecord {
  tool_name: string
  arguments: Record<string, unknown>
  success: boolean
  summary: string
}

export interface GeoPoint {
  longitude: number
  latitude: number
}

export interface POIRecommendation {
  name: string
  poi_id: string | null
  address: string
  tags: string[]
  rating: number | null
  recommended_duration_minutes: number | null
  opening_hours: string | null
  district: string | null
  longitude: number | null
  latitude: number | null
  source: string | null
}

export interface RouteStep {
  instruction: string
  distance_text: string
  duration_text: string
}

export interface RouteSummary {
  day_number: number | null
  title: string
  from_name: string
  to_name: string
  waypoints: string[]
  distance_text: string
  duration_text: string
  mode: string
  steps: RouteStep[]
  polyline: GeoPoint[]
}

export interface DailyForecast {
  date: string
  day_weather: string
  night_weather: string
  high_temperature: string
  low_temperature: string
  advice: string
}

export interface WeatherSummary {
  overview: string
  temperature_range: string
  suggestions: string[]
  daily_forecasts: DailyForecast[]
}

export interface PlanningContext {
  destination: string
  attractions: POIRecommendation[]
  restaurants: POIRecommendation[]
  hotels: POIRecommendation[]
  routes: RouteSummary[]
  weather: WeatherSummary
}

export interface MealRecommendation {
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  venue_name: string
  cuisine: string
  suggestion: string
  estimated_cost: string
}

export interface Activity {
  start_time: string
  end_time: string
  title: string
  category: string
  description: string
  location_name: string
  transport_from_previous?: string | null
  expected_cost?: string | null
  booking_tip?: string | null
}

export interface DayPlan {
  day_number: number
  date: string
  theme: string
  overview: string
  hotel_area: string
  transport_tips: string[]
  meals: MealRecommendation[]
  activities: Activity[]
  weather?: DailyForecast | null
  route_summary?: RouteSummary | null
}

export interface StayRecommendation {
  area: string
  hotel_name: string
  reason: string
  nightly_budget: string
}

export interface BudgetBreakdown {
  currency: string
  accommodation: string
  transport: string
  food: string
  tickets: string
  extras: string
  total_estimate: string
}

export interface TravelPlan {
  title: string
  summary: string
  weather_summary: string
  best_booking_tip: string
  estimated_budget: BudgetBreakdown
  stay_recommendations: StayRecommendation[]
  city_tips: string[]
  packing_list: string[]
  days: DayPlan[]
}

export interface InitialPlanDay {
  day_number: number
  date: string
  theme: string
  focus: string
  must_visit: string[]
  poi_query: string
  dining_query: string
}

export interface InitialPlanDraft {
  summary: string
  days: InitialPlanDay[]
}

export interface AgentExecution {
  agent_name: string
  success: boolean
  summary: string
  used_llm: boolean
  used_tools: string[]
  warnings: string[]
}

export interface PlanGenerationMeta {
  llm_used: boolean
  fallback_used: boolean
  model_name: string
  warnings: string[]
}

export interface MapRenderConfig {
  provider: 'amap'
  enabled: boolean
  js_api_key: string | null
  security_js_code: string | null
  center: GeoPoint | null
}

export interface IntegrationStatus {
  mcp_enabled: boolean
  mcp_connected: boolean
  mcp_command: string
  available_tools: string[]
  resolved_tools: Record<string, string>
  missing_tools: string[]
  map_rendering_enabled: boolean
  map_js_key_configured: boolean
  security_js_code_configured: boolean
  mock_enabled: boolean
  warnings: string[]
}

export interface PlanningResponse {
  status: 'success'
  generated_at: string
  request_echo: TripPlanningRequest
  initial_plan: InitialPlanDraft
  planning_context: PlanningContext
  agent_trace: AgentExecution[]
  tool_trace: ToolCallRecord[]
  meta: PlanGenerationMeta
  map_config: MapRenderConfig
  integration_status: IntegrationStatus
  plan: TravelPlan
}
