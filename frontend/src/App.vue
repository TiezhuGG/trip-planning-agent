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
  usePlannerPageState,
  plannerPaceOptions,
  plannerStageOptions,
  plannerTransportOptions,
} from "./composables/usePlannerPageState";
import { usePlannerShell } from "./composables/usePlannerShell";
import { usePlannerSubmission } from "./composables/usePlannerSubmission";
import { usePlannerViewModels } from "./composables/usePlannerViewModels";
import { usePlanningSupport } from "./composables/usePlanningSupport";
import { useTripWorkspaceActions } from "./composables/useTripWorkspaceActions";
import { useTripWorkspaceInsights } from "./composables/useTripWorkspaceInsights";
import { isChineseCityName, splitText } from "./utils/tripPlannerForm";
import type { TripWorkspaceVersionSummary } from "./types/planning";

const showDevPanels = import.meta.env.DEV;

const {
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
  restoringTripVersion,
  savingTripVersionLabel,
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
  tripVersions,
  tripVersionsError,
  tripVersionsHasMore,
  tripVersionsLoading,
  retryingPlanningJobId,
  workspaceBusyMessage,
} = usePlannerPageState();

const { startDate, endDate } = usePlannerDateRange(form);

const plannerShell = usePlannerShell({
  form,
  currentTrip,
  result,
  tripNotes,
  draftSaving,
  tripReplanning,
  replanningDays,
  expandedDays,
  focusedWorkspaceDays,
  integrationStatus,
  startDate,
  endDate,
  mustVisitText,
  diningText,
  paceOptions: plannerPaceOptions,
  budgetOptions: plannerBudgetOptions,
});

const planningSupport = usePlanningSupport({
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
  openNotice: plannerShell.openNotice,
});

const derivedState = usePlannerDerivedState({
  form,
  result,
  currentTrip,
  integrationStatus,
  startDate,
  endDate,
  mustVisitText,
  diningText,
  paceLabel: plannerShell.paceLabel,
  budgetLabel: plannerShell.budgetLabel,
});

const workspaceActions = useTripWorkspaceActions({
  currentTrip,
  tripNotes,
  tripSaving,
  tripLoading,
  tripPrechecking,
  tripReplanning,
  workspaceBusyMessage,
  retryingPlanningJobId,
  draftSaving,
  recentPlanningJobs,
  recentPlanningJobsLoading,
  recentPlanningJobsError,
  tripVersions,
  tripVersionsLoading,
  tripVersionsError,
  tripVersionsHasMore,
  restoringTripVersion,
  savingTripVersionLabel,
  recentTrips,
  recentTripsLoading,
  recentTripsError,
  replanningDays,
  shareLink: derivedState.shareLink,
  form,
  mustVisitText,
  diningText,
  showDevPanels,
  applyWorkspace: plannerShell.applyWorkspace,
  openNotice: plannerShell.openNotice,
  syncTripQuery: plannerShell.syncTripQuery,
  isChineseCityName,
  splitText,
});

const plannerSubmission = usePlannerSubmission({
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
  syncTripQuery: plannerShell.syncTripQuery,
  openNotice: plannerShell.openNotice,
  startProgress: planningSupport.startProgress,
  stopProgress: planningSupport.stopProgress,
  setProgressMessage: planningSupport.setProgressMessage,
  buildPlanNotices: planningSupport.buildPlanNotices,
  toUserError: planningSupport.toUserError,
  persistWorkspaceFromResponse: workspaceActions.persistWorkspaceFromResponse,
  saveWorkspacePatch: workspaceActions.saveWorkspacePatch,
  loadPlanningTelemetry: planningSupport.loadPlanningTelemetry,
});

const workspaceInsights = useTripWorkspaceInsights({
  currentTrip,
  result,
});

