import {
  collectPrecheckAffectedDays,
  resolveTripWorkspaceExportReadiness,
} from "./tripWorkspaceExportReadiness";
import { getReservationTargetDaysById } from "./tripWorkspaceReservationCoverageHelpers";
import type {
  DayReadinessItem,
  DayReadinessSummary,
  DeparturePrecheckSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "./useTripWorkspaceInsights";
import type { PlanningJobSummary, TripWorkspace } from "../types/planning";
import { canRetryPlanningJob } from "../utils/planningJobs";

export interface WorkspaceCompletionDimension {
  key: "days" | "reservations" | "precheck" | "export";
  title: string;
  score: number;
  tone: "success" | "info" | "warning";
  summary: string;
}

export interface WorkspaceCompletionOverview {
  score: number;
  statusLabel: string;
  summary: string;
  dimensions: WorkspaceCompletionDimension[];
  incompleteDayNumbers: number[];
  unresolvedReservationDayNumbers: number[];
  precheckAffectedDayNumbers: number[];
  canRefreshPrecheck: boolean;
}

export function buildWorkspaceCompletionOverview(options: {
  workspace: TripWorkspace | null;
  jobs: PlanningJobSummary[];
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  departurePrecheckSummary: DeparturePrecheckSummary;
}): WorkspaceCompletionOverview | null {
  const {
    workspace,
    jobs,
    dayReadinessSummary,
    dayReadinessItems,
    reservationCoverageSummary,
    reservationCoverageItems,
    departurePrecheckSummary,
  } = options;

  if (!workspace) {
    return null;
  }

  const incompleteDayNumbers = dayReadinessItems
    .filter((item) => item.status !== "ready")
    .map((item) => item.dayNumber);

  const unresolvedReservationDayNumbers = [
    ...new Set(
      reservationCoverageItems
        .filter((item) => item.status === "unresolved" || item.status === "pending")
        .flatMap((item) => getReservationTargetDaysById(item.id, workspace)),
    ),
  ].sort((left, right) => left - right);

  const precheckAffectedDayNumbers = collectPrecheckAffectedDays(workspace);
  const exportReadiness = resolveTripWorkspaceExportReadiness(workspace, jobs);

  const dayScore = scoreFromDayReadiness(dayReadinessSummary);
  const reservationScore = scoreFromReservationCoverage(reservationCoverageSummary);
  const precheckScore = scoreFromPrecheck(departurePrecheckSummary);
  const exportScore = scoreFromExportReadiness(exportReadiness.tone, exportReadiness.attentionCount);

  const retryableFailedJobs = jobs.filter(
    (job) => job.trip_id === workspace.id && canRetryPlanningJob(job),
  );

  const baseScore = average([dayScore, reservationScore, precheckScore, exportScore]);
  const penalty = Math.min(retryableFailedJobs.length * 8, 18);
  const score = clampScore(Math.round(baseScore - penalty));

  const dimensions: WorkspaceCompletionDimension[] = [
    {
      key: "days",
      title: "日程完整度",
      score: dayScore,
      tone: toneFromScore(dayScore),
      summary:
        dayReadinessSummary.total > 0
          ? `${dayReadinessSummary.ready}/${dayReadinessSummary.total} 天已就绪`
          : "尚无日程",
    },
    {
      key: "reservations",
      title: "预订落地",
      score: reservationScore,
      tone: toneFromScore(reservationScore),
      summary:
        reservationCoverageSummary.total > 0
          ? `${reservationCoverageSummary.covered}/${reservationCoverageSummary.total} 条已落地`
          : "当前没有固定预订",
    },
    {
      key: "precheck",
      title: "预检状态",
      score: precheckScore,
      tone: toneFromScore(precheckScore),
      summary:
        departurePrecheckSummary.total > 0
          ? `${departurePrecheckSummary.ok} 项正常，${departurePrecheckSummary.warning} 项需关注`
          : "尚无预检摘要",
    },
    {
      key: "export",
      title: "导出准备",
      score: exportScore,
      tone: toneFromScore(exportScore),
      summary: exportReadiness.title,
    },
  ];

  return {
    score,
    statusLabel: resolveStatusLabel(score),
    summary: buildOverviewSummary({
      score,
      retryableFailedJobCount: retryableFailedJobs.length,
      incompleteDayCount: incompleteDayNumbers.length,
      unresolvedReservationCount:
        reservationCoverageSummary.unresolved + reservationCoverageSummary.pending,
      precheckWarningCount: departurePrecheckSummary.warning + departurePrecheckSummary.pending,
    }),
    dimensions,
    incompleteDayNumbers,
    unresolvedReservationDayNumbers,
    precheckAffectedDayNumbers,
    canRefreshPrecheck:
      workspace.status !== "draft" &&
      (departurePrecheckSummary.warning + departurePrecheckSummary.pending > 0 ||
        exportReadiness.tone !== "ok"),
  };
}

function scoreFromDayReadiness(summary: DayReadinessSummary) {
  if (!summary.total) return 0;
  return clampScore(
    Math.round(((summary.ready + summary.partial * 0.6 + summary.pending * 0.2) / summary.total) * 100),
  );
}

function scoreFromReservationCoverage(summary: ReservationCoverageSummary) {
  if (!summary.total) return 100;
  return clampScore(
    Math.round(((summary.covered + summary.pending * 0.25) / summary.total) * 100),
  );
}

function scoreFromPrecheck(summary: DeparturePrecheckSummary) {
  if (!summary.total) return 30;
  return clampScore(
    Math.round(((summary.ok + summary.warning * 0.45 + summary.pending * 0.15) / summary.total) * 100),
  );
}

function scoreFromExportReadiness(
  tone: "ok" | "warning" | "progress",
  attentionCount: number,
) {
  if (tone === "ok") return 100;
  if (tone === "progress") return 45;
  return clampScore(Math.max(30, 68 - attentionCount * 10));
}

function toneFromScore(score: number): WorkspaceCompletionDimension["tone"] {
  if (score >= 85) return "success";
  if (score >= 60) return "info";
  return "warning";
}

function resolveStatusLabel(score: number) {
  if (score >= 85) return "接近可分享";
  if (score >= 65) return "接近完成";
  if (score >= 45) return "仍需整理";
  return "待补齐";
}

function buildOverviewSummary(options: {
  score: number;
  retryableFailedJobCount: number;
  incompleteDayCount: number;
  unresolvedReservationCount: number;
  precheckWarningCount: number;
}) {
  const {
    score,
    retryableFailedJobCount,
    incompleteDayCount,
    unresolvedReservationCount,
    precheckWarningCount,
  } = options;

  const blockers: string[] = [];
  if (retryableFailedJobCount > 0) {
    blockers.push(`${retryableFailedJobCount} 个失败任务`);
  }
  if (precheckWarningCount > 0) {
    blockers.push(`${precheckWarningCount} 个预检关注项`);
  }
  if (unresolvedReservationCount > 0) {
    blockers.push(`${unresolvedReservationCount} 条预订未落地`);
  }
  if (incompleteDayCount > 0) {
    blockers.push(`${incompleteDayCount} 天日程未就绪`);
  }

  if (!blockers.length) {
    return score >= 85
      ? "当前工作区已经比较完整，可以优先复核后导出或分享。"
      : "当前工作区状态稳定，可以继续做细节优化。";
  }

  return `当前主要卡点：${blockers.slice(0, 3).join("；")}。`;
}

function average(values: number[]) {
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function clampScore(value: number) {
  return Math.max(0, Math.min(100, value));
}
