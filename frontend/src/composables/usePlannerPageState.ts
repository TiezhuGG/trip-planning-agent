import { reactive, ref } from "vue"

import {
  createEmptyIntegrationStatus,
  createEmptyPlanningTelemetry,
} from "./usePlanningSupport"
import {
  createInitialTripPlanningRequest,
  plannerBudgetOptions,
  plannerHotelOptions,
  plannerInterestOptions,
  plannerPaceOptions,
  plannerStageOptions,
  plannerTransportOptions,
} from "./plannerPageOptions"
import type {
  IntegrationStatus,
  PlanningJobSummary,
  PlanningTelemetry,
  PlanningResponse,
  TripSummary,
  TripPlanningRequest,
  TripWorkspace,
} from "../types/planning"

export {
  plannerBudgetOptions,
  plannerHotelOptions,
  plannerInterestOptions,
  plannerPaceOptions,
  plannerStageOptions,
  plannerTransportOptions,
}

export function usePlannerPageState() {
  const form = reactive<TripPlanningRequest>(createInitialTripPlanningRequest())
  const mustVisitText = ref(form.must_visit.join("\u3001"))
  const diningText = ref(form.dining_preferences.join("\u3001"))
  const loading = ref(false)
  const progress = ref(0)
  const progressLabel = ref(plannerStageOptions[0])
  const workspaceBusyMessage = ref("")
  const retryingPlanningJobId = ref("")
  const result = ref<PlanningResponse | null>(null)
  const exportRoot = ref<HTMLElement | null>(null)
  const integrationStatus = ref<IntegrationStatus>(createEmptyIntegrationStatus())
  const integrationLoading = ref(false)
  const integrationError = ref("")
  const telemetry = ref<PlanningTelemetry>(createEmptyPlanningTelemetry())
  const telemetryLoading = ref(false)
  const telemetryError = ref("")
  const currentTrip = ref<TripWorkspace | null>(null)
  const tripNotes = ref("")
  const tripSaving = ref(false)
  const tripLoading = ref(false)
  const tripPrechecking = ref(false)
  const tripReplanning = ref(false)
  const draftSaving = ref(false)
  const recentTrips = ref<TripSummary[]>([])
  const recentTripsLoading = ref(false)
  const recentTripsError = ref("")
  const recentPlanningJobs = ref<PlanningJobSummary[]>([])
  const recentPlanningJobsLoading = ref(false)
  const recentPlanningJobsError = ref("")
  const replanningDays = ref<number[]>([])
  const expandedDays = ref<number[]>([])
  const focusedWorkspaceDays = ref<number[]>([])

  return {
    currentTrip,
    diningText,
    draftSaving,
    expandedDays,
    focusedWorkspaceDays,
    exportRoot,
    form,
    integrationError,
    integrationLoading,
    integrationStatus,
    loading,
    mustVisitText,
    progress,
    progressLabel,
    recentPlanningJobs,
    recentPlanningJobsError,
    recentPlanningJobsLoading,
    recentTrips,
    recentTripsError,
    recentTripsLoading,
    replanningDays,
    result,
    telemetry,
    telemetryError,
    telemetryLoading,
    tripLoading,
    tripNotes,
    tripPrechecking,
    tripReplanning,
    tripSaving,
    retryingPlanningJobId,
    workspaceBusyMessage,
  }
}
