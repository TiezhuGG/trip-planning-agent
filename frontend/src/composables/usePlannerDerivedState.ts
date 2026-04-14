import { computed, type Ref } from "vue";

import { formatTravelers, isChineseCityName } from "../utils/tripPlannerForm";
import type {
  DailyForecast,
  DayPOI,
  IntegrationStatus,
  PlanningResponse,
  RouteSummary,
  TripPlanningRequest,
  TripWorkspace,
} from "../types/planning";

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

export function usePlannerDerivedState(options: {
  form: TripPlanningRequest;
  result: Ref<PlanningResponse | null>;
  currentTrip: Ref<TripWorkspace | null>;
  integrationStatus: Ref<IntegrationStatus>;
  startDate: Ref<string>;
  endDate: Ref<string>;
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
    paceLabel,
    budgetLabel,
  } = options;

  const currentIntegrationStatus = computed(
    () => result.value?.integration_status ?? integrationStatus.value,
  );

  const shareLink = computed(() =>
    currentTrip.value
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

  const destinationValid = computed(() => isChineseCityName(form.destination));

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
    destinationValid,
  };
}
