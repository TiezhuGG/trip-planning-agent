<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

import { useWorkspaceVersionCompare } from "../composables/useWorkspaceVersionCompare";
import { getTripWorkspaceVersion } from "../api/planning";
import WorkspaceVersionCompareDayList from "./WorkspaceVersionCompareDayList.vue";
import WorkspaceVersionCompareFilterToolbar from "./WorkspaceVersionCompareFilterToolbar.vue";
import WorkspaceVersionCompareSummaryPanel from "./WorkspaceVersionCompareSummaryPanel.vue";
import type {
  CompareCategoryFilter,
  CompareChangeDetailKind,
  CompareChangeFilter,
  CompareChangeSignals,
  CompareCollectionChangeCounts,
  CompareDayDiffItem,
  CompareOverviewItem,
  CompareSummaryItem,
} from "./workspaceVersionCompareTypes";
import type {
  Activity,
  DayPlan,
  MealRecommendation,
  RouteStep,
  TripWorkspace,
  TripWorkspaceVersion,
  TripWorkspaceVersionSummary,
  WorkspaceTimelineEventKind,
} from "../types/planning";
import { formatDateTimeZhCn } from "../utils/workspaceFormatting";
import {
  formatWorkspaceResultLabel,
  formatWorkspaceStatusLabel,
  resolveWorkspaceStatusBadgeClass,
} from "../utils/workspaceStatus";
import {
  buildCompareDayDiffItem,
  buildDayExtendedHighlights,
  buildPlanCollectionChangeCounts,
  countDayCollectionItems,
  formatDeltaValue,
  formatChangeCounts,
  hasRouteCompareDiff,
  hasStayCompareDiff,
  hasTimelineCompareDiff,
  matchesCompareCategory,
  matchesCompareHighlight,
} from "../utils/workspaceVersionCompareDiff";

type BatchAction = "star" | "unstar" | "archive" | "unarchive";
type QuickFilter = "all" | "snapshot" | "starred" | "archived";
type ReviewStatus = "pending" | "done";
type ReviewFilter = "all" | "pending" | "done";

type ReviewQueueItem = {
  version: number;
  label: string;
  addedAt: string;
  status: ReviewStatus;
};

type BatchActionResult = {
  action: BatchAction;
  count: number;
  versionNumbers: number[];
  createdAt: string;
};

const REVIEW_QUEUE_STORAGE_PREFIX = "trip-workspace-version-review-queue:";

const props = defineProps<{
  workspace: TripWorkspace | null;
  versions: TripWorkspaceVersionSummary[];
  loading: boolean;
  error: string;
  hasMoreVersions: boolean;
  restoringVersion: number | null;
  savingVersionLabel: number | null;
}>();

const emit = defineEmits<{
  (event: "restore", version: number): void;
  (event: "save-label", version: number, versionLabel: string): void;
  (event: "toggle-star", version: TripWorkspaceVersionSummary): void;
  (event: "toggle-archive", version: TripWorkspaceVersionSummary): void;
  (event: "batch-update", versions: TripWorkspaceVersionSummary[], action: BatchAction): void;
  (event: "load-more"): void;
  (event: "load-all"): void;
  (event: "delete", version: number): void;
  (event: "focus-days", dayNumbers: number[]): void;
}>();

const originLabels: Record<WorkspaceTimelineEventKind, string> = {
  created: "创建",
  updated: "更新",
  generated: "生成",
  snapshot: "快照",
  replanned: "重规划",
  prechecked: "预检",
  restored: "恢复",
  share_revoked: "关闭分享",
  share_regenerated: "重建分享",
};

const batchActionLabels: Record<BatchAction, string> = {
  star: "批量加星",
  unstar: "批量取消加星",
  archive: "批量归档",
  unarchive: "批量取消归档",
};

const activeQuickFilter = ref<QuickFilter>("all");
const reviewQueueFilterMode = ref<ReviewFilter>("all");
const reviewQueueSearchText = ref("");
const reviewQueue = ref<ReviewQueueItem[]>([]);
const selectedReviewQueueVersions = ref<number[]>([]);
const selectedVersionNumbers = ref<number[]>([]);
const versionDetailCache = ref<Record<number, TripWorkspaceVersion>>({});
const compareLoading = ref(false);
const compareError = ref("");
const batchActionResult = ref<BatchActionResult | null>(null);

const versionListSectionRef = ref<HTMLElement | null>(null);
const reviewQueueSectionRef = ref<HTMLElement | null>(null);
const compareSectionRef = ref<HTMLElement | null>(null);

const snapshotCount = computed(
  () => props.versions.filter((item) => item.version_origin_kind === "snapshot").length,
);
const starredCount = computed(() => props.versions.filter((item) => item.is_starred).length);
const archivedCount = computed(() => props.versions.filter((item) => item.is_archived).length);

const filteredVersions = computed(() => {
  if (activeQuickFilter.value === "snapshot") {
    return props.versions.filter((item) => item.version_origin_kind === "snapshot");
  }
  if (activeQuickFilter.value === "starred") {
    return props.versions.filter((item) => item.is_starred);
  }
  if (activeQuickFilter.value === "archived") {
    return props.versions.filter((item) => item.is_archived);
  }
  return props.versions;
});

const currentVersion = computed(() => props.versions.find((item) => item.is_current) ?? null);
const compareTargetVersion = computed(
  () => props.versions.find((item) => item.version === compareTargetVersionNumber.value) ?? null,
);
const reviewQueueStorageKey = computed(() =>
  props.workspace?.id ? `${REVIEW_QUEUE_STORAGE_PREFIX}${props.workspace.id}` : "",
);

