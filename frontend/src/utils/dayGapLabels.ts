import type { ReplanSummary } from "../types/planning";
import type { DayGapType } from "../composables/tripWorkspaceDayReadinessHelpers";

type GapLabelKey = DayGapType | NonNullable<ReplanSummary["repair_gap"]>;

const DAY_GAP_LABELS: Record<GapLabelKey, string> = {
  stay: "住宿",
  meal: "餐饮",
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  snack: "加餐",
  activity: "活动",
  reservation: "预订",
  "day-plan": "日程",
};

export function formatDayGapLabel(value?: GapLabelKey | null): string {
  if (!value) return "--";
  return DAY_GAP_LABELS[value] ?? value;
}