const { setupViewProps, resultViewProps, noticeModalProps } = usePlannerViewModels(
  {
    summaryTags: derivedState.summaryTags,
    isEditingWorkspace: derivedState.isEditingWorkspace,
    localDraftRestored: plannerShell.localDraftRestored,
    localDraftSavedAt: plannerShell.localDraftSavedAt,
    currentTrip,
    form,
    plannerInterestOptions,
    plannerTransportOptions,
    plannerHotelOptions,
    plannerPaceOptions,
    plannerBudgetOptions,
    showDevPanels,
    inputSummary: derivedState.inputSummary,
    progress,
    progressLabel,
    loading,
    draftSaving,
    recentTrips,
    recentTripsLoading,
    recentTripsError,
    planningChecks: derivedState.planningChecks,
    canSaveDraft: derivedState.canSaveDraft,
    canSubmit: derivedState.canSubmit,
    saveDraftHint: derivedState.saveDraftHint,
    submitHint: derivedState.submitHint,
    currentIntegrationStatus: derivedState.currentIntegrationStatus,
    integrationLoading,
    telemetry,
    telemetryLoading,
    telemetryError,
    paceLabel: plannerShell.paceLabel,
    toggleSelection: plannerShell.toggleSelection,
  },
  {
    result,
    currentTrip,
    tripNotes,
    shareLink: derivedState.shareLink,
    tripSaving,
    retryingPlanningJobId,
    workspaceBusyMessage,
    tripLoading,
    tripPrechecking,
    tripReplanning,
    recentPlanningJobs,
    recentPlanningJobsLoading,
    recentPlanningJobsError,
    tripVersions,
    tripVersionsLoading,
    tripVersionsError,
    tripVersionsHasMore,
    restoringTripVersion,
    savingTripVersionLabel,
    replanningDays,
    expandedDays,
    focusedWorkspaceDays,
    showDevPanels,
    telemetry,
    telemetryLoading,
    telemetryError,
    itineraryMapPois: derivedState.itineraryMapPois,
    itineraryRoutes: derivedState.itineraryRoutes,
    itineraryWeatherForecasts: derivedState.itineraryWeatherForecasts,
    reservationAlerts: workspaceInsights.reservationAlerts,
    reservationCoverageSummary: workspaceInsights.reservationCoverageSummary,
    reservationCoverageItems: workspaceInsights.reservationCoverageItems,
    dayReadinessSummary: workspaceInsights.dayReadinessSummary,
    dayReadinessItems: workspaceInsights.dayReadinessItems,
    departurePrecheckSummary: workspaceInsights.departurePrecheckSummary,
    departurePrecheckItems: workspaceInsights.departurePrecheckItems,
    paceLabel: plannerShell.paceLabel,
    budgetLabel: plannerShell.budgetLabel,
  },
  plannerShell.noticeModal,
);

const { notificationEvents, resultViewEvents, setupViewEvents } = usePlannerAppBridge({
  showDevPanels,
  initializePlanner: plannerShell.initializePlanner,
  loadSharedTrip: workspaceActions.loadSharedTrip,
  loadRecentTrips: workspaceActions.loadRecentTrips,
  loadIntegrationStatus: planningSupport.loadIntegrationStatus,
  loadPlanningTelemetry: planningSupport.loadPlanningTelemetry,
  resetPlanner: plannerShell.resetPlanner,
  submitPlan: plannerSubmission.submitPlan,
  saveDraft: workspaceActions.saveDraft,
  openRecentTrip: workspaceActions.loadWorkspaceById,
  editCurrentTrip: plannerShell.editCurrentTrip,
  exportAs: planningSupport.exportAs,
  updateTripNotes: plannerShell.updateTripNotes,
  saveTripNotesAndLocks: workspaceActions.saveTripNotesAndLocks,
  copyShareLink: workspaceActions.copyShareLink,
  revokeShareLink: workspaceActions.revokeShareLink,
  regenerateShareLink: workspaceActions.regenerateShareLink,
  exportCalendarFile: workspaceActions.exportCalendarFile,
  replanUnlockedDays: workspaceActions.replanUnlockedDays,
  createWorkspaceVersionSnapshot: workspaceActions.createWorkspaceVersionSnapshot,
  deleteWorkspaceVersion: workspaceActions.deleteWorkspaceVersion,
  loadTripVersions: workspaceActions.loadTripVersions,
  currentTripId: () => currentTrip.value?.id,
  currentTripVersionCount: () => tripVersions.value.length,
  hasMoreTripVersions: () => tripVersionsHasMore.value,
  restoreWorkspaceVersion: workspaceActions.restoreWorkspaceVersion,
  saveWorkspaceVersionLabel: workspaceActions.saveWorkspaceVersionLabel,
  toggleWorkspaceVersionStar: (version: TripWorkspaceVersionSummary) =>
    workspaceActions.saveWorkspaceVersionMeta(version.version, {
      versionLabel: version.version_label,
      isStarred: !version.is_starred,
      isArchived: version.is_archived,
    }),
  toggleWorkspaceVersionArchive: (version: TripWorkspaceVersionSummary) =>
    workspaceActions.saveWorkspaceVersionMeta(version.version, {
      versionLabel: version.version_label,
      isStarred: version.is_starred,
      isArchived: !version.is_archived,
    }),
  batchUpdateWorkspaceVersions: workspaceActions.batchUpdateWorkspaceVersions,
  focusWorkspaceDays: plannerShell.focusWorkspaceDays,
  clearWorkspaceFocus: plannerShell.clearWorkspaceFocus,
  refreshDeparturePrecheck: workspaceActions.refreshDeparturePrecheck,
  retryRecentPlanningJob: workspaceActions.retryRecentPlanningJob,
  addReservation: workspaceActions.addReservation,
  removeReservation: workspaceActions.removeReservation,
  toggleDay: plannerShell.toggleDay,
  toggleTripDayLock: workspaceActions.toggleTripDayLock,
  replanDay: workspaceActions.replanDay,
  repairDayGap: workspaceActions.repairDayGap,
  closeNotice: plannerShell.closeNotice,
  dismissLocalDraftNotice: plannerShell.dismissLocalDraftNotice,
});
</script>

