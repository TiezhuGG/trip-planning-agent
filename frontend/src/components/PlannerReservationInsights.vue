<script setup lang="ts">
import type {
  DayGapType,
  DayReadinessItem,
  DayReadinessSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";

const props = defineProps<{
  reservationAlerts: string[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
  replanningDays: number[];
}>();

const emit = defineEmits<{
  (event: "repair-day-gap", payload: { dayNumber: number; gapType: DayGapType }): void;
}>();

function coverageStatusLabel(status: ReservationCoverageItem["status"]) {
  if (status === "covered") return "已落地";
  if (status === "unresolved") return "待处理";
  return "待生成";
}

function coverageStatusClass(status: ReservationCoverageItem["status"]) {
  if (status === "covered") return "bg-emerald-100 text-emerald-700";
  if (status === "unresolved") return "bg-amber-100 text-amber-700";
  return "bg-slate-200 text-slate-600";
}

function readinessStatusLabel(status: DayReadinessItem["status"]) {
  if (status === "ready") return "完整";
  if (status === "partial") return "可用";
  if (status === "missing") return "缺口";
  return "待生成";
}

function readinessStatusClass(status: DayReadinessItem["status"]) {
  if (status === "ready") return "bg-emerald-100 text-emerald-700";
  if (status === "partial") return "bg-sky-100 text-sky-700";
  if (status === "missing") return "bg-amber-100 text-amber-700";
  return "bg-slate-200 text-slate-600";
}

function conflictKindLabel(kind: "activity" | "meal" | "stay") {
  if (kind === "activity") return "活动冲突";
  if (kind === "meal") return "用餐冲突";
  return "住宿冲突";
}
</script>

<template>
  <div>
    <div
      v-if="props.reservationAlerts.length"
      class="mt-4 rounded-[18px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      <div class="font-medium">预订提醒</div>
      <div class="mt-2 space-y-1 text-xs leading-5">
        <div v-for="item in props.reservationAlerts" :key="item">{{ item }}</div>
      </div>
    </div>

    <div
      v-if="props.reservationCoverageSummary.total"
      class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-sm text-slate-600"
    >
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="font-medium text-ink">预订落地情况</div>
        <div class="flex flex-wrap gap-2 text-xs">
          <span class="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
            已落地 {{ props.reservationCoverageSummary.covered }}
          </span>
          <span class="rounded-full bg-amber-50 px-3 py-1 text-amber-700">
            待处理 {{ props.reservationCoverageSummary.unresolved }}
          </span>
          <span class="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
            待生成 {{ props.reservationCoverageSummary.pending }}
          </span>
        </div>
      </div>

      <div class="mt-3 space-y-2">
        <div
          v-for="item in props.reservationCoverageItems"
          :key="item.id"
          class="rounded-[14px] border border-slate-100 bg-slate-50 px-3 py-3"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex flex-wrap items-center gap-2">
              <div class="font-medium text-ink">{{ item.title }}</div>
              <span
                v-if="item.autoAnchoredDays.length"
                class="rounded-full bg-sky-100 px-2.5 py-1 text-[11px] text-sky-700"
              >
                自动注入
              </span>
              <span
                v-if="item.coordinatedDays.length"
                class="rounded-full bg-violet-100 px-2.5 py-1 text-[11px] text-violet-700"
              >
                多预订协调
              </span>
            </div>
            <span class="rounded-full px-3 py-1 text-xs" :class="coverageStatusClass(item.status)">
              {{ coverageStatusLabel(item.status) }}
            </span>
          </div>

          <div class="mt-2 text-xs leading-5 text-slate-500">{{ item.detail }}</div>

          <div
            v-if="item.reasonSummary && (item.status !== 'covered' || item.autoAnchoredDays.length)"
            class="mt-2 rounded-[12px] px-3 py-2 text-xs leading-5"
            :class="
              item.status === 'unresolved'
                ? 'border border-amber-100 bg-amber-50 text-amber-700'
                : item.status === 'pending'
                  ? 'border border-slate-200 bg-slate-100 text-slate-600'
                  : 'border border-sky-100 bg-sky-50 text-sky-700'
            "
          >
            {{ item.reasonSummary }}
          </div>

          <div v-if="item.conflictItems.length" class="mt-2 space-y-2">
            <div
              v-for="conflict in item.conflictItems"
              :key="`${item.id}-${conflict.dayNumber}-${conflict.kind}-${conflict.label}`"
              class="rounded-[12px] border border-amber-100 bg-white px-3 py-2 text-xs leading-5 text-amber-800"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] text-amber-700">
                  D{{ conflict.dayNumber }}
                </span>
                <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600">
                  {{ conflictKindLabel(conflict.kind) }}
                </span>
                <span v-if="conflict.timeText" class="text-[11px] text-slate-500">
                  {{ conflict.timeText }}
                </span>
              </div>
              <div class="mt-1">{{ conflict.summary }}</div>
            </div>
          </div>

          <div
            v-if="item.coordinationTip"
            class="mt-2 rounded-[12px] border border-violet-100 bg-violet-50 px-3 py-2 text-xs leading-5 text-violet-700"
          >
            {{ item.coordinationTip }}
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="props.dayReadinessSummary.total"
      class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-sm text-slate-600"
    >
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="font-medium text-ink">按天完成度</div>
        <div class="flex flex-wrap gap-2 text-xs">
          <span class="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
            完整 {{ props.dayReadinessSummary.ready }}
          </span>
          <span class="rounded-full bg-sky-50 px-3 py-1 text-sky-700">
            可用 {{ props.dayReadinessSummary.partial }}
          </span>
          <span class="rounded-full bg-amber-50 px-3 py-1 text-amber-700">
            缺口 {{ props.dayReadinessSummary.missing }}
          </span>
          <span class="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
            待生成 {{ props.dayReadinessSummary.pending }}
          </span>
        </div>
      </div>

      <div class="mt-3 space-y-2">
        <div
          v-for="item in props.dayReadinessItems"
          :key="`${item.dayNumber}-${item.date}`"
          class="rounded-[14px] border border-slate-100 bg-slate-50 px-3 py-3"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="font-medium text-ink">第 {{ item.dayNumber }} 天</div>
              <div class="mt-1 text-xs text-slate-500">{{ item.date }}</div>
            </div>
            <span class="rounded-full px-3 py-1 text-xs" :class="readinessStatusClass(item.status)">
              {{ readinessStatusLabel(item.status) }}
            </span>
          </div>

          <div class="mt-3 flex flex-wrap gap-2 text-xs">
            <span class="rounded-full bg-white px-3 py-1 text-slate-600">
              预订 {{ item.reservations }}
            </span>
            <span class="rounded-full bg-white px-3 py-1 text-slate-600">
              已落地 {{ item.coveredReservations }}
            </span>
            <span
              v-if="item.unresolvedReservations"
              class="rounded-full bg-amber-50 px-3 py-1 text-amber-700"
            >
              待处理 {{ item.unresolvedReservations }}
            </span>
          </div>

          <div class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="signal in item.signals"
              :key="signal"
              class="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-700"
            >
              {{ signal }}
            </span>
          </div>

          <div
            v-if="item.coordinationSummary"
            class="mt-3 rounded-[12px] border border-violet-100 bg-violet-50 px-3 py-2 text-xs leading-5 text-violet-700"
          >
            {{ item.coordinationSummary }}
          </div>

          <div v-if="item.gaps.length" class="mt-3 space-y-1 text-xs leading-5 text-amber-700">
            <div v-for="gap in item.gaps" :key="gap">{{ gap }}</div>
          </div>

          <div v-if="item.actions.length" class="mt-3 flex flex-wrap gap-2">
            <button
              v-for="action in item.actions"
              :key="`${item.dayNumber}-${action.gapType}`"
              type="button"
              class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1.5 text-xs text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="props.replanningDays.includes(item.dayNumber)"
              @click="emit('repair-day-gap', { dayNumber: item.dayNumber, gapType: action.gapType })"
            >
              {{ props.replanningDays.includes(item.dayNumber) ? "修复中..." : action.label }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
