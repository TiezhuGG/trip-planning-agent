import { onScopeDispose, type Ref } from "vue";

import {
  createTripWorkspaceVersionSnapshot,
  createTripWorkspace,
  deleteTripWorkspaceVersion,
  downloadTripWorkspaceCalendar,
  getPlanningJob,
  getTripWorkspace,
  getTripWorkspaceVersion,
  getTripWorkspaceByShareToken,
  listPlanningJobs,
  listRecentTripWorkspaces,
  listTripWorkspaceVersions,
  patchTripWorkspace,
  restoreTripWorkspaceVersion,
  regenerateTripWorkspaceShare,
  revokeTripWorkspaceShare,
  startTripWorkspacePrecheckJob,
  startUpdateTripWorkspaceJob,
  updateTripWorkspaceVersionLabel,
  updateTripWorkspaceVersionMeta,
} from "../api/planning";
import type {
  CalendarExportScope,
  PlanningJobSummary,
  PlanningResponse,
  ReservationItem,
  TripPlanningRequest,
  TripSummary,
  TripWorkspace,
  TripWorkspaceVersionSummary,
} from "../types/planning";
import {
  humanizePlanningJobProgress,
  isPlanningJobActive,
  waitForPlanningJob,
} from "../utils/planningJobs";
import {
  buildCalendarExportNotice as buildCalendarExportNoticeShared,
  collectPrecheckAffectedDays,
} from "./tripWorkspaceExportReadiness";
import {
  buildPersistedWorkspacePayload,
  buildWorkspacePatchPayload,
  ensureCurrentWorkspace,
  normalizeDraftRequest,
  toActionErrorMessage,
  type NoticeTone,
} from "./tripWorkspaceActionHelpers";

type WorkspacePatch = {
  manual_notes?: string | null;
  locked_day_numbers?: number[] | null;
  reservations?: ReservationItem[] | null;
  request_brief?: TripPlanningRequest | null;
  generate_response?: boolean;
};

type BatchVersionAction = "star" | "unstar" | "archive" | "unarchive";

