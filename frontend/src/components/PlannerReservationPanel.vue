<script setup lang="ts">
import type {
  DayReadinessItem,
  DayReadinessSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";
import type { ReservationItem, TripWorkspace } from "../types/planning";

import PlannerReservationDraftForm from "./PlannerReservationDraftForm.vue";
import PlannerReservationInsights from "./PlannerReservationInsights.vue";

defineProps<{
  workspace: TripWorkspace | null;
  saving: boolean;
  reservations: ReservationItem[];
  reservationAlerts: string[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
}>();

const emit = defineEmits<{
  (event: "add-reservation", value: Omit<ReservationItem, "id">): void;
  (event: "remove-reservation", id: string): void;
}>();

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}
</script>

<template>
  <div class="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
    <div class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4">
      <div class="font-medium text-ink">固定预订 / 外部锚点</div>
      <PlannerReservationInsights
        :reservation-alerts="reservationAlerts"
        :reservation-coverage-summary="reservationCoverageSummary"
        :reservation-coverage-items="reservationCoverageItems"
        :day-readiness-summary="dayReadinessSummary"
        :day-readiness-items="dayReadinessItems"
      />

      <div v-if="reservations.length" class="mt-4 space-y-3">
        <div
          v-for="item in reservations"
          :key="item.id"
          class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-sm text-slate-600"
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="font-medium text-ink">{{ item.title }}</div>
              <div class="mt-1 text-xs uppercase tracking-[0.12em] text-slate-400">
                {{ item.type }}
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
          <div class="mt-3 text-xs text-slate-500">
            时间：{{ formatDateTime(item.start_at) }}{{ item.end_at ? ` - ${formatDateTime(item.end_at)}` : "" }}
          </div>
          <div v-if="item.location" class="mt-1 text-xs text-slate-500">地点：{{ item.location }}</div>
          <div v-if="item.confirmation_code" class="mt-1 text-xs text-slate-500">
            预订号：{{ item.confirmation_code }}
          </div>
          <div v-if="item.source" class="mt-1 text-xs text-slate-500">来源：{{ item.source }}</div>
          <div v-if="item.notes" class="mt-2 text-sm text-slate-600">{{ item.notes }}</div>
        </div>
      </div>
      <div v-else class="mt-4 text-sm text-slate-500">
        还没有固定安排。可以先录入酒店、车票、预约或门票，后续规划会围绕这些锚点展开。
      </div>
    </div>

    <PlannerReservationDraftForm
      :workspace="workspace"
      :saving="saving"
      @add-reservation="(value) => emit('add-reservation', value)"
    />
  </div>
</template>
