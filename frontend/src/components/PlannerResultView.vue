<script setup lang="ts">
import type {
  CalendarExportScope,
  DailyForecast,
  DayPOI,
  PlanningJobSummary,
  PlanningResponse,
  PlanningTelemetry,
  ReservationItem,
  RouteSummary,
  TripWorkspace,
} from "../types/planning";
import type {
  DayGapRepairPayload,
  DayReadinessItem,
  DayReadinessSummary,
  DeparturePrecheckItem,
  DeparturePrecheckSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";

import AgentTrace from "./AgentTrace.vue";
import AmapMap from "./AmapMap.vue";
import CurrentPlanningJobBanner from "./CurrentPlanningJobBanner.vue";
import DailyItinerarySection from "./DailyItinerarySection.vue";
import PlannerAgentSummaryPanel from "./PlannerAgentSummaryPanel.vue";
import PlannerResultHero from "./PlannerResultHero.vue";
import PlannerResultToolbar from "./PlannerResultToolbar.vue";
import PlanningTelemetryPanel from "./PlanningTelemetryPanel.vue";
import TripWorkspacePanel from "./TripWorkspacePanel.vue";

defineProps<{
  result: PlanningResponse;
  currentTrip: TripWorkspace | null;
  tripNotes: string;
  shareLink: string;
  tripSaving: boolean;
  retryingPlanningJobId: string;
  workspaceBusyMessage: string;
  tripLoading: boolean;
  tripPrechecking: boolean;
  tripReplanning: boolean;
  recentPlanningJobs: PlanningJobSummary[];
  recentPlanningJobsLoading: boolean;
  recentPlanningJobsError: string;
  replanningDays: number[];
  expandedDays: number[];
  focusedWorkspaceDays: number[];
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
  departurePrecheckSummary: DeparturePrecheckSummary;
  departurePrecheckItems: DeparturePrecheckItem[];
  budgetLabel: (value: PlanningResponse["request_echo"]["budget_level"]) => string;
  paceLabel: (value: PlanningResponse["request_echo"]["pace"]) => string;
}>();

defineEmits<{
  (e: "edit-current-trip"): void;
  (e: "reset"): void;
  (e: "export", format: "png" | "pdf"): void;
  (e: "export-calendar", scope: CalendarExportScope): void;
  (e: "update:notes", value: string): void;
  (e: "save-notes"): void;
  (e: "copy-share"): void;
  (e: "revoke-share"): void;
  (e: "regenerate-share"): void;
  (e: "replan-trip"): void;
  (e: "focus-workspace-days", dayNumbers: number[]): void;
  (e: "clear-workspace-focus"): void;
  (e: "refresh-precheck"): void;
  (e: "retry-planning-job", job: PlanningJobSummary): void;
  (e: "repair-day-gap", payload: DayGapRepairPayload): void;
  (e: "add-reservation", item: Omit<ReservationItem, "id">): void;
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
      :workspace="currentTrip"
      :recent-planning-jobs="recentPlanningJobs"
      @edit-current-trip="$emit('edit-current-trip')"
      @reset="$emit('reset')"
      @export="(format) => $emit('export', format)"
      @export-calendar="(scope) => $emit('export-calendar', scope)"
    />
    <PlannerResultHero
      :result="result"
      :budget-label="budgetLabel"
      :pace-label="paceLabel"
    />
    <CurrentPlanningJobBanner
      :jobs="recentPlanningJobs"
      :busy-message="workspaceBusyMessage"
    />
    <TripWorkspacePanel
      :workspace="currentTrip"
      :notes="tripNotes"
      :share-link="shareLink"
      :saving="tripSaving || tripLoading"
      :retrying-job-id="retryingPlanningJobId"
      :busy-message="workspaceBusyMessage"
      :prechecking="tripPrechecking"
      :replanning="tripReplanning"
      :recent-planning-jobs="recentPlanningJobs"
      :recent-planning-jobs-loading="recentPlanningJobsLoading"
      :recent-planning-jobs-error="recentPlanningJobsError"
      :replanning-days="replanningDays"
      :focused-workspace-days="focusedWorkspaceDays"
      :reservations="currentTrip?.reservations ?? []"
      :reservation-alerts="reservationAlerts"
      :reservation-coverage-summary="reservationCoverageSummary"
      :reservation-coverage-items="reservationCoverageItems"
      :day-readiness-summary="dayReadinessSummary"
      :day-readiness-items="dayReadinessItems"
      :departure-precheck-summary="departurePrecheckSummary"
      :departure-precheck-items="departurePrecheckItems"
      @update:notes="(value) => $emit('update:notes', value)"
      @save-notes="$emit('save-notes')"
      @copy-share="$emit('copy-share')"
      @revoke-share="$emit('revoke-share')"
      @regenerate-share="$emit('regenerate-share')"
      @export-calendar="(scope) => $emit('export-calendar', scope)"
      @focus-workspace-days="(dayNumbers) => $emit('focus-workspace-days', dayNumbers)"
      @clear-workspace-focus="$emit('clear-workspace-focus')"
      @replan-trip="$emit('replan-trip')"
      @refresh-precheck="$emit('refresh-precheck')"
      @retry-planning-job="(job) => $emit('retry-planning-job', job)"
      @repair-day-gap="(payload) => $emit('repair-day-gap', payload)"
      @add-reservation="(item) => $emit('add-reservation', item)"
      @remove-reservation="(reservationId) => $emit('remove-reservation', reservationId)"
    />
    <section class="space-y-6">
      <div class="space-y-6">
        <article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">地图</div>
              <h2 class="mt-3 text-2xl font-semibold text-ink">
                景点信息与地图标注
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
          :highlighted-days="focusedWorkspaceDays"
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
