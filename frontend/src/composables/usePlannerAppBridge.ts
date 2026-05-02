import { onMounted } from "vue";

import type { CalendarExportScope, PlanningJobSummary, ReservationItem } from "../types/planning";
import type { DayGapRepairPayload, DayGapType } from "./useTripWorkspaceInsights";

type InitializePlannerFn = (args: {
  showDevPanels: boolean;
  loadSharedTrip: (shareToken: string) => Promise<unknown>;
  loadRecentTrips: () => Promise<unknown>;
  loadIntegrationStatus: (forceRefresh?: boolean) => Promise<unknown>;
  loadPlanningTelemetry: () => Promise<unknown>;
}) => void;

type SetupViewEvents = {
  reset: () => void;
  submit: () => void;
  "dismiss-local-draft": () => void;
  "open-recent-trip": (tripId: string) => void;
  "save-draft": () => void;
  "refresh-recent-trips": () => void;
  "refresh-integration": () => void;
  "refresh-telemetry": () => void;
};

type ResultViewEvents = {
  "edit-current-trip": () => void;
  reset: () => void;
  export: (format: "png" | "pdf") => void;
  "export-calendar": (scope: CalendarExportScope) => void;
  "update:notes": (value: string) => void;
  "save-notes": () => void;
  "copy-share": () => void;
  "revoke-share": () => void;
  "regenerate-share": () => void;
  "replan-trip": () => void;
  "focus-workspace-days": (dayNumbers: number[]) => void;
  "clear-workspace-focus": () => void;
  "refresh-precheck": () => void;
  "add-reservation": (value: Omit<ReservationItem, "id">) => void;
  "remove-reservation": (id: string) => void;
  "toggle-day": (dayNumber: number) => void;
  "toggle-lock": (dayNumber: number) => void;
  "replan-day": (dayNumber: number) => void;
  "repair-day-gap": (payload: DayGapRepairPayload) => void;
  "retry-planning-job": (job: PlanningJobSummary) => void;
  "refresh-telemetry": () => void;
};

export function usePlannerAppBridge(options: {
  showDevPanels: boolean;
  initializePlanner: InitializePlannerFn;
  loadSharedTrip: (shareToken: string) => Promise<unknown>;
  loadRecentTrips: () => Promise<unknown>;
  loadIntegrationStatus: (forceRefresh?: boolean) => Promise<unknown>;
  loadPlanningTelemetry: () => Promise<unknown>;
  resetPlanner: () => void;
  submitPlan: () => void;
  saveDraft: () => void;
  openRecentTrip: (tripId: string) => void;
  editCurrentTrip: () => void;
  exportAs: (format: "png" | "pdf") => void;
  updateTripNotes: (value: string) => void;
  saveTripNotesAndLocks: () => void;
  copyShareLink: () => void;
  revokeShareLink: () => void;
  regenerateShareLink: () => void;
  exportCalendarFile: (scope?: CalendarExportScope) => void;
  replanUnlockedDays: () => void;
  focusWorkspaceDays: (dayNumbers: number[]) => void;
  clearWorkspaceFocus: () => void;
  refreshDeparturePrecheck: () => void;
  retryRecentPlanningJob: (job: PlanningJobSummary) => Promise<void>;
  addReservation: (value: Omit<ReservationItem, "id">) => void;
  removeReservation: (id: string) => void;
  toggleDay: (dayNumber: number) => void;
  toggleTripDayLock: (dayNumber: number) => void;
  replanDay: (dayNumber: number) => void;
  repairDayGap: (
    dayNumber: number,
    gapType: DayGapType,
    options?: { reasonOverride?: string; actionLabelOverride?: string },
  ) => void;
  closeNotice: () => void;
  dismissLocalDraftNotice: () => void;
}) {
  const refreshIntegration = () => options.loadIntegrationStatus(true);

  const setupViewEvents: SetupViewEvents = {
    reset: options.resetPlanner,
    submit: options.submitPlan,
    "dismiss-local-draft": options.dismissLocalDraftNotice,
    "open-recent-trip": options.openRecentTrip,
    "save-draft": options.saveDraft,
    "refresh-recent-trips": options.loadRecentTrips,
    "refresh-integration": refreshIntegration,
    "refresh-telemetry": options.loadPlanningTelemetry,
  };

  const resultViewEvents: ResultViewEvents = {
    "edit-current-trip": options.editCurrentTrip,
    reset: options.resetPlanner,
    export: options.exportAs,
    "export-calendar": (scope) => options.exportCalendarFile(scope),
    "update:notes": options.updateTripNotes,
    "save-notes": options.saveTripNotesAndLocks,
    "copy-share": options.copyShareLink,
    "revoke-share": options.revokeShareLink,
    "regenerate-share": options.regenerateShareLink,
    "replan-trip": options.replanUnlockedDays,
    "focus-workspace-days": options.focusWorkspaceDays,
    "clear-workspace-focus": options.clearWorkspaceFocus,
    "refresh-precheck": options.refreshDeparturePrecheck,
    "retry-planning-job": options.retryRecentPlanningJob,
    "add-reservation": options.addReservation,
    "remove-reservation": options.removeReservation,
    "toggle-day": options.toggleDay,
    "toggle-lock": options.toggleTripDayLock,
    "replan-day": options.replanDay,
    "repair-day-gap": ({ dayNumber, gapType, reasonOverride, actionLabelOverride }) =>
      options.repairDayGap(dayNumber, gapType, {
        reasonOverride,
        actionLabelOverride,
      }),
    "refresh-telemetry": options.loadPlanningTelemetry,
  };

  const notificationEvents = {
    close: options.closeNotice,
  };

  onMounted(() => {
    options.initializePlanner({
      showDevPanels: options.showDevPanels,
      loadSharedTrip: options.loadSharedTrip,
      loadRecentTrips: options.loadRecentTrips,
      loadIntegrationStatus: options.loadIntegrationStatus,
      loadPlanningTelemetry: options.loadPlanningTelemetry,
    });
  });

  return {
    setupViewEvents,
    resultViewEvents,
    notificationEvents,
  };
}
