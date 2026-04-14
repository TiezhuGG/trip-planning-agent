<script setup lang="ts">
import type {
  DayReadinessItem,
  DayReadinessSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";

defineProps<{
  reservationAlerts: string[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
}>();
</script>

<template>
  <div>
    <div
      v-if="reservationAlerts.length"
      class="mt-4 rounded-[18px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      <div class="font-medium">预订提醒</div>
      <div class="mt-2 space-y-1 text-xs leading-5">
        <div v-for="item in reservationAlerts" :key="item">{{ item }}</div>
      </div>
    </div>

    <div
      v-if="reservationCoverageSummary.total"
      class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-sm text-slate-600"
    >
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="font-medium text-ink">预订覆盖检查</div>
        <div class="flex flex-wrap gap-2 text-xs">
          <span class="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
            已覆盖 {{ reservationCoverageSummary.covered }}
          </span>
          <span class="rounded-full bg-amber-50 px-3 py-1 text-amber-700">
            待确认 {{ reservationCoverageSummary.unresolved }}
          </span>
          <span class="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
            待生成 {{ reservationCoverageSummary.pending }}
          </span>
        </div>
      </div>
      <div class="mt-3 space-y-2">
        <div
          v-for="item in reservationCoverageItems"
          :key="item.id"
          class="rounded-[14px] border border-slate-100 bg-slate-50 px-3 py-3"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="font-medium text-ink">{{ item.title }}</div>
            <span
              class="rounded-full px-3 py-1 text-xs"
              :class="
                item.status === 'covered'
                  ? 'bg-emerald-100 text-emerald-700'
                  : item.status === 'unresolved'
                    ? 'bg-amber-100 text-amber-700'
                    : 'bg-slate-200 text-slate-600'
              "
            >
              {{
                item.status === "covered"
                  ? "已覆盖"
                  : item.status === "unresolved"
                    ? "待确认"
                    : "待生成"
              }}
            </span>
          </div>
          <div class="mt-2 text-xs leading-5 text-slate-500">{{ item.detail }}</div>
        </div>
      </div>
    </div>

    <div
      v-if="dayReadinessSummary.total"
      class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-sm text-slate-600"
    >
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="font-medium text-ink">按天完成度</div>
        <div class="flex flex-wrap gap-2 text-xs">
          <span class="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
            完整 {{ dayReadinessSummary.ready }}
          </span>
          <span class="rounded-full bg-sky-50 px-3 py-1 text-sky-700">
            可用 {{ dayReadinessSummary.partial }}
          </span>
          <span class="rounded-full bg-amber-50 px-3 py-1 text-amber-700">
            缺口 {{ dayReadinessSummary.missing }}
          </span>
          <span class="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
            待生成 {{ dayReadinessSummary.pending }}
          </span>
        </div>
      </div>
      <div class="mt-3 space-y-2">
        <div
          v-for="item in dayReadinessItems"
          :key="`${item.dayNumber}-${item.date}`"
          class="rounded-[14px] border border-slate-100 bg-slate-50 px-3 py-3"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="font-medium text-ink">第 {{ item.dayNumber }} 天</div>
              <div class="mt-1 text-xs text-slate-500">{{ item.date }}</div>
            </div>
            <span
              class="rounded-full px-3 py-1 text-xs"
              :class="
                item.status === 'ready'
                  ? 'bg-emerald-100 text-emerald-700'
                  : item.status === 'partial'
                    ? 'bg-sky-100 text-sky-700'
                    : item.status === 'missing'
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-slate-200 text-slate-600'
              "
            >
              {{
                item.status === "ready"
                  ? "完整"
                  : item.status === "partial"
                    ? "可用"
                    : item.status === "missing"
                      ? "缺口"
                      : "待生成"
              }}
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
              未落地 {{ item.unresolvedReservations }}
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
            v-if="item.gaps.length"
            class="mt-3 space-y-1 text-xs leading-5 text-amber-700"
          >
            <div v-for="gap in item.gaps" :key="gap">{{ gap }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
