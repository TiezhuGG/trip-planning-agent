import type { PlanningResponse } from "./planning-response"
import type { TripPlanningRequest } from "./planning-request"

export type ReservationType =
  | "flight"
  | "train"
  | "hotel"
  | "restaurant"
  | "ticket"
  | "other"

export interface ReservationItem {
  id: string
  type: ReservationType
  title: string
  start_at: string | null
  end_at: string | null
  location: string
  notes: string
  source: string
  confirmation_code: string
}

export interface TripWorkspace {
  id: string
  share_token: string
  status: "draft" | "ready"
  version: number
  created_at: string
  updated_at: string
  request_brief: TripPlanningRequest
  manual_notes: string
  locked_day_numbers: number[]
  reservations: ReservationItem[]
  response_snapshot: PlanningResponse | null
}

export interface TripCreateRequest {
  request_brief: TripPlanningRequest
  response_snapshot?: PlanningResponse | null
  manual_notes?: string
  locked_day_numbers?: number[]
  reservations?: ReservationItem[]
  generate_response?: boolean
  include_debug?: boolean
}

export interface TripWorkspacePatchRequest {
  request_brief?: TripPlanningRequest | null
  manual_notes?: string | null
  locked_day_numbers?: number[] | null
  reservations?: ReservationItem[] | null
  generate_response?: boolean
  include_debug?: boolean
}

export interface ReplanRequest {
  scope: "trip" | "day"
  day_numbers: number[]
  preserve_locked_days?: boolean
  reason?: string | null
  include_debug?: boolean
}
