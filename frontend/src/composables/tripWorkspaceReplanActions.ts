import type { Ref } from "vue";

import { replanTripWorkspace } from "../api/planning";
import type { TripWorkspace } from "../types/planning";
import {
  ensureCurrentWorkspace,
  type NoticeTone,
  toActionErrorMessage,
} from "./tripWorkspaceActionHelpers";

export function createTripWorkspaceReplanActions(options: {
  currentTrip: Ref<TripWorkspace | null>;
  tripNotes: Ref<string>;
  tripReplanning: Ref<boolean>;
  replanningDays: Ref<number[]>;
  showDevPanels: boolean;
  applyWorkspace: (workspace: TripWorkspace, options?: { syncUrl?: boolean }) => void;
  openNotice: (tone: NoticeTone, title: string, messages: string[]) => void;
}) {
  const {
    currentTrip,
    tripNotes,
    tripReplanning,
    replanningDays,
    showDevPanels,
    applyWorkspace,
    openNotice,
  } = options;

  function beginDayReplan(dayNumber: number) {
    replanningDays.value = [...new Set([...replanningDays.value, dayNumber])];
  }

  function endDayReplan(dayNumber: number) {
    replanningDays.value = replanningDays.value.filter((item) => item !== dayNumber);
  }

  async function replanDay(dayNumber: number) {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先等待行程结果保存完成。",
    );
    if (!workspace) {
      return;
    }

    beginDayReplan(dayNumber);
    try {
      const nextWorkspace = await replanTripWorkspace(workspace.id, {
        scope: "day",
        day_numbers: [dayNumber],
        reason: tripNotes.value || null,
        include_debug: showDevPanels,
      });
      applyWorkspace(nextWorkspace, { syncUrl: false });
      openNotice("success", "单日重规划完成", [`第 ${dayNumber} 天已更新。`]);
    } catch (error) {
      const message = toActionErrorMessage(error, "重规划失败，请稍后重试。");
      openNotice("error", "单日重规划失败", [message]);
    } finally {
      endDayReplan(dayNumber);
    }
  }

  async function replanUnlockedDays() {
    const workspace = ensureCurrentWorkspace(
      currentTrip,
      openNotice,
      "请先等待行程结果保存完成。",
    );
    if (!workspace) {
      return;
    }

    tripReplanning.value = true;
    try {
      const nextWorkspace = await replanTripWorkspace(workspace.id, {
        scope: "trip",
        day_numbers: [],
        preserve_locked_days: true,
        reason: tripNotes.value || null,
        include_debug: showDevPanels,
      });
      applyWorkspace(nextWorkspace, { syncUrl: false });
      openNotice("success", "整趟重规划完成", ["未锁定日期已刷新。"]);
    } catch (error) {
      const message = toActionErrorMessage(error, "重规划失败，请稍后重试。");
      openNotice("error", "整趟重规划失败", [message]);
    } finally {
      tripReplanning.value = false;
    }
  }

  return {
    replanDay,
    replanUnlockedDays,
  };
}
