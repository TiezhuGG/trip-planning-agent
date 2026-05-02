<script setup lang="ts">
import { computed } from "vue";

import type { DayGapRepairPayload } from "../composables/useTripWorkspaceInsights";
import type { PrecheckSummary } from "../types/planning";
import {
  formatPrecheckStatusLabel,
  resolvePrecheckStatusBadgeClass,
} from "../utils/precheckSummary";
import { formatDateTimeZhCn, sortUniqueNumbers } from "../utils/workspaceFormatting";

type SummaryItem = NonNullable<PrecheckSummary>["items"][number];
type SummaryAction = {
  gap: NonNullable<SummaryItem["recommended_gap"]>;
  label: string;
  reason: string;
};

type DayRepairAction = {
  dayNumber: number;
  items: Array<{
    key: string;
    title: string;
    label: string;
    reason: string;
    gap: SummaryAction["gap"];
  }>;
};

const props = defineProps<{
  summary: PrecheckSummary | null | undefined;
  replanningDays: number[];
}>();

const emit = defineEmits<{
  (event: "repair-day-gap", payload: DayGapRepairPayload): void;
}>();

const warningCount = computed(
  () => props.summary?.items.filter((item) => item.after_status === "warning").length ?? 0,
);

const actionableItems = computed(() =>
  (props.summary?.items ?? []).filter(
    (item) =>
      item.after_status === "warning" &&
      resolveActions(item).length > 0 &&
      actionDays(item).length > 0,
  ),
);

const actionableCount = computed(() => actionableItems.value.length);

const affectedDaysCount = computed(() => {
  const days = new Set<number>();
  for (const item of props.summary?.items ?? []) {
    for (const day of item.after_days) {
      days.add(day);
    }
  }
  return days.size;
});

const conflictCount = computed(
  () =>
    (props.summary?.items ?? []).reduce(
      (total, item) => total + (item.conflict_items?.length ?? 0),
      0,
    ),
);

const actionableDayNumbers = computed(() =>
  sortUniqueNumbers(
    actionableItems.value.flatMap((item) => actionDays(item)),
  ),
);

const dayRepairActions = computed<DayRepairAction[]>(() => {
  const actionMap = new Map<number, DayRepairAction["items"]>();

  for (const item of actionableItems.value) {
    const days = actionDays(item);
    const actions = resolveActions(item);
    for (const dayNumber of days) {
      const current = actionMap.get(dayNumber) ?? [];
      for (const action of actions) {
        current.push({
          key: item.key,
          title: item.title,
          label: action.label,
          reason: action.reason,
          gap: action.gap,
        });
      }
      actionMap.set(dayNumber, current);
    }
  }

  return actionableDayNumbers.value.map((dayNumber) => ({
    dayNumber,
    items: actionMap.get(dayNumber) ?? [],
  }));
});

function changeLabel(item: SummaryItem) {
  if (item.before_status !== "ok" && item.after_status === "ok") return "已恢复";
  if (item.before_status === "ok" && item.after_status === "warning") return "新增风险";
  if (item.after_status === "warning") return "仍需处理";
  if (item.after_status === "pending") return "待补齐";
  return "已确认";
}

function changeClass(item: SummaryItem) {
  if (item.before_status !== "ok" && item.after_status === "ok") {
    return "bg-emerald-50 text-emerald-700";
  }
  if (item.before_status === "ok" && item.after_status === "warning") {
    return "bg-rose-50 text-rose-700";
  }
  if (item.after_status === "warning") {
    return "bg-amber-50 text-amber-700";
  }
  return "bg-slate-100 text-slate-600";
}

function formatDateTime(value?: string | null) {
  return formatDateTimeZhCn(value);
}

function formatDayLabel(day: number) {
  return `第 ${day} 天`;
}

function uniqueDays(days: number[]) {
  return sortUniqueNumbers(days);
}

function actionDays(item: SummaryItem) {
  return uniqueDays(item.after_days);
}

function isRepairingDay(day: number) {
  return props.replanningDays.includes(day);
}

