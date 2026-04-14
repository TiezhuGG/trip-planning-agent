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
  PlanningTelemetry,
  PlanningResponse,
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
  const tripReplanning = ref(false)
  const draftSaving = ref(false)
  const replanningDays = ref<number[]>([])
  const expandedDays = ref<number[]>([])

  return {
    currentTrip,
    diningText,
    draftSaving,
    expandedDays,
    exportRoot,
    form,
    integrationError,
    integrationLoading,
    integrationStatus,
    loading,
    mustVisitText,
    progress,
    progressLabel,
    replanningDays,
    result,
    telemetry,
    telemetryError,
    telemetryLoading,
    tripLoading,
    tripNotes,
    tripReplanning,
    tripSaving,
  }
}
