<script setup lang="ts">
import DailyItineraryCard from "./DailyItineraryCard.vue";
import type {
  DailyForecast,
  DayPlan,
  MealRecommendation,
  POIRecommendation,
  RouteSummary,
} from "../types/planning";

const props = defineProps<{
  days: DayPlan[];
  routes: RouteSummary[];
  weatherForecasts: DailyForecast[];
  restaurants: POIRecommendation[];
  expandedDays: number[];
}>();

const emit = defineEmits<{
  (event: "toggle", dayNumber: number): void;
}>();

function isDayExpanded(dayNumber: number) {
  return props.expandedDays.includes(dayNumber);
}

function toggleDay(dayNumber: number) {
  emit("toggle", dayNumber);
}

function getDayRoute(day: DayPlan): RouteSummary | null {
  return (
    day.route_summary ??
    props.routes.find((route) => route.day_number === day.day_number) ??
    null
  );
}

function getDayWeather(day: DayPlan): DailyForecast | null {
  return (
    day.weather ??
    props.weatherForecasts.find((forecast) => forecast.date === day.date) ??
    null
  );
}

function getMealRecommendations(
  day: DayPlan,
): Array<MealRecommendation | POIRecommendation> {
  if (day.meals.length) return day.meals;
  if (!props.restaurants.length) return [];
  const take = Math.min(3, props.restaurants.length);
  const startIndex = ((day.day_number - 1) * take) % props.restaurants.length;
  return Array.from(
    { length: take },
    (_, index) => props.restaurants[(startIndex + index) % props.restaurants.length],
  );
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
      <span class="rounded-full bg-[#eff5f8] px-4 py-2 text-sm text-[#48637b]"
        >整卡展开后查看当日细节</span
      >
    </div>
    <div class="mt-5 space-y-4">
      <DailyItineraryCard
        v-for="day in days"
        :key="day.day_number"
        :day="day"
        :expanded="isDayExpanded(day.day_number)"
        :route-summary="getDayRoute(day)"
        :weather="getDayWeather(day)"
        :meal-recommendations="getMealRecommendations(day)"
        @toggle="toggleDay"
      />
    </div>
  </article>
</template>