function resolveActions(item: SummaryItem): SummaryAction[] {
  if (item.actions?.length) {
    return item.actions;
  }
  if (!item.recommended_gap || !item.action_label) {
    return [];
  }
  return [
    {
      gap: item.recommended_gap,
      label: item.action_label,
      reason: item.action_reason,
    },
  ];
}

function conflictKindLabel(kind: NonNullable<SummaryItem["conflict_items"]>[number]["kind"]) {
  if (kind === "activity") return "活动冲突";
  if (kind === "meal") return "用餐冲突";
  return "住宿冲突";
}

function dayCountLabel(days: number[]) {
  return days.length ? `${days.length} 个影响日期` : "无影响日期";
}

function firstRepairAction(dayNumber: number) {
  return dayRepairActions.value.find((item) => item.dayNumber === dayNumber)?.items[0] ?? null;
}

function emitRepairDay(dayNumber: number) {
  const action = firstRepairAction(dayNumber);
  if (!action) return;
  emit("repair-day-gap", {
    dayNumber,
    gapType: action.gap,
    reasonOverride: action.reason || undefined,
    actionLabelOverride: action.label || undefined,
  });
}

function summarizeDayActions(dayNumber: number) {
  const item = dayRepairActions.value.find((entry) => entry.dayNumber === dayNumber);
  if (!item) return "";
  const labels = Array.from(new Set(item.items.map((entry) => entry.label))).slice(0, 2);
  return labels.join("、");
}
</script>

