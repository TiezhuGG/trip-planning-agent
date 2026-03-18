<script setup lang="ts">
import type {
  DailyForecast,
  DayPlan,
  MealRecommendation,
  RouteSummary,
} from "../types/planning";

const props = defineProps<{
  day: DayPlan;
  expanded: boolean;
  routeSummaries: RouteSummary[];
  weather: DailyForecast | null;
  mealRecommendations: MealRecommendation[];
}>();

const emit = defineEmits<{
  (event: "toggle", dayNumber: number): void;
}>();

function onToggle() {
  emit("toggle", props.day.day_number);
}

function mealLabel(type: string) {
  return (
    { breakfast: "早餐", lunch: "午餐", dinner: "晚餐", snack: "加餐" }[type] ??
    type
  );
}

function formatCny(value: number, suffix = "") {
  if (!value) return "";
  return `¥${value.toLocaleString()}${suffix}`;
}
</script>

<template>
  <article class="rounded-[28px] border border-[#dbe5ef] bg-white px-5 py-5 shadow-sm">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="text-lg font-semibold text-ink">
          第{{ day.day_number }}天 · {{ day.theme }}
        </div>
        <div class="mt-2 text-sm text-slate-500">
          {{ day.date }}
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="rounded-full border border-[#d7e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b] shadow-sm">
          {{ weather?.day_weather || "--" }}
          {{ weather ? `${weather.low_temperature}°-${weather.high_temperature}°` : "" }}
        </span>
        <span class="rounded-full border border-[#d7e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b] shadow-sm">
          当日人均 {{ formatCny(day.cost_breakdown.total_per_person_cny) }}
        </span>
        <button
          type="button"
          class="rounded-full border border-[#c7d6e4] bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm"
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
          <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f8fbfd] px-4 py-4 text-sm text-slate-600 shadow-sm">
            <div class="font-medium text-ink">当日景点与活动</div>
            <div v-if="day.activities.length" class="mt-3 space-y-3">
              <div
                v-for="(activity, activityIndex) in day.activities"
                :key="`${day.day_number}-${activity.start_time}-${activity.title}-${activityIndex}`"
                class="rounded-[18px] border border-[#dfe8f1] bg-white px-3 py-3"
              >
                <div class="font-medium text-ink">
                  {{ activity.start_time }} - {{ activity.end_time }} · {{ activity.title }}
                </div>
                <div class="mt-2 leading-6">
                  {{ activity.description }}
                </div>
                <div class="mt-2 text-xs text-slate-500">
                  门票：{{ activity.expected_cost || formatCny(activity.ticket_cost_cny, "/人") || "待确认" }}
                </div>
                <div
                  v-if="activity.transport_from_previous"
                  class="mt-2 text-xs text-slate-500"
                >
                  {{ activity.transport_from_previous }}
                </div>
              </div>
            </div>
            <div v-else class="mt-3 text-slate-500">暂无活动安排</div>
          </div>

          <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f8fbfd] px-4 py-4 text-sm text-slate-600 shadow-sm">
            <div class="font-medium text-ink">酒店住宿推荐</div>
            <div class="mt-3 rounded-[18px] border border-[#dfe8f1] bg-white px-3 py-3">
              <div class="font-medium text-ink">
                {{ day.stay.hotel_name || "待确认酒店" }}
              </div>
              <div class="mt-2 text-xs text-slate-500">
                区域：{{ day.stay.area || day.hotel_area || "待定" }}
              </div>
              <div class="mt-2 text-xs leading-6 text-slate-500">
                {{ day.stay.reason || "优先靠近当日主要行程点，减少往返时间。" }}
              </div>
              <div class="mt-3 text-xs text-[#2f5a81]">
                当日酒店费用：{{ formatCny(day.stay.room_nightly_cost_cny, "/间夜") || "待确认" }}
              </div>
            </div>
          </div>
        </div>

        <div class="space-y-3">
          <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f8fbfd] px-4 py-4 text-sm text-slate-600 shadow-sm">
            <div class="font-medium text-ink">路线概览</div>
            <div v-if="routeSummaries.length" class="mt-3 space-y-3">
              <div
                v-for="(route, routeIndex) in routeSummaries"
                :key="`${day.day_number}-${route.title}-${route.from_name}-${route.to_name}-${routeIndex}`"
                class="rounded-[18px] border border-[#dfe8f1] bg-white px-3 py-3"
              >
                <div class="font-medium text-ink">{{ route.title || `路线 ${routeIndex + 1}` }}</div>
                <div class="mt-2 text-xs text-slate-500">
                  {{ route.from_name || "起点待定" }} → {{ route.to_name || "终点待定" }}
                </div>
                <div class="mt-2 text-xs text-slate-500">
                  {{ route.distance_text || "距离待补充" }}
                  {{ route.duration_text ? ` · ${route.duration_text}` : "" }}
                </div>
                <div class="mt-2 text-xs text-[#2f5a81]">
                  当段交通费用：{{ formatCny(route.estimated_transport_cost_cny, "/人") || "待确认" }}
                </div>
              </div>
            </div>
            <div v-else class="mt-3 text-slate-500">暂无路线信息</div>
          </div>

          <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f8fbfd] px-4 py-4 text-sm text-slate-600 shadow-sm">
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
            <div v-else class="mt-3 text-slate-500">暂无天气信息</div>
          </div>

          <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f8fbfd] px-4 py-4 text-sm text-slate-600 shadow-sm">
            <div class="font-medium text-ink">餐饮推荐</div>
            <div v-if="mealRecommendations.length" class="mt-3 space-y-2">
              <div
                v-for="(meal, mealIndex) in mealRecommendations"
                :key="`${day.day_number}-${meal.venue_name}-${meal.meal_type}-${mealIndex}`"
                class="rounded-[18px] border border-[#dfe8f1] bg-white px-3 py-3"
              >
                <div class="font-medium text-ink">
                  {{ mealLabel(meal.meal_type) }} · {{ meal.venue_name }}
                </div>
                <div class="mt-2 text-xs leading-6 text-slate-500">
                  {{ [meal.cuisine, meal.suggestion].filter(Boolean).join(" · ") }}
                </div>
                <div class="mt-2 text-xs text-[#2f5a81]">
                  {{ meal.estimated_cost || formatCny(meal.estimated_cost_cny, "/人") || "费用待确认" }}
                </div>
              </div>
            </div>
            <div v-else class="mt-3 text-slate-500">暂无餐饮推荐</div>
          </div>
        </div>
      </div>
    </div>
  </article>
</template>
