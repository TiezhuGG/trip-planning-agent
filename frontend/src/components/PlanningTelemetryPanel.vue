<script setup lang="ts">
import { computed, ref } from "vue";

import type {
  PlanningTelemetry,
  StageTimingPoint,
  StageTimingStats,
} from "../types/planning";

type TimeWindow = "all" | "5m" | "1h";

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

const windowLabel = computed(() => {
  if (timeWindow.value === "5m") return "最近 5 分钟";
  if (timeWindow.value === "1h") return "最近 1 小时";
  return "全部";
});

const cacheHitRate = computed(() => {
  if (!props.telemetry.total_requests) return 0;
  return Math.round((props.telemetry.cache_hits / props.telemetry.total_requests) * 100);
});

const stageRows = computed(() => {
  const keyword = filterText.value.trim().toLowerCase();
  const rows = Object.entries(props.telemetry.stages ?? {}).map(([stage, stats]) => {
    const points = pointsForWindow(stats);
    const values = points.length ? points.map((item) => item.value_ms) : stats.recent_ms ?? [];
    return {
      stage,
      stats,
      points,
      values,
      slow: stageTone(stats) === "slow",
    };
  });

  const filtered = rows.filter((row) => {
    if (slowOnly.value && !row.slow) return false;
    if (!keyword) return true;
    return stageLabel(row.stage).toLowerCase().includes(keyword);
  });

  filtered.sort((left, right) => {
    const leftSlow = left.slow ? 1 : 0;
    const rightSlow = right.slow ? 1 : 0;
    if (leftSlow !== rightSlow) return rightSlow - leftSlow;
    return right.stats.p95_ms - left.stats.p95_ms;
  });

  return filtered;
});

const telemetrySummary = computed(() => {
  const lines: string[] = [];
  lines.push("# Planner Telemetry Report");
  lines.push("");
  lines.push(`- Time: ${formatDatetime(props.telemetry.updated_at)}`);
  lines.push(`- Range: ${windowLabel.value}`);
  lines.push(`- Requests: ${props.telemetry.total_requests}`);
  lines.push(`- Cache Hit: ${props.telemetry.cache_hits} (${cacheHitRate.value}%)`);
  lines.push(`- Window Size: ${props.telemetry.window_size}`);
  lines.push("");

  const slowStages = stageRows.value.filter((item) => item.slow).slice(0, 5);
  if (slowStages.length) {
    lines.push("## Slow Stages (Top)");
    for (const item of slowStages) {
      lines.push(
        `- ${stageLabel(item.stage)}: p95=${item.stats.p95_ms}ms, max=${item.stats.max_ms}ms, last=${item.stats.last_ms}ms`,
      );
    }
    lines.push("");
  }

  lines.push("## Stage Table");
  lines.push("");
  lines.push("| Stage | Count | P50 | P95 | Max | Last |");
  lines.push("| --- | ---: | ---: | ---: | ---: | ---: |");
  for (const item of stageRows.value) {
    lines.push(
      `| ${stageLabel(item.stage)} | ${item.stats.count} | ${item.stats.p50_ms}ms | ${item.stats.p95_ms}ms | ${item.stats.max_ms}ms | ${item.stats.last_ms}ms |`,
    );
  }
  if (!stageRows.value.length) {
    lines.push("| (no data) | 0 | 0ms | 0ms | 0ms | 0ms |");
  }
  return lines.join("\n");
});

function stageTone(stats: StageTimingStats): "slow" | "normal" {
  if (stats.p95_ms >= 8000 || stats.max_ms >= 10000) return "slow";
  return "normal";
}

function stageLabel(name: string): string {
  return name.replace(/_/g, " ");
}

function formatDatetime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function pointsForWindow(stats: StageTimingStats): StageTimingPoint[] {
  const points = stats.recent_points ?? [];
  if (timeWindow.value === "all") return points;

  const now = Date.now();
  const windowMs = timeWindow.value === "5m" ? 5 * 60 * 1000 : 60 * 60 * 1000;
  const cutoff = now - windowMs;
  return points.filter((item) => {
    const ts = new Date(item.at).getTime();
    return !Number.isNaN(ts) && ts >= cutoff;
  });
}

function sparklinePoints(values: number[]): string {
  if (!values.length) return "";
  if (values.length === 1) return "0,20 120,20";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1, max - min);
  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 120;
      const y = 22 - ((value - min) / span) * 18;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

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
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Telemetry</div>
        <h3 class="mt-2 text-xl font-semibold text-ink">阶段耗时统计</h3>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="rounded-full border border-[#c9d6e2] bg-white px-4 py-2 text-sm text-[#35516b]"
          @click="copySummary"
        >
          {{ copied ? "已复制" : "复制摘要" }}
        </button>
        <button
          type="button"
          class="rounded-full border border-[#c9d6e2] bg-white px-4 py-2 text-sm text-[#35516b]"
          @click="exportMarkdown"
        >
          导出 Markdown
        </button>
        <button
          type="button"
          class="rounded-full border border-[#c9d6e2] bg-[#f5f8fb] px-4 py-2 text-sm text-[#35516b]"
          @click="emit('refresh')"
        >
          {{ loading ? "刷新中..." : "刷新" }}
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
        <span class="mb-1 block text-xs text-slate-500">时间窗口</span>
        <select
          v-model="timeWindow"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        >
          <option value="all">全部</option>
          <option value="5m">最近 5 分钟</option>
          <option value="1h">最近 1 小时</option>
        </select>
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-1 block text-xs text-slate-500">Stage 过滤</span>
        <input
          v-model="filterText"
          type="text"
          placeholder="例如 route / compose"
          class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        />
      </label>
      <label class="flex items-end gap-2 text-sm text-slate-600">
        <input v-model="slowOnly" type="checkbox" class="h-4 w-4 rounded border-slate-300" />
        <span>仅看慢阶段</span>
      </label>
    </div>

    <div class="mt-5 grid gap-3 sm:grid-cols-4">
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">Requests</div>
        <div class="mt-2 font-medium text-ink">{{ telemetry.total_requests }}</div>
      </div>
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">Cache Hit</div>
        <div class="mt-2 font-medium text-ink">{{ telemetry.cache_hits }}</div>
      </div>
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">Hit Rate</div>
        <div class="mt-2 font-medium text-ink">{{ cacheHitRate }}%</div>
      </div>
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">Window</div>
        <div class="mt-2 font-medium text-ink">{{ telemetry.window_size }}</div>
      </div>
    </div>

    <div class="mt-4 text-xs text-slate-500">
      最近更新时间：{{ formatDatetime(telemetry.updated_at) }}
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
            <th class="px-3 py-2">Stage</th>
            <th class="px-3 py-2">Trend</th>
            <th class="px-3 py-2">Count</th>
            <th class="px-3 py-2">P50</th>
            <th class="px-3 py-2">P95</th>
            <th class="px-3 py-2">Max</th>
            <th class="px-3 py-2">Last</th>
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
            <td class="px-3 py-3 text-slate-500" colspan="7">暂无阶段统计数据</td>
          </tr>
        </tbody>
      </table>
    </div>
  </article>
</template>
