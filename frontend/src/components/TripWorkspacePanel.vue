<script setup lang="ts">
import type {
  DayReadinessItem,
  DayReadinessSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";
import type { ReservationItem, TripWorkspace } from "../types/planning";

import PlannerReservationPanel from "./PlannerReservationPanel.vue";
import PlannerWorkspaceSummary from "./PlannerWorkspaceSummary.vue";

defineProps<{
  workspace: TripWorkspace | null;
  notes: string;
  shareLink: string;
  saving: boolean;
  replanning: boolean;
  reservations: ReservationItem[];
  reservationAlerts: string[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
}>();

const emit = defineEmits<{
  (event: "update:notes", value: string): void;
  (event: "save-notes"): void;
  (event: "copy-share"): void;
  (event: "replan-trip"): void;
  (event: "add-reservation", value: Omit<ReservationItem, "id">): void;
  (event: "remove-reservation", id: string): void;
}>();
</script>

<template>
  <article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7">
    <PlannerWorkspaceSummary
      :workspace="workspace"
      :notes="notes"
      :share-link="shareLink"
      :saving="saving"
      :replanning="replanning"
      :reservations-count="reservations.length"
      @update:notes="(value) => emit('update:notes', value)"
      @save-notes="emit('save-notes')"
      @copy-share="emit('copy-share')"
      @replan-trip="emit('replan-trip')"
    />

    <div class="mt-6">
      <PlannerReservationPanel
        :workspace="workspace"
        :saving="saving"
        :reservations="reservations"
        :reservation-alerts="reservationAlerts"
        :reservation-coverage-summary="reservationCoverageSummary"
        :reservation-coverage-items="reservationCoverageItems"
        :day-readiness-summary="dayReadinessSummary"
        :day-readiness-items="dayReadinessItems"
        @add-reservation="(value) => emit('add-reservation', value)"
        @remove-reservation="(id) => emit('remove-reservation', id)"
      />
    </div>
  </article>
</template>
