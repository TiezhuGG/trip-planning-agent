<script setup lang="ts">
import { computed, ref } from "vue";

import type { PlanningTelemetry } from "../types/planning";
import {
  buildStageRows,
  buildTelemetrySummary,
  formatTelemetryDatetime,
  sparklinePoints,
  stageLabel,
  TELEMETRY_PANEL_LABELS,
  TIME_WINDOW_LABELS,
  type TimeWindow,
} from "./planningTelemetryPanelHelpers";

const props = defineProps<{
  telemetry: PlanningTelemetry;
  loading: boolean;
  error: string;
}>();

const emit = defineEmits<{
  (event: "refresh"): void;
}>();

const copied = ref(false);
const filterText = ref("");
const slowOnly = ref(false);
const timeWindow = ref<TimeWindow>("all");
let copiedTimer: number | null = null;

const cacheHitRate = computed(() => {
  if (!props.telemetry.total_requests) return 0;
  return Math.round((props.telemetry.cache_hits / props.telemetry.total_requests) * 100);
});

const windowLabel = computed(() => TIME_WINDOW_LABELS[timeWindow.value]);

const stageRows = computed(() =>
  buildStageRows(
    props.telemetry,
    filterText.value,
    slowOnly.value,
    timeWindow.value,
  ),
);

const telemetrySummary = computed(() =>
  buildTelemetrySummary(
    props.telemetry,
    stageRows.value,
    timeWindow.value,
    cacheHitRate.value,
  ),
);

async function copySummary() {
  try {
    await navigator.clipboard.writeText(telemetrySummary.value);
    copied.value = true;
    if (copiedTimer) window.clearTimeout(copiedTimer);
    copiedTimer = window.setTimeout(() => {
      copied.value = false;
    }, 1200);
  } catch {
    copied.value = false;
  }
}

function exportMarkdown() {
  const blob = new Blob([telemetrySummary.value], { type: "text/markdown;charset=utf-8" });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  anchor.href = href;
  anchor.download = `planner-telemetry-${timestamp}.md`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(href);
}
</script>

<template>
  <article class="rounded-[36px] border border-[#d8e3ee] bg-white p-6 shadow-card">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">运行遥测</div>
        <h3 class="mt-2 text-xl font-semibold text-ink">{{ TELEMETRY_PANEL_LABELS.title }}</h3>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-full border border-[#c9d6e2] bg-white px-4 py-2 text-sm text-[#35516b]"
          @click="copySummary"
        >
          {{ copied ? TELEMETRY_PANEL_LABELS.copyDone : TELEMETRY_PANEL_LABELS.copyIdle }}
        </button>
        <button
          type="button"
          class="rounded-full border border-[#c9d6e2] bg-white px-4 py-2 text-sm text-[#35516b]"
          @click="exportMarkdown"
        >
          {{ TELEMETRY_PANEL_LABELS.exportMarkdown }}
        </button>
        <button
          type="button"
          class="rounded-full border border-[#c9d6e2] bg-[#f5f8fb] px-4 py-2 text-sm text-[#35516b]"
          @click="emit('refresh')"
        >
          {{ loading ? TELEMETRY_PANEL_LABELS.refreshLoading : TELEMETRY_PANEL_LABELS.refreshIdle }}
        </button>
      </div>
    </div>

    <div
      v-if="error"
      class="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
    >
      {{ error }}
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-3">
      <label class="text-sm text-slate-600">
        <span class="mb-1 block text-xs text-slate-500">{{ TELEMETRY_PANEL_LABELS.timeWindow }}</span>
        <select
          v-model="timeWindow"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        >
          <option value="all">{{ TIME_WINDOW_LABELS.all }}</option>
          <option value="5m">{{ TIME_WINDOW_LABELS["5m"] }}</option>
          <option value="1h">{{ TIME_WINDOW_LABELS["1h"] }}</option>
        </select>
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-1 block text-xs text-slate-500">{{ TELEMETRY_PANEL_LABELS.stageFilter }}</span>
        <input
          v-model="filterText"
          type="text"
          :placeholder="TELEMETRY_PANEL_LABELS.stageFilterPlaceholder"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        />
      </label>
      <label class="flex items-end gap-2 text-sm text-slate-600">
        <input v-model="slowOnly" type="checkbox" class="h-4 w-4 rounded border-slate-300" />
        <span>{{ TELEMETRY_PANEL_LABELS.slowOnly }}</span>
      </label>
    </div>

    <div class="mt-5 grid gap-3 sm:grid-cols-4">
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">请求数</div>
        <div class="mt-2 font-medium text-ink">{{ telemetry.total_requests }}</div>
      </div>
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">缓存命中</div>
        <div class="mt-2 font-medium text-ink">{{ telemetry.cache_hits }}</div>
      </div>
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">命中率</div>
        <div class="mt-2 font-medium text-ink">{{ cacheHitRate }}%</div>
      </div>
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">时间范围</div>
        <div class="mt-2 font-medium text-ink">{{ windowLabel }}</div>
      </div>
    </div>

    <div class="mt-4 text-xs text-slate-500">
      {{ TELEMETRY_PANEL_LABELS.updatedAt }}{{ formatTelemetryDatetime(telemetry.updated_at) }}
    </div>

    <div
      v-if="telemetry.warnings.length"
      class="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      <div v-for="item in telemetry.warnings" :key="item">{{ item }}</div>
    </div>

    <div class="mt-4 overflow-x-auto">
      <table class="min-w-full border-collapse text-sm">
        <thead>
          <tr class="text-left text-xs uppercase tracking-[0.12em] text-slate-500">
            <th class="px-3 py-2">阶段</th>
            <th class="px-3 py-2">趋势</th>
            <th class="px-3 py-2">次数</th>
            <th class="px-3 py-2">P50</th>
            <th class="px-3 py-2">P95</th>
            <th class="px-3 py-2">最大值</th>
            <th class="px-3 py-2">最近值</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in stageRows"
            :key="item.stage"
            class="border-t border-slate-100"
          >
            <td class="px-3 py-2">
              <span
                class="inline-flex rounded-full px-2 py-1 text-xs"
                :class="
                  item.slow
                    ? 'bg-amber-100 text-amber-800'
                    : 'bg-emerald-100 text-emerald-800'
                "
              >
                {{ stageLabel(item.stage) }}
              </span>
            </td>
            <td class="px-3 py-2">
              <svg viewBox="0 0 120 24" width="120" height="24" class="block">
                <polyline
                  :points="sparklinePoints(item.values)"
                  fill="none"
                  stroke="#35516b"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </td>
            <td class="px-3 py-2 text-slate-600">{{ item.stats.count }}</td>
            <td class="px-3 py-2 text-slate-600">{{ item.stats.p50_ms }}ms</td>
            <td class="px-3 py-2 text-slate-700">{{ item.stats.p95_ms }}ms</td>
            <td class="px-3 py-2 text-slate-600">{{ item.stats.max_ms }}ms</td>
            <td class="px-3 py-2 text-slate-600">{{ item.stats.last_ms }}ms</td>
          </tr>
          <tr v-if="!stageRows.length" class="border-t border-slate-100">
            <td class="px-3 py-3 text-slate-500" colspan="7">
              {{ TELEMETRY_PANEL_LABELS.noData }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </article>
</template>
