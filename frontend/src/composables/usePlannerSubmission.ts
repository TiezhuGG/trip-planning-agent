import type { Ref } from "vue";

import {
  getPlanningJob,
  startGeneratePlanJob,
} from "../api/planning";
import type {
  IntegrationStatus,
  PlanningResponse,
  TripPlanningRequest,
  TripWorkspace,
} from "../types/planning";
import { humanizePlanningJobProgress, waitForPlanningJob } from "../utils/planningJobs";
import { splitText } from "../utils/tripPlannerForm";
import { buildTripPlanningRequestPayload } from "../utils/tripWorkspacePayloads";

type NoticeTone = "success" | "warning" | "error";

export function usePlannerSubmission(options: {
  form: TripPlanningRequest;
  mustVisitText: Ref<string>;
  diningText: Ref<string>;
  loading: Ref<boolean>;
  result: Ref<PlanningResponse | null>;
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  expandedDays: Ref<number[]>;
  integrationStatus: Ref<IntegrationStatus>;
  showDevPanels: boolean;
  isChineseCityName: (value: string) => boolean;
  syncTripQuery: (shareToken?: string | null) => void;
  openNotice: (tone: NoticeTone, title: string, messages: string[]) => void;
  startProgress: () => void;
  stopProgress: (success?: boolean) => void;
  setProgressMessage: (message: string) => void;
  buildPlanNotices: (response: PlanningResponse) => string[];
  toUserError: (message: string) => string;
  persistWorkspaceFromResponse: (response: PlanningResponse) => Promise<void>;
  saveWorkspacePatch: (
    patch: {
      manual_notes?: string | null;
      locked_day_numbers?: number[] | null;
      reservations?: TripWorkspace["reservations"] | null;
      request_brief?: TripPlanningRequest | null;
      generate_response?: boolean;
    },
    options?: { propagateErrors?: boolean },
  ) => Promise<TripWorkspace | null>;
  loadPlanningTelemetry: () => Promise<unknown>;
}) {
  const {
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
    setProgressMessage,
    buildPlanNotices,
    toUserError,
    persistWorkspaceFromResponse,
    saveWorkspacePatch,
    loadPlanningTelemetry,
  } = options;

  async function submitPlan() {
    const normalizedDestination = form.destination.trim();
    if (!isChineseCityName(normalizedDestination)) {
      openNotice("error", "目的地格式不支持", [
        "目的地目前只支持中文城市名，例如：上海、北京市。",
      ]);
      return;
    }

    loading.value = true;
    form.must_visit = splitText(mustVisitText.value);
    form.dining_preferences = splitText(diningText.value);
    form.destination = normalizedDestination;

    const requestPayload = buildTripPlanningRequestPayload({
      form,
      mustVisit: form.must_visit,
      diningPreferences: form.dining_preferences,
    });

    startProgress();

    try {
      if (currentTrip.value) {
        const nextWorkspace = await saveWorkspacePatch(
          {
            request_brief: requestPayload,
            manual_notes: tripNotes.value,
            locked_day_numbers: currentTrip.value.locked_day_numbers,
            reservations: currentTrip.value.reservations,
            generate_response: true,
          },
          { propagateErrors: true },
        );

        const response = nextWorkspace?.response_snapshot;
        if (!response) {
          throw new Error("Workspace refresh completed without a generated response.");
        }

        result.value = response;
        integrationStatus.value = response.integration_status;
      } else {
        syncTripQuery(null);

        const job = await startGeneratePlanJob(requestPayload, { debug: showDevPanels });
        setProgressMessage(humanizePlanningJobProgress(job));

        const completedJob = await waitForPlanningJob(job.id, getPlanningJob, {
          onProgress(nextJob) {
            setProgressMessage(humanizePlanningJobProgress(nextJob));
          },
        });

        const response = completedJob.planning_response;
        if (!response) {
          throw new Error("Planning job completed without a response payload.");
        }

        result.value = response;
        integrationStatus.value = response.integration_status;
        await persistWorkspaceFromResponse(response);
      }

      expandedDays.value = [];
      stopProgress(true);

      const notices = result.value ? buildPlanNotices(result.value) : [];
      if (notices.length) {
        openNotice("warning", "行程已生成，请留意这些事项", notices);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "生成行程失败，请稍后重试。";
      stopProgress(false);
      openNotice("error", "生成行程失败", [toUserError(message)]);
      console.error("plan generation failed", error);
    } finally {
      loading.value = false;
      if (showDevPanels) {
        void loadPlanningTelemetry();
      }
    }
  }

  return {
    submitPlan,
  };
}
