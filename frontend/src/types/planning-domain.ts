import type { TripPlanningRequest } from "./planning-request"

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

export interface DayPOI {
  kind: "activity" | "meal" | "stay"
  label: string
  poi: POIRecommendation
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
  estimated_transport_cost_cny: number
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
  meal_type: "breakfast" | "lunch" | "dinner" | "snack"
  venue_name: string
  cuisine: string
  suggestion: string
  estimated_cost: string
  estimated_cost_cny: number
  poi?: POIRecommendation | null
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
  ticket_cost_cny: number
  booking_tip?: string | null
  poi?: POIRecommendation | null
}

export interface DayStayInfo {
  area: string
  hotel_name: string
  reason: string
  room_nightly_cost_cny: number
  poi?: POIRecommendation | null
}

export interface DayCostBreakdown {
  accommodation_per_person_cny: number
  transport_per_person_cny: number
  food_per_person_cny: number
  tickets_per_person_cny: number
  extras_per_person_cny: number
  total_per_person_cny: number
}

export interface DayPlan {
  day_number: number
  date: string
  theme: string
  overview: string
  hotel_area: string
  stay: DayStayInfo
  cost_breakdown: DayCostBreakdown
  transport_tips: string[]
  meals: MealRecommendation[]
  activities: Activity[]
  weather?: DailyForecast | null
  route_summary?: RouteSummary | null
  route_summaries: RouteSummary[]
  route_segments: RouteSummary[]
  map_pois: DayPOI[]
  fallbacks: string[]
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

export interface ReservationSeedContext {
  request_brief: TripPlanningRequest
}
