import type { Ref } from "vue";

import {
  getPlanningJob,
  startReplanTripWorkspaceJob,
} from "../api/planning";
import type { ReplanRequest, TripWorkspace } from "../types/planning";
import { humanizePlanningJobProgress, waitForPlanningJob } from "../utils/planningJobs";
import type { DayGapType } from "./tripWorkspaceDayReadinessHelpers";
import {
  ensureCurrentWorkspace,
  toActionErrorMessage,
  type NoticeTone,
} from "./tripWorkspaceActionHelpers";

type DayReplanNoticeOptions = {
  reason?: string | null;
  payload?: Partial<ReplanRequest>;
  successTitle: string;
  successMessage: string;
  failureTitle: string;
  fallbackFailureMessage: string;
};

const WAIT_FOR_WORKSPACE_MESSAGE = "请先等待当前工作区保存完成后再继续操作。";

export function createTripWorkspaceReplanActions(options: {
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  tripReplanning: Ref<boolean>;
  replanningDays: Ref<number[]>;
  busyMessage: Ref<string>;
  refreshRecentJobs: (tripId?: string, limit?: number) => Promise<void>;
  showDevPanels: boolean;
  applyWorkspace: (
    workspace: TripWorkspace,
    options?: { syncUrl?: boolean; focusDayNumbers?: number[] },
  ) => void;
  queueAutoDeparturePrecheck: (workspace: TripWorkspace) => void;
  openNotice: (tone: NoticeTone, title: string, messages: string[]) => void;
}) {
  const {
    currentTrip,
    tripNotes,
    tripReplanning,
    replanningDays,
    busyMessage,
    refreshRecentJobs,
    showDevPanels,
    applyWorkspace,
    queueAutoDeparturePrecheck,
    openNotice,
  } = options;

  function beginDayReplan(dayNumber: number) {
    replanningDays.value = [...new Set([...replanningDays.value, dayNumber])];
  }

  function endDayReplan(dayNumber: number) {
    replanningDays.value = replanningDays.value.filter((item) => item !== dayNumber);
  }

  async function runReplanJob(
    workspaceId: string,
    payload: ReplanRequest,
  ): Promise<TripWorkspace> {
    const job = await startReplanTripWorkspaceJob(workspaceId, payload);
    void refreshRecentJobs(workspaceId);
    busyMessage.value = humanizePlanningJobProgress(job);

    const completedJob = await waitForPlanningJob(job.id, getPlanningJob, {
      onProgress(nextJob) {
        busyMessage.value = humanizePlanningJobProgress(nextJob);
      },
    });

    const nextWorkspace = completedJob.trip_workspace;
    if (!nextWorkspace) {
      throw new Error("Replan completed without a workspace payload.");
    }

    return nextWorkspace;
  }

  async function runDayReplan(dayNumber: number, noticeOptions: DayReplanNoticeOptions) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      WAIT_FOR_WORKSPACE_MESSAGE,
    );
    if (!workspace) {
      return;
    }

    beginDayReplan(dayNumber);
    busyMessage.value = `正在重排第 ${dayNumber} 天行程...`;

    try {
      const nextWorkspace = await runReplanJob(workspace.id, {
        scope: "day",
        day_numbers: [dayNumber],
        repair_mode: "replace",
        ...noticeOptions.payload,
        reason: noticeOptions.reason ?? null,
        include_debug: showDevPanels,
      });

      applyWorkspace(nextWorkspace, {
        syncUrl: false,
        focusDayNumbers: nextWorkspace.last_replan_summary?.target_days ?? [dayNumber],
      });
      void refreshRecentJobs(nextWorkspace.id);
      queueAutoDeparturePrecheck(nextWorkspace);

      openNotice(
        "success",
        noticeOptions.successTitle,
        buildReplanSuccessMessages(nextWorkspace, {
          dayNumber,
          fallbackMessage: noticeOptions.successMessage,
        }),
      );
    } catch (error) {
      const message = toActionErrorMessage(error, noticeOptions.fallbackFailureMessage);
      openNotice("error", noticeOptions.failureTitle, [message]);
    } finally {
      endDayReplan(dayNumber);
      busyMessage.value = "";
    }
  }

  async function replanDay(dayNumber: number) {
    await runDayReplan(dayNumber, {
      reason: tripNotes.value || null,
      payload: {
        repair_mode: "replace",
      },
      successTitle: "单日重规划已完成",
      successMessage: `第 ${dayNumber} 天的行程已更新。`,
      failureTitle: "单日重规划失败",
      fallbackFailureMessage: "重规划失败，请稍后重试。",
    });
  }

  async function repairDayGap(
    dayNumber: number,
    gapType: DayGapType,
    options: { reasonOverride?: string; actionLabelOverride?: string } = {},
  ) {
    const actionLabel = options.actionLabelOverride || resolveGapRepairLabel(gapType);

    await runDayReplan(dayNumber, {
      reason: options.reasonOverride || buildGapRepairReason(dayNumber, gapType, tripNotes.value),
      payload: {
        repair_mode: "fill_gaps",
        repair_gap: gapType,
      },
      successTitle: "缺口修复已完成",
      successMessage: `已按“${actionLabel}”重新生成第 ${dayNumber} 天。`,
      failureTitle: "缺口修复失败",
      fallbackFailureMessage: "补齐当日缺口失败，请稍后重试。",
    });
  }

  async function replanUnlockedDays() {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      WAIT_FOR_WORKSPACE_MESSAGE,
    );
    if (!workspace) {
      return;
    }

    tripReplanning.value = true;
    busyMessage.value = "正在重排未锁定的日期...";

    try {
      const nextWorkspace = await runReplanJob(workspace.id, {
        scope: "trip",
        day_numbers: [],
        preserve_locked_days: true,
        repair_mode: "replace",
        reason: tripNotes.value || null,
        include_debug: showDevPanels,
      });

      applyWorkspace(nextWorkspace, {
        syncUrl: false,
        focusDayNumbers: nextWorkspace.last_replan_summary?.target_days ?? [],
      });
      void refreshRecentJobs(nextWorkspace.id);
      queueAutoDeparturePrecheck(nextWorkspace);

      openNotice(
        "success",
        "整段重规划已完成",
        buildReplanSuccessMessages(nextWorkspace, {
          fallbackMessage: "未锁定日期的安排已刷新。",
        }),
      );
    } catch (error) {
      const message = toActionErrorMessage(error, "重规划失败，请稍后重试。");
      openNotice("error", "整段重规划失败", [message]);
    } finally {
      tripReplanning.value = false;
      busyMessage.value = "";
    }
  }

  return {
    replanDay,
    repairDayGap,
    replanUnlockedDays,
  };
}

