import type { PlanningResponse, TripWorkspace } from "../types/planning";
import { addDays } from "../utils/tripPlannerForm";
import type { ReservationCoverageItem } from "./tripWorkspaceReservationCoverageHelpers";
import {
  getReservationTargetDays,
  getReservationTargetDaysById,
} from "./tripWorkspaceReservationCoverageHelpers";

export interface DayReadinessItem {
  dayNumber: number;
  date: string;
  status: "ready" | "partial" | "missing" | "pending";
  reservations: number;
  coveredReservations: number;
  unresolvedReservations: number;
  signals: string[];
  gaps: string[];
}

export interface DayReadinessSummary {
  total: number;
  ready: number;
  partial: number;
  missing: number;
  pending: number;
}

export function buildDayReadinessItems(options: {
  workspace: TripWorkspace | null;
  result: PlanningResponse | null;
  reservationCoverageItems: ReservationCoverageItem[];
}): DayReadinessItem[] {
  const { workspace, result, reservationCoverageItems } = options;
  if (!workspace) return [];

  return Array.from({ length: workspace.request_brief.days }, (_, index) => {
    const dayNumber = index + 1;
    const date = addDays(workspace.request_brief.start_date, index);
    const dayPlan = result?.plan.days.find((day) => day.day_number === dayNumber) ?? null;
    const reservationsForDay = workspace.reservations.filter((item) =>
      getReservationTargetDays(item, workspace).includes(dayNumber),
    );
    const reservationStates = reservationCoverageItems.filter((item) =>
      getReservationTargetDaysById(item.id, workspace).includes(dayNumber),
    );
    const coveredReservations = reservationStates.filter(
      (item) => item.status === "covered",
    ).length;
    const unresolvedReservations = reservationStates.filter(
      (item) => item.status === "unresolved",
    ).length;

    if (!result) {
      return {
        dayNumber,
        date,
        status: "pending",
        reservations: reservationsForDay.length,
        coveredReservations: 0,
        unresolvedReservations: 0,
        signals: reservationsForDay.length ? ["已录入预约锚点"] : ["待生成日程"],
        gaps: ["尚未生成当日安排"],
      };
    }

    const hasStay =
      Boolean(dayPlan?.stay.hotel_name?.trim()) ||
      Boolean(dayPlan?.hotel_area?.trim()) ||
      reservationsForDay.some((item) => item.type === "hotel");
    const hasMeal =
      Boolean(dayPlan?.meals.length) ||
      reservationsForDay.some((item) => item.type === "restaurant");
    const hasActivity =
      Boolean(dayPlan?.activities.length) ||
      reservationsForDay.some((item) => item.type === "ticket" || item.type === "other");
    const hasTransportAnchor = reservationsForDay.some(
      (item) => item.type === "flight" || item.type === "train",
    );

    const signals: string[] = [];
    if (hasStay) signals.push("住宿已覆盖");
    if (hasMeal) signals.push("餐饮已覆盖");
    if (hasActivity) signals.push("活动已覆盖");
    if (hasTransportAnchor) signals.push("已有交通锚点");
    if (coveredReservations) signals.push(`已落地预约 ${coveredReservations} 条`);

    const gaps: string[] = [];
    if (!hasStay) gaps.push("缺少住宿安排");
    if (!hasMeal) gaps.push("缺少餐饮安排");
    if (!hasActivity) gaps.push("缺少主要活动");
    if (unresolvedReservations) gaps.push(`有 ${unresolvedReservations} 条预约未落地`);
    if (!dayPlan) gaps.push("未生成当日日程");

    const status: DayReadinessItem["status"] =
      !dayPlan
        ? "missing"
        : gaps.length === 0
          ? "ready"
          : gaps.length <= 2 && signals.length >= 2
            ? "partial"
            : "missing";

    return {
      dayNumber,
      date,
      status,
      reservations: reservationsForDay.length,
      coveredReservations,
      unresolvedReservations,
      signals: signals.length ? signals : ["待补充安排"],
      gaps,
    };
  });
}

export function summarizeDayReadiness(items: DayReadinessItem[]): DayReadinessSummary {
  return {
    total: items.length,
    ready: items.filter((item) => item.status === "ready").length,
    partial: items.filter((item) => item.status === "partial").length,
    missing: items.filter((item) => item.status === "missing").length,
    pending: items.filter((item) => item.status === "pending").length,
  };
}
