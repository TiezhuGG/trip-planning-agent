import type { PlanningResponse } from "../types/planning";
import type { ReservationCoverageItem } from "./tripWorkspaceReservationCoverageHelpers";

export interface DeparturePrecheckItem {
  key: string;
  status: "ok" | "warning" | "pending";
  title: string;
  summary: string;
  detail: string;
}

export interface DeparturePrecheckSummary {
  total: number;
  ok: number;
  warning: number;
  pending: number;
}

export function buildDeparturePrecheckItems(options: {
  result: PlanningResponse | null;
  reservationCoverageItems: ReservationCoverageItem[];
}): DeparturePrecheckItem[] {
  const { result, reservationCoverageItems } = options;
  if (!result) {
    return [];
  }

  const days = result.plan.days;
  const items: DeparturePrecheckItem[] = [];

  const missingWeatherDays = days
    .filter((day) => !day.weather)
    .map((day) => day.day_number);
  const weatherRiskDays = days
    .filter((day) =>
      day.weather
        ? isWeatherRisk(day.weather.day_weather, day.weather.night_weather, day.weather.advice)
        : false,
    )
    .map((day) => day.day_number);

  if (missingWeatherDays.length) {
    items.push({
      key: "weather",
      status: "warning",
      title: "天气校验",
      summary: `第 ${missingWeatherDays.join("、")} 天缺少天气信息`,
      detail: "建议在出发前重新生成或人工确认当日预报，避免按过期天气安排户外活动。",
    });
  } else if (weatherRiskDays.length) {
    items.push({
      key: "weather",
      status: "warning",
      title: "天气校验",
      summary: `第 ${weatherRiskDays.join("、")} 天存在天气风险`,
      detail: "检测到降雨、高温或大风等风险，建议检查活动是否需要改成室内或错峰出行。",
    });
  } else {
    items.push({
      key: "weather",
      status: "ok",
      title: "天气校验",
      summary: "每日天气信息齐全",
      detail: "当前行程每天都带有天气摘要，可直接作为出发前确认的基础信息。",
    });
  }

  const routeMissingDays = days
    .filter((day) => !day.route_summary && !day.route_summaries.length && !day.route_segments.length)
    .map((day) => day.day_number);
  if (routeMissingDays.length) {
    items.push({
      key: "route",
      status: "warning",
      title: "路线校验",
      summary: `第 ${routeMissingDays.join("、")} 天缺少路线摘要`,
      detail: "建议补齐路线上下文，尤其是跨区移动较多的日期，避免现场再临时规划。",
    });
  } else {
    items.push({
      key: "route",
      status: "ok",
      title: "路线校验",
      summary: "每日都带有路线摘要",
      detail: "当前工作区的每一天都具备路线信息，可继续结合地图核对通勤时长。",
    });
  }

  const unresolvedReservations = reservationCoverageItems.filter((item) => item.status === "unresolved");
  const autoAnchoredReservations = reservationCoverageItems.filter((item) => item.autoAnchoredDays.length);
  if (unresolvedReservations.length) {
    items.push({
      key: "reservation",
      status: "warning",
      title: "预订校验",
      summary: `${unresolvedReservations.length} 条预订仍未明确落地`,
      detail: unresolvedReservations
        .slice(0, 3)
        .map((item) => item.title)
        .join("、"),
    });
  } else if (autoAnchoredReservations.length) {
    items.push({
      key: "reservation",
      status: "warning",
      title: "预订校验",
      summary: `${autoAnchoredReservations.length} 条预订由系统保底注入`,
      detail: "这些预订已经被写回行程，但建议人工再确认时间窗和周边安排是否合理。",
    });
  } else if (reservationCoverageItems.length) {
    items.push({
      key: "reservation",
      status: "ok",
      title: "预订校验",
      summary: "预订都已明确落地",
      detail: "当前固定预订都能在行程里找到对应安排，没有待确认项。",
    });
  } else {
    items.push({
      key: "reservation",
      status: "pending",
      title: "预订校验",
      summary: "当前没有固定预订",
      detail: "如果已经订好酒店、门票或交通，建议录入后再做一次最终确认。",
    });
  }

  const openingHoursMissing = collectOpeningHoursGaps(result);
  if (openingHoursMissing.length) {
    const preview = openingHoursMissing.slice(0, 3).map((item) => item.label).join("、");
    items.push({
      key: "opening-hours",
      status: "warning",
      title: "营业时间校验",
      summary: `${openingHoursMissing.length} 个地点缺少营业时间`,
      detail: preview,
    });
  } else {
    items.push({
      key: "opening-hours",
      status: "ok",
      title: "营业时间校验",
      summary: "主要地点都带有开放时间",
      detail: "当前 POI 信息足够支持出发前核对营业状态。",
    });
  }

  return items;
}

export function summarizeDeparturePrecheck(
  items: DeparturePrecheckItem[],
): DeparturePrecheckSummary {
  return {
    total: items.length,
    ok: items.filter((item) => item.status === "ok").length,
    warning: items.filter((item) => item.status === "warning").length,
    pending: items.filter((item) => item.status === "pending").length,
  };
}

function isWeatherRisk(dayWeather: string, nightWeather: string, advice: string) {
  const text = [dayWeather, nightWeather, advice].join(" ");
  return /(雷阵雨|暴雨|台风|大风|高温|暴晒|寒潮|冰雹)/.test(text);
}

function collectOpeningHoursGaps(result: PlanningResponse) {
  const gaps: Array<{ dayNumber: number; label: string }> = [];

  for (const day of result.plan.days) {
    const candidates = [
      {
        label: day.stay.hotel_name,
        openingHours: day.stay.poi?.opening_hours,
        source: day.stay.poi?.source ?? "",
      },
      ...day.meals.map((meal) => ({
        label: meal.venue_name,
        openingHours: meal.poi?.opening_hours,
        source: meal.poi?.source ?? "",
      })),
      ...day.activities.map((activity) => ({
        label: activity.title,
        openingHours: activity.poi?.opening_hours,
        source: activity.poi?.source ?? "",
      })),
    ];

    for (const item of candidates) {
      if (!item.label || !item.source || item.source === "manual_placeholder") {
        continue;
      }
      if (item.openingHours) {
        continue;
      }

      gaps.push({ dayNumber: day.day_number, label: `第 ${day.day_number} 天：${item.label}` });
    }
  }

  return gaps;
}
