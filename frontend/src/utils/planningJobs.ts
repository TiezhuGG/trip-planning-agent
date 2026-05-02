import type { PlanningJob } from "../types/planning";

type LoadJob = (jobId: string) => Promise<PlanningJob>;

const PLANNING_JOB_KIND_LABELS: Record<PlanningJob["kind"], string> = {
  generate_plan: "生成规划",
  update_trip: "更新工作区",
  replan_trip: "重规划",
  precheck_trip: "出发前预检",
};

const PLANNING_JOB_KIND_SUBJECTS: Record<PlanningJob["kind"], string> = {
  generate_plan: "规划",
  update_trip: "工作区更新",
  replan_trip: "重规划",
  precheck_trip: "出发前预检",
};

const PLANNING_JOB_STATUS_LABELS: Record<PlanningJob["status"], string> = {
  queued: "排队中",
  running: "进行中",
  succeeded: "已完成",
  failed: "失败",
};

const PLANNING_JOB_STATUS_BADGE_CLASSES: Record<PlanningJob["status"], string> = {
  queued: "border-amber-100 bg-amber-50 text-amber-700",
  running: "border-sky-100 bg-sky-50 text-sky-700",
  succeeded: "border-emerald-100 bg-emerald-50 text-emerald-700",
  failed: "border-rose-100 bg-rose-50 text-rose-700",
};

export function formatPlanningJobKind(kind: PlanningJob["kind"]): string {
  return PLANNING_JOB_KIND_LABELS[kind];
}

export function formatPlanningJobStatus(status: PlanningJob["status"]): string {
  return PLANNING_JOB_STATUS_LABELS[status];
}

export function resolvePlanningJobStatusBadgeClass(status: PlanningJob["status"]): string {
  return PLANNING_JOB_STATUS_BADGE_CLASSES[status];
}

export function isPlanningJobActiveStatus(status: PlanningJob["status"]): boolean {
  return status === "queued" || status === "running";
}

export function isPlanningJobActive(
  job: Pick<PlanningJob, "status">,
): boolean {
  return isPlanningJobActiveStatus(job.status);
}

export function canRetryPlanningJob(job: Pick<PlanningJob, "kind" | "status">): boolean {
  return job.status === "failed" && ["update_trip", "precheck_trip"].includes(job.kind);
}

export function formatPlanningJobDuration(
  job: Pick<PlanningJob, "started_at" | "updated_at" | "completed_at">,
): string {
  if (!job.started_at) return "未开始";

  const startedAt = new Date(job.started_at).getTime();
  const endedAt = new Date(job.completed_at ?? job.updated_at).getTime();
  if (Number.isNaN(startedAt) || Number.isNaN(endedAt) || endedAt < startedAt) {
    return "时长未知";
  }

  const totalSeconds = Math.round((endedAt - startedAt) / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) return `${seconds} 秒`;
  return `${minutes} 分 ${seconds} 秒`;
}

export async function waitForPlanningJob(
  jobId: string,
  loadJob: LoadJob,
  options: {
    intervalMs?: number;
    timeoutMs?: number;
    onProgress?: (job: PlanningJob) => void;
  } = {},
): Promise<PlanningJob> {
  const intervalMs = options.intervalMs ?? 1000;
  const timeoutMs = options.timeoutMs ?? 120000;
  const startedAt = Date.now();

  while (true) {
    const job = await loadJob(jobId);
    options.onProgress?.(job);

    if (job.status === "succeeded") {
      return job;
    }
    if (job.status === "failed") {
      throw new Error(job.error_message || "任务执行失败");
    }
    if (Date.now() - startedAt >= timeoutMs) {
      throw new Error("任务执行超时，请稍后重试。");
    }
    await delay(intervalMs);
  }
}

export function humanizePlanningJobProgress(
  job: Pick<PlanningJob, "kind" | "status" | "progress_message">,
): string {
  const message = job.progress_message.trim();
  if (!message) {
    return fallbackPlanningJobProgress(job);
  }

  const knownMessages: Record<string, string> = {
    "Planning job queued.": "已提交规划任务，正在排队。",
    "Planning in progress.": "正在生成规划，请稍候。",
    "Planning completed.": "规划已生成，正在整理结果。",
    "Workspace refresh job queued.": "已提交工作区更新任务，正在排队。",
    "Workspace refresh in progress.": "正在更新工作区并重新生成结果。",
    "Workspace refresh completed.": "工作区已更新完成。",
    "Replan job queued.": "已提交重规划任务，正在排队。",
    "Replan in progress.": "正在重排行程，请稍候。",
    "Replan completed.": "重规划已完成，正在刷新视图。",
    "Precheck job queued.": "已提交出发前预检任务，正在排队。",
    "Precheck in progress.": "正在刷新出发前预检。",
    "Precheck completed.": "出发前预检已刷新完成。",
    "Job failed.": "任务执行失败。",
  };

  return knownMessages[message] ?? message;
}

function fallbackPlanningJobProgress(
  job: Pick<PlanningJob, "kind" | "status">,
): string {
  if (job.status === "failed") {
    return "任务执行失败。";
  }
  if (job.status === "succeeded") {
    return "任务已完成。";
  }

  return job.status === "queued"
    ? `${PLANNING_JOB_KIND_SUBJECTS[job.kind]}任务已提交，正在排队。`
    : `${PLANNING_JOB_KIND_SUBJECTS[job.kind]}进行中。`;
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
