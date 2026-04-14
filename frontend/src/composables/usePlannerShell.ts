import { reactive, type Ref } from "vue";

import type {
  IntegrationStatus,
  PlanningResponse,
  TripPlanningRequest,
  TripWorkspace,
} from "../types/planning";
import { applyRequestToFormState } from "../utils/tripPlannerForm";

type NoticeTone = "success" | "warning" | "error";

type NoticeModalState = {
  open: boolean;
  tone: NoticeTone;
  title: string;
  messages: string[];
};

type PlannerOption<T> = {
  label: string;
  value: T;
};

export function usePlannerShell(options: {
  form: TripPlanningRequest;
  currentTrip: Ref<TripWorkspace | null>;
  result: Ref<PlanningResponse | null>;
  tripNotes: Ref<string>;
  draftSaving: Ref<boolean>;
  tripReplanning: Ref<boolean>;
  replanningDays: Ref<number[]>;
  expandedDays: Ref<number[]>;
  integrationStatus: Ref<IntegrationStatus>;
  startDate: Ref<string>;
  endDate: Ref<string>;
  mustVisitText: Ref<string>;
  diningText: Ref<string>;
  paceOptions: PlannerOption<TripPlanningRequest["pace"]>[];
  budgetOptions: PlannerOption<TripPlanningRequest["budget_level"]>[];
}) {
  const {
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
    paceOptions,
    budgetOptions,
  } = options;

  const noticeModal = reactive<NoticeModalState>({
    open: false,
    tone: "warning",
    title: "",
    messages: [],
  });

  function openNotice(tone: NoticeTone, title: string, messages: string[]) {
    if (!messages.length) return;
    noticeModal.tone = tone;
    noticeModal.title = title;
    noticeModal.messages = [...new Set(messages.filter(Boolean))];
    noticeModal.open = true;
  }

  function closeNotice() {
    noticeModal.open = false;
    noticeModal.tone = "warning";
    noticeModal.title = "";
    noticeModal.messages = [];
  }

  function syncTripQuery(shareToken?: string | null) {
    const url = new URL(window.location.href);
    if (shareToken) url.searchParams.set("trip", shareToken);
    else url.searchParams.delete("trip");
    window.history.replaceState({}, "", url.toString());
  }

  function applyWorkspace(workspace: TripWorkspace, config: { syncUrl?: boolean } = {}) {
    currentTrip.value = workspace;
    tripNotes.value = workspace.manual_notes ?? "";
    result.value = workspace.response_snapshot ?? null;
    if (workspace.response_snapshot) {
      integrationStatus.value = workspace.response_snapshot.integration_status;
    }
    applyRequestToFormState({
      form,
      request: workspace.request_brief,
      startDate,
      endDate,
      mustVisitText,
      diningText,
    });
    if (config.syncUrl !== false) {
      syncTripQuery(workspace.share_token);
    }
  }

  function updateTripNotes(value: string) {
    tripNotes.value = value;
  }

  function toggleSelection(list: string[], value: string) {
    const index = list.indexOf(value);
    if (index >= 0) list.splice(index, 1);
    else list.push(value);
  }

  function initializePlanner(options: {
    showDevPanels: boolean;
    loadSharedTrip: (shareToken: string) => Promise<unknown>;
    loadIntegrationStatus: (refresh?: boolean) => Promise<unknown>;
    loadPlanningTelemetry: () => Promise<unknown>;
  }) {
    const startupTasks: Promise<unknown>[] = [];
    const shareToken = new URLSearchParams(window.location.search).get("trip");
    if (shareToken) startupTasks.push(options.loadSharedTrip(shareToken));
    if (options.showDevPanels) {
      startupTasks.push(
        options.loadIntegrationStatus(),
        options.loadPlanningTelemetry(),
      );
    }
    if (startupTasks.length) {
      void Promise.all(startupTasks);
    }
  }

  function editCurrentTrip() {
    result.value = null;
    replanningDays.value = [];
    tripReplanning.value = false;
    expandedDays.value = [];
  }

  function resetPlanner() {
    result.value = null;
    currentTrip.value = null;
    tripNotes.value = "";
    draftSaving.value = false;
    replanningDays.value = [];
    tripReplanning.value = false;
    expandedDays.value = [];
    syncTripQuery(null);
  }

  function toggleDay(dayNumber: number) {
    expandedDays.value = expandedDays.value.includes(dayNumber)
      ? expandedDays.value.filter((item) => item !== dayNumber)
      : [...expandedDays.value, dayNumber];
  }

  function paceLabel(value: TripPlanningRequest["pace"]) {
    return paceOptions.find((item) => item.value === value)?.label ?? value;
  }

  function budgetLabel(value: TripPlanningRequest["budget_level"]) {
    return budgetOptions.find((item) => item.value === value)?.label ?? value;
  }

  return {
    noticeModal,
    openNotice,
    closeNotice,
    syncTripQuery,
    applyWorkspace,
    updateTripNotes,
    toggleSelection,
    initializePlanner,
    editCurrentTrip,
    resetPlanner,
    toggleDay,
    paceLabel,
    budgetLabel,
  };
}
