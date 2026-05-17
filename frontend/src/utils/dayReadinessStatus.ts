import type { DayReadinessItem } from "../composables/useTripWorkspaceInsights";

export function formatDayReadinessStatusLabel(status: DayReadinessItem["status"]) {
  if (status === "ready") return "完整";
  if (status === "partial") return "可用";
  if (status === "missing") return "缺口";
  return "待生成";
}

export function resolveDayReadinessStatusClass(status: DayReadinessItem["status"]) {
  if (status === "ready") return "bg-emerald-100 text-emerald-700";
  if (status === "partial") return "bg-sky-100 text-sky-700";
  if (status === "missing") return "bg-amber-100 text-amber-700";
  return "bg-slate-200 text-slate-600";
}
