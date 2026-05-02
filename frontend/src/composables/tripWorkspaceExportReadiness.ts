import type {
  CalendarExportScope,
  PlanningJobSummary,
  PrecheckSummary,
  TripWorkspace,
} from "../types/planning";
import {
  canRetryPlanningJob,
  formatPlanningJobKind,
  isPlanningJobActive,
} from "../utils/planningJobs";
import { formatDateTimeZhCn } from "../utils/workspaceFormatting";

export type ExportReadinessTone = "ok" | "warning" | "progress";

export interface ExportReadinessState {
  tone: ExportReadinessTone;
  title: string;
  detail: string;
  attentionCount: number;
}

export type WorkspaceNextStepTone = "info" | "warning" | "success" | "progress";

export type WorkspaceNextStepAction =
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
      kind: "focus-days";
      label: string;
      emphasis: "primary" | "secondary";
      dayNumbers: number[];
    }
  | {
      kind: "export-calendar";
      label: string;
      emphasis: "primary" | "secondary";
      scope: CalendarExportScope;
    };

export interface WorkspaceNextStepState {
  tone: WorkspaceNextStepTone;
  title: string;
  detail: string;
  actions: WorkspaceNextStepAction[];
}

export function resolveTripWorkspaceExportReadiness(
  workspace: TripWorkspace | null,
  jobs: PlanningJobSummary[],
): ExportReadinessState {
  if (!workspace) {
    return {
      tone: "warning",
      title: "请先保存工作区",
      detail: "保存后再导出日历，能拿到更稳定的行程版本和预检状态。",
      attentionCount: 0,
    };
  }

  if (hasRunningPrecheckJob(workspace.id, jobs)) {
    return {
      tone: "progress",
      title: "预检正在后台刷新",
      detail: "检测到新的出发前预检任务正在执行，建议等完成后再导出。",
      attentionCount: 0,
    };
  }

  const summary = workspace.last_precheck_summary;
  if (!summary) {
    return {
      tone: "warning",
      title: "建议导出前先刷新预检",
      detail: "当前还没有出发前预检结果，导出后请手动核对天气、路线和预订落地情况。",
      attentionCount: 0,
    };
  }

  if (isPrecheckSummaryStale(workspace)) {
    return {
      tone: "warning",
      title: "最近一次预检已经过期",
      detail: "工作区在上次预检后又发生过变更，建议等待自动预检完成或手动刷新一次。",
      attentionCount: countPrecheckAttentionItems(summary),
    };
  }

  const attentionCount = countPrecheckAttentionItems(summary);
  if (!attentionCount) {
    return {
      tone: "ok",
      title: "当前适合直接导出",
      detail: `最近一次预检时间为 ${formatDateTime(summary.created_at)}，未发现待处理问题。`,
      attentionCount,
    };
  }

  return {
    tone: "warning",
    title: `最近一次预检仍有 ${attentionCount} 项待关注`,
    detail: summary.items
      .filter((item) => item.after_status === "warning" || item.after_status === "pending")
      .slice(0, 2)
      .map((item) => `${item.title}：${item.after_summary}`)
      .join("；"),
    attentionCount,
  };
}

export function resolveTripWorkspaceNextStep(
  workspace: TripWorkspace | null,
  jobs: PlanningJobSummary[],
): WorkspaceNextStepState | null {
  if (!workspace) {
    return null;
  }

  const retryableFailedJob =
    jobs.find(
      (job) =>
        job.trip_id === workspace.id &&
        canRetryPlanningJob(job),
    ) ?? null;

  if (retryableFailedJob) {
    return {
      tone: "warning",
      title: "先恢复失败任务",
      detail:
        retryableFailedJob.error_message ||
        `${formatJobKind(retryableFailedJob.kind)}失败，建议先重试，避免后续判断仍基于旧状态。`,
      actions: [
        {
          kind: "retry-job",
          label: `重试${formatJobKind(retryableFailedJob.kind)}`,
          emphasis: "primary",
          job: retryableFailedJob,
        },
        ...buildFocusChangedDaysAction(workspace, "查看最近改动", "secondary"),
      ],
    };
  }

  if (hasRunningPrecheckJob(workspace.id, jobs)) {
    return {
      tone: "progress",
      title: "等待预检刷新完成",
      detail: "新的出发前预检正在后台执行，完成后再决定是否导出或继续调整更稳妥。",
      actions: buildFocusChangedDaysAction(workspace, "先看最近改动", "secondary"),
    };
  }

  const readiness = resolveTripWorkspaceExportReadiness(workspace, jobs);
  const precheckAffectedDays = collectPrecheckAffectedDays(workspace);

  if (!workspace.last_precheck_summary || isPrecheckSummaryStale(workspace)) {
    return {
      tone: "warning",
      title: "建议先刷新预检",
      detail: readiness.detail,
      actions: [
        { kind: "refresh-precheck", label: "刷新预检", emphasis: "primary" },
        ...(precheckAffectedDays.length
          ? [
              {
                kind: "focus-days" as const,
                label: "查看受影响日期",
                emphasis: "secondary" as const,
                dayNumbers: precheckAffectedDays,
              },
            ]
          : buildFocusChangedDaysAction(workspace, "查看最近改动", "secondary")),
      ],
    };
  }

  if (readiness.attentionCount > 0) {
    return {
      tone: "warning",
      title: "先处理预检关注项",
      detail: readiness.detail,
      actions: [
        ...(precheckAffectedDays.length
          ? [
              {
                kind: "focus-days" as const,
                label: "定位关注日期",
                emphasis: "primary" as const,
                dayNumbers: precheckAffectedDays,
              },
            ]
          : []),
        { kind: "refresh-precheck", label: "重新刷新预检", emphasis: "secondary" },
      ],
    };
  }

  const latestReplanDays = workspace.last_replan_summary?.target_days ?? [];
  if (latestReplanDays.length) {
    return {
      tone: "info",
      title: "建议复核最近改动",
      detail: `最近一次重规划影响了 ${latestReplanDays.length} 天，确认无误后再分享或导出更合适。`,
      actions: [
        {
          kind: "focus-days",
          label: "查看改动日期",
          emphasis: "primary",
          dayNumbers: latestReplanDays,
        },
        {
          kind: "export-calendar",
          label: "直接导出日历",
          emphasis: "secondary",
          scope: "full",
        },
      ],
    };
  }

  if (readiness.tone === "ok") {
    return {
      tone: "success",
      title: "工作区已可导出",
      detail: readiness.detail,
      actions: [
        {
          kind: "export-calendar",
          label: "导出完整日历",
          emphasis: "primary",
          scope: "full",
        },
      ],
    };
  }

  return null;
}

