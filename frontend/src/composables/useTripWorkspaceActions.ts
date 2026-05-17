import type { Ref } from "vue";

import type {
  PlanningJobSummary,
  TripSummary,
  TripPlanningRequest,
  TripWorkspace,
  TripWorkspaceVersionSummary,
} from "../types/planning";
import {
  toActionErrorMessage,
  type NoticeTone,
} from "./tripWorkspaceActionHelpers";
import { createTripWorkspacePersistenceActions } from "./tripWorkspacePersistenceActions";
import { createTripWorkspaceReplanActions } from "./tripWorkspaceReplanActions";
import { createTripWorkspaceReservationActions } from "./tripWorkspaceReservationActions";

export function useTripWorkspaceActions(options: {
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  tripSaving: Ref<boolean>;
  tripLoading: Ref<boolean>;
  tripPrechecking: Ref<boolean>;
  tripReplanning: Ref<boolean>;
  workspaceBusyMessage: Ref<string>;
  retryingPlanningJobId: Ref<string>;
  draftSaving: Ref<boolean>;
  recentPlanningJobs: Ref<PlanningJobSummary[]>;
  recentPlanningJobsLoading: Ref<boolean>;
  recentPlanningJobsError: Ref<string>;
  tripVersions: Ref<TripWorkspaceVersionSummary[]>;
  tripVersionsLoading: Ref<boolean>;
  tripVersionsError: Ref<string>;
  tripVersionsHasMore: Ref<boolean>;
  restoringTripVersion: Ref<number | null>;
  savingTripVersionLabel: Ref<number | null>;
  recentTrips: Ref<TripSummary[]>;
  recentTripsLoading: Ref<boolean>;
  recentTripsError: Ref<string>;
  replanningDays: Ref<number[]>;
  shareLink: Ref<string>;
  form: TripPlanningRequest;
  mustVisitText: Ref<string>;
  diningText: Ref<string>;
  showDevPanels: boolean;
  applyWorkspace: (
    workspace: TripWorkspace,
    options?: { syncUrl?: boolean; focusDayNumbers?: number[] },
  ) => void;
  openNotice: (tone: NoticeTone, title: string, messages: string[]) => void;
  syncTripQuery: (shareToken?: string | null) => void;
  isChineseCityName: (value: string) => boolean;
  splitText: (value: string) => string[];
}) {
  const {
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
  } = options;

  const persistenceActions = createTripWorkspacePersistenceActions({
    currentTrip,
    tripNotes,
    tripSaving,
    tripLoading,
    tripPrechecking,
    busyMessage: workspaceBusyMessage,
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

  const reservationActions = createTripWorkspaceReservationActions({
    currentTrip,
    tripNotes,
    openNotice,
    saveWorkspacePatch: persistenceActions.saveWorkspacePatch,
  });

  const replanActions = createTripWorkspaceReplanActions({
    currentTrip,
    tripNotes,
    tripReplanning,
    replanningDays,
    busyMessage: workspaceBusyMessage,
    refreshRecentJobs: persistenceActions.loadRecentPlanningJobs,
    showDevPanels,
    applyWorkspace,
    queueAutoDeparturePrecheck: persistenceActions.queueAutoDeparturePrecheck,
    openNotice,
  });

  async function retryRecentPlanningJob(job: PlanningJobSummary) {
    retryingPlanningJobId.value = job.id;

    try {
      if (job.kind === "update_trip") {
        const workspace = currentTrip.value;
        if (!workspace) {
          openNotice("warning", "无法重试任务", [
            "当前工作区不存在，无法重新执行这项更新任务。",
          ]);
          return;
        }

        await persistenceActions.saveWorkspacePatch(
          {
            request_brief: workspace.request_brief,
            manual_notes: tripNotes.value,
            locked_day_numbers: workspace.locked_day_numbers,
            reservations: workspace.reservations,
            generate_response: true,
          },
          { propagateErrors: true },
        );
        return;
      }

      if (job.kind === "precheck_trip") {
        await persistenceActions.refreshDeparturePrecheck();
        return;
      }

      openNotice("warning", "暂不支持直接重试", [
        "当前任务类型暂时不能从这里直接重试，请回到对应操作入口重新发起。",
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "任务重试失败，请稍后重试。");
      openNotice("error", "任务重试失败", [message]);
    } finally {
      retryingPlanningJobId.value = "";
    }
  }

  return {
    ...persistenceActions,
    ...reservationActions,
    ...replanActions,
    retryRecentPlanningJob,
  };
}
