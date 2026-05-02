import type { PlanningResponse } from "./planning-response"
import type { TripPlanningRequest } from "./planning-request"
import type { ReservationConflictItem } from "./planning-diagnostics"

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

export interface ReplanDaySummary {
  day_number: number
  highlights: string[]
  changes?: Array<{
    kind: "stay" | "meal" | "activity" | "route" | "budget" | "reservation"
    label: string
    before: string
    after: string
  }>
}

export interface ReplanSummary {
  created_at: string
  scope: "trip" | "day"
  repair_mode: "replace" | "fill_gaps"
  repair_gap:
    | "stay"
    | "meal"
    | "breakfast"
    | "lunch"
    | "dinner"
    | "snack"
    | "activity"
    | "reservation"
    | "day-plan"
    | null
  target_days: number[]
  title: string
  items: ReplanDaySummary[]
}

export interface PrecheckSummaryItem {
  key: string
  title: string
  before_status: "ok" | "warning" | "pending"
  after_status: "ok" | "warning" | "pending"
  before_days: number[]
  after_days: number[]
  recommended_gap:
    | "stay"
    | "meal"
    | "breakfast"
    | "lunch"
    | "dinner"
    | "snack"
    | "activity"
    | "reservation"
    | "day-plan"
    | null
  action_label: string
  action_reason: string
  actions?: Array<{
    gap:
      | "stay"
      | "meal"
      | "breakfast"
      | "lunch"
      | "dinner"
      | "snack"
      | "activity"
      | "reservation"
      | "day-plan"
    label: string
    reason: string
  }>
  before_summary: string
  after_summary: string
  conflict_items?: ReservationConflictItem[]
}

export interface PrecheckSummary {
  created_at: string
  title: string
  items: PrecheckSummaryItem[]
}

export type WorkspaceStatus =
  | "draft"
  | "ready"
  | "action_required"
  | "generating"
  | "error"

export type WorkspaceTimelineEventKind =
  | "created"
  | "updated"
  | "generated"
  | "replanned"
  | "prechecked"
  | "share_revoked"
  | "share_regenerated"

export type CalendarExportScope = "full" | "reservations" | "itinerary"

export interface WorkspaceTimelineEvent {
  id: string
  created_at: string
  kind: WorkspaceTimelineEventKind
  title: string
  summary: string
  version: number
  target_days: number[]
}

export interface TripSummary {
  id: string
  share_token: string
  share_enabled: boolean
  status: WorkspaceStatus
  version: number
  destination: string
  start_date: string
  days: number
  updated_at: string
  created_at: string
  reservations_count: number
  locked_day_count: number
  has_result: boolean
  title: string
}

export interface TripWorkspace {
  id: string
  share_token: string
  share_enabled: boolean
  status: WorkspaceStatus
  version: number
  created_at: string
  updated_at: string
  request_brief: TripPlanningRequest
  manual_notes: string
  locked_day_numbers: number[]
  reservations: ReservationItem[]
  last_replan_summary?: ReplanSummary | null
  last_precheck_summary?: PrecheckSummary | null
  timeline: WorkspaceTimelineEvent[]
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

export interface PrecheckRefreshRequest {
  include_debug?: boolean
}

export interface ReplanRequest {
  scope: "trip" | "day"
  day_numbers: number[]
  preserve_locked_days?: boolean
  repair_mode?: "replace" | "fill_gaps"
  repair_gap?:
    | "stay"
    | "meal"
    | "breakfast"
    | "lunch"
    | "dinner"
    | "snack"
    | "activity"
    | "reservation"
    | "day-plan"
    | null
  reason?: string | null
  include_debug?: boolean
}
