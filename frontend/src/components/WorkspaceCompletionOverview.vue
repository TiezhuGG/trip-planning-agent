<script setup lang="ts">
import { computed } from "vue";

import { buildWorkspaceCompletionOverview } from "../composables/tripWorkspaceCompletionOverview";
import type {
  DayReadinessItem,
  DayReadinessSummary,
  DeparturePrecheckSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";
import type { PlanningJobSummary, TripWorkspace } from "../types/planning";

const props = defineProps<{
  workspace: TripWorkspace | null;
  jobs: PlanningJobSummary[];
  prechecking: boolean;
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  departurePrecheckSummary: DeparturePrecheckSummary;
}>();

const emit = defineEmits<{
  (event: "focus-days", dayNumbers: number[]): void;
  (event: "refresh-precheck"): void;
}>();

const overview = computed(() =>
  buildWorkspaceCompletionOverview({
    workspace: props.workspace,
    jobs: props.jobs,
    dayReadinessSummary: props.dayReadinessSummary,
    dayReadinessItems: props.dayReadinessItems,
    reservationCoverageSummary: props.reservationCoverageSummary,
    reservationCoverageItems: props.reservationCoverageItems,
    departurePrecheckSummary: props.departurePrecheckSummary,
  }),
);

function progressClass(score: number) {
  if (score >= 85) return "bg-emerald-500";
  if (score >= 60) return "bg-sky-500";
  return "bg-amber-500";
}

function dimensionClass(score: number) {
  if (score >= 85) return "border-emerald-100 bg-emerald-50/70";
  if (score >= 60) return "border-sky-100 bg-sky-50/70";
  return "border-amber-100 bg-amber-50/70";
}

function dimensionInteractiveClass(key: string) {
  if (isDimensionInteractive(key)) {
    return "cursor-pointer transition hover:-translate-y-0.5 hover:shadow-sm";
  }
  return "";
}

function focusDays(dayNumbers: number[]) {
  if (!dayNumbers.length) return;
  emit("focus-days", dayNumbers);
}

function isDimensionInteractive(key: string) {
  const data = overview.value;
  if (!data) return false;
  if (key === "days") return data.incompleteDayNumbers.length > 0;
  if (key === "reservations") return data.unresolvedReservationDayNumbers.length > 0;
  if (key === "precheck") return data.precheckAffectedDayNumbers.length > 0 || data.canRefreshPrecheck;
  if (key === "export") return data.canRefreshPrecheck || data.precheckAffectedDayNumbers.length > 0;
  return false;
}

function onDimensionClick(key: string) {
  const data = overview.value;
  if (!data) return;

  if (key === "days") {
    focusDays(data.incompleteDayNumbers);
    return;
  }
  if (key === "reservations") {
    focusDays(data.unresolvedReservationDayNumbers);
    return;
  }
  if (key === "precheck") {
    if (data.precheckAffectedDayNumbers.length) {
      focusDays(data.precheckAffectedDayNumbers);
      return;
    }
    if (data.canRefreshPrecheck) {
      emit("refresh-precheck");
    }
    return;
  }
  if (key === "export") {
    if (data.canRefreshPrecheck) {
      emit("refresh-precheck");
      return;
    }
    focusDays(data.precheckAffectedDayNumbers);
  }
}

function dimensionHint(key: string) {
  const data = overview.value;
  if (!data) return "";

  if (key === "days" && data.incompleteDayNumbers.length) return "点击查看未就绪日期";
  if (key === "reservations" && data.unresolvedReservationDayNumbers.length) {
    return "点击查看预订未落地日期";
  }
  if (key === "precheck") {
    if (data.precheckAffectedDayNumbers.length) return "点击查看预检影响日期";
    if (data.canRefreshPrecheck) return "点击刷新预检";
  }
  if (key === "export") {
    if (data.canRefreshPrecheck) return "点击刷新导出前预检";
    if (data.precheckAffectedDayNumbers.length) return "点击查看导出风险日期";
  }
  return "";
}
</script>

<template>
  <section
    v-if="overview"
    class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600"
  >
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="font-medium text-ink">完成度概览</div>
        <div class="mt-1 text-xs text-slate-500">{{ overview.summary }}</div>
      </div>
      <div class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3 text-right">
        <div class="text-xs uppercase tracking-[0.14em] text-slate-400">工作区评分</div>
        <div class="mt-1 text-2xl font-semibold text-ink">{{ overview.score }}</div>
        <div class="text-xs text-slate-500">{{ overview.statusLabel }}</div>
      </div>
    </div>

    <div class="mt-4 h-2 overflow-hidden rounded-full bg-white">
      <div
        class="h-full rounded-full transition-all"
        :class="progressClass(overview.score)"
        :style="{ width: `${overview.score}%` }"
      />
    </div>

    <div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <button
        v-for="dimension in overview.dimensions"
        :key="dimension.key"
        type="button"
        class="rounded-[18px] border px-4 py-4 text-left"
        :class="[dimensionClass(dimension.score), dimensionInteractiveClass(dimension.key)]"
        :disabled="!isDimensionInteractive(dimension.key)"
        @click="onDimensionClick(dimension.key)"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-xs uppercase tracking-[0.14em] text-slate-400">
              {{ dimension.title }}
            </div>
            <div class="mt-2 text-xl font-semibold text-ink">{{ dimension.score }}</div>
          </div>
        </div>
        <div class="mt-2 text-xs leading-5 text-slate-600">{{ dimension.summary }}</div>
        <div v-if="dimensionHint(dimension.key)" class="mt-2 text-[11px] text-slate-500">
          {{ dimensionHint(dimension.key) }}
        </div>
      </button>
    </div>

    <div class="mt-4 flex flex-wrap gap-3">
      <button
        v-if="overview.incompleteDayNumbers.length"
        type="button"
        class="rounded-full border border-[#d7e2ec] bg-white px-4 py-2 text-sm text-[#35516b] transition hover:bg-[#eef4f9]"
        @click="focusDays(overview.incompleteDayNumbers)"
      >
        查看未就绪日期
      </button>

      <button
        v-if="overview.unresolvedReservationDayNumbers.length"
        type="button"
        class="rounded-full border border-[#d7e2ec] bg-white px-4 py-2 text-sm text-[#35516b] transition hover:bg-[#eef4f9]"
        @click="focusDays(overview.unresolvedReservationDayNumbers)"
      >
        查看预订未落地日期
      </button>

      <button
        v-if="overview.precheckAffectedDayNumbers.length"
        type="button"
        class="rounded-full border border-[#d7e2ec] bg-white px-4 py-2 text-sm text-[#35516b] transition hover:bg-[#eef4f9]"
        @click="focusDays(overview.precheckAffectedDayNumbers)"
      >
        查看预检影响日期
      </button>

      <button
        v-if="overview.canRefreshPrecheck"
        type="button"
        class="rounded-full border border-[#16324d] bg-[#16324d] px-4 py-2 text-sm text-white transition hover:bg-[#22486d] disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="props.prechecking"
        @click="emit('refresh-precheck')"
      >
        {{ props.prechecking ? "刷新中..." : "刷新预检状态" }}
      </button>
    </div>
  </section>
</template>