const sortedReviewQueue = computed(() => {
  const keyword = reviewQueueSearchText.value.trim().toLowerCase();
  return [...reviewQueue.value]
    .filter((item) => {
      const matchesFilter =
        reviewQueueFilterMode.value === "all" || item.status === reviewQueueFilterMode.value;
      const haystack = [`v${item.version}`, item.label].join(" ").toLowerCase();
      return matchesFilter && (!keyword || haystack.includes(keyword));
    })
    .sort((a, b) => {
      if (a.status !== b.status) {
        return a.status === "pending" ? -1 : 1;
      }
      return Date.parse(b.addedAt) - Date.parse(a.addedAt) || b.version - a.version;
    });
});

const reviewQueuePendingCount = computed(
  () => reviewQueue.value.filter((item) => item.status === "pending").length,
);
const reviewQueueDoneCount = computed(
  () => reviewQueue.value.filter((item) => item.status === "done").length,
);

const currentVersionDetail = computed(() => {
  if (!currentVersion.value || !props.workspace) return null;
  return (
    versionDetailCache.value[currentVersion.value.version] ?? {
      trip_id: props.workspace.id,
      version: currentVersion.value.version,
      captured_at: currentVersion.value.updated_at,
      is_current: true,
      workspace: props.workspace,
    }
  );
});

const compareTargetVersionDetail = computed(() =>
  compareTargetVersion.value
    ? versionDetailCache.value[compareTargetVersion.value.version] ?? null
    : null,
);

const compareSummaryItems = computed<CompareSummaryItem[]>(() => {
  if (!currentVersion.value || !compareTargetVersion.value) return [];
  return [
    {
      key: "status",
      label: "状态",
      current: formatWorkspaceStatusLabel(currentVersion.value.status),
      target: formatWorkspaceStatusLabel(compareTargetVersion.value.status),
    },
    {
      key: "label",
      label: "标签",
      current: resolveVersionLabel(currentVersion.value),
      target: resolveVersionLabel(compareTargetVersion.value),
    },
    {
      key: "origin",
      label: "来源",
      current: resolveOriginLabel(currentVersion.value.version_origin_kind),
      target: resolveOriginLabel(compareTargetVersion.value.version_origin_kind),
    },
    {
      key: "updated",
      label: "更新时间",
      current: formatDateTimeZhCn(currentVersion.value.updated_at),
      target: formatDateTimeZhCn(compareTargetVersion.value.updated_at),
    },
  ].filter((item) => item.current !== item.target);
});

const latestBatchActionResultCount = computed(() => batchActionResult.value?.count ?? 0);
const latestBatchActionResultSummary = computed(() => {
  if (!batchActionResult.value) return "";
  const versionText = batchActionResult.value.versionNumbers
    .slice(0, 4)
    .map((version) => `v${version}`)
    .join("、");
  const suffix =
    batchActionResult.value.versionNumbers.length > 4
      ? `等 ${batchActionResult.value.versionNumbers.length} 个版本`
      : versionText;
  return `${batchActionLabels[batchActionResult.value.action]} ${batchActionResult.value.count} 个版本${suffix ? `：${suffix}` : ""}`;
});
const latestBatchActionNeedsReview = computed(
  () => latestBatchActionResultCount.value > 0 && reviewQueuePendingCount.value > 0,
);

const compareDayDiffItems = computed<CompareDayDiffItem[]>(() => {
  const currentDays = currentVersionDetail.value?.workspace.response_snapshot?.plan.days ?? [];
  const targetDays = compareTargetVersionDetail.value?.workspace.response_snapshot?.plan.days ?? [];
  if (!currentDays.length || !targetDays.length) return [];

  const currentDayMap = new Map(currentDays.map((day) => [day.day_number, day]));
  const targetDayMap = new Map(targetDays.map((day) => [day.day_number, day]));
  const dayNumbers = [...new Set([...currentDayMap.keys(), ...targetDayMap.keys()])].sort(
    (a, b) => a - b,
  );

  return dayNumbers
    .map((dayNumber) => {
      const currentDay = currentDayMap.get(dayNumber);
      const targetDay = targetDayMap.get(dayNumber);
      return buildCompareDayDiffItem(dayNumber, currentDay, targetDay);
    })
    .filter((item): item is CompareDayDiffItem => item !== null);
});

const compareChangedFieldCount = computed(() =>
  compareDayDiffItems.value.reduce((sum, item) => sum + item.fields.length, 0),
);

const compareAggregatedSignals = computed<CompareChangeSignals>(() =>
  compareDayDiffItems.value.reduce(
    (totals, item) => ({
      time: totals.time + item.changeSignals.time,
      location: totals.location + item.changeSignals.location,
      route: totals.route + item.changeSignals.route,
      collection: totals.collection + item.changeSignals.collection,
      meta: totals.meta + item.changeSignals.meta,
    }),
    {
      time: 0,
      location: 0,
      route: 0,
      collection: 0,
      meta: 0,
    },
  ),
);

const compareActivityChangeCounts = computed(() => {
  const currentDays = currentVersionDetail.value?.workspace.response_snapshot?.plan.days ?? [];
  const targetDays = compareTargetVersionDetail.value?.workspace.response_snapshot?.plan.days ?? [];
  return buildPlanCollectionChangeCounts(currentDays, targetDays, "activities");
});

const compareMealChangeCounts = computed(() => {
  const currentDays = currentVersionDetail.value?.workspace.response_snapshot?.plan.days ?? [];
  const targetDays = compareTargetVersionDetail.value?.workspace.response_snapshot?.plan.days ?? [];
  return buildPlanCollectionChangeCounts(currentDays, targetDays, "meals");
});

