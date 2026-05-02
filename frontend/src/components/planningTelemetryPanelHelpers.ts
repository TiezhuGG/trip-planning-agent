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
  title: "阶段耗时统计",
  copyIdle: "复制摘要",
  copyDone: "已复制",
  exportMarkdown: "导出 Markdown",
  refreshIdle: "刷新",
  refreshLoading: "刷新中...",
  timeWindow: "时间窗口",
  stageFilter: "阶段过滤",
  stageFilterPlaceholder: "例如 route / compose",
  slowOnly: "仅看慢阶段",
  updatedAt: "最近更新时间：",
  noData: "暂无阶段统计数据",
} as const;

export const TIME_WINDOW_LABELS: Record<TimeWindow, string> = {
  all: "全部",
  "5m": "最近 5 分钟",
  "1h": "最近 1 小时",
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
  lines.push("# 规划遥测报告");
  lines.push("");
  lines.push(`- 时间：${formatTelemetryDatetime(telemetry.updated_at)}`);
  lines.push(`- 范围：${TIME_WINDOW_LABELS[timeWindow]}`);
  lines.push(`- 请求数：${telemetry.total_requests}`);
  lines.push(`- 缓存命中：${telemetry.cache_hits} (${cacheHitRate}%)`);
  lines.push(`- 窗口大小：${telemetry.window_size}`);
  lines.push("");

  const slowStages = stageRows.filter((item) => item.slow).slice(0, 5);
  if (slowStages.length) {
    lines.push("## 慢阶段概览");
    for (const item of slowStages) {
      lines.push(
        `- ${stageLabel(item.stage)}：P95=${item.stats.p95_ms}ms，最大值=${item.stats.max_ms}ms，最近值=${item.stats.last_ms}ms`,
      );
    }
    lines.push("");
  }

  lines.push("## 阶段明细");
  lines.push("");
  lines.push("| 阶段 | 次数 | P50 | P95 | 最大值 | 最近值 |");
  lines.push("| --- | ---: | ---: | ---: | ---: | ---: |");
  for (const item of stageRows) {
    lines.push(
      `| ${stageLabel(item.stage)} | ${item.stats.count} | ${item.stats.p50_ms}ms | ${item.stats.p95_ms}ms | ${item.stats.max_ms}ms | ${item.stats.last_ms}ms |`,
    );
  }
  if (!stageRows.length) {
    lines.push("| 暂无数据 | 0 | 0ms | 0ms | 0ms | 0ms |");
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
