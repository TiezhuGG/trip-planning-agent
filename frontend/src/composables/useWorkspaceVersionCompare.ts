import { computed, ref, watch, type ComputedRef, type Ref } from "vue";

import type { TripWorkspaceVersion, TripWorkspaceVersionSummary } from "../types/planning";
import { formatDateTimeZhCn } from "../utils/workspaceFormatting";
import {
  type CompareActiveFilterChip,
  type CompareCategoryFilter,
  type CompareChangeFilter,
  type CompareDayDiffItem,
  type CompareFilterChipKey,
  type CompareImpactFilter,
  type CompareOverviewItem,
  type CompareSignalFocus,
  type CompareSortMode,
  type CompareSummaryItem,
} from "../components/workspaceVersionCompareTypes";

const COMPARE_FILTER_STORAGE_PREFIX = "trip-workspace-version-compare-filters:";

type CompareFilterState = {
  compareCategoryFilter: CompareCategoryFilter;
  compareChangeFilter: CompareChangeFilter;
  compareSortMode: CompareSortMode;
  compareImpactFilter: CompareImpactFilter;
  compareSignalFocus: CompareSignalFocus;
  compareManualHighImpactThreshold: number | null;
  compareTargetVersionNumber: number | null;
};

export function useWorkspaceVersionCompare(options: {
  workspaceId: Ref<string | undefined>;
  versions: Ref<TripWorkspaceVersionSummary[]>;
  currentVersion: ComputedRef<TripWorkspaceVersionSummary | null>;
  compareTargetVersion: ComputedRef<TripWorkspaceVersionSummary | null>;
  currentVersionDetail: ComputedRef<TripWorkspaceVersion | null>;
  compareTargetVersionDetail: ComputedRef<TripWorkspaceVersion | null>;
  compareSummaryItems: ComputedRef<CompareSummaryItem[]>;
  compareDayDiffItems: ComputedRef<CompareDayDiffItem[]>;
  compareExtendedHighlightsByDay: ComputedRef<Record<number, string[]>>;
  compareOverviewItems: ComputedRef<CompareOverviewItem[]>;
  resolveVersionLabel: (version: TripWorkspaceVersionSummary) => string;
  matchesCompareCategory: (label: string, filter: CompareCategoryFilter) => boolean;
  matchesCompareHighlight: (highlight: string, filter: CompareCategoryFilter) => boolean;
  hasRouteCompareDiff: (day: CompareDayDiffItem) => boolean;
  hasStayCompareDiff: (day: CompareDayDiffItem) => boolean;
  hasTimelineCompareDiff: (day: CompareDayDiffItem) => boolean;
}) {
  const {
    workspaceId,
    versions,
    currentVersion,
    compareTargetVersion,
    currentVersionDetail,
    compareTargetVersionDetail,
    compareSummaryItems,
    compareDayDiffItems,
    compareExtendedHighlightsByDay,
    compareOverviewItems,
    resolveVersionLabel,
    matchesCompareCategory,
    matchesCompareHighlight,
    hasRouteCompareDiff,
    hasStayCompareDiff,
    hasTimelineCompareDiff,
  } = options;

  const compareCategoryFilterLabels: Record<CompareCategoryFilter, string> = {
    all: "全部",
    activities: "活动",
    meals: "餐饮",
    stay: "住宿",
    route: "路线",
  };

  const compareChangeFilterLabels: Record<CompareChangeFilter, string> = {
    all: "全部变更",
    added: "整天新增",
    removed: "整天移除",
    changed: "内容变更",
  };

  const compareSortModeLabels: Record<CompareSortMode, string> = {
    day: "按天排序",
    impact: "按强度排序",
  };

  const compareImpactFilterLabels: Record<CompareImpactFilter, string> = {
    all: "全部强度",
    high: "仅看高强度",
  };

  const compareSignalFocusLabels: Record<CompareSignalFocus, string> = {
    all: "全部信号",
    time: "时间信号",
    location: "地点信号",
    route: "路线信号",
    structure: "结构信号",
  };

  const compareTargetVersionNumber = ref<number | null>(null);
  const compareCategoryFilter = ref<CompareCategoryFilter>("all");
  const compareChangeFilter = ref<CompareChangeFilter>("all");
  const compareSortMode = ref<CompareSortMode>("day");
  const compareImpactFilter = ref<CompareImpactFilter>("all");
  const compareSignalFocus = ref<CompareSignalFocus>("all");
  const compareManualHighImpactThreshold = ref<number | null>(null);

  const compareFilterStorageKey = computed(() =>
    workspaceId.value ? `${COMPARE_FILTER_STORAGE_PREFIX}${workspaceId.value}` : "",
  );

  const filteredCompareDayDiffItems = computed(() => {
    const filtered = compareDayDiffItems.value.filter((day) => {
      const matchesCategory =
        compareCategoryFilter.value === "all" ||
        day.fields.some((field) => matchesCompareCategory(field.label, compareCategoryFilter.value)) ||
        day.timelineEntries.some((entry) =>
          compareCategoryFilter.value === "activities"
            ? entry.kind === "activity"
            : compareCategoryFilter.value === "meals"
              ? entry.kind === "meal"
              : false,
        ) ||
        (compareCategoryFilter.value === "route" && day.routeStepEntries.length > 0) ||
        compareExtendedHighlightsByDay.value[day.dayNumber]?.some((highlight) =>
          matchesCompareHighlight(highlight, compareCategoryFilter.value),
        );

      const matchesChangeKind =
        compareChangeFilter.value === "all" || day.changeKind === compareChangeFilter.value;

      const matchesImpact =
        compareImpactFilter.value === "all" || day.impactScore >= compareHighImpactThreshold.value;

      const matchesSignalFocus =
        compareSignalFocus.value === "all" ||
        (compareSignalFocus.value === "time" && day.changeSignals.time > 0) ||
        (compareSignalFocus.value === "location" && day.changeSignals.location > 0) ||
        (compareSignalFocus.value === "route" && day.changeSignals.route > 0) ||
        (compareSignalFocus.value === "structure" &&
          day.changeSignals.collection + day.changeSignals.meta > 0);

      return matchesCategory && matchesChangeKind && matchesImpact && matchesSignalFocus;
    });

    return [...filtered].sort((a, b) => {
      if (compareSortMode.value === "impact") {
        return b.impactScore - a.impactScore || a.dayNumber - b.dayNumber;
      }
      return a.dayNumber - b.dayNumber;
    });
  });

  const filteredCompareDayCount = computed(() => filteredCompareDayDiffItems.value.length);
  const hasCompareContent = computed(
    () => compareSummaryItems.value.length > 0 || compareDayDiffItems.value.length > 0,
  );
  const compareRouteDiffDayCount = computed(
    () => compareDayDiffItems.value.filter((item) => hasRouteCompareDiff(item)).length,
  );
  const compareStayDiffDayCount = computed(
    () => compareDayDiffItems.value.filter((item) => hasStayCompareDiff(item)).length,
  );
  const compareTimelineDiffDayCount = computed(
    () => compareDayDiffItems.value.filter((item) => hasTimelineCompareDiff(item)).length,
  );

  const compareTotalImpactScore = computed(() =>
    compareDayDiffItems.value.reduce((sum, item) => sum + item.impactScore, 0),
  );
  const compareAverageImpactScore = computed(() =>
    compareDayDiffItems.value.length
      ? (compareTotalImpactScore.value / compareDayDiffItems.value.length).toFixed(1)
      : "0.0",
  );
  const compareMaxImpactItem = computed(() =>
    compareDayDiffItems.value.reduce<CompareDayDiffItem | null>(
      (max, item) => (!max || item.impactScore > max.impactScore ? item : max),
      null,
    ),
  );
  const compareRecommendedHighImpactThreshold = computed(() =>
    compareDayDiffItems.value.length
      ? Math.max(6, Math.ceil(compareTotalImpactScore.value / compareDayDiffItems.value.length))
      : 6,
  );
  const compareHighImpactThreshold = computed(() =>
    compareManualHighImpactThreshold.value == null
      ? compareRecommendedHighImpactThreshold.value
      : Math.max(1, Math.floor(compareManualHighImpactThreshold.value)),
  );
  const compareHighImpactCount = computed(
    () =>
      compareDayDiffItems.value.filter((item) => item.impactScore >= compareHighImpactThreshold.value)
        .length,
  );

  const compareActiveFilterChips = computed<CompareActiveFilterChip[]>(() => {
    const chips: CompareActiveFilterChip[] = [];

    if (compareCategoryFilter.value !== "all") {
      chips.push({
        key: "category",
        label: `分类：${compareCategoryFilterLabels[compareCategoryFilter.value]}`,
      });
    }

    if (compareChangeFilter.value !== "all") {
      chips.push({
        key: "change",
        label: `变更：${compareChangeFilterLabels[compareChangeFilter.value]}`,
      });
    }

    if (compareSortMode.value !== "day") {
      chips.push({
        key: "sort",
        label: `排序：${compareSortModeLabels[compareSortMode.value]}`,
      });
    }

    if (compareImpactFilter.value !== "all") {
      chips.push({
        key: "impact",
        label: `强度：${compareImpactFilterLabels[compareImpactFilter.value]}`,
      });
    }

    if (compareSignalFocus.value !== "all") {
      chips.push({
        key: "signal",
        label: `信号：${compareSignalFocusLabels[compareSignalFocus.value]}`,
      });
    }

    if (compareManualHighImpactThreshold.value !== null) {
      chips.push({
        key: "threshold",
        label: `阈值：${compareHighImpactThreshold.value}`,
      });
    }

    return chips;
  });

  function resetCompareFilters() {
    compareCategoryFilter.value = "all";
    compareChangeFilter.value = "all";
    compareSortMode.value = "day";
    compareImpactFilter.value = "all";
    compareSignalFocus.value = "all";
    compareManualHighImpactThreshold.value = null;
  }

  function focusRouteCompareDiffs() {
    compareCategoryFilter.value = "route";
    compareSignalFocus.value = "route";
    compareChangeFilter.value = "all";
    compareImpactFilter.value = "all";
    compareSortMode.value = "impact";
  }

  function focusStayCompareDiffs() {
    compareCategoryFilter.value = "stay";
    compareSignalFocus.value = "location";
    compareChangeFilter.value = "all";
    compareImpactFilter.value = "all";
    compareSortMode.value = "impact";
  }

  function focusTimelineCompareDiffs() {
    compareCategoryFilter.value = "all";
    compareSignalFocus.value = "time";
    compareChangeFilter.value = "changed";
    compareImpactFilter.value = "all";
    compareSortMode.value = "impact";
  }

  function clearCompareFilterChip(key: CompareFilterChipKey) {
    if (key === "category") {
      compareCategoryFilter.value = "all";
      return;
    }
    if (key === "change") {
      compareChangeFilter.value = "all";
      return;
    }
    if (key === "sort") {
      compareSortMode.value = "day";
      return;
    }
    if (key === "impact") {
      compareImpactFilter.value = "all";
      return;
    }
    if (key === "signal") {
      compareSignalFocus.value = "all";
      return;
    }
    compareManualHighImpactThreshold.value = null;
  }

  function focusFilteredDayDiffs(emitFocusDays: (dayNumbers: number[]) => void) {
    const dayNumbers = filteredCompareDayDiffItems.value.map((item) => item.dayNumber);
    if (!dayNumbers.length) return;
    emitFocusDays(dayNumbers);
  }

  function buildCompareExport(markdown: boolean) {
    const currentLabel = currentVersion.value ? resolveVersionLabel(currentVersion.value) : "当前版本";
    const targetLabel = compareTargetVersion.value
      ? resolveVersionLabel(compareTargetVersion.value)
      : "对比版本";
    const lines: string[] = [
      markdown ? "# 版本对比导出" : "版本对比导出",
      `工作区: ${workspaceId.value ?? "unknown"}`,
      `当前版本: ${currentLabel}`,
      `对比版本: ${targetLabel}`,
      `导出时间: ${formatDateTimeZhCn(new Date().toISOString())}`,
      `筛选状态: 分类=${compareCategoryFilterLabels[compareCategoryFilter.value]}, 变更=${compareChangeFilterLabels[compareChangeFilter.value]}, 强度=${compareImpactFilterLabels[compareImpactFilter.value]}, 信号=${compareSignalFocusLabels[compareSignalFocus.value]}, 排序=${compareSortModeLabels[compareSortMode.value]}`,
      `高强度阈值: ${compareHighImpactThreshold.value}（推荐 ${compareRecommendedHighImpactThreshold.value}）`,
      "",
    ];

    if (compareOverviewItems.value.length) {
      lines.push(markdown ? "## 总览" : "总览");
      compareOverviewItems.value.forEach((item) => {
        lines.push(`- ${item.label}: ${item.value} (${item.description})`);
      });
      lines.push("");
    }

    if (compareSummaryItems.value.length) {
      lines.push(markdown ? "## 元数据" : "元数据");
      compareSummaryItems.value.forEach((item) => {
        lines.push(`- ${item.label}: ${item.current} -> ${item.target}`);
      });
      lines.push("");
    }

    if (filteredCompareDayDiffItems.value.length) {
      lines.push(markdown ? "## 按天差异" : "按天差异");
      filteredCompareDayDiffItems.value.forEach((day) => {
        lines.push(`${markdown ? "###" : ""} 第 ${day.dayNumber} 天 (${day.changeLabel})`.trim());
        day.fields.forEach((field) => {
          lines.push(`- ${field.label}: ${field.current} -> ${field.target}`);
        });
        day.highlights.forEach((highlight) => {
          lines.push(`- 摘要: ${highlight}`);
        });
        (compareExtendedHighlightsByDay.value[day.dayNumber] ?? []).forEach((highlight) => {
          lines.push(`- 细节: ${highlight}`);
        });
        day.timelineEntries.forEach((entry) => {
          lines.push(`- ${entry.kind} ${entry.label}: ${entry.current} -> ${entry.target}`);
        });
        day.routeStepEntries.forEach((entry) => {
          lines.push(`- 路线 ${entry.label}: ${entry.current} -> ${entry.target}`);
        });
        lines.push("");
      });
    }

    return lines.join("\n");
  }

  function triggerTextDownload(content: string, filename: string) {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    window.URL.revokeObjectURL(url);
  }

  function exportCompareText() {
    if (!hasCompareContent.value) return;
    triggerTextDownload(buildCompareExport(false), "workspace-version-compare.txt");
  }

  function exportCompareMarkdown() {
    if (!hasCompareContent.value) return;
    triggerTextDownload(buildCompareExport(true), "workspace-version-compare.md");
  }

  function normalizeCompareFilterState(state: unknown): CompareFilterState | null {
    if (!state || typeof state !== "object") return null;
    const candidate = state as Partial<CompareFilterState>;

    const categoryFilters: CompareCategoryFilter[] = ["all", "activities", "meals", "stay", "route"];
    const changeFilters: CompareChangeFilter[] = ["all", "added", "removed", "changed"];
    const sortModes: CompareSortMode[] = ["day", "impact"];
    const impactFilters: CompareImpactFilter[] = ["all", "high"];
    const signalFocuses: CompareSignalFocus[] = ["all", "time", "location", "route", "structure"];

    return {
      compareCategoryFilter: categoryFilters.includes(candidate.compareCategoryFilter as CompareCategoryFilter)
        ? (candidate.compareCategoryFilter as CompareCategoryFilter)
        : "all",
      compareChangeFilter: changeFilters.includes(candidate.compareChangeFilter as CompareChangeFilter)
        ? (candidate.compareChangeFilter as CompareChangeFilter)
        : "all",
      compareSortMode: sortModes.includes(candidate.compareSortMode as CompareSortMode)
        ? (candidate.compareSortMode as CompareSortMode)
        : "day",
      compareImpactFilter: impactFilters.includes(candidate.compareImpactFilter as CompareImpactFilter)
        ? (candidate.compareImpactFilter as CompareImpactFilter)
        : "all",
      compareSignalFocus: signalFocuses.includes(candidate.compareSignalFocus as CompareSignalFocus)
        ? (candidate.compareSignalFocus as CompareSignalFocus)
        : "all",
      compareManualHighImpactThreshold:
        typeof candidate.compareManualHighImpactThreshold === "number" &&
        Number.isFinite(candidate.compareManualHighImpactThreshold)
          ? Math.max(1, Math.floor(candidate.compareManualHighImpactThreshold))
          : null,
      compareTargetVersionNumber:
        typeof candidate.compareTargetVersionNumber === "number" &&
        Number.isFinite(candidate.compareTargetVersionNumber)
          ? candidate.compareTargetVersionNumber
          : null,
    };
  }

  watch(
    workspaceId,
    () => {
      resetCompareFilters();

      if (typeof window === "undefined" || !compareFilterStorageKey.value) {
        compareTargetVersionNumber.value = null;
        return;
      }

      try {
        const raw = window.localStorage.getItem(compareFilterStorageKey.value);
        const savedState = raw ? normalizeCompareFilterState(JSON.parse(raw)) : null;
        if (!savedState) {
          compareTargetVersionNumber.value = null;
          return;
        }
        compareCategoryFilter.value = savedState.compareCategoryFilter;
        compareChangeFilter.value = savedState.compareChangeFilter;
        compareSortMode.value = savedState.compareSortMode;
        compareImpactFilter.value = savedState.compareImpactFilter;
        compareSignalFocus.value = savedState.compareSignalFocus;
        compareManualHighImpactThreshold.value = savedState.compareManualHighImpactThreshold;
        compareTargetVersionNumber.value = savedState.compareTargetVersionNumber;
      } catch {
        compareTargetVersionNumber.value = null;
      }
    },
    { immediate: true },
  );

  watch(
    [
      compareCategoryFilter,
      compareChangeFilter,
      compareSortMode,
      compareImpactFilter,
      compareSignalFocus,
      compareManualHighImpactThreshold,
      compareTargetVersionNumber,
    ],
    () => {
      if (typeof window === "undefined" || !compareFilterStorageKey.value) return;
      const state: CompareFilterState = {
        compareCategoryFilter: compareCategoryFilter.value,
        compareChangeFilter: compareChangeFilter.value,
        compareSortMode: compareSortMode.value,
        compareImpactFilter: compareImpactFilter.value,
        compareSignalFocus: compareSignalFocus.value,
        compareManualHighImpactThreshold: compareManualHighImpactThreshold.value,
        compareTargetVersionNumber: compareTargetVersionNumber.value,
      };
      window.localStorage.setItem(compareFilterStorageKey.value, JSON.stringify(state));
    },
    { deep: true },
  );

  watch(
    versions,
    (nextVersions) => {
      if (
        compareTargetVersionNumber.value == null ||
        !nextVersions.some((item) => item.version === compareTargetVersionNumber.value)
      ) {
        compareTargetVersionNumber.value =
          nextVersions.find((item) => !item.is_current)?.version ?? null;
      }
    },
    { immediate: true, deep: true },
  );

  return {
    compareCategoryFilterLabels,
    compareChangeFilterLabels,
    compareSortModeLabels,
    compareImpactFilterLabels,
    compareSignalFocusLabels,
    compareTargetVersionNumber,
    compareCategoryFilter,
    compareChangeFilter,
    compareSortMode,
    compareImpactFilter,
    compareSignalFocus,
    compareManualHighImpactThreshold,
    filteredCompareDayDiffItems,
    filteredCompareDayCount,
    hasCompareContent,
    compareRouteDiffDayCount,
    compareStayDiffDayCount,
    compareTimelineDiffDayCount,
    compareAverageImpactScore,
    compareHighImpactCount,
    compareMaxImpactItem,
    compareRecommendedHighImpactThreshold,
    compareHighImpactThreshold,
    compareActiveFilterChips,
    resetCompareFilters,
    focusRouteCompareDiffs,
    focusStayCompareDiffs,
    focusTimelineCompareDiffs,
    clearCompareFilterChip,
    focusFilteredDayDiffs,
    exportCompareText,
    exportCompareMarkdown,
  };
}
