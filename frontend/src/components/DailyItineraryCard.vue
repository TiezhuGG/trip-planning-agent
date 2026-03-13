<script setup lang="ts">
import type {
  DailyForecast,
  DayPlan,
  MealRecommendation,
  POIRecommendation,
  RouteSummary,
} from "../types/planning";

const props = defineProps<{
  day: DayPlan;
  expanded: boolean;
  routeSummary: RouteSummary | null;
  weather: DailyForecast | null;
  mealRecommendations: Array<MealRecommendation | POIRecommendation>;
}>();

const emit = defineEmits<{
  (event: "toggle", dayNumber: number): void;
}>();

function onToggle() {
  emit("toggle", props.day.day_number);
}

function isStructuredMeal(
  item: MealRecommendation | POIRecommendation,
): item is MealRecommendation {
  return "meal_type" in item;
}

function mealLabel(type: string) {
  return (
    { breakfast: "早餐", lunch: "午餐", dinner: "晚餐", snack: "加餐" }[type] ??
    type
  );
}

function mealTitle(item: MealRecommendation | POIRecommendation) {
  return isStructuredMeal(item)
    ? `${mealLabel(item.meal_type)} · ${item.venue_name}`
    : item.name;
}

function mealSubtitle(item: MealRecommendation | POIRecommendation) {
  return isStructuredMeal(item)
    ? [item.cuisine, item.suggestion, item.estimated_cost]
        .filter(Boolean)
        .join(" · ")
    : [item.address, item.tags.join(" / ")].filter(Boolean).join(" · ");
}
</script>

<template>
  <article
    class="rounded-[28px] border border-slate-100 bg-[linear-gradient(180deg,#f7fafb,#f3f6f8)] px-5 py-5 shadow-sm"
  >
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="text-lg font-semibold text-ink">
          第 {{ day.day_number }} 天 · {{ day.theme }}
        </div>
        <div class="mt-2 text-sm text-slate-500">
          {{ day.date }}
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="rounded-full bg-white px-4 py-2 text-sm text-slate-600 shadow-sm">
          {{ weather?.day_weather || "--" }}
          {{ weather ? `${weather.low_temperature}°-${weather.high_temperature}°` : "" }}
        </span>
        <button
          type="button"
          class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 shadow-sm"
          @click="onToggle"
        >
          {{ expanded ? "收起详情" : "展开详情" }}
        </button>
      </div>
    </div>

    <div v-if="expanded" class="mt-5 grid gap-4">
      <p class="text-sm leading-7 text-slate-600">
        {{ day.overview }}
      </p>

      <div class="grid gap-4 xl:grid-cols-[1.08fr_0.92fr]">
        <div class="space-y-3">
          <template v-if="day.activities.length">
            <div
              v-for="activity in day.activities"
              :key="`${day.day_number}-${activity.start_time}-${activity.title}`"
              class="rounded-[22px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm"
            >
              <div class="font-medium text-ink">
                {{ activity.start_time }} - {{ activity.end_time }} · {{ activity.title }}
              </div>
              <div class="mt-2 leading-6">
                {{ activity.description }}
              </div>
              <div
                v-if="activity.transport_from_previous"
                class="mt-3 text-xs text-slate-500"
              >
                {{ activity.transport_from_previous }}
              </div>
            </div>
          </template>
          <div
            v-else
            class="rounded-[22px] bg-white px-4 py-4 text-sm text-slate-500 shadow-sm"
          >
            暂无详细活动安排
          </div>
        </div>

        <div class="space-y-3">
          <div class="rounded-[22px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm">
            <div class="font-medium text-ink">路线概览</div>
            <div class="mt-3 leading-6">
              {{ routeSummary?.distance_text || "距离待补充" }}
              {{ routeSummary?.duration_text ? ` · ${routeSummary.duration_text}` : "" }}
            </div>
            <div
              v-if="routeSummary?.from_name || routeSummary?.to_name"
              class="mt-2 text-xs text-slate-500"
            >
              {{ routeSummary?.from_name || "起点待定" }} →
              {{ routeSummary?.to_name || "终点待定" }}
            </div>
          </div>

            <div class="rounded-[22px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm">
              <div class="font-medium text-ink">天气与体感</div>
              <div v-if="weather" class="mt-3">
                <div>
                  {{ weather.day_weather }} / {{ weather.night_weather }}
                </div>
                <div class="mt-2 text-xs text-slate-500">
                  {{ weather.low_temperature }}° - {{ weather.high_temperature }}°
                </div>
                <div class="mt-3 leading-6">
                  {{ weather.advice }}
                </div>
              </div>
              <div v-else class="mt-3 text-slate-500">
                暂无天气信息
              </div>
            </div>

            <div class="rounded-[22px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm">
              <div class="font-medium text-ink">餐饮推荐</div>
              <div v-if="mealRecommendations.length" class="mt-3 space-y-2">
                <div
                  v-for="meal in mealRecommendations"
                  :key="`${day.day_number}-${mealTitle(meal)}-${mealSubtitle(meal)}`"
                  class="rounded-[18px] bg-panel px-3 py-3"
                >
                  <div class="font-medium text-ink">
                    {{ mealTitle(meal) }}
                  </div>
                  <div class="mt-2 text-xs leading-6 text-slate-500">
                    {{ mealSubtitle(meal) }}
                  </div>
                </div>
              </div>
              <div v-else class="mt-3 text-slate-500">
                暂无餐饮推荐
              </div>
            </div>
        </div>
      </div>
    </div>
  </article>
</template>