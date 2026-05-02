import type {
  DayPlan,
  PlanningResponse,
  ReservationItem,
  TripWorkspace,
} from "../types/planning";
import { addDays } from "../utils/tripPlannerForm";
import type { ReservationCoverageItem } from "./tripWorkspaceReservationCoverageHelpers";
import {
  getReservationTargetDays,
  getReservationTargetDaysById,
} from "./tripWorkspaceReservationCoverageHelpers";

export type DayGapType =
  | "stay"
  | "meal"
  | "breakfast"
  | "lunch"
  | "dinner"
  | "snack"
  | "activity"
  | "reservation"
  | "day-plan";

export interface DayGapRepairPayload {
  dayNumber: number;
  gapType: DayGapType;
  reasonOverride?: string;
  actionLabelOverride?: string;
}

export interface DayReadinessAction {
  gapType: DayGapType;
  label: string;
  reason: string;
}

export interface DayReadinessItem {
  dayNumber: number;
  date: string;
  status: "ready" | "partial" | "missing" | "pending";
  reservations: number;
  coveredReservations: number;
  unresolvedReservations: number;
  signals: string[];
  coordinationSummary: string;
  gaps: string[];
  actions: DayReadinessAction[];
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
  if (!workspace) {
    return [];
  }

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
    const coveredReservations = reservationStates.filter((item) => item.status === "covered").length;
    const unresolvedReservations = reservationStates.filter((item) => item.status === "unresolved").length;
    const coordinatedReservations = reservationStates.filter((item) =>
      item.coordinatedDays.includes(dayNumber),
    ).length;

    if (!result) {
      return {
        dayNumber,
        date,
        status: "pending",
        reservations: reservationsForDay.length,
        coveredReservations: 0,
        unresolvedReservations: 0,
        signals: reservationsForDay.length ? ["已录入固定预订"] : ["等待生成日程"],
        coordinationSummary: "",
        gaps: ["当天行程尚未生成"],
        actions: buildDayReadinessActions({
          dayNumber,
          hasStay: false,
          hasBreakfast: false,
          hasLunch: false,
          hasDinner: false,
          hasActivity: false,
          unresolvedReservations: 0,
          hasDayPlan: false,
        }),
      };
    }

    const mealCoverage = resolveDayMealCoverage(dayPlan, reservationsForDay);
    const hasStay =
      Boolean(dayPlan?.stay.hotel_name?.trim()) ||
      Boolean(dayPlan?.hotel_area?.trim()) ||
      reservationsForDay.some((item) => item.type === "hotel");
    const hasActivity =
      Boolean(dayPlan?.activities.length) ||
      reservationsForDay.some((item) => item.type === "ticket" || item.type === "other");
    const hasTransportAnchor = reservationsForDay.some(
      (item) => item.type === "flight" || item.type === "train",
    );
    const coordinationSummary = resolveDayCoordinationSummary(dayPlan);

    const signals: string[] = [];
    if (hasStay) signals.push("住宿已覆盖");
    if (mealCoverage.hasAnyMeal) signals.push("餐饮已覆盖");
    if (hasActivity) signals.push("活动已覆盖");
    if (hasTransportAnchor) signals.push("已有交通安排");
    if (coveredReservations) signals.push(`已落地预订 ${coveredReservations} 条`);
    if (coordinatedReservations) signals.push(`已做多预订协调 ${coordinatedReservations} 条`);

