import { onMounted } from "vue";

import type { ReservationItem } from "../types/planning";

type InitializePlannerFn = (args: {
  showDevPanels: boolean;
  loadSharedTrip: (shareToken: string) => Promise<unknown>;
  loadIntegrationStatus: (forceRefresh?: boolean) => Promise<unknown>;
  loadPlanningTelemetry: () => Promise<unknown>;
}) => void;

type SetupViewEvents = {
  reset: () => void;
  submit: () => void;
  "save-draft": () => void;
  "refresh-integration": () => void;
  "refresh-telemetry": () => void;
};

type ResultViewEvents = {
  "edit-current-trip": () => void;
  reset: () => void;
  export: (format: "png" | "pdf") => void;
  "update:notes": (value: string) => void;
  "save-notes": () => void;
  "copy-share": () => void;
  "replan-trip": () => void;
  "add-reservation": (value: Omit<ReservationItem, "id" | "created_at">) => void;
  "remove-reservation": (id: string) => void;
  "toggle-day": (dayNumber: number) => void;
  "toggle-lock": (dayNumber: number) => void;
  "replan-day": (dayNumber: number) => void;
  "refresh-telemetry": () => void;
};

export function usePlannerAppBridge(options: {
  showDevPanels: boolean;
  initializePlanner: InitializePlannerFn;
  loadSharedTrip: (shareToken: string) => Promise<unknown>;
  loadIntegrationStatus: (forceRefresh?: boolean) => Promise<unknown>;
  loadPlanningTelemetry: () => Promise<unknown>;
  resetPlanner: () => void;
  submitPlan: () => void;
  saveDraft: () => void;
  editCurrentTrip: () => void;
  exportAs: (format: "png" | "pdf") => void;
  updateTripNotes: (value: string) => void;
  saveTripNotesAndLocks: () => void;
  copyShareLink: () => void;
  replanUnlockedDays: () => void;
  addReservation: (value: Omit<ReservationItem, "id" | "created_at">) => void;
  removeReservation: (id: string) => void;
  toggleDay: (dayNumber: number) => void;
  toggleTripDayLock: (dayNumber: number) => void;
  replanDay: (dayNumber: number) => void;
  closeNotice: () => void;
}) {
  const refreshIntegration = () => options.loadIntegrationStatus(true);

  const setupViewEvents: SetupViewEvents = {
    reset: options.resetPlanner,
    submit: options.submitPlan,
    "save-draft": options.saveDraft,
    "refresh-integration": refreshIntegration,
    "refresh-telemetry": options.loadPlanningTelemetry,
  };

  const resultViewEvents: ResultViewEvents = {
    "edit-current-trip": options.editCurrentTrip,
    reset: options.resetPlanner,
    export: options.exportAs,
    "update:notes": options.updateTripNotes,
    "save-notes": options.saveTripNotesAndLocks,
    "copy-share": options.copyShareLink,
    "replan-trip": options.replanUnlockedDays,
    "add-reservation": options.addReservation,
    "remove-reservation": options.removeReservation,
    "toggle-day": options.toggleDay,
    "toggle-lock": options.toggleTripDayLock,
    "replan-day": options.replanDay,
    "refresh-telemetry": options.loadPlanningTelemetry,
  };

  const notificationEvents = {
    close: options.closeNotice,
  };

  onMounted(() => {
    options.initializePlanner({
      showDevPanels: options.showDevPanels,
      loadSharedTrip: options.loadSharedTrip,
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
