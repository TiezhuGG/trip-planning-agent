<script setup lang="ts">
import { computed } from "vue";

import {
  collectPrecheckAffectedDays,
  countPrecheckAttentionItems,
  hasRunningPrecheckJob,
  isPrecheckSummaryStale,
} from "../composables/tripWorkspaceExportReadiness";
import { getReservationTargetDaysById } from "../composables/tripWorkspaceReservationCoverageHelpers";
import type {
  DayGapRepairPayload,
  DayReadinessItem,
  DayReadinessSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";
import type { PlanningJobSummary, TripWorkspace } from "../types/planning";
import { canRetryPlanningJob, formatPlanningJobKind } from "../utils/planningJobs";
import { sortUniqueNumbers } from "../utils/workspaceFormatting";

type ChecklistAction =
  | {
      kind: "focus-days";
      label: string;
      emphasis: "primary" | "secondary";
      dayNumbers: number[];
    }
  | {
      kind: "retry-job";
      label: string;
      emphasis: "primary" | "secondary";
      job: PlanningJobSummary;
    }
  | {
      kind: "refresh-precheck";
      label: string;
      emphasis: "primary" | "secondary";
    }
  | {
      kind: "repair-day-gap";
      label: string;
      emphasis: "primary" | "secondary";
      payload: DayGapRepairPayload;
    };

type ChecklistItem = {
  key: string;
  tone: "warning" | "info";
  title: string;
  detail: string;
  actions: ChecklistAction[];
};

const props = defineProps<{
  workspace: TripWorkspace | null;
  jobs: PlanningJobSummary[];
  prechecking: boolean;
  retryingJobId: string;
  replanningDays: number[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
}>();

const emit = defineEmits<{
  (event: "focus-days", dayNumbers: number[]): void;
  (event: "retry-job", job: PlanningJobSummary): void;
  (event: "refresh-precheck"): void;
  (event: "repair-day-gap", payload: DayGapRepairPayload): void;
}>();

const checklistItems = computed<ChecklistItem[]>(() => {
  const workspace = props.workspace;
  if (!workspace) {
    return [];
  }

  const items: ChecklistItem[] = [];
  const retryableFailedJobs = props.jobs.filter(
    (job) => job.trip_id === workspace.id && canRetryPlanningJob(job),
  );

  if (retryableFailedJobs.length) {
    const firstJob = retryableFailedJobs[0];
    items.push({
      key: "failed-jobs",
      tone: "warning",
      title: `有 ${retryableFailedJobs.length} 个后台任务失败`,
      detail:
        firstJob.error_message ||
        `${formatJobKind(firstJob.kind)}失败，建议先重试，避免后续判断继续基于旧状态。`,
      actions: [
        {
          kind: "retry-job",
          label: `重试${formatJobKind(firstJob.kind)}`,
          emphasis: "primary",
          job: firstJob,
        },
      ],
    });
  }

  const precheckAttentionCount = workspace.last_precheck_summary
    ? countPrecheckAttentionItems(workspace.last_precheck_summary)
    : 0;
  const needsPrecheckRefresh =
    workspace.status !== "draft" &&
    !hasRunningPrecheckJob(workspace.id, props.jobs) &&
    (!workspace.last_precheck_summary ||
      isPrecheckSummaryStale(workspace) ||
      precheckAttentionCount > 0);

  if (needsPrecheckRefresh) {
    const affectedDays = collectPrecheckAffectedDays(workspace);
    items.push({
      key: "precheck",
      tone: "warning",
      title: workspace.last_precheck_summary ? "预检结果需要更新" : "还没有预检结果",
      detail: workspace.last_precheck_summary
        ? precheckAttentionCount > 0
          ? `最近一次预检仍有 ${precheckAttentionCount} 项待关注，建议刷新后再继续。`
          : "工作区在上次预检后发生过变更，建议重新刷新。"
        : "建议先运行一次出发前预检，再决定是否导出或分享。",
      actions: [
        { kind: "refresh-precheck", label: "刷新预检", emphasis: "primary" },
        ...(affectedDays.length
          ? [
              {
                kind: "focus-days" as const,
                label: "查看受影响日期",
                emphasis: "secondary" as const,
                dayNumbers: affectedDays,
              },
            ]
          : []),
      ],
    });
  }

  if (
    props.reservationCoverageSummary.unresolved > 0 ||
    props.reservationCoverageSummary.pending > 0
  ) {
    const unresolvedItems = props.reservationCoverageItems.filter(
      (item) => item.status === "unresolved" || item.status === "pending",
    );
    const unresolvedDays = uniqueSorted(
      unresolvedItems.flatMap((item) =>
        workspace ? getReservationTargetDaysById(item.id, workspace) : [],
      ),
    );
    const firstDay = unresolvedDays[0];

    items.push({
      key: "reservation-coverage",
      tone: "warning",
      title: `有 ${unresolvedItems.length} 条预订尚未完全落地`,
      detail:
        unresolvedItems
          .slice(0, 2)
          .map((item) => item.title)
          .join("、") || "还有预订需要回写到具体行程日期。",
      actions: [
        ...(unresolvedDays.length
          ? [
              {
                kind: "focus-days" as const,
                label: "查看相关日期",
                emphasis: "primary" as const,
                dayNumbers: unresolvedDays,
              },
            ]
          : []),
        ...(typeof firstDay === "number"
          ? [
              {
                kind: "repair-day-gap" as const,
                label: `修复第 ${firstDay} 天预订落地`,
                emphasis: "secondary" as const,
                payload: {
                  dayNumber: firstDay,
                  gapType: "reservation" as const,
                  actionLabelOverride: "落地固定预订",
                },
              },
            ]
          : []),
      ],
    });
  }

  const incompleteDays = props.dayReadinessItems.filter((item) => item.status !== "ready");
  if (incompleteDays.length) {
    const firstActionableDay = incompleteDays.find(
      (item) => item.actions.length > 0 && !props.replanningDays.includes(item.dayNumber),
    );

    items.push({
      key: "day-readiness",
      tone: "info",
      title: `还有 ${incompleteDays.length} 天的日程未完全就绪`,
      detail: incompleteDays
        .slice(0, 2)
        .map((item) => `第 ${item.dayNumber} 天：${item.gaps[0] ?? "仍需补充"}`)
        .join("；"),
      actions: [
        {
          kind: "focus-days",
          label: "查看未就绪日期",
          emphasis: "primary",
          dayNumbers: incompleteDays.map((item) => item.dayNumber),
        },
        ...(firstActionableDay
          ? [
              {
                kind: "repair-day-gap" as const,
                label: firstActionableDay.actions[0].label,
                emphasis: "secondary" as const,
                payload: {
                  dayNumber: firstActionableDay.dayNumber,
                  gapType: firstActionableDay.actions[0].gapType,
                  reasonOverride: firstActionableDay.actions[0].reason,
                  actionLabelOverride: firstActionableDay.actions[0].label,
                },
              },
            ]
          : []),
      ],
    });
  }

  return items.slice(0, 4);
});

function uniqueSorted(dayNumbers: number[]) {
  return sortUniqueNumbers(dayNumbers);
}

function formatJobKind(kind: PlanningJobSummary["kind"]) {
  return formatPlanningJobKind(kind);
}

function itemClass(tone: ChecklistItem["tone"]) {
  return tone === "warning"
    ? "border-amber-100 bg-amber-50/70"
    : "border-[#dbe5ef] bg-[#f8fbfd]";
}

function itemToneLabel(tone: ChecklistItem["tone"]) {
  return tone === "warning" ? "优先处理" : "继续完善";
}

function itemToneClass(tone: ChecklistItem["tone"]) {
  return tone === "warning"
    ? "bg-amber-100 text-amber-700"
    : "bg-sky-100 text-sky-700";
}

function actionClass(action: ChecklistAction) {
  return action.emphasis === "primary"
    ? "border-[#16324d] bg-[#16324d] text-white hover:bg-[#22486d]"
    : "border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]";
}

function actionDisabled(action: ChecklistAction) {
  if (action.kind === "retry-job") {
    return props.retryingJobId === action.job.id;
  }
  if (action.kind === "refresh-precheck") {
    return props.prechecking;
  }
  if (action.kind === "repair-day-gap") {
    return props.replanningDays.includes(action.payload.dayNumber);
  }
  return false;
}

function actionLabel(action: ChecklistAction) {
  if (action.kind === "retry-job" && props.retryingJobId === action.job.id) {
    return "重试中...";
  }
  if (action.kind === "refresh-precheck" && props.prechecking) {
    return "刷新中...";
  }
  if (
    action.kind === "repair-day-gap" &&
    props.replanningDays.includes(action.payload.dayNumber)
  ) {
    return "处理中...";
  }
  return action.label;
}

function triggerAction(action: ChecklistAction) {
  switch (action.kind) {
    case "focus-days":
      emit("focus-days", action.dayNumbers);
      return;
    case "retry-job":
      emit("retry-job", action.job);
      return;
    case "refresh-precheck":
      emit("refresh-precheck");
      return;
    case "repair-day-gap":
      emit("repair-day-gap", action.payload);
  }
}
</script>

<template>
  <section
    v-if="checklistItems.length"
    class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="font-medium text-ink">待办清单</div>
        <div class="mt-1 text-xs text-slate-500">
          把仍未收口的问题拆成可执行动作，按优先级逐项处理。
        </div>
      </div>
      <div class="text-xs text-slate-500">{{ checklistItems.length }} 项待处理</div>
    </div>

    <div class="mt-4 space-y-3">
      <article
        v-for="item in checklistItems"
        :key="item.key"
        class="rounded-[18px] border px-4 py-4"
        :class="itemClass(item.tone)"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <div class="font-medium text-ink">{{ item.title }}</div>
              <span
                class="rounded-full px-2.5 py-1 text-[11px]"
                :class="itemToneClass(item.tone)"
              >
                {{ itemToneLabel(item.tone) }}
              </span>
            </div>
            <div class="mt-1 text-xs leading-5 text-slate-600">{{ item.detail }}</div>
          </div>
        </div>

        <div v-if="item.actions.length" class="mt-3 flex flex-wrap gap-3">
          <button
            v-for="action in item.actions"
            :key="`${item.key}-${action.kind}-${action.label}`"
            type="button"
            class="rounded-full border px-3 py-1.5 text-xs transition disabled:cursor-not-allowed disabled:opacity-60"
            :class="actionClass(action)"
            :disabled="actionDisabled(action)"
            @click="triggerAction(action)"
          >
            {{ actionLabel(action) }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>
