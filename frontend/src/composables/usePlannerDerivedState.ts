import { computed, type Ref } from "vue";

import type {
  DailyForecast,
  DayPOI,
  IntegrationStatus,
  PlanningResponse,
  RouteSummary,
  TripPlanningRequest,
  TripWorkspace,
} from "../types/planning";
import { formatTravelers, isChineseCityName } from "../utils/tripPlannerForm";

function resolveDayRoutes(day: {
  route_segments?: RouteSummary[];
  route_summaries?: RouteSummary[];
  route_summary?: RouteSummary | null;
}): RouteSummary[] {
  if (day.route_segments?.length) return day.route_segments;
  if (day.route_summaries?.length) return day.route_summaries;
  if (day.route_summary) return [day.route_summary];
  return [];
}

export interface PlannerInputCheck {
  tone: "blocking" | "warning" | "ready";
  text: string;
}

export function usePlannerDerivedState(options: {
  form: TripPlanningRequest;
  result: Ref<PlanningResponse | null>;
  currentTrip: Ref<TripWorkspace | null>;
  integrationStatus: Ref<IntegrationStatus>;
  startDate: Ref<string>;
  endDate: Ref<string>;
  mustVisitText: Ref<string>;
  diningText: Ref<string>;
  paceLabel: (value: TripPlanningRequest["pace"]) => string;
  budgetLabel: (value: TripPlanningRequest["budget_level"]) => string;
}) {
  const {
    form,
    result,
    currentTrip,
    integrationStatus,
    startDate,
    endDate,
    mustVisitText,
    diningText,
    paceLabel,
    budgetLabel,
  } = options;

  const currentIntegrationStatus = computed(
    () => result.value?.integration_status ?? integrationStatus.value,
  );

  const shareLink = computed(() =>
    currentTrip.value?.share_enabled
      ? `${window.location.origin}${window.location.pathname}?trip=${currentTrip.value.share_token}`
      : "",
  );

  const isEditingWorkspace = computed(
    () => Boolean(currentTrip.value) && !result.value,
  );

  const itineraryMapPois = computed<DayPOI[]>(() => {
    const response = result.value;
    if (!response) return [];
    const selected: DayPOI[] = [];
    const seen = new Set<string>();
    for (const day of response.plan.days) {
      for (const item of day.map_pois ?? []) {
        if (item.kind === "meal") continue;
        const key =
          item.poi.poi_id || `${item.kind}:${item.poi.name}:${item.poi.address}`;
        if (seen.has(key)) continue;
        seen.add(key);
        selected.push(item);
      }
    }
    return selected;
  });

  const itineraryRoutes = computed(
    () => result.value?.plan.days.flatMap((day) => resolveDayRoutes(day)) ?? [],
  );

  const itineraryWeatherForecasts = computed<DailyForecast[]>(() => {
    const response = result.value;
    if (!response) return [];
    const daily = response.plan.days
      .map((day) => day.weather)
      .filter((item): item is DailyForecast => Boolean(item));
    if (daily.length) return daily;
    return response.planning_context.weather.daily_forecasts ?? [];
  });

  const travelerSummary = computed(() => formatTravelers(form.travelers));
  const totalTravelers = computed(
    () =>
      Math.max(Number(form.travelers.adults) || 0, 0) +
      Math.max(Number(form.travelers.children) || 0, 0) +
      Math.max(Number(form.travelers.seniors) || 0, 0),
  );

  const inputSummary = computed(() => [
    {
      label: "路线",
      value: `${form.origin?.trim() || "本地出发"} → ${
        form.destination || "待填写"
      }`,
    },
    { label: "日期", value: `${startDate.value} - ${endDate.value}` },
    { label: "同行", value: travelerSummary.value },
    { label: "节奏", value: paceLabel(form.pace) },
    { label: "预算", value: budgetLabel(form.budget_level) },
    { label: "住宿", value: form.hotel_style || "未设置" },
  ]);

  const summaryTags = computed(() =>
    [
      ...new Set([
        ...form.interests.slice(0, 3),
        ...form.transport_preferences.slice(0, 2),
      ]),
    ].slice(0, 5),
  );

  const blockingChecks = computed<PlannerInputCheck[]>(() => {
    const checks: PlannerInputCheck[] = [];
    if (!form.destination.trim()) {
      checks.push({ tone: "blocking", text: "请先填写目的地城市。" });
    } else if (!isChineseCityName(form.destination)) {
      checks.push({
        tone: "blocking",
        text: "目的地目前仅支持中文城市名，例如上海、杭州、北京市。",
      });
    }

    if (!startDate.value || !endDate.value) {
      checks.push({ tone: "blocking", text: "请补全完整的出发和结束日期。" });
    }

    if (totalTravelers.value <= 0) {
      checks.push({ tone: "blocking", text: "至少需要填写 1 位同行人。" });
    }

    return checks;
  });

  const warningChecks = computed<PlannerInputCheck[]>(() => {
    const checks: PlannerInputCheck[] = [];

    if (!form.interests.length) {
      checks.push({
        tone: "warning",
        text: "还没有选择兴趣偏好，结果会更偏通用探索路线。",
      });
    }

    if (!form.transport_preferences.length) {
      checks.push({
        tone: "warning",
        text: "还没有选择交通偏好，系统会按默认策略分配通勤方式。",
      });
    }

    if (!mustVisitText.value.trim() && !diningText.value.trim() && !form.notes?.trim()) {
      checks.push({
        tone: "warning",
        text: "当前补充信息较少，建议至少写几个必去点、饮食偏好或备注。",
      });
    }

    if ((form.travelers.children > 0 || form.travelers.seniors > 0) && form.pace === "intense") {
      checks.push({
        tone: "warning",
        text: "同行里有儿童或长者，当前“紧凑”节奏可能偏赶，建议确认是否需要放缓。",
      });
    }

    if (
      (form.travelers.children > 0 || form.travelers.seniors > 0) &&
      form.transport_preferences.includes("步行")
    ) {
      checks.push({
        tone: "warning",
        text: "已选择步行优先，同时有儿童或长者同行，建议补充打车或公共交通作为备选。",
      });
    }

    if (form.days >= 8 && !mustVisitText.value.trim()) {
      checks.push({
        tone: "warning",
        text: "这是一段较长行程，补充几个必去点会更利于稳定生成每日重点。",
      });
    }

    return checks;
  });

  const planningChecks = computed<PlannerInputCheck[]>(() => {
    const checks = [...blockingChecks.value, ...warningChecks.value];
    if (checks.length) return checks.slice(0, 4);
    return [{ tone: "ready", text: "输入信息已达到可生成标准，可以直接开始规划。" }];
  });

  const canSaveDraft = computed(() => Boolean(form.destination.trim()) && isChineseCityName(form.destination));
  const canSubmit = computed(() => blockingChecks.value.length === 0);

  const submitHint = computed(() => {
    if (blockingChecks.value.length) return blockingChecks.value[0].text;
    if (warningChecks.value.length) return warningChecks.value[0].text;
    return "信息完整，可直接开始规划。";
  });

  const saveDraftHint = computed(() => {
    if (!form.destination.trim()) {
      return "请先填写目的地城市，再保存服务端草稿。";
    }
    if (!isChineseCityName(form.destination)) {
      return "保存草稿前，目的地需要是中文城市名，例如上海、杭州、北京市。";
    }
    if (blockingChecks.value.length) {
      return "当前还不适合直接生成，但已经可以先保存为工作区草稿。";
    }
    return "当前输入可直接保存为工作区草稿。";
  });

  return {
    currentIntegrationStatus,
    shareLink,
    isEditingWorkspace,
    itineraryMapPois,
    itineraryRoutes,
    itineraryWeatherForecasts,
    travelerSummary,
    inputSummary,
    summaryTags,
    planningChecks,
    canSaveDraft,
    canSubmit,
    saveDraftHint,
    submitHint,
  };
}
