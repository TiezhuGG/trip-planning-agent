import type { TripSummary, TripWorkspace } from "../types/planning";

type WorkspaceStatus = TripSummary["status"] | TripWorkspace["status"];

const WORKSPACE_STATUS_LABELS: Record<WorkspaceStatus, string> = {
  draft: "草稿",
  ready: "已就绪",
  action_required: "待处理",
  generating: "生成中",
  error: "异常",
};

const WORKSPACE_STATUS_TEXT_CLASSES: Record<WorkspaceStatus, string> = {
  draft: "text-ink",
  ready: "text-emerald-700",
  action_required: "text-amber-700",
  generating: "text-sky-700",
  error: "text-rose-700",
};

const WORKSPACE_STATUS_FILTER_TONES: Record<WorkspaceStatus, string> = {
  draft: "border-slate-200 bg-slate-100 text-slate-700",
  ready: "border-emerald-200 bg-emerald-50 text-emerald-700",
  action_required: "border-amber-200 bg-amber-50 text-amber-700",
  generating: "border-sky-200 bg-sky-50 text-sky-700",
  error: "border-rose-200 bg-rose-50 text-rose-700",
};

const WORKSPACE_STATUS_BADGE_CLASSES: Record<WorkspaceStatus, string> = {
  draft: "border-slate-200 bg-white text-slate-600",
  ready: "border-emerald-100 bg-emerald-50 text-emerald-700",
  action_required: "border-amber-100 bg-amber-50 text-amber-700",
  generating: "border-sky-100 bg-sky-50 text-sky-700",
  error: "border-rose-100 bg-rose-50 text-rose-700",
};

export function formatWorkspaceStatusLabel(status?: WorkspaceStatus | null): string {
  return status ? WORKSPACE_STATUS_LABELS[status] : "未保存";
}

export function resolveWorkspaceStatusTextClass(status?: WorkspaceStatus | null): string {
  return status ? WORKSPACE_STATUS_TEXT_CLASSES[status] : "text-ink";
}

export function resolveWorkspaceStatusFilterTone(status: WorkspaceStatus): string {
  return WORKSPACE_STATUS_FILTER_TONES[status];
}

export function resolveWorkspaceStatusBadgeClass(status: WorkspaceStatus): string {
  return WORKSPACE_STATUS_BADGE_CLASSES[status];
}

export function formatWorkspaceResultLabel(hasResult: boolean): string {
  return hasResult ? "已生成结果" : "仅草稿";
}

export function formatWorkspaceShareLabel(shareEnabled: boolean): string {
  return shareEnabled ? "分享已开启" : "分享已关闭";
}