const currentPlanDayMap = computed(
  () =>
    new Map(
      (currentVersionDetail.value?.workspace.response_snapshot?.plan.days ?? []).map((day) => [
        day.day_number,
        day,
      ]),
    ),
);

const targetPlanDayMap = computed(
  () =>
    new Map(
      (compareTargetVersionDetail.value?.workspace.response_snapshot?.plan.days ?? []).map((day) => [
        day.day_number,
        day,
      ]),
    ),
);

const compareOverviewItemsV2 = computed<CompareOverviewItem[]>(() => {
  if (!compareTargetVersion.value) return [];

  const currentDays = currentVersionDetail.value?.workspace.response_snapshot?.plan.days ?? [];
  const targetDays = compareTargetVersionDetail.value?.workspace.response_snapshot?.plan.days ?? [];

  if (!currentDays.length || !targetDays.length) {
    return compareSummaryItems.value.length
      ? [
          {
            key: "metadata-only",
            label: "元数据差异",
            value: String(compareSummaryItems.value.length),
            description: "当前仅能展示版本级元数据差异。",
            toneClass: "border-amber-200 bg-amber-50 text-amber-800",
          },
        ]
      : [];
  }

  const routeChangedCount = compareDayDiffItems.value.filter((item) =>
    item.fields.some((field) => field.label === "路线"),
  ).length;
  const stayChangedCount = compareDayDiffItems.value.filter((item) =>
    item.fields.some((field) => field.label === "住宿" || field.label === "住宿区域"),
  ).length;

  return [
    {
      key: "changed-days",
      label: "变更天数",
      value: `${compareDayDiffItems.value.length}`,
      description: compareDayDiffItems.value.length ? "有差异的行程天数" : "当前与对比版本无日程差异",
      toneClass: "border-sky-200 bg-sky-50 text-sky-800",
    },
    {
      key: "changed-fields",
      label: "差异字段",
      value: `${compareChangedFieldCount.value}`,
      description: "日程对比卡片中的差异字段总数",
      toneClass: "border-violet-200 bg-violet-50 text-violet-800",
    },
    {
      key: "activity-delta",
      label: "活动变化",
      value: formatChangeCounts(compareActivityChangeCounts.value),
      description: "新增 / 移除 / 变更的活动数",
      toneClass: "border-amber-200 bg-amber-50 text-amber-800",
    },
    {
      key: "meal-delta",
      label: "餐饮变化",
      value: formatChangeCounts(compareMealChangeCounts.value),
      description: "新增 / 移除 / 变更的餐饮数",
      toneClass: "border-emerald-200 bg-emerald-50 text-emerald-800",
    },
    {
      key: "routing-and-stay",
      label: "住宿/路线",
      value: `${stayChangedCount}/${routeChangedCount}`,
      description: "前者是住宿变更天数，后者是路线变更天数",
      toneClass: "border-slate-200 bg-slate-50 text-slate-700",
    },
    {
      key: "signal-core",
      label: "时间/地点/路线",
      value: `${compareAggregatedSignals.value.time}/${compareAggregatedSignals.value.location}/${compareAggregatedSignals.value.route}`,
      description: "累计时间、地点与路线相关的变更信号",
      toneClass: "border-slate-200 bg-slate-50 text-slate-700",
    },
    {
      key: "signal-structure",
      label: "结构/元数据",
      value: `${compareAggregatedSignals.value.collection}/${compareAggregatedSignals.value.meta}`,
      description: "累计集合结构与元数据相关的变更信号",
      toneClass: "border-violet-200 bg-violet-50 text-violet-800",
    },
    {
      key: "impact-overview",
      label: "强度/高强度",
      value: `${compareAverageImpactScore.value}/${compareHighImpactCount.value}`,
      description: compareMaxImpactItem.value
        ? `前者为平均强度，后者为高强度天数，最高为 D${compareMaxImpactItem.value.dayNumber} (${compareMaxImpactItem.value.impactScore})`
        : "当前无可用强度数据。",
      toneClass: "border-rose-200 bg-rose-50 text-rose-800",
    },
  ];
});

const compareExtendedHighlightsByDay = computed<Record<number, string[]>>(() => {
  const next: Record<number, string[]> = {};
  compareDayDiffItems.value.forEach((item) => {
    next[item.dayNumber] = buildDayExtendedHighlights(
      currentPlanDayMap.value.get(item.dayNumber),
      targetPlanDayMap.value.get(item.dayNumber),
    );
  });
  return next;
});

const {
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
  focusFilteredDayDiffs: emitFilteredCompareDayFocus,
  exportCompareText,
  exportCompareMarkdown,
} = useWorkspaceVersionCompare({
  workspaceId: computed(() => props.workspace?.id),
  versions: computed(() => props.versions),
  currentVersion,
  compareTargetVersion,
  currentVersionDetail,
  compareTargetVersionDetail,
  compareSummaryItems,
  compareDayDiffItems,
  compareExtendedHighlightsByDay,
  compareOverviewItems: compareOverviewItemsV2,
  resolveVersionLabel,
  matchesCompareCategory,
  matchesCompareHighlight,
  hasRouteCompareDiff,
  hasStayCompareDiff,
  hasTimelineCompareDiff,
});

const selectedVersions = computed(() =>
  filteredVersions.value.filter(
    (version) =>
      selectedVersionNumbers.value.includes(version.version) && !version.is_current,
  ),
);
const selectableFilteredVersions = computed(() =>
  filteredVersions.value.filter((version) => !version.is_current),
);
const allFilteredSelected = computed(
  () =>
    selectableFilteredVersions.value.length > 0 &&
    selectableFilteredVersions.value.every((item) =>
      selectedVersionNumbers.value.includes(item.version),
    ),
);