    const gaps: string[] = [];
    if (!hasStay) gaps.push("缺少住宿安排");
    if (!mealCoverage.hasBreakfast) gaps.push("缺少早餐安排");
    if (!mealCoverage.hasLunch) gaps.push("缺少午餐安排");
    if (!mealCoverage.hasDinner) gaps.push("缺少晚餐安排");
    if (!hasActivity) gaps.push("缺少主要活动");
    if (unresolvedReservations) gaps.push(`还有 ${unresolvedReservations} 条预订尚未落地`);
    if (!dayPlan) gaps.push("当天行程尚未生成");

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
      coordinationSummary,
      gaps,
      actions: buildDayReadinessActions({
        dayNumber,
        hasStay,
        hasBreakfast: mealCoverage.hasBreakfast,
        hasLunch: mealCoverage.hasLunch,
        hasDinner: mealCoverage.hasDinner,
        hasActivity,
        unresolvedReservations,
        hasDayPlan: Boolean(dayPlan),
      }),
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

function buildDayReadinessActions(options: {
  dayNumber: number;
  hasStay: boolean;
  hasBreakfast: boolean;
  hasLunch: boolean;
  hasDinner: boolean;
  hasActivity: boolean;
  unresolvedReservations: number;
  hasDayPlan: boolean;
}): DayReadinessAction[] {
  const {
    dayNumber,
    hasStay,
    hasBreakfast,
    hasLunch,
    hasDinner,
    hasActivity,
    unresolvedReservations,
    hasDayPlan,
  } = options;
  const actions: DayReadinessAction[] = [];

  if (!hasDayPlan) {
    actions.push({
      gapType: "day-plan",
      label: "生成当天行程",
      reason: `请优先补齐第 ${dayNumber} 天的完整行程，确保住宿、餐饮、活动和固定预订都能落地。`,
    });
    return actions;
  }

  if (!hasStay) {
    actions.push({
      gapType: "stay",
      label: "补齐住宿",
      reason: `请优先补齐第 ${dayNumber} 天的住宿安排，并围绕住宿位置优化当天动线。`,
    });
  }

  if (!hasBreakfast) {
    actions.push({
      gapType: "breakfast",
      label: "补早餐",
      reason: `请补齐第 ${dayNumber} 天的早餐安排，优先考虑住宿点附近、出发方便且开门较早的选择。`,
    });
  }

  if (!hasLunch) {
    actions.push({
      gapType: "lunch",
      label: "补午餐",
      reason: `请补齐第 ${dayNumber} 天的午餐安排，尽量靠近中午时段的主要活动或交通节点。`,
    });
  }

  if (!hasDinner) {
    actions.push({
      gapType: "dinner",
      label: "补晚餐",
      reason: `请补齐第 ${dayNumber} 天的晚餐安排，优先考虑晚间活动结束后的用餐便利性。`,
    });
  }

  if (!hasActivity) {
    actions.push({
      gapType: "activity",
      label: "补齐活动",
      reason: `请补齐第 ${dayNumber} 天的核心活动，避免该天只剩空白时间或仅有交通安排。`,
    });
  }

  if (unresolvedReservations) {
    actions.push({
      gapType: "reservation",
      label: "落地预订",
      reason: `请重新梳理第 ${dayNumber} 天的安排，明确覆盖未落地预订，并避免与现有时间窗冲突。`,
    });
  }

  return actions;
}

function resolveDayMealCoverage(
  dayPlan: DayPlan | null,
  reservationsForDay: ReservationItem[],
): {
  hasAnyMeal: boolean;
  hasBreakfast: boolean;
  hasLunch: boolean;
  hasDinner: boolean;
} {
  const mealTypes = new Set(dayPlan?.meals.map((meal) => meal.meal_type) ?? []);
  const restaurantReservations = reservationsForDay.filter((item) => item.type === "restaurant");

  return {
    hasAnyMeal: Boolean(dayPlan?.meals.length) || restaurantReservations.length > 0,
    hasBreakfast:
      mealTypes.has("breakfast") ||
      restaurantReservations.some((item) => reservationMatchesMealSlot(item, "breakfast")),
    hasLunch:
      mealTypes.has("lunch") ||
      restaurantReservations.some((item) => reservationMatchesMealSlot(item, "lunch")),
    hasDinner:
      mealTypes.has("dinner") ||
      restaurantReservations.some((item) => reservationMatchesMealSlot(item, "dinner")),
  };
}

function reservationMatchesMealSlot(
  reservation: ReservationItem,
  slot: "breakfast" | "lunch" | "dinner",
): boolean {
  const content = `${reservation.title} ${reservation.notes}`.toLowerCase();
  const hour = resolveReservationHour(reservation);

  if (slot === "breakfast") {
    if (
      content.includes("breakfast") ||
      content.includes("brunch") ||
      content.includes("早餐") ||
      content.includes("早茶") ||
      content.includes("早饭")
    ) {
      return true;
    }
    return hour >= 5 && hour < 11;
  }

  if (slot === "lunch") {
    if (
      content.includes("lunch") ||
      content.includes("brunch") ||
      content.includes("午餐") ||
      content.includes("中饭")
    ) {
      return true;
    }
    return hour >= 10 && hour < 15;
  }

  if (
    content.includes("dinner") ||
    content.includes("supper") ||
    content.includes("晚餐") ||
    content.includes("晚饭")
  ) {
    return true;
  }

  return hour >= 17 && hour < 23;
}

function resolveReservationHour(reservation: ReservationItem): number {
  if (!reservation.start_at) {
    return -1;
  }

  const hour = new Date(reservation.start_at).getHours();
  return Number.isFinite(hour) ? hour : -1;
}

function resolveDayCoordinationSummary(dayPlan: DayPlan | null): string {
  if (!dayPlan) {
    return "";
  }

  return dayPlan.transport_tips.find((tip) => tip.startsWith("固定预订顺序：")) ?? "";
}
