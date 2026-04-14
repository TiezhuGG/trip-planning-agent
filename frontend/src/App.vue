<script setup lang="ts">

import NotificationModal from "./components/NotificationModal.vue";
import PlannerResultView from "./components/PlannerResultView.vue";
import PlannerSetupView from "./components/PlannerSetupView.vue";
import { usePlannerAppBridge } from "./composables/usePlannerAppBridge";
import { usePlannerDateRange } from "./composables/usePlannerDateRange";
import { usePlannerDerivedState } from "./composables/usePlannerDerivedState";
import {
  plannerBudgetOptions,
  plannerHotelOptions,
  plannerInterestOptions,
  plannerPaceOptions,
  usePlannerPageState,
  plannerStageOptions,
  plannerTransportOptions,
} from "./composables/usePlannerPageState";
import { usePlannerViewModels } from "./composables/usePlannerViewModels";
import { usePlannerShell } from "./composables/usePlannerShell";
import { usePlannerSubmission } from "./composables/usePlannerSubmission";
import { useTripWorkspaceActions } from "./composables/useTripWorkspaceActions";
import { useTripWorkspaceInsights } from "./composables/useTripWorkspaceInsights";
import { usePlanningSupport } from "./composables/usePlanningSupport";
import { isChineseCityName, splitText } from "./utils/tripPlannerForm";

const showDevPanels = import.meta.env.VITE_SHOW_DEV_PANELS === "true";
const {
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
} = usePlannerPageState();
const { startDate, endDate } = usePlannerDateRange(form);
const {
  reservationAlerts,
  reservationCoverageItems,
  reservationCoverageSummary,
  dayReadinessItems,
  dayReadinessSummary,
} = useTripWorkspaceInsights({
  currentTrip,
  result,
});
const {
  noticeModal,
  applyWorkspace,
  budgetLabel,
  closeNotice,
  editCurrentTrip,
  initializePlanner,
  openNotice,
  paceLabel,
  resetPlanner,
  syncTripQuery,
  toggleDay,
  toggleSelection,
  updateTripNotes,
} = usePlannerShell({
  form,
  currentTrip,
  result,
  tripNotes,
  draftSaving,
  tripReplanning,
  replanningDays,
  expandedDays,
  integrationStatus,
  startDate,
  endDate,
  mustVisitText,
  diningText,
  paceOptions: plannerPaceOptions,
  budgetOptions: plannerBudgetOptions,
});
const {
  currentIntegrationStatus,
  shareLink,
  isEditingWorkspace,
  itineraryMapPois,
  itineraryRoutes,
  itineraryWeatherForecasts,
  inputSummary,
  summaryTags,
  destinationValid,
} = usePlannerDerivedState({
  form,
  result,
  currentTrip,
  integrationStatus,
  startDate,
  endDate,
  paceLabel,
  budgetLabel,
});
const {
  addReservation,
  copyShareLink,
  loadSharedTrip,
  persistWorkspaceFromResponse,
  removeReservation,
  replanDay,
  replanUnlockedDays,
  saveDraft,
  saveTripNotesAndLocks,
  saveWorkspacePatch,
  toggleTripDayLock,
} = useTripWorkspaceActions({
  currentTrip,
  tripNotes,
  tripSaving,
  tripLoading,
  tripReplanning,
  draftSaving,
  replanningDays,
  shareLink,
  form,
  mustVisitText,
  diningText,
  showDevPanels,
  applyWorkspace,
  openNotice,
  syncTripQuery,
  isChineseCityName,
  splitText,
});
const {
  buildPlanNotices,
  exportAs,
  loadIntegrationStatus,
  loadPlanningTelemetry,
  startProgress,
  stopProgress,
  toUserError,
} = usePlanningSupport({
  integrationStatus,
  integrationLoading,
  integrationError,
  telemetry,
  telemetryLoading,
  telemetryError,
  progress,
  progressLabel,
  exportRoot,
  result,
  expandedDays,
  showDevPanels,
  stageOptions: plannerStageOptions,
  openNotice,
});
const { submitPlan } = usePlannerSubmission({
  form,
  mustVisitText,
  diningText,
  loading,
  result,
  currentTrip,
  tripNotes,
  expandedDays,
  integrationStatus,
  showDevPanels,
  isChineseCityName,
  syncTripQuery,
  openNotice,
  startProgress,
  stopProgress,
  buildPlanNotices,
  toUserError,
  persistWorkspaceFromResponse,
  saveWorkspacePatch,
  loadPlanningTelemetry,
});
const { setupViewProps, resultViewProps, noticeModalProps } = usePlannerViewModels(
  {
    summaryTags,
    isEditingWorkspace,
    currentTrip,
    form,
    plannerInterestOptions,
    plannerTransportOptions,
    plannerHotelOptions,
    plannerPaceOptions,
    plannerBudgetOptions,
    showDevPanels,
    inputSummary,
    progress,
    progressLabel,
    loading,
    draftSaving,
    destinationValid,
    currentIntegrationStatus,
    integrationLoading,
    telemetry,
    telemetryLoading,
    telemetryError,
    paceLabel,
    toggleSelection,
  },
  {
    result,
    currentTrip,
    tripNotes,
    shareLink,
    tripSaving,
    tripLoading,
    tripReplanning,
    replanningDays,
    expandedDays,
    showDevPanels,
    telemetry,
    telemetryLoading,
    telemetryError,
    itineraryMapPois,
    itineraryRoutes,
    itineraryWeatherForecasts,
    reservationAlerts,
    reservationCoverageSummary,
    reservationCoverageItems,
    dayReadinessSummary,
    dayReadinessItems,
    paceLabel,
    budgetLabel,
  },
  noticeModal,
);
const { setupViewEvents, resultViewEvents, notificationEvents } = usePlannerAppBridge({
  showDevPanels,
  initializePlanner,
  loadSharedTrip,
  loadIntegrationStatus,
  loadPlanningTelemetry,
  resetPlanner,
  submitPlan,
  saveDraft,
  editCurrentTrip,
  exportAs,
  updateTripNotes,
  saveTripNotesAndLocks,
  copyShareLink,
  replanUnlockedDays,
  addReservation,
  removeReservation,
  toggleDay,
  toggleTripDayLock,
  replanDay,
  closeNotice,
});
</script>
<template>
  <div class="min-h-screen bg-[#eef4f9] text-ink">
    <div class="mx-auto max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8">
      <section
        v-if="!result"
      >
        <PlannerSetupView
          v-bind="setupViewProps"
          v-on="setupViewEvents"
          v-model:start-date="startDate"
          v-model:end-date="endDate"
          v-model:must-visit-text="mustVisitText"
          v-model:dining-text="diningText"
        />
      </section>
      <section v-else ref="exportRoot">
        <PlannerResultView
          v-bind="resultViewProps"
          v-on="resultViewEvents"
        />
      </section>
    </div>
  </div>
  <NotificationModal
    v-bind="noticeModalProps"
    v-on="notificationEvents"
  />
</template>
