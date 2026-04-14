import { computed, type Ref } from "vue";

import type {
  DailyForecast,
  DayPOI,
  IntegrationStatus,
  PlanningResponse,
  PlanningTelemetry,
  RouteSummary,
  TripPlanningRequest,
  TripWorkspace,
} from "../types/planning";
import type {
  DayReadinessItem,
  DayReadinessSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "./useTripWorkspaceInsights";

type NoticeModalState = {
  open: boolean;
  tone: "success" | "warning" | "error";
  title: string;
  messages: string[];
};

type SummaryItem = { label: string; value: string };

type SetupViewModelOptions = {
  summaryTags: Ref<string[]>;
  isEditingWorkspace: Ref<boolean>;
  currentTrip: Ref<TripWorkspace | null>;
  form: TripPlanningRequest;
  plannerInterestOptions: string[];
  plannerTransportOptions: string[];
  plannerHotelOptions: string[];
  plannerPaceOptions: Array<{ label: string; value: TripPlanningRequest["pace"] }>;
  plannerBudgetOptions: Array<{ label: string; value: TripPlanningRequest["budget_level"] }>;
  showDevPanels: boolean;
  inputSummary: Ref<SummaryItem[]>;
  progress: Ref<number>;
  progressLabel: Ref<string>;
  loading: Ref<boolean>;
  draftSaving: Ref<boolean>;
  destinationValid: Ref<boolean>;
  currentIntegrationStatus: Ref<IntegrationStatus>;
  integrationLoading: Ref<boolean>;
  telemetry: Ref<PlanningTelemetry>;
  telemetryLoading: Ref<boolean>;
  telemetryError: Ref<string>;
  paceLabel: (value: TripPlanningRequest["pace"]) => string;
  toggleSelection: (list: string[], value: string) => void;
};

type ResultViewModelOptions = {
  result: Ref<PlanningResponse | null>;
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  shareLink: Ref<string>;
  tripSaving: Ref<boolean>;
  tripLoading: Ref<boolean>;
  tripReplanning: Ref<boolean>;
  replanningDays: Ref<number[]>;
  expandedDays: Ref<number[]>;
  showDevPanels: boolean;
  telemetry: Ref<PlanningTelemetry>;
  telemetryLoading: Ref<boolean>;
  telemetryError: Ref<string>;
  itineraryMapPois: Ref<DayPOI[]>;
  itineraryRoutes: Ref<RouteSummary[]>;
  itineraryWeatherForecasts: Ref<DailyForecast[]>;
  reservationAlerts: Ref<string[]>;
  reservationCoverageSummary: Ref<ReservationCoverageSummary>;
  reservationCoverageItems: Ref<ReservationCoverageItem[]>;
  dayReadinessSummary: Ref<DayReadinessSummary>;
  dayReadinessItems: Ref<DayReadinessItem[]>;
  paceLabel: (value: PlanningResponse["request_echo"]["pace"]) => string;
  budgetLabel: (value: PlanningResponse["request_echo"]["budget_level"]) => string;
};

export function usePlannerViewModels(
  setupOptions: SetupViewModelOptions,
  resultOptions: ResultViewModelOptions,
  noticeModal: NoticeModalState,
) {
  const setupViewProps = computed(() => ({
    summaryTags: setupOptions.summaryTags.value,
    isEditingWorkspace: setupOptions.isEditingWorkspace.value,
    editingTripVersion: setupOptions.currentTrip.value?.version ?? null,
    form: setupOptions.form,
    interestOptions: setupOptions.plannerInterestOptions,
    transportOptions: setupOptions.plannerTransportOptions,
    hotelOptions: setupOptions.plannerHotelOptions,
    paceOptions: setupOptions.plannerPaceOptions,
    budgetOptions: setupOptions.plannerBudgetOptions,
    showDevPanels: setupOptions.showDevPanels,
    inputSummary: setupOptions.inputSummary.value,
    progress: setupOptions.progress.value,
    progressLabel: setupOptions.progressLabel.value,
    loading: setupOptions.loading.value,
    draftSaving: setupOptions.draftSaving.value,
    destinationValid: setupOptions.destinationValid.value,
    currentIntegrationStatus: setupOptions.currentIntegrationStatus.value,
    integrationLoading: setupOptions.integrationLoading.value,
    telemetry: setupOptions.telemetry.value,
    telemetryLoading: setupOptions.telemetryLoading.value,
    telemetryError: setupOptions.telemetryError.value,
    paceLabel: setupOptions.paceLabel,
    toggleSelection: setupOptions.toggleSelection,
  }));

  const resultViewProps = computed(() => ({
    result: resultOptions.result.value!,
    currentTrip: resultOptions.currentTrip.value,
    tripNotes: resultOptions.tripNotes.value,
    shareLink: resultOptions.shareLink.value,
    tripSaving: resultOptions.tripSaving.value,
    tripLoading: resultOptions.tripLoading.value,
    tripReplanning: resultOptions.tripReplanning.value,
    replanningDays: resultOptions.replanningDays.value,
    expandedDays: resultOptions.expandedDays.value,
    showDevPanels: resultOptions.showDevPanels,
    telemetry: resultOptions.telemetry.value,
    telemetryLoading: resultOptions.telemetryLoading.value,
    telemetryError: resultOptions.telemetryError.value,
    itineraryMapPois: resultOptions.itineraryMapPois.value,
    itineraryRoutes: resultOptions.itineraryRoutes.value,
    itineraryWeatherForecasts: resultOptions.itineraryWeatherForecasts.value,
    reservationAlerts: resultOptions.reservationAlerts.value,
    reservationCoverageSummary: resultOptions.reservationCoverageSummary.value,
    reservationCoverageItems: resultOptions.reservationCoverageItems.value,
    dayReadinessSummary: resultOptions.dayReadinessSummary.value,
    dayReadinessItems: resultOptions.dayReadinessItems.value,
    paceLabel: resultOptions.paceLabel,
    budgetLabel: resultOptions.budgetLabel,
  }));

  const noticeModalProps = computed(() => ({
    open: noticeModal.open,
    tone: noticeModal.tone,
    title: noticeModal.title,
    messages: noticeModal.messages,
  }));

  return {
    setupViewProps,
    resultViewProps,
    noticeModalProps,
  };
}