<template>
  <div
    class="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(157,196,228,0.32),_transparent_36%),linear-gradient(180deg,_#eff5fa_0%,_#f8fbfd_52%,_#edf3f8_100%)] text-slate-900"
  >
    <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <PlannerSetupView
        v-if="!result"
        v-bind="setupViewProps"
        v-model:start-date="startDate"
        v-model:end-date="endDate"
        v-model:must-visit-text="mustVisitText"
        v-model:dining-text="diningText"
        @reset="setupViewEvents.reset"
        @submit="setupViewEvents.submit"
        @dismiss-local-draft="setupViewEvents['dismiss-local-draft']"
        @open-recent-trip="setupViewEvents['open-recent-trip']"
        @save-draft="setupViewEvents['save-draft']"
        @refresh-recent-trips="setupViewEvents['refresh-recent-trips']"
        @refresh-integration="setupViewEvents['refresh-integration']"
        @refresh-telemetry="setupViewEvents['refresh-telemetry']"
      />

      <div v-else ref="exportRoot">
        <PlannerResultView
          v-bind="resultViewProps"
          @edit-current-trip="resultViewEvents['edit-current-trip']"
          @reset="resultViewEvents.reset"
          @export="resultViewEvents.export"
          @export-calendar="resultViewEvents['export-calendar']"
          @update:notes="resultViewEvents['update:notes']"
          @save-notes="resultViewEvents['save-notes']"
          @copy-share="resultViewEvents['copy-share']"
          @revoke-share="resultViewEvents['revoke-share']"
          @regenerate-share="resultViewEvents['regenerate-share']"
          @replan-trip="resultViewEvents['replan-trip']"
          @create-trip-version-snapshot="resultViewEvents['create-trip-version-snapshot']"
          @delete-trip-version="resultViewEvents['delete-trip-version']"
          @restore-trip-version="resultViewEvents['restore-trip-version']"
          @save-trip-version-label="resultViewEvents['save-trip-version-label']"
          @toggle-trip-version-star="resultViewEvents['toggle-trip-version-star']"
          @toggle-trip-version-archive="resultViewEvents['toggle-trip-version-archive']"
          @batch-trip-version-update="resultViewEvents['batch-trip-version-update']"
          @load-more-trip-versions="resultViewEvents['load-more-trip-versions']"
          @load-all-trip-versions="resultViewEvents['load-all-trip-versions']"
          @focus-workspace-days="resultViewEvents['focus-workspace-days']"
          @clear-workspace-focus="resultViewEvents['clear-workspace-focus']"
          @refresh-precheck="resultViewEvents['refresh-precheck']"
          @retry-planning-job="resultViewEvents['retry-planning-job']"
          @add-reservation="resultViewEvents['add-reservation']"
          @remove-reservation="resultViewEvents['remove-reservation']"
          @toggle-day="resultViewEvents['toggle-day']"
          @toggle-lock="resultViewEvents['toggle-lock']"
          @replan-day="resultViewEvents['replan-day']"
          @repair-day-gap="resultViewEvents['repair-day-gap']"
          @refresh-telemetry="resultViewEvents['refresh-telemetry']"
        />
      </div>
    </main>

    <NotificationModal
      v-bind="noticeModalProps"
      @close="notificationEvents.close"
    />
  </div>
</template>
