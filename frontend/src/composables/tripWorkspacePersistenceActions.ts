import type { Ref } from "vue";

import {
  createTripWorkspace,
  getTripWorkspaceByShareToken,
  patchTripWorkspace,
} from "../api/planning";
import type {
  PlanningResponse,
  ReservationItem,
  TripPlanningRequest,
  TripWorkspace,
} from "../types/planning";
import {
  buildPersistedWorkspacePayload,
  buildWorkspacePatchPayload,
  ensureCurrentWorkspace,
  type NoticeTone,
  normalizeDraftRequest,
  toActionErrorMessage,
} from "./tripWorkspaceActionHelpers";

type WorkspacePatch = {
  manual_notes?: string | null;
  locked_day_numbers?: number[] | null;
  reservations?: ReservationItem[] | null;
  request_brief?: TripPlanningRequest | null;
  generate_response?: boolean;
};

export function createTripWorkspacePersistenceActions(options: {
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  tripSaving: Ref<boolean>;
  tripLoading: Ref<boolean>;
  draftSaving: Ref<boolean>;
  shareLink: Ref<string>;
  form: TripPlanningRequest;
  mustVisitText: Ref<string>;
  diningText: Ref<string>;
  showDevPanels: boolean;
  applyWorkspace: (workspace: TripWorkspace, options?: { syncUrl?: boolean }) => void;
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
    draftSaving,
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

  async function loadSharedTrip(shareToken: string) {
    tripLoading.value = true;
    try {
      const workspace = await getTripWorkspaceByShareToken(shareToken);
      applyWorkspace(workspace);
      openNotice("success", "已载入分享行程", [
        workspace.response_snapshot
          ? "当前页面已切换到分享工作区，可继续查看、锁定日期或重规划。"
          : "当前分享的是一个草稿工作区，你可以继续补充需求后再生成。",
      ]);
    } catch (error) {
      const message = toActionErrorMessage(error, "读取分享行程失败，请稍后重试。");
      openNotice("error", "读取分享行程失败", [message]);
      syncTripQuery(null);
    } finally {
      tripLoading.value = false;
    }
  }

  async function persistWorkspaceFromResponse(response: PlanningResponse) {
    tripSaving.value = true;
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
    } catch (error) {
      const message = toActionErrorMessage(error, "保存行程工作区失败，请稍后重试。");
      openNotice("warning", "结果已生成，但工作区未保存", [message]);
    } finally {
      tripSaving.value = false;
    }
  }

  async function saveWorkspacePatch(patch: WorkspacePatch) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先等待行程结果保存完成。",
    );
    if (!workspace) {
      return;
    }

    tripSaving.value = true;
    try {
      const nextWorkspace = await patchTripWorkspace(
        workspace.id,
        buildWorkspacePatchPayload({
          currentTrip: workspace,
          tripNotes: tripNotes.value,
          showDevPanels,
          patch,
        }),
      );
      applyWorkspace(nextWorkspace, { syncUrl: false });
    } catch (error) {
      const message = toActionErrorMessage(error, "更新行程工作区失败，请稍后重试。");
      openNotice("error", "保存失败", [message]);
    } finally {
      tripSaving.value = false;
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
      openNotice("warning", "尚无分享链接", ["请先等待工作区保存完成。"]);
      return;
    }
    try {
      await navigator.clipboard.writeText(shareLink.value);
      openNotice("success", "分享链接已复制", [shareLink.value]);
    } catch {
      openNotice("warning", "复制失败", ["当前浏览器不允许直接写入剪贴板。"]);
    }
  }

  return {
    copyShareLink,
    loadSharedTrip,
    persistWorkspaceFromResponse,
    saveDraft,
    saveTripNotesAndLocks,
    saveWorkspacePatch,
  };
}
