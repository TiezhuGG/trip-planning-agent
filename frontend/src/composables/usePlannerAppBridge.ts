import { onMounted } from "vue";

import type {
  CalendarExportScope,
  PlanningJobSummary,
  ReservationItem,
  TripWorkspaceVersionSummary,
} from "../types/planning";
import type { DayGapRepairPayload, DayGapType } from "./useTripWorkspaceInsights";

type BatchVersionAction = "star" | "unstar" | "archive" | "unarchive";

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
  "create-trip-version-snapshot": (versionLabel: string) => void;
  "delete-trip-version": (version: number) => void;
  "restore-trip-version": (version: number) => void;
  "save-trip-version-label": (version: number, versionLabel: string) => void;
  "toggle-trip-version-star": (version: TripWorkspaceVersionSummary) => void;
  "toggle-trip-version-archive": (version: TripWorkspaceVersionSummary) => void;
  "batch-trip-version-update": (
    versions: TripWorkspaceVersionSummary[],
    action: BatchVersionAction,
  ) => void;
  "load-more-trip-versions": () => void;
  "load-all-trip-versions": () => void;
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
  createWorkspaceVersionSnapshot: (versionLabel: string) => void;
  deleteWorkspaceVersion: (version: number) => void;
  restoreWorkspaceVersion: (version: number) => void;
  saveWorkspaceVersionLabel: (version: number, versionLabel: string) => void;
  toggleWorkspaceVersionStar: (version: TripWorkspaceVersionSummary) => void;
  toggleWorkspaceVersionArchive: (version: TripWorkspaceVersionSummary) => void;
  batchUpdateWorkspaceVersions: (
    versions: TripWorkspaceVersionSummary[],
    action: BatchVersionAction,
  ) => Promise<void>;
  loadTripVersions: (
    tripId?: string,
    limit?: number,
    options?: { offset?: number; append?: boolean },
  ) => Promise<void>;
  currentTripId: () => string | undefined;
  currentTripVersionCount: () => number;
  hasMoreTripVersions: () => boolean;
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
    "create-trip-version-snapshot": options.createWorkspaceVersionSnapshot,
    "delete-trip-version": options.deleteWorkspaceVersion,
    "restore-trip-version": options.restoreWorkspaceVersion,
    "save-trip-version-label": options.saveWorkspaceVersionLabel,
    "toggle-trip-version-star": options.toggleWorkspaceVersionStar,
    "toggle-trip-version-archive": options.toggleWorkspaceVersionArchive,
    "batch-trip-version-update": options.batchUpdateWorkspaceVersions,
    "load-more-trip-versions": () =>
      options.loadTripVersions(options.currentTripId?.(), 12, {
        offset: options.currentTripVersionCount(),
        append: true,
      }),
    "load-all-trip-versions": async () => {
      while (options.hasMoreTripVersions()) {
        const previousCount = options.currentTripVersionCount();
        await options.loadTripVersions(options.currentTripId?.(), 12, {
          offset: previousCount,
          append: true,
        });
        if (options.currentTripVersionCount() === previousCount) {
          break;
        }
      }
    },
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
