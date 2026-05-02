import type { PlanningResponse } from "./planning-response"
import type { TripWorkspace } from "./planning-workspace"

export type PlanningJobKind =
  | "generate_plan"
  | "update_trip"
  | "replan_trip"
  | "precheck_trip"
export type PlanningJobStatus = "queued" | "running" | "succeeded" | "failed"

export interface PlanningJob {
  id: string
  kind: PlanningJobKind
  status: PlanningJobStatus
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
  trip_id: string | null
  progress_message: string
  error_code: string
  error_message: string
  planning_response: PlanningResponse | null
  trip_workspace: TripWorkspace | null
}

export interface PlanningJobSummary {
  id: string
  kind: PlanningJobKind
  status: PlanningJobStatus
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
  trip_id: string | null
  progress_message: string
  error_code: string
  error_message: string
}
