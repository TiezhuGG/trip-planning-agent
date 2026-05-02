import { reactive, ref, watch, type Ref } from "vue";

import type {
  IntegrationStatus,
  PlanningResponse,
  TripPlanningRequest,
  TripWorkspace,
} from "../types/planning";
import { createInitialTripPlanningRequest } from "./plannerPageOptions";
import { addDays, applyRequestToFormState } from "../utils/tripPlannerForm";
import { sortUniqueNumbers } from "../utils/workspaceFormatting";

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

const PLANNER_LOCAL_DRAFT_STORAGE_KEY = "planner-setup-local-draft";

type PlannerLocalDraft = {
  request: TripPlanningRequest;
  startDate: string;
  endDate: string;
  mustVisitText: string;
  diningText: string;
  updatedAt: string;
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
  focusedWorkspaceDays: Ref<number[]>;
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
    focusedWorkspaceDays,
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
  const localDraftRestored = ref(false);
  const localDraftSavedAt = ref("");
  const initialRequest = createInitialTripPlanningRequest();
  const initialEndDate = addDays(initialRequest.start_date, initialRequest.days - 1);

  watch(
    () => ({
      origin: form.origin ?? "",
      destination: form.destination,
      startDate: startDate.value,
      endDate: endDate.value,
      days: form.days,
      interests: [...form.interests],
      pace: form.pace,
      budgetLevel: form.budget_level,
      transportPreferences: [...form.transport_preferences],
      hotelStyle: form.hotel_style,
      travelers: { ...form.travelers },
      notes: form.notes ?? "",
      mustVisitText: mustVisitText.value,
      diningText: diningText.value,
      currentTripId: currentTrip.value?.id ?? "",
      hasResult: Boolean(result.value),
    }),
    (snapshot) => {
      if (snapshot.currentTripId || snapshot.hasResult) {
        clearLocalPlannerDraft();
        return;
      }
      if (isPristinePlannerState()) {
        clearLocalPlannerDraft();
        return;
      }

      persistLocalPlannerDraft({
        request: {
          origin: form.origin ?? "",
          destination: form.destination,
          start_date: form.start_date,
          days: form.days,
          interests: [...form.interests],
          must_visit: [...form.must_visit],
          pace: form.pace,
          budget_level: form.budget_level,
          transport_preferences: [...form.transport_preferences],
          hotel_style: form.hotel_style,
          dining_preferences: [...form.dining_preferences],
          travelers: { ...form.travelers },
          notes: form.notes ?? "",
        },
        startDate: startDate.value,
        endDate: endDate.value,
        mustVisitText: mustVisitText.value,
        diningText: diningText.value,
        updatedAt: new Date().toISOString(),
      });
    },
    { deep: true },
  );

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

  function applyWorkspace(
    workspace: TripWorkspace,
    config: { syncUrl?: boolean; focusDayNumbers?: number[] } = {},
  ) {
    clearLocalPlannerDraft();
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
    const focusDayNumbers = sortUniqueNumbers(config.focusDayNumbers ?? []);
    focusedWorkspaceDays.value = focusDayNumbers;
    if (focusDayNumbers.length) {
      expandedDays.value = sortUniqueNumbers([...expandedDays.value, ...focusDayNumbers]);
    }
    if (config.syncUrl !== false) {
      syncTripQuery(workspace.share_enabled ? workspace.share_token : null);
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
    loadRecentTrips: () => Promise<unknown>;
    loadIntegrationStatus: (refresh?: boolean) => Promise<unknown>;
    loadPlanningTelemetry: () => Promise<unknown>;
  }) {
    const startupTasks: Promise<unknown>[] = [];
    const shareToken = new URLSearchParams(window.location.search).get("trip");
    if (shareToken) startupTasks.push(options.loadSharedTrip(shareToken));
    else restoreLocalPlannerDraft();
    startupTasks.push(options.loadRecentTrips());
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
    focusedWorkspaceDays.value = [];
  }

  function resetPlanner() {
    const initialRequest = createInitialTripPlanningRequest();
    clearLocalPlannerDraft();
    result.value = null;
    currentTrip.value = null;
    tripNotes.value = "";
    draftSaving.value = false;
    replanningDays.value = [];
    tripReplanning.value = false;
    expandedDays.value = [];
    focusedWorkspaceDays.value = [];
    applyRequestToFormState({
      form,
      request: initialRequest,
      startDate,
      endDate,
      mustVisitText,
      diningText,
    });
    syncTripQuery(null);
  }

  function toggleDay(dayNumber: number) {
    expandedDays.value = expandedDays.value.includes(dayNumber)
      ? expandedDays.value.filter((item) => item !== dayNumber)
      : [...expandedDays.value, dayNumber];
  }

  function focusWorkspaceDays(dayNumbers: number[]) {
    const normalized = sortUniqueNumbers(dayNumbers);
    focusedWorkspaceDays.value = normalized;
    if (normalized.length) {
      expandedDays.value = sortUniqueNumbers([...expandedDays.value, ...normalized]);
    }
  }

  function clearWorkspaceFocus() {
    focusedWorkspaceDays.value = [];
  }

  function paceLabel(value: TripPlanningRequest["pace"]) {
    return paceOptions.find((item) => item.value === value)?.label ?? value;
  }

  function budgetLabel(value: TripPlanningRequest["budget_level"]) {
    return budgetOptions.find((item) => item.value === value)?.label ?? value;
  }

  function dismissLocalDraftNotice() {
    localDraftRestored.value = false;
  }

  function persistLocalPlannerDraft(payload: PlannerLocalDraft) {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(PLANNER_LOCAL_DRAFT_STORAGE_KEY, JSON.stringify(payload));
    localDraftSavedAt.value = payload.updatedAt;
  }

  function clearLocalPlannerDraft() {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(PLANNER_LOCAL_DRAFT_STORAGE_KEY);
    localDraftRestored.value = false;
    localDraftSavedAt.value = "";
  }

  function restoreLocalPlannerDraft() {
    if (typeof window === "undefined") return;
    const rawValue = window.localStorage.getItem(PLANNER_LOCAL_DRAFT_STORAGE_KEY);
    if (!rawValue) return;

    try {
      const parsed = JSON.parse(rawValue) as Partial<PlannerLocalDraft>;
      if (!parsed.request) return;
      applyRequestToFormState({
        form,
        request: {
          ...parsed.request,
          origin: parsed.request.origin ?? "",
          destination: parsed.request.destination ?? "",
          start_date: parsed.request.start_date ?? startDate.value,
          days: Math.max(1, Number(parsed.request.days) || 1),
          interests: [...(parsed.request.interests ?? [])],
          must_visit: [...(parsed.request.must_visit ?? [])],
          pace: parsed.request.pace ?? form.pace,
          budget_level: parsed.request.budget_level ?? form.budget_level,
          transport_preferences: [...(parsed.request.transport_preferences ?? [])],
          hotel_style: parsed.request.hotel_style ?? "",
          dining_preferences: [...(parsed.request.dining_preferences ?? [])],
          travelers: {
            adults: Math.max(1, Number(parsed.request.travelers?.adults) || 1),
            children: Math.max(0, Number(parsed.request.travelers?.children) || 0),
            seniors: Math.max(0, Number(parsed.request.travelers?.seniors) || 0),
          },
          notes: parsed.request.notes ?? "",
        },
        startDate,
        endDate,
        mustVisitText,
        diningText,
      });
      if (parsed.startDate) startDate.value = parsed.startDate;
      if (parsed.endDate) endDate.value = parsed.endDate;
      if (typeof parsed.mustVisitText === "string") mustVisitText.value = parsed.mustVisitText;
      if (typeof parsed.diningText === "string") diningText.value = parsed.diningText;
      localDraftRestored.value = true;
      localDraftSavedAt.value = parsed.updatedAt ?? "";
    } catch {
      clearLocalPlannerDraft();
    }
  }

  function isPristinePlannerState() {
    return (
      (form.origin ?? "").trim() === (initialRequest.origin ?? "").trim() &&
      form.destination.trim() === initialRequest.destination &&
      startDate.value === initialRequest.start_date &&
      endDate.value === initialEndDate &&
      form.days === initialRequest.days &&
      JSON.stringify(form.interests) === JSON.stringify(initialRequest.interests) &&
      JSON.stringify(form.transport_preferences) ===
        JSON.stringify(initialRequest.transport_preferences) &&
      form.pace === initialRequest.pace &&
      form.budget_level === initialRequest.budget_level &&
      form.hotel_style === initialRequest.hotel_style &&
      form.travelers.adults === initialRequest.travelers.adults &&
      form.travelers.children === initialRequest.travelers.children &&
      form.travelers.seniors === initialRequest.travelers.seniors &&
      !(form.notes ?? "").trim() &&
      !mustVisitText.value.trim() &&
      !diningText.value.trim()
    );
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
    focusWorkspaceDays,
    clearWorkspaceFocus,
    paceLabel,
    budgetLabel,
    localDraftRestored,
    localDraftSavedAt,
    dismissLocalDraftNotice,
  };
}
