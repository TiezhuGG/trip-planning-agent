<script setup lang="ts">
import { computed, ref } from "vue";

import type {
  DayGapType,
  DayReadinessItem,
  DayReadinessSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";
import { getReservationTargetDays } from "../composables/tripWorkspaceReservationCoverageHelpers";
import type { ReservationItem, ReservationType, TripWorkspace } from "../types/planning";
import { addDays } from "../utils/tripPlannerForm";
import { formatDateTimeZhCn } from "../utils/workspaceFormatting";

import PlannerReservationDraftForm from "./PlannerReservationDraftForm.vue";
import PlannerReservationInsights from "./PlannerReservationInsights.vue";

type ReservationStateFilter = "all" | "upcoming" | "ongoing" | "past" | "unscheduled";
type ReservationCoverageFilter = "all" | "covered" | "unresolved" | "pending";
type ReservationSortMode = "time" | "coverage" | "type";

const props = defineProps<{
  workspace: TripWorkspace | null;
  saving: boolean;
  replanningDays: number[];
  reservations: ReservationItem[];
  reservationAlerts: string[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
}>();

const emit = defineEmits<{
  (event: "repair-day-gap", payload: { dayNumber: number; gapType: DayGapType }): void;
  (event: "add-reservation", value: Omit<ReservationItem, "id">): void;
  (event: "remove-reservation", id: string): void;
}>();

const filterText = ref("");
const activeType = ref<"all" | ReservationType>("all");
const activeState = ref<ReservationStateFilter>("all");
const activeCoverage = ref<ReservationCoverageFilter>("all");
const activeDay = ref<"all" | number>("all");
const activeSort = ref<ReservationSortMode>("coverage");
const draftTemplate = ref<ReservationItem | null>(null);

function formatDateTime(value?: string | null) {
  return formatDateTimeZhCn(value);
}

const RESERVATION_TYPE_LABELS: Record<ReservationType, string> = {
  flight: "航班",
  train: "火车",
  hotel: "酒店",
  restaurant: "餐厅预订",
  ticket: "门票 / 活动",
  other: "其他安排",
};

const chronologicallySortedReservations = computed(() =>
  [...props.reservations].sort((left, right) => {
    const leftTime = left.start_at ? new Date(left.start_at).getTime() : Number.MAX_SAFE_INTEGER;
    const rightTime = right.start_at ? new Date(right.start_at).getTime() : Number.MAX_SAFE_INTEGER;
    if (leftTime !== rightTime) return leftTime - rightTime;
    return left.title.localeCompare(right.title, "zh-CN");
  }),
);

function formatReservationType(type: ReservationType) {
  return RESERVATION_TYPE_LABELS[type];
}

function resolveReservationState(item: ReservationItem): Exclude<ReservationStateFilter, "all"> {
  if (!item.start_at) return "unscheduled";
  const start = new Date(item.start_at);
  if (Number.isNaN(start.getTime())) return "unscheduled";
  const now = Date.now();
  const end = item.end_at ? new Date(item.end_at) : null;
  if (end && !Number.isNaN(end.getTime()) && end.getTime() < now) return "past";
  if (start.getTime() > now) return "upcoming";
  return "ongoing";
}

function formatReservationStateLabel(item: ReservationItem) {
  const state = resolveReservationState(item);
  if (state === "upcoming") return "即将开始";
  if (state === "ongoing") return "进行中";
  if (state === "past") return "已结束";
  return "时间待定";
}

function reservationStateClass(item: ReservationItem) {
  const state = resolveReservationState(item);
  if (state === "upcoming") return "bg-sky-50 text-sky-700";
  if (state === "ongoing") return "bg-emerald-50 text-emerald-700";
  if (state === "past") return "bg-slate-100 text-slate-600";
  return "bg-amber-50 text-amber-700";
}

const reservationStateFilters = computed(() => {
  const counts = chronologicallySortedReservations.value.reduce<
    Record<Exclude<ReservationStateFilter, "all">, number>
  >(
    (accumulator, item) => {
      accumulator[resolveReservationState(item)] += 1;
      return accumulator;
    },
    {
      upcoming: 0,
      ongoing: 0,
      past: 0,
      unscheduled: 0,
    },
  );

  return [
    { key: "all" as const, label: "全部状态", count: chronologicallySortedReservations.value.length },
    { key: "upcoming" as const, label: "即将开始", count: counts.upcoming },
    { key: "ongoing" as const, label: "进行中", count: counts.ongoing },
    { key: "past" as const, label: "已结束", count: counts.past },
    { key: "unscheduled" as const, label: "时间待定", count: counts.unscheduled },
  ].filter((item) => item.key === "all" || item.count > 0);
});

const reservationSummaryCards = computed(() => {
  const stateCounts = reservationStateFilters.value.reduce<Partial<Record<ReservationStateFilter, number>>>(
    (accumulator, item) => {
      accumulator[item.key] = item.count;
      return accumulator;
    },
    {},
  );

  return [
    {
      key: "all" as const,
      label: "固定预订",
      count: chronologicallySortedReservations.value.length,
      tone: "border-[#dfe8f1] bg-white text-[#35516b]",
    },
    {
      key: "upcoming" as const,
      label: "即将开始",
      count: stateCounts.upcoming ?? 0,
      tone: "border-sky-100 bg-sky-50 text-sky-700",
    },
    {
      key: "ongoing" as const,
      label: "进行中",
      count: stateCounts.ongoing ?? 0,
      tone: "border-emerald-100 bg-emerald-50 text-emerald-700",
    },
    {
      key: "unscheduled" as const,
      label: "时间待定",
      count: stateCounts.unscheduled ?? 0,
      tone: "border-amber-100 bg-amber-50 text-amber-700",
    },
  ];
});

const reservationTypeFilters = computed(() => {
  const counts = chronologicallySortedReservations.value.reduce<Record<ReservationType, number>>(
    (accumulator, item) => {
      accumulator[item.type] += 1;
      return accumulator;
    },
    {
      flight: 0,
      train: 0,
      hotel: 0,
      restaurant: 0,
      ticket: 0,
      other: 0,
    },
  );

  return [
    { key: "all" as const, label: "全部类型", count: chronologicallySortedReservations.value.length },
    ...Object.entries(RESERVATION_TYPE_LABELS)
      .map(([key, label]) => ({
        key: key as ReservationType,
        label,
        count: counts[key as ReservationType],
      }))
      .filter((item) => item.count > 0),
  ];
});

const reservationCoverageMap = computed(
  () => new Map(props.reservationCoverageItems.map((item) => [item.id, item])),
);

const reservationCoverageFilters = computed(() => {
  const counts = props.reservationCoverageItems.reduce<
    Record<Exclude<ReservationCoverageFilter, "all">, number>
  >(
    (accumulator, item) => {
      accumulator[item.status] += 1;
      return accumulator;
    },
    {
      covered: 0,
      unresolved: 0,
      pending: 0,
    },
  );

  return [
    { key: "all" as const, label: "全部落地状态", count: chronologicallySortedReservations.value.length },
    { key: "covered" as const, label: "已落地", count: counts.covered },
    { key: "unresolved" as const, label: "待处理", count: counts.unresolved },
    { key: "pending" as const, label: "待生成", count: counts.pending },
  ].filter((item) => item.key === "all" || item.count > 0);
});

const reservationSortOptions: Array<{ key: ReservationSortMode; label: string }> = [
  { key: "coverage", label: "按落地优先" },
  { key: "time", label: "按时间优先" },
  { key: "type", label: "按类型优先" },
];

const reservationTargetDaysMap = computed(() => {
  if (!props.workspace) return new Map<string, number[]>();

  return new Map(
    props.reservations.map((item) => [item.id, getReservationTargetDays(item, props.workspace as TripWorkspace)]),
  );
});

const reservationDayFilters = computed(() => {
  const workspace = props.workspace;
  if (!workspace) return [];

  return Array.from({ length: workspace.request_brief.days }, (_, index) => {
    const dayNumber = index + 1;
    const date = addDays(workspace.request_brief.start_date, index);
    const total = props.reservations.filter(
      (item) => reservationTargetDaysMap.value.get(item.id)?.includes(dayNumber),
    ).length;
    const unresolved = props.reservationCoverageItems.filter(
      (item) =>
        reservationTargetDaysMap.value.get(item.id)?.includes(dayNumber) &&
        (item.status === "unresolved" || item.status === "pending"),
    ).length;

    return {
      dayNumber,
      date,
      total,
      unresolved,
      label: `D${dayNumber} ${date.slice(5)}`,
    };
  });
});

const dayShortcutFilters = computed(() =>
  reservationDayFilters.value.filter((item) => item.unresolved > 0),
);

const followUpDayRepairActions = computed(() =>
  dayShortcutFilters.value.map((item) => {
    const readiness = props.dayReadinessItems.find((entry) => entry.dayNumber === item.dayNumber);
    const reservationAction = readiness?.actions.find((action) => action.gapType === "reservation");
    return {
      dayNumber: item.dayNumber,
      unresolved: item.unresolved,
      date: item.date,
      repairLabel: reservationAction?.label ?? "落地预订",
    };
  }),
);

const filteredReservations = computed(() => {
  const keyword = filterText.value.trim().toLowerCase();
  const filtered = chronologicallySortedReservations.value.filter((item) => {
    if (activeDay.value !== "all" && !reservationTargetDaysMap.value.get(item.id)?.includes(activeDay.value)) {
      return false;
    }
    if (activeCoverage.value !== "all" && reservationCoverageMap.value.get(item.id)?.status !== activeCoverage.value) {
      return false;
    }
    if (activeType.value !== "all" && item.type !== activeType.value) return false;
    if (activeState.value !== "all" && resolveReservationState(item) !== activeState.value) return false;
    if (!keyword) return true;
    return [item.title, item.location, item.source, item.confirmation_code, item.notes]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(keyword));
  });

  if (activeSort.value === "time") {
    return filtered;
  }

  if (activeSort.value === "type") {
    return [...filtered].sort((left, right) => {
      const typeCompare = formatReservationType(left.type).localeCompare(formatReservationType(right.type), "zh-CN");
      if (typeCompare !== 0) return typeCompare;
      const leftTime = left.start_at ? new Date(left.start_at).getTime() : Number.MAX_SAFE_INTEGER;
      const rightTime = right.start_at ? new Date(right.start_at).getTime() : Number.MAX_SAFE_INTEGER;
      if (leftTime !== rightTime) return leftTime - rightTime;
      return left.title.localeCompare(right.title, "zh-CN");
    });
  }

  return [...filtered].sort((left, right) => {
    const leftCoverage = reservationCoveragePriority(left);
    const rightCoverage = reservationCoveragePriority(right);
    if (leftCoverage !== rightCoverage) return leftCoverage - rightCoverage;

    const leftDay = firstReservationDay(left);
    const rightDay = firstReservationDay(right);
    if (leftDay !== rightDay) return leftDay - rightDay;

    const leftTime = left.start_at ? new Date(left.start_at).getTime() : Number.MAX_SAFE_INTEGER;
    const rightTime = right.start_at ? new Date(right.start_at).getTime() : Number.MAX_SAFE_INTEGER;
    if (leftTime !== rightTime) return leftTime - rightTime;
    return left.title.localeCompare(right.title, "zh-CN");
  });
});

function resetFilters() {
  filterText.value = "";
  activeType.value = "all";
  activeState.value = "all";
  activeCoverage.value = "all";
  activeDay.value = "all";
  activeSort.value = "coverage";
}

function reuseReservation(item: ReservationItem) {
  draftTemplate.value = { ...item };
}

function clearDraftTemplate() {
  draftTemplate.value = null;
}

function isTemplateReservation(item: ReservationItem) {
  return draftTemplate.value?.id === item.id;
}

function reservationDaysLabel(item: ReservationItem) {
  const days = reservationTargetDaysMap.value.get(item.id) ?? [];
  if (!days.length) return "未映射到具体行程日";
  return days.map((dayNumber) => `D${dayNumber}`).join("、");
}

function firstReservationDay(item: ReservationItem) {
  return reservationTargetDaysMap.value.get(item.id)?.[0] ?? Number.MAX_SAFE_INTEGER;
}

function reservationCoverageLabel(item: ReservationItem) {
  const status = reservationCoverageMap.value.get(item.id)?.status;
  if (status === "covered") return "已落地";
  if (status === "unresolved") return "待处理";
  if (status === "pending") return "待生成";
  return "未校验";
}

function reservationCoverageClass(item: ReservationItem) {
  const status = reservationCoverageMap.value.get(item.id)?.status;
  if (status === "covered") return "bg-emerald-50 text-emerald-700";
  if (status === "unresolved") return "bg-amber-50 text-amber-700";
  if (status === "pending") return "bg-slate-100 text-slate-600";
  return "bg-slate-100 text-slate-600";
}

function reservationCoverageReasonSummary(item: ReservationItem) {
  return reservationCoverageMap.value.get(item.id)?.reasonSummary ?? "";
}

function reservationCoveragePriority(item: ReservationItem) {
  const status = reservationCoverageMap.value.get(item.id)?.status;
  if (status === "unresolved") return 0;
  if (status === "pending") return 1;
  if (status === "covered") return 2;
  return 3;
}

function repairableDays(item: ReservationItem) {
  const coverage = reservationCoverageMap.value.get(item.id);
  if (!coverage || coverage.status === "covered") return [];
  return reservationTargetDaysMap.value.get(item.id) ?? [];
}
</script>

<template>
  <div class="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
    <div class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4">
      <div class="font-medium text-ink">固定预订 / 外部安排</div>
      <PlannerReservationInsights
        :reservation-alerts="props.reservationAlerts"
        :reservation-coverage-summary="props.reservationCoverageSummary"
        :reservation-coverage-items="props.reservationCoverageItems"
        :day-readiness-summary="props.dayReadinessSummary"
        :day-readiness-items="props.dayReadinessItems"
        :replanning-days="props.replanningDays"
        @repair-day-gap="(payload) => emit('repair-day-gap', payload)"
      />

      <div v-if="chronologicallySortedReservations.length" class="mt-4 space-y-3">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <button
            v-for="item in reservationSummaryCards"
            :key="item.key"
            type="button"
            class="rounded-[18px] border px-4 py-3 text-left transition hover:-translate-y-0.5 hover:shadow-sm"
            :class="activeState === item.key ? 'border-[#16324d] bg-[#16324d] text-white' : item.tone"
            @click="activeState = item.key"
          >
            <div class="text-xs tracking-[0.16em] opacity-70">{{ item.label }}</div>
            <div class="mt-2 text-2xl font-semibold">{{ item.count }}</div>
          </button>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="text-xs text-slate-500">
            当前显示 {{ filteredReservations.length }} / {{ chronologicallySortedReservations.length }} 条预订
            <span v-if="activeDay !== 'all'">，聚焦 D{{ activeDay }}</span>
          </div>
          <input
            v-model="filterText"
            type="text"
            class="w-full rounded-[16px] border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 sm:w-72"
            placeholder="搜索标题、地点、来源、确认号或备注"
          />
        </div>

        <div
          v-if="filterText || activeType !== 'all' || activeState !== 'all' || activeCoverage !== 'all' || activeDay !== 'all'"
          class="flex justify-end"
        >
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
            @click="resetFilters"
          >
            清空筛选
          </button>
        </div>

        <div v-if="reservationDayFilters.length" class="grid gap-2">
          <div class="text-xs text-slate-500">按行程日聚焦</div>
          <div class="flex flex-wrap gap-2 text-xs">
            <button
              type="button"
              class="rounded-full border px-3 py-1 transition"
              :class="
                activeDay === 'all'
                  ? 'border-[#16324d] bg-[#16324d] text-white'
                  : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
              "
              @click="activeDay = 'all'"
            >
              全部 {{ chronologicallySortedReservations.length }}
            </button>
            <button
              v-for="item in reservationDayFilters"
              :key="item.dayNumber"
              type="button"
              class="rounded-full border px-3 py-1 transition"
              :class="
                activeDay === item.dayNumber
                  ? 'border-[#16324d] bg-[#16324d] text-white'
                  : item.unresolved
                    ? 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'
                    : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
              "
              @click="activeDay = item.dayNumber"
            >
              {{ item.label }} {{ item.total }}
              <span v-if="item.unresolved"> / {{ item.unresolved }} 待处理</span>
            </button>
          </div>
        </div>

        <div v-if="dayShortcutFilters.length" class="grid gap-2">
          <div class="text-xs text-slate-500">需要优先处理</div>
          <div class="flex flex-wrap gap-2 text-xs">
            <button
              type="button"
              class="rounded-full border border-[#16324d] bg-[#16324d] px-3 py-1 text-white transition hover:bg-[#22486d]"
              @click="activeDay = dayShortcutFilters[0].dayNumber"
            >
              先看 D{{ dayShortcutFilters[0].dayNumber }}
            </button>
            <button
              v-for="item in dayShortcutFilters"
              :key="`follow-up-${item.dayNumber}`"
              type="button"
              class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700 transition hover:bg-amber-100"
              @click="activeDay = item.dayNumber"
            >
              聚焦 D{{ item.dayNumber }} / {{ item.unresolved }} 条待处理
            </button>
          </div>
          <div class="flex flex-wrap gap-2 text-xs">
            <button
              v-for="item in followUpDayRepairActions"
              :key="`repair-batch-${item.dayNumber}`"
              type="button"
              class="rounded-full border border-slate-200 bg-white px-3 py-1 text-[#35516b] transition hover:bg-[#eef4f9] disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="props.replanningDays.includes(item.dayNumber)"
              @click="emit('repair-day-gap', { dayNumber: item.dayNumber, gapType: 'reservation' })"
            >
              {{
                props.replanningDays.includes(item.dayNumber)
                  ? `D${item.dayNumber} 修复中...`
                  : `${item.repairLabel} · D${item.dayNumber}`
              }}
            </button>
          </div>
        </div>

        <div class="flex flex-wrap gap-2 text-xs">
          <button
            v-for="item in reservationTypeFilters"
            :key="item.key"
            type="button"
            class="rounded-full border px-3 py-1 transition"
            :class="
              activeType === item.key
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
            "
            @click="activeType = item.key"
          >
            {{ item.label }} {{ item.count }}
          </button>
        </div>

        <div class="flex flex-wrap gap-2 text-xs">
          <button
            v-for="item in reservationStateFilters"
            :key="item.key"
            type="button"
            class="rounded-full border px-3 py-1 transition"
            :class="
              activeState === item.key
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
            "
            @click="activeState = item.key"
          >
            {{ item.label }} {{ item.count }}
          </button>
        </div>

        <div class="flex flex-wrap gap-2 text-xs">
          <button
            v-for="item in reservationCoverageFilters"
            :key="item.key"
            type="button"
            class="rounded-full border px-3 py-1 transition"
            :class="
              activeCoverage === item.key
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : item.key === 'unresolved'
                  ? 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'
                  : item.key === 'pending'
                    ? 'border-slate-200 bg-slate-100 text-slate-600 hover:bg-slate-200'
                    : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
            "
            @click="activeCoverage = item.key"
          >
            {{ item.label }} {{ item.count }}
          </button>
        </div>

        <div class="flex flex-wrap gap-2 text-xs">
          <button
            v-for="item in reservationSortOptions"
            :key="item.key"
            type="button"
            class="rounded-full border px-3 py-1 transition"
            :class="
              activeSort === item.key
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
            "
            @click="activeSort = item.key"
          >
            {{ item.label }}
          </button>
        </div>
      </div>

      <div
        v-if="chronologicallySortedReservations.length && !filteredReservations.length"
        class="mt-4 text-sm text-slate-500"
      >
        当前筛选条件下没有匹配的预订。
      </div>

      <div v-else-if="chronologicallySortedReservations.length" class="mt-4 space-y-3">
        <div
          v-for="item in filteredReservations"
          :key="item.id"
          class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-sm text-slate-600"
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="font-medium text-ink">{{ item.title }}</div>
              <div class="mt-1 flex flex-wrap items-center gap-2 text-xs">
                <span class="tracking-[0.12em] text-slate-400">
                  {{ formatReservationType(item.type) }}
                </span>
                <span class="rounded-full px-2.5 py-1" :class="reservationStateClass(item)">
                  {{ formatReservationStateLabel(item) }}
                </span>
                <span class="rounded-full px-2.5 py-1" :class="reservationCoverageClass(item)">
                  {{ reservationCoverageLabel(item) }}
                </span>
              </div>
            </div>
            <button
              type="button"
              class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-[#35516b]"
              @click="emit('remove-reservation', item.id)"
            >
              删除
            </button>
          </div>

          <div class="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="rounded-full border px-3 py-1 text-xs transition"
              :class="
                isTemplateReservation(item)
                  ? 'border-sky-200 bg-sky-50 text-sky-700'
                  : 'border-slate-200 bg-white text-[#35516b] hover:bg-[#eef4f9]'
              "
              @click="reuseReservation(item)"
            >
              {{ isTemplateReservation(item) ? "当前已作模板" : "复用到草稿" }}
            </button>
            <button
              v-if="isTemplateReservation(item)"
              type="button"
              class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
              @click="clearDraftTemplate"
            >
              退出模板
            </button>
            <button
              v-for="dayNumber in repairableDays(item)"
              :key="`${item.id}-repair-${dayNumber}`"
              type="button"
              class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs text-amber-700 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="props.replanningDays.includes(dayNumber)"
              @click="emit('repair-day-gap', { dayNumber, gapType: 'reservation' })"
            >
              {{
                props.replanningDays.includes(dayNumber)
                  ? `D${dayNumber} 修复中...`
                  : `修复 D${dayNumber}`
              }}
            </button>
          </div>

          <div class="mt-3 text-xs text-slate-500">
            时间：{{ formatDateTime(item.start_at) }}{{ item.end_at ? ` - ${formatDateTime(item.end_at)}` : "" }}
          </div>
          <div class="mt-1 text-xs text-slate-500">映射行程日：{{ reservationDaysLabel(item) }}</div>
          <div
            v-if="reservationCoverageReasonSummary(item)"
            class="mt-2 rounded-[12px] border border-slate-100 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-500"
          >
            {{ reservationCoverageReasonSummary(item) }}
          </div>
          <div v-if="item.location" class="mt-1 text-xs text-slate-500">地点：{{ item.location }}</div>
          <div v-if="item.confirmation_code" class="mt-1 text-xs text-slate-500">
            确认号：{{ item.confirmation_code }}
          </div>
          <div v-if="item.source" class="mt-1 text-xs text-slate-500">来源：{{ item.source }}</div>
          <div v-if="item.notes" class="mt-2 text-sm text-slate-600">{{ item.notes }}</div>
        </div>
      </div>

      <div v-else class="mt-4 text-sm text-slate-500">
        还没有固定预订。可以先录入酒店、交通、门票或餐厅预订，后续生成和重排会优先围绕这些固定安排展开。
      </div>
    </div>

    <PlannerReservationDraftForm
      :workspace="props.workspace"
      :saving="props.saving"
      :template-reservation="draftTemplate"
      @add-reservation="(value) => emit('add-reservation', value)"
      @clear-template="clearDraftTemplate"
    />
  </div>
</template>