function buildReplanSuccessMessages(
  workspace: TripWorkspace,
  options: {
    dayNumber?: number;
    fallbackMessage: string;
  },
): string[] {
  const summary = workspace.last_replan_summary;
  if (!summary) {
    return [options.fallbackMessage];
  }

  const messages = [summary.title];
  if (typeof options.dayNumber === "number") {
    const targetItem = summary.items.find((item) => item.day_number === options.dayNumber);
    if (targetItem) {
      messages.push(...buildReplanItemMessages(targetItem));
    }
  } else {
    messages.push(
      ...summary.items.slice(0, 3).flatMap((item) =>
        buildReplanItemMessages(item, { includeDayPrefix: true }).slice(0, 1),
      ),
    );
  }

  if (messages.length === 1) {
    messages.push(options.fallbackMessage);
  }

  return [...new Set(messages.filter(Boolean))].slice(0, 4);
}

function buildReplanItemMessages(
  item: NonNullable<TripWorkspace["last_replan_summary"]>["items"][number],
  options: { includeDayPrefix?: boolean } = {},
): string[] {
  const prefix = options.includeDayPrefix ? `第 ${item.day_number} 天：` : "";

  if (item.changes?.length) {
    return item.changes.slice(0, 3).map((change) => {
      const before = normalizeChangeValue(change.before);
      const after = normalizeChangeValue(change.after);
      return `${prefix}${change.label}：${before} -> ${after}`;
    });
  }

  return item.highlights.slice(0, 3).map((highlight) => `${prefix}${highlight}`);
}

function normalizeChangeValue(value?: string | null): string {
  return value?.trim() ? value : "未安排";
}

function resolveGapRepairLabel(gapType: DayGapType): string {
  switch (gapType) {
    case "stay":
      return "补齐住宿";
    case "meal":
      return "补齐餐饮";
    case "breakfast":
      return "补早餐";
    case "lunch":
      return "补午餐";
    case "dinner":
      return "补晚餐";
    case "snack":
      return "补加餐";
    case "activity":
      return "补齐活动";
    case "reservation":
      return "安排预订";
    case "day-plan":
      return "生成当日行程";
  }
}

function buildGapRepairReason(
  dayNumber: number,
  gapType: DayGapType,
  manualNotes: string,
): string {
  const reasons: Record<DayGapType, string> = {
    stay: `请优先补齐第 ${dayNumber} 天的住宿安排，并围绕住宿位置优化当天动线。`,
    meal: `请补齐第 ${dayNumber} 天缺失的餐饮安排，优先覆盖午餐和晚餐，并尽量靠近主要活动区域。`,
    breakfast: `请补齐第 ${dayNumber} 天的早餐安排，优先考虑住宿点附近、出发方便且开门较早的选择。`,
    lunch: `请补齐第 ${dayNumber} 天的午餐安排，尽量靠近中午时段的主要活动或交通节点。`,
    dinner: `请补齐第 ${dayNumber} 天的晚餐安排，优先考虑晚间活动结束后的用餐便利性。`,
    snack: `请为第 ${dayNumber} 天补充加餐或轻食节点，优先覆盖长时段活动间隙或夜间返程前后。`,
    activity: `请补齐第 ${dayNumber} 天的核心活动，避免该天只剩空白时间或仅有交通安排。`,
    reservation: `请重新梳理第 ${dayNumber} 天的安排，明确覆盖未落地预订，并避免与现有时间窗冲突。`,
    "day-plan": `请补齐第 ${dayNumber} 天的完整行程，确保住宿、餐饮、活动和固定预订都能落地。`,
  };

  return manualNotes.trim()
    ? `${reasons[gapType]} 用户补充说明：${manualNotes.trim()}`
    : reasons[gapType];
}
