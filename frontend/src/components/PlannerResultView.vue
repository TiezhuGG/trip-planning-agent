<script setup lang="ts">
import AgentTrace from "./AgentTrace.vue";
import AmapMap from "./AmapMap.vue";
import DailyItinerarySection from "./DailyItinerarySection.vue";
import PlannerAgentSummaryPanel from "./PlannerAgentSummaryPanel.vue";
import PlannerResultHero from "./PlannerResultHero.vue";
import PlannerResultToolbar from "./PlannerResultToolbar.vue";
import PlanningTelemetryPanel from "./PlanningTelemetryPanel.vue";
import TripWorkspacePanel from "./TripWorkspacePanel.vue";

import type {
  DailyForecast,
  DayPOI,
  PlanningResponse,
  PlanningTelemetry,
  ReservationItem,
  RouteSummary,
  TripWorkspace,
} from "../types/planning";
import type {
  DayReadinessItem,
  DayReadinessSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";

const props = defineProps<{
  result: PlanningResponse;
  currentTrip: TripWorkspace | null;
  tripNotes: string;
  shareLink: string;
  tripSaving: boolean;
  tripLoading: boolean;
  tripReplanning: boolean;
  replanningDays: number[];
  expandedDays: number[];
  showDevPanels: boolean;
  telemetry: PlanningTelemetry;
  telemetryLoading: boolean;
  telemetryError: string;
  itineraryMapPois: DayPOI[];
  itineraryRoutes: RouteSummary[];
  itineraryWeatherForecasts: DailyForecast[];
  reservationAlerts: string[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
  budgetLabel: (value: PlanningResponse["request_echo"]["budget_level"]) => string;
  paceLabel: (value: PlanningResponse["request_echo"]["pace"]) => string;
}>();

defineEmits<{
  (e: "edit-current-trip"): void;
  (e: "reset"): void;
  (e: "export", format: "png" | "pdf"): void;
  (e: "update:notes", value: string): void;
  (e: "save-notes"): void;
  (e: "copy-share"): void;
  (e: "replan-trip"): void;
  (e: "add-reservation", item: Omit<ReservationItem, "id" | "created_at">): void;
  (e: "remove-reservation", reservationId: string): void;
  (e: "toggle-day", dayNumber: number): void;
  (e: "toggle-lock", dayNumber: number): void;
  (e: "replan-day", dayNumber: number): void;
  (e: "refresh-telemetry"): void;
}>();
</script>

<template>
  <section class="space-y-6">
    <PlannerResultToolbar
      @edit-current-trip="$emit('edit-current-trip')"
      @reset="$emit('reset')"
      @export="(format) => $emit('export', format)"
    />
    <PlannerResultHero
      :result="result"
      :budget-label="budgetLabel"
      :pace-label="paceLabel"
    />
    <TripWorkspacePanel
      :workspace="currentTrip"
      :notes="tripNotes"
      :share-link="shareLink"
      :saving="tripSaving || tripLoading"
      :replanning="tripReplanning"
      :reservations="currentTrip?.reservations ?? []"
      :reservation-alerts="reservationAlerts"
      :reservation-coverage-summary="reservationCoverageSummary"
      :reservation-coverage-items="reservationCoverageItems"
      :day-readiness-summary="dayReadinessSummary"
      :day-readiness-items="dayReadinessItems"
      @update:notes="(value) => $emit('update:notes', value)"
      @save-notes="$emit('save-notes')"
      @copy-share="$emit('copy-share')"
      @replan-trip="$emit('replan-trip')"
      @add-reservation="(item) => $emit('add-reservation', item)"
      @remove-reservation="(reservationId) => $emit('remove-reservation', reservationId)"
    />
    <section class="space-y-6">
      <div class="space-y-6">
        <article
          class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"
        >
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">
                Map
              </div>
              <h2 class="mt-3 text-2xl font-semibold text-ink">
                景点信息和地图标记
              </h2>
            </div>
          </div>
          <div class="mt-5">
            <AmapMap
              :map-config="result.map_config"
              :pois="itineraryMapPois"
              :routes="itineraryRoutes"
            />
          </div>
        </article>
        <DailyItinerarySection
          :days="result.plan.days"
          :routes="itineraryRoutes"
          :weather-forecasts="itineraryWeatherForecasts"
          :reservations="currentTrip?.reservations ?? []"
          :expanded-days="expandedDays"
          :locked-days="currentTrip?.locked_day_numbers ?? []"
          :replanning-days="replanningDays"
          @toggle="(dayNumber) => $emit('toggle-day', dayNumber)"
          @toggle-lock="(dayNumber) => $emit('toggle-lock', dayNumber)"
          @replan-day="(dayNumber) => $emit('replan-day', dayNumber)"
        />
      </div>
    </section>
    <section v-if="showDevPanels" class="grid gap-6 xl:grid-cols-3">
      <PlanningTelemetryPanel
        :telemetry="telemetry"
        :loading="telemetryLoading"
        :error="telemetryError"
        @refresh="$emit('refresh-telemetry')"
      />
      <PlannerAgentSummaryPanel :result="result" />
      <AgentTrace :result="result" />
    </section>
  </section>
</template>
