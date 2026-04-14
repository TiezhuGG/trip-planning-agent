export type Pace = "relaxed" | "balanced" | "intense"
export type BudgetLevel = "economy" | "comfort" | "luxury"

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