<template>
  <section
    v-if="summary"
    class="mt-4 rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">最近刷新</div>
        <div class="mt-1 font-medium text-ink">最近一次预检摘要</div>
        <div class="mt-1 text-xs text-slate-500">{{ summary.title }}</div>
      </div>
      <div class="text-xs text-slate-500">{{ formatDateTime(summary.created_at) }}</div>
    </div>

    <div class="mt-4 flex flex-wrap gap-2 text-xs">
      <span class="rounded-full bg-amber-50 px-3 py-1 text-amber-700">
        待关注 {{ warningCount }}
      </span>
      <span class="rounded-full bg-sky-50 px-3 py-1 text-sky-700">
        可修复 {{ actionableCount }}
      </span>
      <span class="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
        影响日期 {{ affectedDaysCount }}
      </span>
      <span class="rounded-full bg-rose-50 px-3 py-1 text-rose-700">
        冲突 {{ conflictCount }}
      </span>
    </div>

    <div
      v-if="dayRepairActions.length"
      class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="font-medium text-ink">按天连续处理</div>
          <div class="mt-1 text-xs text-slate-500">
            汇总所有可直接修复的预检问题，优先从具体日期切入。
          </div>
        </div>
        <div class="text-xs text-slate-500">共 {{ dayRepairActions.length }} 天可处理</div>
      </div>

      <div class="mt-3 flex flex-wrap gap-2 text-xs">
        <button
          type="button"
          class="rounded-full border border-[#16324d] bg-[#16324d] px-3 py-1 text-white transition hover:bg-[#22486d] disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="isRepairingDay(dayRepairActions[0].dayNumber)"
          @click="emitRepairDay(dayRepairActions[0].dayNumber)"
        >
          {{
            isRepairingDay(dayRepairActions[0].dayNumber)
              ? `第 ${dayRepairActions[0].dayNumber} 天处理中...`
              : `先处理第 ${dayRepairActions[0].dayNumber} 天`
          }}
        </button>
        <button
          v-for="item in dayRepairActions"
          :key="`precheck-focus-${item.dayNumber}`"
          type="button"
          class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="isRepairingDay(item.dayNumber)"
          @click="emitRepairDay(item.dayNumber)"
        >
          {{
            isRepairingDay(item.dayNumber)
              ? `第 ${item.dayNumber} 天处理中...`
              : `${summarizeDayActions(item.dayNumber) || "修复预检问题"} · 第 ${item.dayNumber} 天`
          }}
        </button>
      </div>
    </div>

    <div v-if="summary.items.length" class="mt-4 space-y-3">
      <article
        v-for="item in summary.items"
        :key="item.key"
        class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <div class="font-medium text-ink">{{ item.title }}</div>
              <span class="rounded-full px-3 py-1 text-xs" :class="resolvePrecheckStatusBadgeClass(item.after_status)">
                {{ formatPrecheckStatusLabel(item.after_status) }}
              </span>
              <span class="rounded-full px-3 py-1 text-xs" :class="changeClass(item)">
                {{ changeLabel(item) }}
              </span>
            </div>
            <div class="mt-2 text-sm text-slate-700">{{ item.after_summary }}</div>
          </div>
          <div class="text-xs text-slate-500">{{ dayCountLabel(item.after_days) }}</div>
        </div>

        <div class="mt-3 grid gap-2 text-xs leading-5 text-slate-500 md:grid-cols-2">
          <div class="rounded-[14px] bg-slate-50 px-3 py-3">
            <div class="text-[11px] uppercase tracking-[0.14em] text-slate-400">变更前</div>
            <div v-if="item.before_days.length" class="mt-2 flex flex-wrap gap-2">
              <span
                v-for="day in item.before_days"
                :key="`${item.key}-before-${day}`"
                class="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600"
              >
                {{ formatDayLabel(day) }}
              </span>
            </div>
            <div class="mt-1">{{ item.before_summary }}</div>
          </div>

          <div class="rounded-[14px] bg-emerald-50/40 px-3 py-3">
            <div class="text-[11px] uppercase tracking-[0.14em] text-slate-400">变更后</div>
            <div v-if="item.after_days.length" class="mt-2 flex flex-wrap gap-2">
              <span
                v-for="day in item.after_days"
                :key="`${item.key}-after-${day}`"
                class="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600"
              >
                {{ formatDayLabel(day) }}
              </span>
            </div>
            <div class="mt-1">{{ item.after_summary }}</div>
          </div>
        </div>

        <div
          v-if="item.after_status === 'warning' && resolveActions(item).length"
          class="mt-3 space-y-2"
        >
          <div
            v-for="action in resolveActions(item)"
            :key="`${item.key}-${action.label}`"
            class="rounded-[14px] border border-[#dfe8f1] bg-[#f8fbfd] px-3 py-3"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="font-medium text-[#35516b]">{{ action.label }}</div>
              <div class="text-[11px] text-slate-500">
                {{
                  actionDays(item).length
                    ? `涉及 ${actionDays(item).length} 天`
                    : "暂无可执行日期"
                }}
              </div>
            </div>
            <div v-if="action.reason" class="mt-1 text-xs leading-5 text-slate-500">
              {{ action.reason }}
            </div>
            <div v-if="actionDays(item).length" class="mt-3 flex flex-wrap gap-2">
              <button
                v-for="day in actionDays(item)"
                :key="`${item.key}-${action.label}-${day}`"
                type="button"
                class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1.5 text-xs text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="isRepairingDay(day)"
                @click="
                  emit('repair-day-gap', {
                    dayNumber: day,
                    gapType: action.gap,
                    reasonOverride: action.reason || undefined,
                    actionLabelOverride: action.label || undefined,
                  })
                "
              >
                {{
                  isRepairingDay(day)
                    ? `${formatDayLabel(day)} 处理中...`
                    : `${action.label} · ${formatDayLabel(day)}`
                }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="item.conflict_items?.length" class="mt-3 space-y-2">
          <div
            v-for="conflict in item.conflict_items"
            :key="`${item.key}-${conflict.day_number}-${conflict.kind}-${conflict.label}`"
            class="rounded-[12px] border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800"
          >
            <div class="flex flex-wrap items-center gap-2">
              <span class="rounded-full bg-white px-2.5 py-1 text-[11px] text-amber-700">
                第 {{ conflict.day_number }} 天
              </span>
              <span class="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-600">
                {{ conflictKindLabel(conflict.kind) }}
              </span>
              <span v-if="conflict.time_text" class="text-[11px] text-slate-500">
                {{ conflict.time_text }}
              </span>
            </div>
            <div class="mt-1">{{ conflict.summary }}</div>
          </div>
        </div>
      </article>
    </div>

    <div
      v-else
      class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-xs text-slate-500"
    >
      本次刷新后，主要预检项没有发现新的状态变化。
    </div>
  </section>
</template>
