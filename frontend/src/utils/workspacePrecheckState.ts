import {
  hasRunningPrecheckJob,
  isPrecheckSummaryStale,
  resolveTripWorkspaceExportReadiness,
} from "../composables/tripWorkspaceExportReadiness";
import type { PlanningJobSummary, TripWorkspace } from "../types/planning";

export interface WorkspacePrecheckState {
  label: string;
  className: string;
}

export function resolveWorkspacePrecheckState(
  workspace: TripWorkspace | null,
  jobs: PlanningJobSummary[],
): WorkspacePrecheckState {
  if (!workspace || workspace.status === "draft") {
    return {
      label: "未启用",
      className: "border-slate-200 bg-slate-50 text-slate-600",
    };
  }

  if (hasRunningPrecheckJob(workspace.id, jobs)) {
    return {
      label: "刷新中",
      className: "border-sky-100 bg-sky-50 text-sky-700",
    };
  }

  if (!workspace.last_precheck_summary) {
    return {
      label: "待检查",
      className: "border-amber-100 bg-amber-50 text-amber-700",
    };
  }

  if (isPrecheckSummaryStale(workspace)) {
    return {
      label: "已过期",
      className: "border-amber-100 bg-amber-50 text-amber-700",
    };
  }

  if (resolveTripWorkspaceExportReadiness(workspace, jobs).attentionCount > 0) {
    return {
      label: "需关注",
      className: "border-amber-100 bg-amber-50 text-amber-700",
    };
  }

  return {
    label: "稳定",
    className: "border-emerald-100 bg-emerald-50 text-emerald-700",
  };
}
