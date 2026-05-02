import type { PrecheckSummaryItem } from "../types/planning";

type PrecheckStatus = PrecheckSummaryItem["after_status"];

export function formatPrecheckStatusLabel(status: PrecheckStatus) {
  if (status === "ok") return "正常";
  if (status === "warning") return "需关注";
  return "待补齐";
}

export function resolvePrecheckStatusBadgeClass(status: PrecheckStatus) {
  if (status === "ok") return "bg-emerald-100 text-emerald-700";
  if (status === "warning") return "bg-amber-100 text-amber-700";
  return "bg-slate-200 text-slate-600";
}