export function createTripWorkspacePersistenceActions(options: {
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  tripSaving: Ref<boolean>;
  tripLoading: Ref<boolean>;
  tripPrechecking: Ref<boolean>;
  busyMessage: Ref<string>;
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
    busyMessage,
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
  } = options;

  let recentJobsTimer: number | null = null;
  const autoPrecheckTripIds = new Set<string>();
  const pendingAutoPrecheckTripIds = new Set<string>();

  function clearRecentJobsTimer() {
    if (recentJobsTimer !== null) {
      window.clearTimeout(recentJobsTimer);
      recentJobsTimer = null;
    }
  }

  function scheduleRecentJobsRefresh(tripId: string, limit: number) {
    clearRecentJobsTimer();
    recentJobsTimer = window.setTimeout(() => {
      void loadRecentPlanningJobs(tripId, limit);
    }, 2500);
  }

  function hasActivePrecheckJob(tripId: string) {
    return recentPlanningJobs.value.some(
      (job) =>
        job.trip_id === tripId &&
        job.kind === "precheck_trip" &&
        isPlanningJobActive(job),
    );
  }

  function canAutoRefreshPrecheck(workspace: TripWorkspace | null) {
    return Boolean(workspace && workspace.response_snapshot && workspace.status !== "draft");
  }

  function hasPrecheckAttentionItems(workspace: TripWorkspace) {
    const summary = workspace.last_precheck_summary;
    return Boolean(
      summary &&
        summary.items.some(
          (item) => item.after_status === "warning" || item.after_status === "pending",
        ),
    );
  }

  function reservationsChanged(previous: ReservationItem[], next: ReservationItem[]) {
    return JSON.stringify(previous) !== JSON.stringify(next);
  }

  function queueAutoDeparturePrecheck(workspace: TripWorkspace) {
    if (!canAutoRefreshPrecheck(workspace)) {
      return;
    }
    if (
      tripPrechecking.value ||
      autoPrecheckTripIds.has(workspace.id) ||
      hasActivePrecheckJob(workspace.id)
    ) {
      pendingAutoPrecheckTripIds.add(workspace.id);
      return;
    }
    void runAutoDeparturePrecheck(workspace);
  }

  function drainPendingAutoPrecheck(tripId?: string) {
    if (
      !tripId ||
      tripPrechecking.value ||
      autoPrecheckTripIds.has(tripId) ||
      hasActivePrecheckJob(tripId)
    ) {
      return;
    }
    const latestWorkspace = currentTrip.value;
    if (
      pendingAutoPrecheckTripIds.has(tripId) &&
      latestWorkspace &&
      latestWorkspace.id === tripId &&
      canAutoRefreshPrecheck(latestWorkspace)
    ) {
      pendingAutoPrecheckTripIds.delete(tripId);
      void runAutoDeparturePrecheck(latestWorkspace);
    }
  }

  async function runAutoDeparturePrecheck(workspace: TripWorkspace) {
    autoPrecheckTripIds.add(workspace.id);
    pendingAutoPrecheckTripIds.delete(workspace.id);

    try {
      const job = await startTripWorkspacePrecheckJob(workspace.id, {
        include_debug: showDevPanels,
      });
      void loadRecentPlanningJobs(workspace.id);

      const completedJob = await waitForPlanningJob(job.id, getPlanningJob);
      const nextWorkspace = completedJob.trip_workspace;
      if (!nextWorkspace) {
        return;
      }

      if (currentTrip.value?.id === nextWorkspace.id) {
        applyWorkspace(nextWorkspace, {
          syncUrl: false,
          focusDayNumbers: uniquePrecheckFocusDays(nextWorkspace),
        });
        void loadRecentTrips();
        void loadRecentPlanningJobs(nextWorkspace.id);

        if (hasPrecheckAttentionItems(nextWorkspace)) {
          openNotice(
            "warning",
            "已自动刷新出发前预检",
            buildPrecheckRefreshMessages(nextWorkspace),
          );
        }
      }
    } catch (error) {
      if (currentTrip.value?.id === workspace.id) {
        const message = toActionErrorMessage(error, "自动刷新出发前预检失败，请稍后重试。");
        openNotice("warning", "自动预检未完成", [message]);
      }
    } finally {
      autoPrecheckTripIds.delete(workspace.id);

      const latestWorkspace = currentTrip.value;
      if (
        pendingAutoPrecheckTripIds.has(workspace.id) &&
        latestWorkspace &&
        latestWorkspace.id === workspace.id &&
        canAutoRefreshPrecheck(latestWorkspace)
      ) {
        pendingAutoPrecheckTripIds.delete(workspace.id);
        void runAutoDeparturePrecheck(latestWorkspace);
      }
    }
  }

  onScopeDispose(() => {
    clearRecentJobsTimer();
  });

  async function loadSharedTrip(shareToken: string) {
    tripLoading.value = true;
    try {
      const workspace = await getTripWorkspaceByShareToken(shareToken);
      applyWorkspace(workspace);
      void loadRecentPlanningJobs(workspace.id);
      void loadTripVersions(workspace.id);
      openNotice("success", "已加载分享行程", [
        workspace.response_snapshot
          ? "当前页面已切换到分享工作区，你可以继续查看、锁定日期或重新规划。"
          : "当前分享的是草稿工作区，你可以继续补充需求后再生成。",
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "读取分享行程失败，请稍后重试。");
      openNotice("error", "读取分享行程失败", [message]);
      syncTripQuery(null);
    } finally {
      tripLoading.value = false;
    }
  }

  async function loadWorkspaceById(tripId: string) {
    tripLoading.value = true;
    try {
      const workspace = await getTripWorkspace(tripId);
      applyWorkspace(workspace, { syncUrl: false });
      void loadRecentPlanningJobs(workspace.id);
      void loadTripVersions(workspace.id);
      openNotice("success", "已恢复最近工作区", [
        workspace.response_snapshot
          ? "已恢复到最近一次保存的行程工作区，你可以继续编辑、预检或重新规划。"
          : "已恢复草稿工作区，你可以继续补充信息后生成结果。",
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "读取最近工作区失败，请稍后重试。");
      openNotice("error", "恢复工作区失败", [message]);
    } finally {
      tripLoading.value = false;
    }
  }

  async function loadRecentTrips(limit = 6) {
    recentTripsLoading.value = true;
    recentTripsError.value = "";
    try {
      recentTrips.value = await listRecentTripWorkspaces({ limit });
    } catch (error) {
      recentTripsError.value = toActionErrorMessage(error, "读取最近工作区失败");
      recentTrips.value = [];
    } finally {
      recentTripsLoading.value = false;
    }
  }

  async function loadRecentPlanningJobs(tripId?: string, limit = 8) {
    clearRecentJobsTimer();
    recentPlanningJobsLoading.value = true;
    recentPlanningJobsError.value = "";
    try {
      recentPlanningJobs.value = tripId ? await listPlanningJobs({ limit, tripId }) : [];
      if (
        tripId &&
        recentPlanningJobs.value.some((job) => isPlanningJobActive(job))
      ) {
        scheduleRecentJobsRefresh(tripId, limit);
      }
    } catch (error) {
      recentPlanningJobsError.value = toActionErrorMessage(error, "读取最近任务失败");
      recentPlanningJobs.value = [];
    } finally {
      recentPlanningJobsLoading.value = false;
      drainPendingAutoPrecheck(tripId);
    }
  }

  async function loadTripVersions(
    tripId?: string,
    limit = 12,
    options: { offset?: number; append?: boolean } = {},
  ) {
    if (!tripId) {
      if (!options.append) {
        tripVersions.value = [];
      }
      tripVersionsError.value = "";
      tripVersionsHasMore.value = false;
      return;
    }
    tripVersionsLoading.value = true;
    tripVersionsError.value = "";
    try {
      const response = await listTripWorkspaceVersions(tripId, {
        limit,
        offset: options.offset ?? 0,
      });
      const nextVersions = response.items;
      if (options.append) {
        const merged = [...tripVersions.value];
        for (const version of nextVersions) {
          if (!merged.some((item) => item.version === version.version)) {
            merged.push(version);
          }
        }
        tripVersions.value = merged;
      } else {
        tripVersions.value = nextVersions;
      }
      tripVersionsHasMore.value = response.has_more;
    } catch (error) {
      tripVersionsError.value = toActionErrorMessage(error, "读取版本历史失败");
      if (!options.append) {
        tripVersions.value = [];
      }
      tripVersionsHasMore.value = false;
    } finally {
      tripVersionsLoading.value = false;
    }
  }

  async function persistWorkspaceFromResponse(response: PlanningResponse) {
    tripSaving.value = true;
    busyMessage.value = "正在保存生成结果到工作区。";
    try {
      const workspace = await createTripWorkspace(
        buildPersistedWorkspacePayload({
          requestBrief: response.request_echo,
          responseSnapshot: response,
          tripNotes: tripNotes.value,
          currentTrip: currentTrip.value,
          showDevPanels,
          generateResponse: true,
        }),
      );
      applyWorkspace(workspace);
      void loadRecentTrips();
      void loadRecentPlanningJobs(workspace.id);
      void loadTripVersions(workspace.id);
      queueAutoDeparturePrecheck(workspace);
    } catch (error) {
      const message = toActionErrorMessage(error, "保存行程工作区失败，请稍后重试。");
      openNotice("warning", "结果已生成，但工作区未保存", [message]);
    } finally {
      tripSaving.value = false;
      busyMessage.value = "";
    }
  }

  async function saveWorkspacePatch(
    patch: WorkspacePatch,
    options: { propagateErrors?: boolean } = {},
  ): Promise<TripWorkspace | null> {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先等待行程结果保存完成。",
    );
    if (!workspace) {
      return null;
    }

    tripSaving.value = true;
    busyMessage.value = patch.generate_response
      ? "正在更新工作区并重新生成结果。"
      : "正在保存工作区。";
    try {
      const payload = buildWorkspacePatchPayload({
        currentTrip: workspace,
        tripNotes: tripNotes.value,
        showDevPanels,
        patch,
      });
      let nextWorkspace: TripWorkspace | null;

      if (patch.generate_response) {
        const job = await startUpdateTripWorkspaceJob(workspace.id, payload);
        void loadRecentPlanningJobs(workspace.id);
        busyMessage.value = humanizePlanningJobProgress(job);
        const completedJob = await waitForPlanningJob(job.id, getPlanningJob, {
          onProgress(nextJob) {
            busyMessage.value = humanizePlanningJobProgress(nextJob);
          },
        });
        nextWorkspace = completedJob.trip_workspace;
      } else {
        nextWorkspace = await patchTripWorkspace(workspace.id, payload);
      }

      if (!nextWorkspace) {
        throw new Error("Workspace update completed without a workspace payload.");
      }

      applyWorkspace(nextWorkspace, {
        syncUrl: false,
        focusDayNumbers: uniquePrecheckFocusDays(nextWorkspace),
      });
      void loadRecentTrips();
      void loadRecentPlanningJobs(nextWorkspace.id);
      void loadTripVersions(nextWorkspace.id);
      if (patch.generate_response || reservationsChanged(workspace.reservations, nextWorkspace.reservations)) {
        queueAutoDeparturePrecheck(nextWorkspace);
      }
      return nextWorkspace;
    } catch (error) {
      const message = toActionErrorMessage(error, "更新行程工作区失败，请稍后重试。");
      if (!options.propagateErrors) {
        openNotice("error", "保存失败", [message]);
        return null;
      }
      throw error instanceof Error ? error : new Error(message);
    } finally {
      tripSaving.value = false;
      busyMessage.value = "";
    }
  }

  async function saveTripNotesAndLocks() {
    await saveWorkspacePatch({
      manual_notes: tripNotes.value,
      locked_day_numbers: currentTrip.value?.locked_day_numbers ?? [],
      reservations: currentTrip.value?.reservations ?? [],
    });
  }

  async function saveDraft() {
    const normalized = normalizeDraftRequest({
      form,
      mustVisitText: mustVisitText.value,
      diningText: diningText.value,
      isChineseCityName,
      splitText,
    });
    if (!normalized.ok) {
      openNotice("error", "输入有误", [normalized.message]);
      return;
    }

    draftSaving.value = true;
    try {
      if (currentTrip.value) {
        const workspace = await patchTripWorkspace(
          currentTrip.value.id,
          buildWorkspacePatchPayload({
            currentTrip: currentTrip.value,
            tripNotes: tripNotes.value,
            showDevPanels,
            patch: {
              request_brief: normalized.request,
              generate_response: false,
            },
          }),
        );
        applyWorkspace(workspace, { syncUrl: false });
        void loadRecentTrips();
        void loadRecentPlanningJobs(workspace.id);
        void loadTripVersions(workspace.id);
      } else {
        const workspace = await createTripWorkspace(
          buildPersistedWorkspacePayload({
            requestBrief: normalized.request,
            tripNotes: tripNotes.value,
            currentTrip: null,
            showDevPanels,
            generateResponse: false,
          }),
        );
        applyWorkspace(workspace);
        void loadRecentTrips();
        void loadRecentPlanningJobs(workspace.id);
        void loadTripVersions(workspace.id);
      }
      openNotice("success", "草稿已保存", [
        "当前需求已写入工作区，稍后可以继续生成或修改。",
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "保存草稿失败，请稍后重试。");
      openNotice("error", "草稿保存失败", [message]);
    } finally {
      draftSaving.value = false;
    }
  }

  async function copyShareLink() {
    if (!shareLink.value) {
      openNotice("warning", "暂无分享链接", ["请先等待工作区保存完成。"]);
      return;
    }
    try {
      await navigator.clipboard.writeText(shareLink.value);
      openNotice("success", "分享链接已复制", [shareLink.value]);
    } catch {
      openNotice("warning", "复制失败", ["当前浏览器不允许直接写入剪贴板。"]);
    }
  }

  async function revokeShareLink() {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再管理分享链接。",
    );
    if (!workspace) {
      return;
    }

    tripSaving.value = true;
    busyMessage.value = "正在撤销分享链接。";
    try {
      const nextWorkspace = await revokeTripWorkspaceShare(workspace.id);
      applyWorkspace(nextWorkspace);
      void loadRecentTrips();
      void loadRecentPlanningJobs(nextWorkspace.id);
      void loadTripVersions(nextWorkspace.id);
      openNotice("success", "分享链接已撤销", [
        "旧分享链接已经失效，外部访问将被阻止。",
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "撤销分享链接失败，请稍后重试。");
      openNotice("error", "撤销分享失败", [message]);
    } finally {
      tripSaving.value = false;
      busyMessage.value = "";
    }
  }

  async function regenerateShareLink() {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再生成新的分享链接。",
    );
    if (!workspace) {
      return;
    }

    tripSaving.value = true;
    busyMessage.value = "正在生成新的分享链接。";
    try {
      const nextWorkspace = await regenerateTripWorkspaceShare(workspace.id);
      applyWorkspace(nextWorkspace);
      void loadRecentTrips();
      void loadRecentPlanningJobs(nextWorkspace.id);
      void loadTripVersions(nextWorkspace.id);
      openNotice("success", "新的分享链接已生成", [
        "旧链接已经失效，你可以复制新的分享地址发给他人。",
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "重新生成分享链接失败，请稍后重试。");
      openNotice("error", "生成分享链接失败", [message]);
    } finally {
      tripSaving.value = false;
      busyMessage.value = "";
    }
  }

  async function refreshDeparturePrecheck() {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区并生成结果后再刷新出发前预检。",
    );
    if (!workspace) {
      return;
    }

    tripPrechecking.value = true;
    busyMessage.value = "正在刷新出发前预检。";
    try {
      const job = await startTripWorkspacePrecheckJob(workspace.id, {
        include_debug: showDevPanels,
      });
      void loadRecentPlanningJobs(workspace.id);
      busyMessage.value = humanizePlanningJobProgress(job);
      const completedJob = await waitForPlanningJob(job.id, getPlanningJob, {
        onProgress(nextJob) {
          busyMessage.value = humanizePlanningJobProgress(nextJob);
        },
      });
      const nextWorkspace = completedJob.trip_workspace;
      if (!nextWorkspace) {
        throw new Error("Precheck completed without a workspace payload.");
      }
      applyWorkspace(nextWorkspace, {
        syncUrl: false,
        focusDayNumbers: uniquePrecheckFocusDays(nextWorkspace),
      });
      void loadRecentTrips();
      void loadRecentPlanningJobs(nextWorkspace.id);
      void loadTripVersions(nextWorkspace.id);
      openNotice("success", "出发前预检已刷新", buildPrecheckRefreshMessages(nextWorkspace));
    } catch (error) {
      const message = toActionErrorMessage(error, "刷新出发前预检失败，请稍后重试。");
      openNotice("error", "出发前预检刷新失败", [message]);
    } finally {
      tripPrechecking.value = false;
      busyMessage.value = "";
      drainPendingAutoPrecheck(currentTrip.value?.id);
    }
  }

  async function exportCalendarFileWithPrecheckNotice(scope: CalendarExportScope = "full") {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再导出日历。",
    );
    if (!workspace) {
      return;
    }

    try {
      const { blob, filename } = await downloadTripWorkspaceCalendar(workspace.id, scope);
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      link.click();
      window.URL.revokeObjectURL(objectUrl);

      const exportNotice = buildCalendarExportNoticeShared(workspace, scope, recentPlanningJobs.value);
      openNotice(exportNotice.tone, exportNotice.title, exportNotice.messages);
    } catch (error) {
      const message = toActionErrorMessage(error, "导出日历失败，请稍后重试。");
      openNotice("error", "导出日历失败", [message]);
    }
  }

  async function previewTripVersion(version: number) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再查看历史版本。",
    );
    if (!workspace) {
      return null;
    }
    try {
      return await getTripWorkspaceVersion(workspace.id, version);
    } catch (error) {
      const message = toActionErrorMessage(error, "读取历史版本失败，请稍后重试。");
      openNotice("error", "读取历史版本失败", [message]);
      return null;
    }
  }

  async function restoreWorkspaceVersion(version: number) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再恢复历史版本。",
    );
    if (!workspace) {
      return;
    }

    restoringTripVersion.value = version;
    busyMessage.value = `正在恢复 v${version}...`;
    try {
      const nextWorkspace = await restoreTripWorkspaceVersion(workspace.id, version);
      applyWorkspace(nextWorkspace, { syncUrl: false });
      void loadRecentTrips();
      void loadRecentPlanningJobs(nextWorkspace.id);
      void loadTripVersions(nextWorkspace.id);
      openNotice("success", "已恢复历史版本", [
        `工作区已恢复到 v${version} 的内容，并生成新的当前版本 v${nextWorkspace.version}。`,
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "恢复历史版本失败，请稍后重试。");
      openNotice("error", "恢复历史版本失败", [message]);
    } finally {
      restoringTripVersion.value = null;
      busyMessage.value = "";
    }
  }

  async function createWorkspaceVersionSnapshot(versionLabel: string) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再创建版本快照。",
    );
    if (!workspace) {
      return;
    }

    savingTripVersionLabel.value = workspace.version;
    busyMessage.value = "正在保存当前版本快照。";
    try {
      const nextWorkspace = await createTripWorkspaceVersionSnapshot(workspace.id, {
        version_label: versionLabel,
      });
      applyWorkspace(nextWorkspace, { syncUrl: false });
      void loadRecentTrips();
      void loadRecentPlanningJobs(nextWorkspace.id);
      void loadTripVersions(nextWorkspace.id);
      openNotice("success", "已创建版本快照", [
        versionLabel.trim()
          ? `当前工作区已另存为 v${nextWorkspace.version}，标签为“${versionLabel.trim()}”。`
          : `当前工作区已另存为 v${nextWorkspace.version}。`,
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "创建版本快照失败，请稍后重试。");
      openNotice("error", "创建版本快照失败", [message]);
    } finally {
      savingTripVersionLabel.value = null;
      busyMessage.value = "";
    }
  }

  async function deleteWorkspaceVersion(version: number) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再删除版本快照。",
    );
    if (!workspace) {
      return;
    }

    savingTripVersionLabel.value = version;
    busyMessage.value = `正在删除 v${version} 快照。`;
    try {
      await deleteTripWorkspaceVersion(workspace.id, version);
      void loadTripVersions(workspace.id);
      void loadRecentTrips();
      openNotice("success", "版本快照已删除", [
        `v${version} 已从版本历史中移除。`,
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "删除版本快照失败，请稍后重试。");
      openNotice("error", "删除版本快照失败", [message]);
    } finally {
      savingTripVersionLabel.value = null;
      busyMessage.value = "";
    }
  }

  async function saveWorkspaceVersionLabel(version: number, versionLabel: string) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再更新版本标签。",
    );
    if (!workspace) {
      return;
    }

    savingTripVersionLabel.value = version;
    try {
      const nextWorkspace = await updateTripWorkspaceVersionLabel(workspace.id, version, {
        version_label: versionLabel,
      });
      if (nextWorkspace.version === currentTrip.value?.version) {
        applyWorkspace(nextWorkspace, { syncUrl: false });
      }
      void loadTripVersions(workspace.id);
      void loadRecentTrips();
      openNotice("success", "版本标签已更新", [
        versionLabel.trim()
          ? `v${version} 已命名为“${versionLabel.trim()}”。`
          : `v${version} 的自定义标签已清空。`,
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "更新版本标签失败，请稍后重试。");
      openNotice("error", "版本标签更新失败", [message]);
    } finally {
      savingTripVersionLabel.value = null;
    }
  }

  async function saveWorkspaceVersionMeta(
    version: number,
    options: { versionLabel: string; isStarred: boolean; isArchived: boolean },
  ) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再更新版本元数据。",
    );
    if (!workspace) {
      return;
    }

    savingTripVersionLabel.value = version;
    try {
      const nextWorkspace = await updateTripWorkspaceVersionMeta(workspace.id, version, {
        version_label: options.versionLabel,
        is_starred: options.isStarred,
        is_archived: options.isArchived,
      });
      if (nextWorkspace.version === currentTrip.value?.version) {
        applyWorkspace(nextWorkspace, { syncUrl: false });
      }
      void loadTripVersions(workspace.id);
      void loadRecentTrips();
    } catch (error) {
      const message = toActionErrorMessage(error, "更新版本元数据失败，请稍后重试。");
      openNotice("error", "版本更新失败", [message]);
    } finally {
      savingTripVersionLabel.value = null;
    }
  }

  async function batchUpdateWorkspaceVersions(
    versions: TripWorkspaceVersionSummary[],
    action: BatchVersionAction,
  ) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再批量更新版本。",
    );
    if (!workspace || !versions.length) {
      return;
    }

    const uniqueVersions = versions
      .filter((item, index, source) => source.findIndex((entry) => entry.version === item.version) === index)
      .filter((item) => !item.is_current);

    if (!uniqueVersions.length) {
      return;
    }

    const actionLabel =
      action === "star"
        ? "批量标星"
        : action === "unstar"
          ? "批量取消星标"
          : action === "archive"
            ? "批量归档"
            : "批量取消归档";

    busyMessage.value = `正在${actionLabel}...`;

    try {
      for (const version of uniqueVersions) {
        savingTripVersionLabel.value = version.version;
        const nextWorkspace = await updateTripWorkspaceVersionMeta(workspace.id, version.version, {
          version_label: version.version_label,
          is_starred: action === "star" ? true : action === "unstar" ? false : version.is_starred,
          is_archived: action === "archive" ? true : action === "unarchive" ? false : version.is_archived,
        });
        if (nextWorkspace.version === currentTrip.value?.version) {
          applyWorkspace(nextWorkspace, { syncUrl: false });
        }
      }

      void loadTripVersions(workspace.id);
      void loadRecentTrips();
      openNotice("success", `${actionLabel}完成`, [`已处理 ${uniqueVersions.length} 个版本。`]);
    } catch (error) {
      const message = toActionErrorMessage(error, `${actionLabel}失败，请稍后重试。`);
      openNotice("error", `${actionLabel}失败`, [message]);
    } finally {
      savingTripVersionLabel.value = null;
      busyMessage.value = "";
    }
  }

  async function batchUpdateWorkspaceVersionsV2(
    versions: TripWorkspaceVersionSummary[],
    action: BatchVersionAction,
  ) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先保存工作区后再批量更新版本。",
    );
    if (!workspace || !versions.length) {
      return;
    }

    const uniqueVersions = versions
      .filter(
        (item, index, source) =>
          source.findIndex((entry) => entry.version === item.version) === index,
      )
      .filter((item) => !item.is_current);

    if (!uniqueVersions.length) {
      return;
    }

    const actionLabel =
      action === "star"
        ? "批量标星"
        : action === "unstar"
          ? "批量取消星标"
          : action === "archive"
            ? "批量归档"
            : "批量取消归档";

    busyMessage.value = `正在${actionLabel}...`;

    const updatedVersions: number[] = [];
    const skippedVersions: number[] = [];
    const failedVersions: Array<{ version: number; message: string }> = [];

    try {
      for (const version of uniqueVersions) {
        const nextStarred =
          action === "star" ? true : action === "unstar" ? false : version.is_starred;
        const nextArchived =
          action === "archive" ? true : action === "unarchive" ? false : version.is_archived;

        if (nextStarred === version.is_starred && nextArchived === version.is_archived) {
          skippedVersions.push(version.version);
          continue;
        }

        savingTripVersionLabel.value = version.version;
        try {
          const nextWorkspace = await updateTripWorkspaceVersionMeta(
            workspace.id,
            version.version,
            {
              version_label: version.version_label,
              is_starred: nextStarred,
              is_archived: nextArchived,
            },
          );
          if (nextWorkspace.version === currentTrip.value?.version) {
            applyWorkspace(nextWorkspace, { syncUrl: false });
          }
          updatedVersions.push(version.version);
        } catch (error) {
          failedVersions.push({
            version: version.version,
            message: toActionErrorMessage(error, `v${version.version} 处理失败`),
          });
        }
      }

      void loadTripVersions(workspace.id);
      void loadRecentTrips();

      const summaryMessages: string[] = [];
      if (updatedVersions.length) {
        summaryMessages.push(
          `已成功 ${updatedVersions.length} 个版本：${updatedVersions.map((item) => `v${item}`).join("、")}。`,
        );
      }
      if (skippedVersions.length) {
        summaryMessages.push(`已跳过 ${skippedVersions.length} 个版本（状态无变化）。`);
      }
      if (failedVersions.length) {
        summaryMessages.push(
          `失败 ${failedVersions.length} 个版本：${failedVersions.map((item) => `v${item.version}`).join("、")}。`,
        );
        summaryMessages.push(
          ...failedVersions.slice(0, 3).map((item) => `v${item.version}：${item.message}`),
        );
      }

      openNotice(
        failedVersions.length ? (updatedVersions.length ? "warning" : "error") : "success",
        failedVersions.length ? `${actionLabel}已完成（含部分结果）` : `${actionLabel}完成`,
        summaryMessages.length ? summaryMessages : ["没有需要更新的版本。"],
      );
    } finally {
      savingTripVersionLabel.value = null;
      busyMessage.value = "";
    }
  }

  return {
    copyShareLink,
    exportCalendarFile: exportCalendarFileWithPrecheckNotice,
    queueAutoDeparturePrecheck,
    loadRecentPlanningJobs,
    loadRecentTrips,
    loadTripVersions,
    loadSharedTrip,
    loadWorkspaceById,
    persistWorkspaceFromResponse,
    previewTripVersion,
    createWorkspaceVersionSnapshot,
    deleteWorkspaceVersion,
    batchUpdateWorkspaceVersions: batchUpdateWorkspaceVersionsV2,
    refreshDeparturePrecheck,
    regenerateShareLink,
    restoreWorkspaceVersion,
    saveWorkspaceVersionLabel,
    saveWorkspaceVersionMeta,
    revokeShareLink,
    saveDraft,
    saveTripNotesAndLocks,
    saveWorkspacePatch,
  };
}

function buildPrecheckRefreshMessages(workspace: TripWorkspace): string[] {
  const summary = workspace.last_precheck_summary;
  if (!summary) {
    return ["工作区快照已更新，本次预检没有新增状态变化。"];
  }

  const itemMessages = summary.items
    .slice(0, 3)
    .map((item) => `${item.title}：${item.before_summary} -> ${item.after_summary}`);
  const messages = [summary.title, ...itemMessages];

  if (messages.length === 1) {
    messages.push("工作区快照已更新，本次预检没有新增状态变化。");
  }

  return [...new Set(messages.filter(Boolean))];
}

function uniquePrecheckFocusDays(workspace: TripWorkspace): number[] {
  return collectPrecheckAffectedDays(workspace);
}
