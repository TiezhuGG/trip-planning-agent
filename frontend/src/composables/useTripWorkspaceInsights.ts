import { computed, type Ref } from "vue";

import type { PlanningResponse, TripWorkspace } from "../types/planning";
import {
  buildDayReadinessItems,
  buildReservationAlerts,
  buildReservationCoverageItems,
  summarizeDayReadiness,
  summarizeReservationCoverage,
} from "./tripWorkspaceInsightsHelpers";
export type {
  DayReadinessItem,
  DayReadinessSummary,
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

  return {
    reservationAlerts,
    reservationCoverageItems,
    reservationCoverageSummary,
    dayReadinessItems,
    dayReadinessSummary,
  };
}
