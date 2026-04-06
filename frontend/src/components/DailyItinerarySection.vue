<script setup lang="ts">
import DailyItineraryCard from "./DailyItineraryCard.vue";
import type { DailyForecast, DayPlan, MealRecommendation, RouteSummary } from "../types/planning";

const props = defineProps<{
  days: DayPlan[];
  routes: RouteSummary[];
  weatherForecasts: DailyForecast[];
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
        >展开后可查看当日路线、住宿与费用</span
      >
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
        @toggle="toggleDay"
      />
    </div>
  </article>
</template>
