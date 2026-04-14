import type {
  PlanningTelemetry,
  StageTimingPoint,
  StageTimingStats,
} from "../types/planning";

export type TimeWindow = "all" | "5m" | "1h";

export interface TelemetryStageRow {
  stage: string;
  stats: StageTimingStats;
  points: StageTimingPoint[];
  values: number[];
  slow: boolean;
}

export const TELEMETRY_PANEL_LABELS = {
  title: "\u9636\u6bb5\u8017\u65f6\u7edf\u8ba1",
  copyIdle: "\u590d\u5236\u6458\u8981",
  copyDone: "\u5df2\u590d\u5236",
  exportMarkdown: "\u5bfc\u51fa Markdown",
  refreshIdle: "\u5237\u65b0",
  refreshLoading: "\u5237\u65b0\u4e2d...",
  timeWindow: "\u65f6\u95f4\u7a97\u53e3",
  stageFilter: "Stage \u8fc7\u6ee4",
  stageFilterPlaceholder: "\u4f8b\u5982 route / compose",
  slowOnly: "\u4ec5\u770b\u6162\u9636\u6bb5",
  updatedAt: "\u6700\u8fd1\u66f4\u65b0\u65f6\u95f4\uff1a",
  noData: "\u6682\u65e0\u9636\u6bb5\u7edf\u8ba1\u6570\u636e",
} as const;

export const TIME_WINDOW_LABELS: Record<TimeWindow, string> = {
  all: "\u5168\u90e8",
  "5m": "\u6700\u8fd1 5 \u5206\u949f",
  "1h": "\u6700\u8fd1 1 \u5c0f\u65f6",
};

export function stageTone(stats: StageTimingStats): "slow" | "normal" {
  if (stats.p95_ms >= 8000 || stats.max_ms >= 10000) return "slow";
  return "normal";
}

export function stageLabel(name: string): string {
  return name.replace(/_/g, " ");
}

export function formatTelemetryDatetime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function pointsForWindow(
  stats: StageTimingStats,
  timeWindow: TimeWindow,
  now = Date.now(),
): StageTimingPoint[] {
  const points = stats.recent_points ?? [];
  if (timeWindow === "all") return points;

  const windowMs = timeWindow === "5m" ? 5 * 60 * 1000 : 60 * 60 * 1000;
  const cutoff = now - windowMs;
  return points.filter((item) => {
    const ts = new Date(item.at).getTime();
    return !Number.isNaN(ts) && ts >= cutoff;
  });
}

export function buildStageRows(
  telemetry: PlanningTelemetry,
  filterText: string,
  slowOnly: boolean,
  timeWindow: TimeWindow,
): TelemetryStageRow[] {
  const keyword = filterText.trim().toLowerCase();
  const rows = Object.entries(telemetry.stages ?? {}).map(([stage, stats]) => {
    const points = pointsForWindow(stats, timeWindow);
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
    if (slowOnly && !row.slow) return false;
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
}

export function buildTelemetrySummary(
  telemetry: PlanningTelemetry,
  stageRows: TelemetryStageRow[],
  timeWindow: TimeWindow,
  cacheHitRate: number,
): string {
  const lines: string[] = [];
  lines.push("# Planner Telemetry Report");
  lines.push("");
  lines.push(`- Time: ${formatTelemetryDatetime(telemetry.updated_at)}`);
  lines.push(`- Range: ${TIME_WINDOW_LABELS[timeWindow]}`);
  lines.push(`- Requests: ${telemetry.total_requests}`);
  lines.push(`- Cache Hit: ${telemetry.cache_hits} (${cacheHitRate}%)`);
  lines.push(`- Window Size: ${telemetry.window_size}`);
  lines.push("");

  const slowStages = stageRows.filter((item) => item.slow).slice(0, 5);
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
  for (const item of stageRows) {
    lines.push(
      `| ${stageLabel(item.stage)} | ${item.stats.count} | ${item.stats.p50_ms}ms | ${item.stats.p95_ms}ms | ${item.stats.max_ms}ms | ${item.stats.last_ms}ms |`,
    );
  }
  if (!stageRows.length) {
    lines.push("| (no data) | 0 | 0ms | 0ms | 0ms | 0ms |");
  }
  return lines.join("\n");
}

export function sparklinePoints(values: number[]): string {
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