function resolveOriginLabel(kind: WorkspaceTimelineEventKind | null) {
  return kind == null ? "手动保存" : originLabels[kind];
}

function resolveVersionLabel(version: TripWorkspaceVersionSummary) {
  return version.version_label?.trim() || version.title?.trim() || `v${version.version}`;
}

function resolveReviewStatusLabel(status: ReviewStatus) {
  return status === "pending" ? "待复查" : "已复查";
}

function resolveCompareChangeKindLabel(kind: Exclude<CompareChangeFilter, "all">) {
  if (kind === "added") return "整天新增";
  if (kind === "removed") return "整天移除";
  return "内容变更";
}

function applyQuickFilter(filter: QuickFilter) {
  activeQuickFilter.value = filter;
  nextTick(() => {
    versionListSectionRef.value?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function isVersionInReviewQueue(versionNumber: number) {
  return reviewQueue.value.some((item) => item.version === versionNumber);
}

function addVersionToReviewQueue(version: TripWorkspaceVersionSummary) {
  if (isVersionInReviewQueue(version.version)) return;
  reviewQueue.value = [
    {
      version: version.version,
      label: resolveVersionLabel(version),
      addedAt: new Date().toISOString(),
      status: "pending",
    },
    ...reviewQueue.value,
  ];
}

function removeVersionFromReviewQueue(versionNumber: number) {
  reviewQueue.value = reviewQueue.value.filter((item) => item.version !== versionNumber);
}

function toggleVersionReviewQueue(version: TripWorkspaceVersionSummary) {
  if (isVersionInReviewQueue(version.version)) {
    removeVersionFromReviewQueue(version.version);
  } else {
    addVersionToReviewQueue(version);
  }
}

function toggleReviewQueueItemSelection(versionNumber: number) {
  selectedReviewQueueVersions.value = selectedReviewQueueVersions.value.includes(versionNumber)
    ? selectedReviewQueueVersions.value.filter((item) => item !== versionNumber)
    : [...selectedReviewQueueVersions.value, versionNumber];
}

function updateSelectedReviewQueueStatus(status: ReviewStatus) {
  const selected = new Set(selectedReviewQueueVersions.value);
  reviewQueue.value = reviewQueue.value.map((item) =>
    selected.has(item.version) ? { ...item, status } : item,
  );
}

function removeSelectedReviewQueueItems() {
  const selected = new Set(selectedReviewQueueVersions.value);
  reviewQueue.value = reviewQueue.value.filter((item) => !selected.has(item.version));
  selectedReviewQueueVersions.value = [];
}

function markAllReviewQueueDone() {
  reviewQueue.value = reviewQueue.value.map((item) =>
    item.status === "pending" ? { ...item, status: "done" } : item,
  );
}

function clearCompletedReviewQueueItems() {
  reviewQueue.value = reviewQueue.value.filter((item) => item.status !== "done");
}

function toggleVersionSelection(versionNumber: number) {
  selectedVersionNumbers.value = selectedVersionNumbers.value.includes(versionNumber)
    ? selectedVersionNumbers.value.filter((item) => item !== versionNumber)
    : [...selectedVersionNumbers.value, versionNumber];
}

function toggleSelectAllFilteredVersions() {
  if (allFilteredSelected.value) {
    const removable = new Set(selectableFilteredVersions.value.map((item) => item.version));
    selectedVersionNumbers.value = selectedVersionNumbers.value.filter(
      (versionNumber) => !removable.has(versionNumber),
    );
    return;
  }

  const merged = new Set(selectedVersionNumbers.value);
  selectableFilteredVersions.value.forEach((item) => merged.add(item.version));
  selectedVersionNumbers.value = [...merged];
}

function runBatchAction(action: BatchAction) {
  if (!selectedVersions.value.length) return;

  emit("batch-update", selectedVersions.value, action);

  const now = new Date().toISOString();
  selectedVersions.value.forEach((version) => {
    const existing = reviewQueue.value.find((item) => item.version === version.version);
    if (existing) {
      existing.status = "pending";
      existing.addedAt = now;
      existing.label = resolveVersionLabel(version);
    } else {
      reviewQueue.value.unshift({
        version: version.version,
        label: resolveVersionLabel(version),
        addedAt: now,
        status: "pending",
      });
    }
  });

  batchActionResult.value = {
    action,
    count: selectedVersions.value.length,
    versionNumbers: selectedVersions.value.map((item) => item.version),
    createdAt: now,
  };

  selectedVersionNumbers.value = [];
}

function focusDayDiff(dayNumber: number) {
  emit("focus-days", [dayNumber]);
}

function focusFilteredDayDiffs() {
  emitFilteredCompareDayFocus((dayNumbers) => emit("focus-days", dayNumbers));
}

function buildPendingReviewQueueExport(markdown: boolean) {
  return [
    markdown ? "# 待复查版本队列" : "待复查版本队列",
    `工作区：${props.workspace?.id ?? "未知"}`,
    `导出时间：${formatDateTimeZhCn(new Date().toISOString())}`,
    "",
    ...reviewQueue.value
      .filter((item) => item.status === "pending")
      .sort((a, b) => b.version - a.version)
      .map(
        (item, index) =>
          `${index + 1}. v${item.version} ${item.label} (${formatDateTimeZhCn(item.addedAt)})`,
      ),
  ].join("\n");
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

function exportPendingReviewQueueText() {
  if (reviewQueuePendingCount.value > 0) {
    triggerTextDownload(buildPendingReviewQueueExport(false), "workspace-review-queue.txt");
  }
}

function exportPendingReviewQueueMarkdown() {
  if (reviewQueuePendingCount.value > 0) {
    triggerTextDownload(buildPendingReviewQueueExport(true), "workspace-review-queue.md");
  }
}

async function ensureVersionDetail(versionNumber: number) {
  if (versionDetailCache.value[versionNumber] || !props.workspace?.id) return;
  versionDetailCache.value = {
    ...versionDetailCache.value,
    [versionNumber]: await getTripWorkspaceVersion(props.workspace.id, versionNumber),
  };
}

async function compareWithCurrentVersion(versionNumber: number) {
  if (!props.workspace?.id) return;
  compareTargetVersionNumber.value = versionNumber;
  compareError.value = "";
  compareLoading.value = true;

  try {
    if (currentVersion.value) {
      await ensureVersionDetail(currentVersion.value.version);
    }
    await ensureVersionDetail(versionNumber);
  } catch {
    compareError.value = "读取版本详情失败，当前仅显示基础对比信息。";
  } finally {
    compareLoading.value = false;
  }

  await nextTick();
  compareSectionRef.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function focusReviewQueue() {
  await focusReviewQueueWithFilter("all");
}

async function focusReviewQueueWithFilter(filter: ReviewFilter) {
  reviewQueueFilterMode.value = filter;
  await nextTick();
  reviewQueueSectionRef.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function normalizeReviewQueueItems(items: unknown): ReviewQueueItem[] {
  if (!Array.isArray(items)) return [];
  return items.flatMap((item) => {
    if (
      item &&
      typeof item === "object" &&
      typeof (item as ReviewQueueItem).version === "number" &&
      typeof (item as ReviewQueueItem).label === "string" &&
      typeof (item as ReviewQueueItem).addedAt === "string" &&
      ((item as ReviewQueueItem).status === "pending" ||
        (item as ReviewQueueItem).status === "done")
    ) {
      return [item as ReviewQueueItem];
    }
    return [];
  });
}

watch(
  () => props.workspace?.id,
  () => {
    selectedReviewQueueVersions.value = [];
    selectedVersionNumbers.value = [];
    versionDetailCache.value = {};
    compareError.value = "";
    batchActionResult.value = null;

    if (typeof window === "undefined" || !reviewQueueStorageKey.value) {
      reviewQueue.value = [];
    } else {
      try {
        const raw = window.localStorage.getItem(reviewQueueStorageKey.value);
        reviewQueue.value = raw ? normalizeReviewQueueItems(JSON.parse(raw)) : [];
      } catch {
        reviewQueue.value = [];
      }
    }
  },
  { immediate: true },
);

watch(
  reviewQueue,
  () => {
    if (typeof window !== "undefined" && reviewQueueStorageKey.value) {
      window.localStorage.setItem(reviewQueueStorageKey.value, JSON.stringify(reviewQueue.value));
    }
    selectedReviewQueueVersions.value = selectedReviewQueueVersions.value.filter((version) =>
      reviewQueue.value.some((item) => item.version === version),
    );
  },
  { deep: true },
);

watch(
  () => props.versions,
  (versions) => {
    reviewQueue.value = reviewQueue.value.map((item) => {
      const version = versions.find((candidate) => candidate.version === item.version);
      return version ? { ...item, label: resolveVersionLabel(version) } : item;
    });

    selectedVersionNumbers.value = selectedVersionNumbers.value.filter((versionNumber) =>
      versions.some((item) => item.version === versionNumber && !item.is_current),
    );

    versionDetailCache.value = Object.fromEntries(
      Object.entries(versionDetailCache.value).filter(([version]) =>
        versions.some((item) => item.version === Number(version)),
      ),
    );
  },
  { immediate: true, deep: true },
);

watch(compareTargetVersionNumber, async (versionNumber) => {
  if (versionNumber == null || !props.workspace?.id || compareLoading.value) return;
  if (versionDetailCache.value[versionNumber]) return;
  try {
    await ensureVersionDetail(versionNumber);
  } catch {
    compareError.value = "读取版本详情失败，当前仅显示基础对比信息。";
  }
});

defineExpose({
  compareWithCurrentVersion,
  focusFilteredDayDiffs,
  resetCompareFilters,
  applyQuickFilter,
  focusReviewQueue,
  focusReviewQueueWithFilter,
  exportPendingReviewQueueText,
  exportPendingReviewQueueMarkdown,
  exportCompareText,
  exportCompareMarkdown,
  markAllReviewQueueDone,
  clearCompletedReviewQueueItems,
  get latestBatchActionResultCount() {
    return latestBatchActionResultCount.value;
  },
  get latestBatchActionResultSummary() {
    return latestBatchActionResultSummary.value;
  },
  get latestBatchActionNeedsReview() {
    return latestBatchActionNeedsReview.value;
  },
  get reviewQueuePendingCount() {
    return reviewQueuePendingCount.value;
  },
  get reviewQueueDoneCount() {
    return reviewQueueDoneCount.value;
  },
});

</script>

<template>
  <section class="space-y-5">
    <div class="rounded-3xl border border-[#d7e2ec] bg-white p-5">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-sm font-semibold text-ink">版本历史</div>
          <div class="mt-1 text-xs text-slate-500">管理工作区快照、批量操作记录和复查队列。</div>
        </div>
        <div class="flex flex-wrap gap-2 text-xs">
          <span class="rounded-full border border-[#d7e2ec] bg-[#f8fbfd] px-3 py-1 text-[#35516b]">
            {{ props.versions.length }} 个版本
          </span>
          <span class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-sky-700">快照 {{ snapshotCount }}</span>
          <span class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700">加星 {{ starredCount }}</span>
          <span class="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-slate-700">归档 {{ archivedCount }}</span>
        </div>
      </div>
    </div>

    <div ref="versionListSectionRef" class="rounded-3xl border border-[#d7e2ec] bg-white p-5">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="text-sm font-semibold text-ink">版本列表</div>
        <div class="flex flex-wrap gap-2 text-xs">
          <button
            type="button"
            class="rounded-full px-3 py-1.5"
            :class="activeQuickFilter === 'all' ? 'border border-[#d7e2ec] bg-[#eef4f9] text-[#1f3448]' : 'border border-[#d7e2ec] bg-white text-[#35516b]'"
            @click="applyQuickFilter('all')"
          >
            全部
          </button>
          <button
            type="button"
            class="rounded-full px-3 py-1.5"
            :class="activeQuickFilter === 'snapshot' ? 'border border-sky-200 bg-sky-100 text-sky-800' : 'border border-sky-200 bg-sky-50 text-sky-700'"
            @click="applyQuickFilter('snapshot')"
          >
            快照
          </button>
          <button
            type="button"
            class="rounded-full px-3 py-1.5"
            :class="activeQuickFilter === 'starred' ? 'border border-amber-200 bg-amber-100 text-amber-800' : 'border border-amber-200 bg-amber-50 text-amber-700'"
            @click="applyQuickFilter('starred')"
          >
            加星
          </button>
          <button
            type="button"
            class="rounded-full px-3 py-1.5"
            :class="activeQuickFilter === 'archived' ? 'border border-slate-300 bg-slate-200 text-slate-800' : 'border border-slate-200 bg-slate-100 text-slate-700'"
            @click="applyQuickFilter('archived')"
          >
            归档
          </button>
        </div>
      </div>

      <div v-if="batchActionResult" class="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <div class="font-semibold">{{ latestBatchActionResultSummary }}</div>
        <div class="mt-1 text-xs text-amber-700">已自动加入复查队列，待复查 {{ reviewQueuePendingCount }} 项。</div>
      </div>

      <div v-if="selectableFilteredVersions.length" class="mt-4 rounded-2xl border border-[#d7e2ec] bg-[#f8fbfd] p-4">
        <div class="flex flex-wrap items-center justify-between gap-3 text-xs">
          <label class="inline-flex items-center gap-2 text-[#35516b]">
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-[#c8d6e5] text-sky-600"
              :checked="allFilteredSelected"
              @change="toggleSelectAllFilteredVersions"
            />
            <span>选择当前筛选结果中的版本</span>
          </label>
          <div class="text-slate-500">已选 {{ selectedVersions.length }} 个版本</div>
        </div>
        <div v-if="selectedVersions.length" class="mt-3 flex flex-wrap gap-2 text-xs">
          <button type="button" class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-700" @click="runBatchAction('star')">批量加星</button>
          <button type="button" class="rounded-full border border-amber-200 bg-white px-3 py-1.5 text-amber-700" @click="runBatchAction('unstar')">批量取消加星</button>
          <button type="button" class="rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-violet-700" @click="runBatchAction('archive')">批量归档</button>
          <button type="button" class="rounded-full border border-violet-200 bg-white px-3 py-1.5 text-violet-700" @click="runBatchAction('unarchive')">批量取消归档</button>
        </div>
      </div>

      <div v-if="props.error" class="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{{ props.error }}</div>
      <div v-else-if="props.loading" class="mt-4 text-sm text-slate-500">正在加载版本历史...</div>
      <div v-else-if="!filteredVersions.length" class="mt-4 text-sm text-slate-500">当前筛选条件下没有版本。</div>
      <div v-else class="mt-4 grid gap-3">
        <article v-for="version in filteredVersions" :key="version.version" class="rounded-3xl border border-[#eef4f9] bg-white p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="flex min-w-0 flex-1 items-start gap-3">
              <input
                v-if="!version.is_current"
                :checked="selectedVersionNumbers.includes(version.version)"
                type="checkbox"
                class="mt-1 h-4 w-4 rounded border-[#c8d6e5] text-sky-600"
                @change="toggleVersionSelection(version.version)"
              />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <div class="text-sm font-semibold text-ink">{{ resolveVersionLabel(version) }}</div>
                  <span class="rounded-full border px-2 py-1 text-[11px]" :class="resolveWorkspaceStatusBadgeClass(version.status)">{{ formatWorkspaceStatusLabel(version.status) }}</span>
                  <span class="rounded-full border border-[#d7e2ec] bg-white px-2 py-1 text-[11px] text-[#35516b]">{{ resolveOriginLabel(version.version_origin_kind) }}</span>
                  <span v-if="version.is_current" class="rounded-full border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] text-sky-700">当前版本</span>
                  <span v-if="isVersionInReviewQueue(version.version)" class="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">在复查队列</span>
                </div>
                <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                  <span>{{ `v${version.version}` }}</span>
                  <span>{{ formatWorkspaceResultLabel(version.has_result) }}</span>
                  <span>{{ `更新时间 ${formatDateTimeZhCn(version.updated_at)}` }}</span>
                </div>
                <div class="mt-2 text-sm text-slate-600">{{ version.title || "未命名版本" }}</div>
              </div>
            </div>
          </div>
          <div class="mt-4 flex flex-wrap gap-2 text-xs">
            <button type="button" class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1.5 text-[#35516b] disabled:opacity-60" :disabled="version.is_current || props.restoringVersion === version.version" @click="emit('restore', version.version)">{{ props.restoringVersion === version.version ? "恢复中..." : "恢复为当前" }}</button>
            <button type="button" class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1.5 text-[#35516b] disabled:opacity-60" :disabled="props.savingVersionLabel === version.version" @click="emit('save-label', version.version, resolveVersionLabel(version))">{{ props.savingVersionLabel === version.version ? "保存中..." : "保存标签" }}</button>
            <button type="button" class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-700" @click="emit('toggle-star', version)">{{ version.is_starred ? "取消加星" : "加星" }}</button>
            <button type="button" class="rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-violet-700" @click="emit('toggle-archive', version)">{{ version.is_archived ? "取消归档" : "归档" }}</button>
            <button type="button" class="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-emerald-700" @click="toggleVersionReviewQueue(version)">{{ isVersionInReviewQueue(version.version) ? "移出复查" : "加入复查" }}</button>
            <button type="button" class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-sky-700 disabled:opacity-60" :disabled="version.is_current" @click="compareWithCurrentVersion(version.version)">对比当前</button>
            <button type="button" class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1.5 text-rose-700" @click="emit('delete', version.version)">删除</button>
          </div>
        </article>
      </div>

      <div class="mt-4 flex flex-wrap gap-2 text-xs">
        <button v-if="props.hasMoreVersions" type="button" class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1.5 text-[#35516b]" @click="emit('load-more')">加载更多</button>
        <button v-if="props.hasMoreVersions" type="button" class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1.5 text-[#35516b]" @click="emit('load-all')">加载全部</button>
      </div>
    </div>

    <div ref="reviewQueueSectionRef" class="rounded-3xl border border-[#d7e2ec] bg-white p-5">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="text-sm font-semibold text-ink">复查队列</div>
          <div class="mt-1 text-xs text-slate-500">集中处理需要回看的版本。</div>
        </div>
        <div class="flex flex-wrap gap-2 text-xs">
          <span class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700">待复查 {{ reviewQueuePendingCount }}</span>
          <span class="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-emerald-700">已复查 {{ reviewQueueDoneCount }}</span>
        </div>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-2 text-xs">
        <button type="button" class="rounded-full px-3 py-1.5" :class="reviewQueueFilterMode === 'all' ? 'border border-[#d7e2ec] bg-[#eef4f9] text-[#1f3448]' : 'border border-[#d7e2ec] bg-white text-[#35516b]'" @click="reviewQueueFilterMode = 'all'">全部</button>
        <button type="button" class="rounded-full px-3 py-1.5" :class="reviewQueueFilterMode === 'pending' ? 'border border-rose-200 bg-rose-100 text-rose-800' : 'border border-rose-200 bg-rose-50 text-rose-700'" @click="reviewQueueFilterMode = 'pending'">待复查</button>
        <button type="button" class="rounded-full px-3 py-1.5" :class="reviewQueueFilterMode === 'done' ? 'border border-emerald-200 bg-emerald-100 text-emerald-800' : 'border border-emerald-200 bg-emerald-50 text-emerald-700'" @click="reviewQueueFilterMode = 'done'">已复查</button>
        <input v-model="reviewQueueSearchText" type="search" class="min-w-[220px] flex-1 rounded-full border border-[#d7e2ec] px-3 py-1.5 text-[#35516b] outline-none" placeholder="搜索版本号或标签" />
      </div>

      <div class="mt-4 flex flex-wrap gap-2 text-xs">
        <button v-if="selectedReviewQueueVersions.length" type="button" class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1.5 text-rose-700" @click="updateSelectedReviewQueueStatus('pending')">标记待复查</button>
        <button v-if="selectedReviewQueueVersions.length" type="button" class="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-emerald-700" @click="updateSelectedReviewQueueStatus('done')">标记已复查</button>
        <button v-if="selectedReviewQueueVersions.length" type="button" class="rounded-full border border-slate-200 bg-slate-100 px-3 py-1.5 text-slate-700" @click="removeSelectedReviewQueueItems">移除已选</button>
        <button v-if="reviewQueuePendingCount > 0" type="button" class="rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-emerald-700" @click="markAllReviewQueueDone">全部标记已复查</button>
        <button v-if="reviewQueueDoneCount > 0" type="button" class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-slate-700" @click="clearCompletedReviewQueueItems">清空已复查</button>
        <button v-if="reviewQueuePendingCount > 0" type="button" class="rounded-full border border-sky-200 bg-white px-3 py-1.5 text-sky-700" @click="exportPendingReviewQueueText">导出文本</button>
        <button v-if="reviewQueuePendingCount > 0" type="button" class="rounded-full border border-sky-200 bg-white px-3 py-1.5 text-sky-700" @click="exportPendingReviewQueueMarkdown">导出 Markdown</button>
      </div>

      <div v-if="selectedReviewQueueVersions.length" class="mt-3 text-xs text-slate-500">已选 {{ selectedReviewQueueVersions.length }} 项。</div>
      <div v-if="!reviewQueue.length" class="mt-4 rounded-2xl border border-dashed border-[#d7e2ec] bg-[#f8fbfd] px-4 py-5 text-sm text-slate-500">还没有加入复查队列的版本。</div>
      <div v-else-if="!sortedReviewQueue.length" class="mt-4 rounded-2xl border border-dashed border-[#d7e2ec] bg-[#f8fbfd] px-4 py-5 text-sm text-slate-500">当前筛选条件下没有匹配项。</div>
      <div v-else class="mt-4 grid gap-3">
        <article v-for="item in sortedReviewQueue" :key="item.version" class="rounded-3xl border border-[#eef4f9] bg-white p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <label class="flex min-w-0 flex-1 cursor-pointer items-start gap-3">
              <input :checked="selectedReviewQueueVersions.includes(item.version)" type="checkbox" class="mt-1 h-4 w-4 rounded border-[#c8d6e5] text-sky-600" @change="toggleReviewQueueItemSelection(item.version)" />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <div class="text-sm font-semibold text-ink">{{ item.label }}</div>
                  <span class="rounded-full border px-2 py-1 text-[11px]" :class="item.status === 'pending' ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'">{{ resolveReviewStatusLabel(item.status) }}</span>
                  <span class="rounded-full border border-[#d7e2ec] bg-white px-2 py-1 text-[11px] text-[#35516b]">{{ `v${item.version}` }}</span>
                </div>
                <div class="mt-2 text-xs text-slate-500">加入时间 {{ formatDateTimeZhCn(item.addedAt) }}</div>
              </div>
            </label>
            <div class="flex flex-wrap gap-2 text-xs">
              <button type="button" class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-sky-700" @click="compareWithCurrentVersion(item.version)">对比当前</button>
              <button type="button" class="rounded-full border border-slate-200 bg-slate-100 px-3 py-1.5 text-slate-700" @click="removeVersionFromReviewQueue(item.version)">移除</button>
            </div>
          </div>
        </article>
      </div>
    </div>

    <div ref="compareSectionRef" class="rounded-3xl border border-[#d7e2ec] bg-white p-5">
      <div>
        <div class="text-sm font-semibold text-ink">版本对比</div>
        <div class="mt-1 text-xs text-slate-500">对比当前版本与历史版本的元数据和日程差异。</div>
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <div class="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sky-800">当前版本：{{ currentVersion ? resolveVersionLabel(currentVersion) : "暂无" }}</div>
        <select v-model="compareTargetVersionNumber" class="min-w-[240px] rounded-2xl border border-[#d7e2ec] bg-white px-4 py-3 text-[#35516b]">
          <option :value="null">选择要对比的版本</option>
          <option v-for="version in props.versions.filter((item) => !item.is_current)" :key="version.version" :value="version.version">
            {{ `v${version.version} · ${resolveVersionLabel(version)}` }}
          </option>
        </select>
      </div>
      <div v-if="compareLoading" class="mt-4 text-sm text-slate-500">正在加载版本详情...</div>
      <div v-else-if="compareError" class="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{{ compareError }}</div>
      <div v-if="!compareTargetVersion" class="mt-4 rounded-2xl border border-dashed border-[#d7e2ec] bg-[#f8fbfd] px-4 py-5 text-sm text-slate-500">从版本列表或复查队列中选择一个版本进行对比。</div>
      <div v-else-if="compareSummaryItems.length === 0 && compareDayDiffItems.length === 0" class="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-5 text-sm text-emerald-800">当前版本与选中版本的关键元数据和日程摘要一致。</div>
      <div v-else class="mt-4 space-y-4">
        <WorkspaceVersionCompareSummaryPanel
          :filtered-compare-day-count="filteredCompareDayCount"
          :active-filter-chips="compareActiveFilterChips"
          :overview-items="compareOverviewItemsV2"
          :summary-items="compareSummaryItems"
          @export-text="exportCompareText"
          @export-markdown="exportCompareMarkdown"
          @focus-filtered-days="focusFilteredDayDiffs"
          @reset-filters="resetCompareFilters"
          @clear-filter-chip="clearCompareFilterChip"
        />

        <div v-if="compareDayDiffItems.length" class="space-y-3">
          <div class="text-sm font-semibold text-ink">按天差异</div>
          <WorkspaceVersionCompareFilterToolbar
            :compare-category-filter="compareCategoryFilter"
            :compare-change-filter="compareChangeFilter"
            :compare-sort-mode="compareSortMode"
            :compare-impact-filter="compareImpactFilter"
            :compare-signal-focus="compareSignalFocus"
            :compare-high-impact-threshold="compareHighImpactThreshold"
            :compare-recommended-high-impact-threshold="compareRecommendedHighImpactThreshold"
            :compare-manual-high-impact-threshold="compareManualHighImpactThreshold"
            :compare-route-diff-day-count="compareRouteDiffDayCount"
            :compare-stay-diff-day-count="compareStayDiffDayCount"
            :compare-timeline-diff-day-count="compareTimelineDiffDayCount"
            @update:compare-category-filter="compareCategoryFilter = $event"
            @update:compare-change-filter="compareChangeFilter = $event"
            @update:compare-sort-mode="compareSortMode = $event"
            @update:compare-impact-filter="compareImpactFilter = $event"
            @update:compare-signal-focus="compareSignalFocus = $event"
            @update:compare-manual-high-impact-threshold="compareManualHighImpactThreshold = $event"
            @focus-route-diffs="focusRouteCompareDiffs"
            @focus-stay-diffs="focusStayCompareDiffs"
            @focus-timeline-diffs="focusTimelineCompareDiffs"
          />
          <div v-if="compareDayDiffItems.length > 0 && filteredCompareDayCount === 0" class="rounded-2xl border border-dashed border-[#d7e2ec] bg-[#f8fbfd] px-4 py-4 text-sm text-slate-500">
            当前筛选条件下没有匹配的差异天数，请调整分类、变更类型、强度或信号筛选。
          </div>
          <WorkspaceVersionCompareDayList
            :items="filteredCompareDayDiffItems"
            :extended-highlights-by-day="compareExtendedHighlightsByDay"
            @focus-day="focusDayDiff"
          />
        </div>
      </div>
    </div>
  </section>
</template>
