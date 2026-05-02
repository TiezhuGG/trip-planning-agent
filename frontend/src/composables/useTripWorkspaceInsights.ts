import { computed, type Ref } from "vue";

import type { PlanningResponse, TripWorkspace } from "../types/planning";
import {
  buildDayReadinessItems,
  buildDeparturePrecheckItems,
  buildReservationAlerts,
  buildReservationCoverageItems,
  summarizeDayReadiness,
  summarizeDeparturePrecheck,
  summarizeReservationCoverage,
} from "./tripWorkspaceInsightsHelpers";
export type {
  DayGapType,
  DayGapRepairPayload,
  DayReadinessAction,
  DayReadinessItem,
  DayReadinessSummary,
  DeparturePrecheckItem,
  DeparturePrecheckSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "./tripWorkspaceInsightsHelpers";

export function useTripWorkspaceInsights(options: {
  currentTrip: Ref<TripWorkspace | null>;
  result: Ref<PlanningResponse | null>;
}) {
  const { currentTrip, result } = options;

  const reservationAlerts = computed(() => buildReservationAlerts(currentTrip.value));

  const reservationCoverageItems = computed(() =>
    buildReservationCoverageItems({
      workspace: currentTrip.value,
      result: result.value,
    }),
  );

  const reservationCoverageSummary = computed(() =>
    summarizeReservationCoverage(reservationCoverageItems.value),
  );

  const dayReadinessItems = computed(() =>
    buildDayReadinessItems({
      workspace: currentTrip.value,
      result: result.value,
      reservationCoverageItems: reservationCoverageItems.value,
    }),
  );

  const dayReadinessSummary = computed(() =>
    summarizeDayReadiness(dayReadinessItems.value),
  );

  const departurePrecheckItems = computed(() =>
    buildDeparturePrecheckItems({
      result: result.value,
      reservationCoverageItems: reservationCoverageItems.value,
    }),
  );

  const departurePrecheckSummary = computed(() =>
    summarizeDeparturePrecheck(departurePrecheckItems.value),
  );

  return {
    reservationAlerts,
    reservationCoverageItems,
    reservationCoverageSummary,
    dayReadinessItems,
    dayReadinessSummary,
    departurePrecheckItems,
    departurePrecheckSummary,
  };
}
