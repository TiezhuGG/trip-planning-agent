import type {
  DayPlan,
  PlanningResponse,
  ReservationItem,
  TripWorkspace,
} from "../types/planning";
import { addDays, diffDays, formatDate } from "../utils/tripPlannerForm";

export interface ReservationCoverageItem {
  id: string;
  title: string;
  status: "covered" | "unresolved" | "pending";
  detail: string;
}

export interface ReservationCoverageSummary {
  total: number;
  covered: number;
  unresolved: number;
  pending: number;
}

export function buildReservationAlerts(workspace: TripWorkspace | null): string[] {
  if (!workspace) return [];
  const tripStart = workspace.request_brief.start_date;
  const tripEnd = addDays(tripStart, workspace.request_brief.days - 1);
  const messages: string[] = [];

  for (const item of workspace.reservations) {
    const startDate = extractIsoDate(item.start_at);
    const endDate = extractIsoDate(item.end_at);

    if (!startDate && !endDate) {
      messages.push(`“${item.title}” 未填写时间，当前无法自动挂到具体日期。`);
      continue;
    }
    if (startDate && endDate && endDate < startDate) {
      messages.push(`“${item.title}” 的时间范围异常，请检查开始和结束时间。`);
      continue;
    }
    if (
      (startDate && startDate > tripEnd && (!endDate || endDate > tripEnd)) ||
      (endDate && endDate < tripStart && (!startDate || startDate < tripStart))
    ) {
      messages.push(`“${item.title}” 当前未落入本次行程日期范围。`);
    }
  }

  return [...new Set(messages)];
}

export function buildReservationCoverageItems(options: {
  workspace: TripWorkspace | null;
  result: PlanningResponse | null;
}): ReservationCoverageItem[] {
  const { workspace, result } = options;
  if (!workspace) return [];

  return workspace.reservations.map((item) => {
    const targetDays = getReservationTargetDays(item, workspace);

    if (!result) {
      if (!item.start_at && !item.end_at) {
        return {
          id: item.id,
          title: item.title,
          status: "pending",
          detail: "缺少时间，生成后也无法自动校验。",
        };
      }
      return {
        id: item.id,
        title: item.title,
        status: "pending",
        detail: targetDays.length
          ? `预计影响第 ${targetDays.join("、")} 天，待生成结果后校验。`
          : "待生成结果后校验。",
      };
    }

    const matchedDays = result.plan.days
      .filter((day) => reservationMatchesDay(item, day, workspace))
      .map((day) => day.day_number);

    if (matchedDays.length) {
      return {
        id: item.id,
        title: item.title,
        status: "covered",
        detail: `已在第 ${matchedDays.join("、")} 天的行程内容中找到对应锚点。`,
      };
    }

    if (!targetDays.length) {
      return {
        id: item.id,
        title: item.title,
        status: "unresolved",
        detail: "生成结果中未找到明确映射，请手动确认。",
      };
    }

    return {
      id: item.id,
      title: item.title,
      status: "unresolved",
      detail: `第 ${targetDays.join("、")} 天未找到明确映射，建议重排对应日期。`,
    };
  });
}

export function summarizeReservationCoverage(
  items: ReservationCoverageItem[],
): ReservationCoverageSummary {
  return {
    total: items.length,
    covered: items.filter((item) => item.status === "covered").length,
    unresolved: items.filter((item) => item.status === "unresolved").length,
    pending: items.filter((item) => item.status === "pending").length,
  };
}

export function getReservationTargetDays(
  reservation: ReservationItem,
  workspace: TripWorkspace,
) {
  const tripStart = workspace.request_brief.start_date;
  const tripEnd = addDays(tripStart, workspace.request_brief.days - 1);
  const startDate = extractIsoDate(reservation.start_at) ?? extractIsoDate(reservation.end_at);
  const endDate = extractIsoDate(reservation.end_at) ?? extractIsoDate(reservation.start_at);
  if (!startDate || !endDate) return [];
  const effectiveStart = startDate < tripStart ? tripStart : startDate;
  const effectiveEnd = endDate > tripEnd ? tripEnd : endDate;
  if (effectiveEnd < effectiveStart) return [];

  const days: number[] = [];
  let current = effectiveStart;
  while (current <= effectiveEnd) {
    days.push(diffDays(tripStart, current));
    current = addDays(current, 1);
  }
  return days;
}

export function getReservationTargetDaysById(
  reservationId: string,
  workspace: TripWorkspace,
) {
  const reservation = workspace.reservations.find((item) => item.id === reservationId);
  return reservation ? getReservationTargetDays(reservation, workspace) : [];
}

function extractIsoDate(value?: string | null) {
  if (!value) return null;
  const matched = value.match(/^(\d{4}-\d{2}-\d{2})/);
  if (matched) return matched[1];
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : formatDate(parsed);
}

function normalizeReservationSearchText(value?: string | null) {
  if (!value) return "";
  return [...value.toLowerCase()]
    .filter((char) => /[0-9a-z\u4e00-\u9fff]/.test(char))
    .join("");
}

function reservationSearchTokens(reservation: ReservationItem) {
  const parts = [reservation.title, reservation.location];
  const tokens: string[] = [];
  for (const part of parts) {
    for (const token of (part || "").split(/[^0-9a-zA-Z\u4e00-\u9fff]+/)) {
      const normalized = normalizeReservationSearchText(token);
      if (normalized.length >= 2 && !tokens.includes(normalized)) {
        tokens.push(normalized);
      }
    }
  }
  return tokens;
}

function buildReservationDaySearchText(reservation: ReservationItem, day: DayPlan) {
  if (reservation.type === "hotel") {
    return normalizeReservationSearchText(
      [day.stay.hotel_name, day.stay.area, day.hotel_area, day.overview].join(" "),
    );
  }
  if (reservation.type === "restaurant") {
    return normalizeReservationSearchText(
      [
        day.overview,
        ...day.meals.map((meal) => meal.venue_name),
        ...day.meals.map((meal) => meal.poi?.name ?? ""),
        ...day.meals.map((meal) => meal.poi?.address ?? ""),
      ].join(" "),
    );
  }
  return normalizeReservationSearchText(
    [
      day.theme,
      day.overview,
      ...day.transport_tips,
      ...day.activities.map((activity) => activity.title),
      ...day.activities.map((activity) => activity.location_name),
      ...day.activities.map((activity) => activity.description),
      ...day.activities.map((activity) => activity.poi?.name ?? ""),
      ...day.activities.map((activity) => activity.poi?.address ?? ""),
    ].join(" "),
  );
}

function reservationMatchesDay(
  reservation: ReservationItem,
  day: DayPlan,
  workspace: TripWorkspace,
) {
  const targetDays = getReservationTargetDays(reservation, workspace);
  if (targetDays.length && !targetDays.includes(day.day_number)) {
    return false;
  }

  const dayText = buildReservationDaySearchText(reservation, day);
  const title = normalizeReservationSearchText(reservation.title);
  const location = normalizeReservationSearchText(reservation.location);
  if (title && dayText.includes(title)) return true;
  if (location && dayText.includes(location)) return true;

  const tokens = reservationSearchTokens(reservation);
  const hits = tokens.filter((token) => dayText.includes(token));
  if (hits.length >= 2) return true;
  return tokens.some((token) => token.length >= 4 && dayText.includes(token));
}