export function buildCalendarExportNotice(
  workspace: TripWorkspace,
  scope: CalendarExportScope,
  jobs: PlanningJobSummary[],
): { tone: "success" | "warning"; title: string; messages: string[] } {
  const readiness = resolveTripWorkspaceExportReadiness(workspace, jobs);
  const baseMessage =
    scope === "full"
      ? "已导出完整日历，包含预订和生成行程。"
      : scope === "reservations"
        ? "已导出预订日历，适合提醒固定安排。"
        : "已导出行程日历，适合单独查看生成安排。";

  if (readiness.tone === "ok") {
    return {
      tone: "success",
      title: "日历文件已导出",
      messages: [baseMessage, "最近一次出发前预检未发现待处理问题。"],
    };
  }

  return {
    tone: "warning",
    title: "日历文件已导出",
    messages:
      readiness.tone === "progress"
        ? [baseMessage, "检测到出发前预检仍在后台刷新，建议完成后再核对最终版本。"]
        : [baseMessage, readiness.detail],
  };
}

export function exportReadinessClass(tone: ExportReadinessTone) {
  if (tone === "ok") return "border-emerald-100 bg-emerald-50/70 text-emerald-800";
  if (tone === "progress") return "border-sky-100 bg-sky-50/80 text-sky-800";
  return "border-amber-100 bg-amber-50/80 text-amber-800";
}

export function workspaceNextStepClass(tone: WorkspaceNextStepTone) {
  if (tone === "success") return "border-emerald-100 bg-emerald-50/70 text-emerald-900";
  if (tone === "progress") return "border-sky-100 bg-sky-50/80 text-sky-900";
  if (tone === "warning") return "border-amber-100 bg-amber-50/80 text-amber-900";
  return "border-[#dbe5ef] bg-[#f8fbfd] text-slate-900";
}

export function countPrecheckAttentionItems(summary: PrecheckSummary) {
  return summary.items.filter(
    (item) => item.after_status === "warning" || item.after_status === "pending",
  ).length;
}

export function hasRunningPrecheckJob(tripId: string, jobs: PlanningJobSummary[]) {
  if (!tripId) return false;
  return jobs.some(
    (job) =>
      job.trip_id === tripId &&
      job.kind === "precheck_trip" &&
      isPlanningJobActive(job),
  );
}

export function isPrecheckSummaryStale(workspace: TripWorkspace) {
  if (!workspace.last_precheck_summary) {
    return false;
  }

  const updatedAt = new Date(workspace.updated_at).getTime();
  const precheckedAt = new Date(workspace.last_precheck_summary.created_at).getTime();
  if (Number.isNaN(updatedAt) || Number.isNaN(precheckedAt)) {
    return false;
  }

  return updatedAt > precheckedAt;
}

export function collectPrecheckAffectedDays(workspace: TripWorkspace) {
  const summary = workspace.last_precheck_summary;
  if (!summary) {
    return [];
  }

  return [
    ...new Set(
      summary.items.flatMap((item) => (item.after_days.length ? item.after_days : item.before_days)),
    ),
  ].sort((left, right) => left - right);
}

function buildFocusChangedDaysAction(
  workspace: TripWorkspace,
  label: string,
  emphasis: "primary" | "secondary",
) {
  const dayNumbers = workspace.last_replan_summary?.target_days ?? [];
  return dayNumbers.length
    ? [
        {
          kind: "focus-days" as const,
          label,
          emphasis,
          dayNumbers,
        },
      ]
    : [];
}

function formatJobKind(kind: PlanningJobSummary["kind"]) {
  return formatPlanningJobKind(kind);
}

function formatDateTime(value?: string | null) {
  return formatDateTimeZhCn(value);
}
