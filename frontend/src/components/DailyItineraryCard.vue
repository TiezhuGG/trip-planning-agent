<script setup lang="ts">
import type {
  DailyForecast,
  DayPlan,
  MealRecommendation,
  ReservationItem,
  RouteSummary,
} from "../types/planning";

const props = defineProps<{
  day: DayPlan;
  expanded: boolean;
  routeSummaries: RouteSummary[];
  weather: DailyForecast | null;
  mealRecommendations: MealRecommendation[];
  reservations?: ReservationItem[];
  locked?: boolean;
  replanning?: boolean;
}>();

const emit = defineEmits<{
  (event: "toggle", dayNumber: number): void;
  (event: "toggle-lock", dayNumber: number): void;
  (event: "replan-day", dayNumber: number): void;
}>();

function onToggle() {
  emit("toggle", props.day.day_number);
}

function onToggleLock() {
  emit("toggle-lock", props.day.day_number);
}

function onReplanDay() {
  emit("replan-day", props.day.day_number);
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

function shortAddress(value?: string | null) {
  if (!value) return "";
  return value.length > 28 ? `${value.slice(0, 28)}...` : value;
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

function reservationTypeLabel(type: string) {
  return (
    {
      flight: "航班",
      train: "火车",
      hotel: "酒店",
      restaurant: "餐厅",
      ticket: "门票",
      other: "预约",
    }[type] ?? type
  );
}
</script>

<template>
  <article class="rounded-[28px] border border-[#dbe5ef] bg-white px-5 py-5 shadow-sm">
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
        <button
          type="button"
          class="rounded-full border border-[#c7d6e4] bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm"
          @click="onToggleLock"
        >
          {{ locked ? "解除锁定" : "锁定当天" }}
        </button>
        <button
          type="button"
          class="rounded-full border border-[#16324d] bg-[#16324d] px-4 py-2 text-sm text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="replanning"
          @click="onReplanDay"
        >
          {{ replanning ? "重规划中..." : "重排当天" }}
        </button>
      </div>
    </div>

    <div v-if="expanded" class="mt-5 grid gap-4">
      <p class="text-sm leading-7 text-slate-600">
        {{ day.overview }}
      </p>

      <div
        v-if="reservations?.length"
        class="rounded-[22px] border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900 shadow-sm"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="font-medium">当日固定安排</div>
          <span class="rounded-full bg-white/80 px-3 py-1 text-xs text-amber-700">
            {{ reservations.length }} 个锚点
          </span>
        </div>
        <div class="mt-3 space-y-3">
          <div
            v-for="item in reservations"
            :key="item.id"
            class="rounded-[18px] border border-amber-100 bg-white px-3 py-3 text-sm text-slate-600"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="font-medium text-ink">{{ item.title }}</div>
                <div class="mt-1 text-xs uppercase tracking-[0.12em] text-amber-700">
                  {{ reservationTypeLabel(item.type) }}
                </div>
              </div>
              <div class="text-xs text-slate-500">
                {{ formatDateTime(item.start_at) }}{{ item.end_at ? ` - ${formatDateTime(item.end_at)}` : "" }}
              </div>
            </div>
            <div v-if="item.location" class="mt-2 text-xs text-slate-500">
              地点：{{ item.location }}
            </div>
            <div v-if="item.notes" class="mt-2 leading-6">
              {{ item.notes }}
            </div>
          </div>
        </div>
      </div>

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
                <div class="mt-2 text-xs text-[#35516b]">
                  {{ activity.poi?.name || activity.location_name }}
                </div>
                <div v-if="activity.poi?.address" class="mt-1 text-xs text-slate-500">
                  {{ shortAddress(activity.poi.address) }}
                </div>
                <div class="mt-2 leading-6">
                  {{ activity.description }}
                </div>
                <div class="mt-2 text-xs text-slate-500">
                  票价：{{
                    activity.expected_cost ||
                    formatCny(activity.ticket_cost_cny, "/人") ||
                    "待确认"
                  }}
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
              <div v-if="day.stay.poi?.address" class="mt-1 text-xs text-slate-500">
                地址：{{ shortAddress(day.stay.poi.address) }}
              </div>
              <div class="mt-3 text-xs text-[#2f5a81]">
                当日酒店费用：{{
                  formatCny(day.stay.room_nightly_cost_cny, "/间夜") || "待确认"
                }}
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
                <div class="font-medium text-ink">
                  {{ route.title || `路线 ${routeIndex + 1}` }}
                </div>
                <div class="mt-2 text-xs text-slate-500">
                  {{ route.from_name || "起点待定" }} → {{ route.to_name || "终点待定" }}
                </div>
                <div class="mt-2 text-xs text-slate-500">
                  {{ route.distance_text || "距离待补充" }}
                  {{ route.duration_text ? ` · ${route.duration_text}` : "" }}
                </div>
                <div class="mt-2 text-xs text-[#2f5a81]">
                  当段交通费用：{{
                    formatCny(route.estimated_transport_cost_cny, "/人") || "待确认"
                  }}
                </div>
              </div>
            </div>
            <div v-else class="mt-3 text-slate-500">暂无路线信息</div>
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
                <div v-if="meal.poi?.address" class="mt-1 text-xs text-slate-500">
                  {{ shortAddress(meal.poi.address) }}
                </div>
                <div class="mt-2 text-xs text-[#2f5a81]">
                  {{
                    meal.estimated_cost ||
                    formatCny(meal.estimated_cost_cny, "/人") ||
                    "费用待确认"
                  }}
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
