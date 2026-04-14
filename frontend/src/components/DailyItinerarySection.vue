<script setup lang="ts">
import DailyItineraryCard from "./DailyItineraryCard.vue";
import type {
  DailyForecast,
  DayPlan,
  MealRecommendation,
  ReservationItem,
  RouteSummary,
} from "../types/planning";

const props = defineProps<{
  days: DayPlan[];
  routes: RouteSummary[];
  weatherForecasts: DailyForecast[];
  reservations?: ReservationItem[];
  expandedDays: number[];
  lockedDays?: number[];
  replanningDays?: number[];
}>();

const emit = defineEmits<{
  (event: "toggle", dayNumber: number): void;
  (event: "toggle-lock", dayNumber: number): void;
  (event: "replan-day", dayNumber: number): void;
}>();

function isDayExpanded(dayNumber: number) {
  return props.expandedDays.includes(dayNumber);
}

function toggleDay(dayNumber: number) {
  emit("toggle", dayNumber);
}

function getDayRoutes(day: DayPlan): RouteSummary[] {
  if (day.route_segments?.length) return day.route_segments;
  if (day.route_summaries?.length) return day.route_summaries;
  if (day.route_summary) return [day.route_summary];
  return props.routes.filter((route) => route.day_number === day.day_number);
}

function getDayWeather(day: DayPlan): DailyForecast | null {
  return (
    day.weather ??
    props.weatherForecasts.find((forecast) => forecast.date === day.date) ??
    null
  );
}

function getMealRecommendations(day: DayPlan): MealRecommendation[] {
  return day.meals;
}

function extractIsoDate(value?: string | null) {
  if (!value) return null;
  const matched = value.match(/^(\d{4}-\d{2}-\d{2})/);
  if (matched) return matched[1];
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  const year = parsed.getFullYear();
  const month = `${parsed.getMonth() + 1}`.padStart(2, "0");
  const day = `${parsed.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getDayReservations(day: DayPlan): ReservationItem[] {
  return (props.reservations ?? []).filter((item) => {
    const startDate = extractIsoDate(item.start_at);
    const endDate = extractIsoDate(item.end_at);
    if (startDate && endDate) return startDate <= day.date && endDate >= day.date;
    if (startDate) return startDate === day.date;
    if (endDate) return endDate === day.date;
    return false;
  });
}

function isDayLocked(dayNumber: number) {
  return props.lockedDays?.includes(dayNumber) ?? false;
}

function isDayReplanning(dayNumber: number) {
  return props.replanningDays?.includes(dayNumber) ?? false;
}
</script>

<template>
  <article
    class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"
  >
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">
          Daily Itinerary
        </div>
        <h2 class="mt-3 text-2xl font-semibold text-ink">
          每日详细行程
        </h2>
      </div>
      <span class="rounded-full bg-[#eff5f8] px-4 py-2 text-sm text-[#48637b]">
        展开后可查看当日路线、住宿与费用
      </span>
    </div>
    <div class="mt-5 space-y-4">
      <DailyItineraryCard
        v-for="(day, index) in days"
        :key="`${day.day_number}-${day.date}-${index}`"
        :day="day"
        :expanded="isDayExpanded(day.day_number)"
        :route-summaries="getDayRoutes(day)"
        :weather="getDayWeather(day)"
        :meal-recommendations="getMealRecommendations(day)"
        :reservations="getDayReservations(day)"
        :locked="isDayLocked(day.day_number)"
        :replanning="isDayReplanning(day.day_number)"
        @toggle="toggleDay"
        @toggle-lock="emit('toggle-lock', $event)"
        @replan-day="emit('replan-day', $event)"
      />
    </div>
  </article>
</template>
