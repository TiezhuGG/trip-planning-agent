<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

import { buildWorkspaceCompletionOverview } from "../composables/tripWorkspaceCompletionOverview";
import {
  collectPrecheckAffectedDays,
  countPrecheckAttentionItems,
  hasRunningPrecheckJob,
  shouldRefreshPrecheck,
} from "../composables/tripWorkspaceExportReadiness";
import { getReservationTargetDaysById } from "../composables/tripWorkspaceReservationCoverageHelpers";
import type {
  CalendarExportScope,
  PlanningJobSummary,
  ReservationItem,
  TripWorkspace,
  TripWorkspaceVersionSummary,
} from "../types/planning";
import type {
  DayGapRepairPayload,
  DayReadinessItem,
  DayReadinessSummary,
  DeparturePrecheckItem,
  DeparturePrecheckSummary,
  ReservationCoverageItem,
  ReservationCoverageSummary,
} from "../composables/useTripWorkspaceInsights";
import { canRetryPlanningJob } from "../utils/planningJobs";
import { formatDateTimeZhCn, sortUniqueNumbers } from "../utils/workspaceFormatting";

import DeparturePrecheckPanel from "./DeparturePrecheckPanel.vue";
import DeparturePrecheckSummaryCard from "./DeparturePrecheckSummaryCard.vue";
import PlannerReservationPanel from "./PlannerReservationPanel.vue";
import PlannerWorkspaceSummary from "./PlannerWorkspaceSummary.vue";
import WorkspaceActionChecklist from "./WorkspaceActionChecklist.vue";
import WorkspaceActivityTimeline from "./WorkspaceActivityTimeline.vue";
import WorkspaceChangeDigest from "./WorkspaceChangeDigest.vue";
import WorkspaceCompletionOverview from "./WorkspaceCompletionOverview.vue";
import WorkspaceNextStepCard from "./WorkspaceNextStepCard.vue";
import WorkspaceVersionHistoryPanel from "./WorkspaceVersionHistoryPanel.vue";

type SectionKey =
  | "overview"
  | "next-step"
  | "checklist"
  | "changes"
  | "timeline"
  | "versions"
  | "precheck"
  | "reservations";

type SectionTone = "neutral" | "info" | "warning" | "success";
type WorkspaceFocusShortcutKey = "day-readiness" | "reservation" | "precheck" | "changes";
type VersionHistoryQuickFilter = "all" | "snapshot" | "starred" | "archived";
type BatchVersionAction = "star" | "unstar" | "archive" | "unarchive";
type SnapshotRecommendation = {
  badge: string;
  title: string;
  summary: string;
  suggestedLabel: string;
  panelClass: string;
  badgeClass: string;
};
type SnapshotFollowup = {
  versionNumber: number;
  versionLabel: string;
};
type VersionTimelineEntry = {
  key: string;
  title: string;
  detail: string;
  version: TripWorkspaceVersionSummary | null;
  toneClass: string;
  badgeClass: string;
  action: "compare" | "filter";
  filter?: VersionHistoryQuickFilter;
};

const COLLAPSED_SECTIONS_STORAGE_KEY = "trip-workspace-panel-collapsed-sections";

const props = defineProps<{
  workspace: TripWorkspace | null;
  notes: string;
  shareLink: string;
  saving: boolean;
  retryingJobId: string;
  busyMessage: string;
  prechecking: boolean;
  replanning: boolean;
  recentPlanningJobs: PlanningJobSummary[];
  recentPlanningJobsLoading: boolean;
  recentPlanningJobsError: string;
  tripVersions: TripWorkspaceVersionSummary[];
  tripVersionsLoading: boolean;
  tripVersionsError: string;
  tripVersionsHasMore: boolean;
  restoringTripVersion: number | null;
  savingTripVersionLabel: number | null;
  replanningDays: number[];
  focusedWorkspaceDays: number[];
  reservations: ReservationItem[];
  reservationAlerts: string[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
  dayReadinessSummary: DayReadinessSummary;
  dayReadinessItems: DayReadinessItem[];
  departurePrecheckSummary: DeparturePrecheckSummary;
  departurePrecheckItems: DeparturePrecheckItem[];
}>();

const emit = defineEmits<{
  (event: "update:notes", value: string): void;
  (event: "save-notes"): void;
  (event: "copy-share"): void;
  (event: "revoke-share"): void;
  (event: "regenerate-share"): void;
  (event: "export-calendar", scope: CalendarExportScope): void;
  (event: "create-trip-version-snapshot", versionLabel: string): void;
  (event: "delete-trip-version", version: number): void;
  (event: "focus-workspace-days", dayNumbers: number[]): void;
  (event: "clear-workspace-focus"): void;
  (event: "replan-trip"): void;
  (event: "restore-trip-version", version: number): void;
  (event: "save-trip-version-label", version: number, versionLabel: string): void;
  (event: "toggle-trip-version-star", version: TripWorkspaceVersionSummary): void;
  (event: "toggle-trip-version-archive", version: TripWorkspaceVersionSummary): void;
  (event: "batch-trip-version-update", versions: TripWorkspaceVersionSummary[], action: BatchVersionAction): void;
  (event: "load-more-trip-versions"): void;
  (event: "load-all-trip-versions"): void;
  (event: "refresh-precheck"): void;
  (event: "retry-planning-job", job: PlanningJobSummary): void;
  (event: "repair-day-gap", payload: DayGapRepairPayload): void;
  (event: "add-reservation", value: Omit<ReservationItem, "id">): void;
  (event: "remove-reservation", id: string): void;
}>();

const snapshotLabelDraft = ref("");
const pendingSnapshotLabel = ref("");
const latestCreatedSnapshot = ref<SnapshotFollowup | null>(null);
const versionHistoryPanelRef = ref<{
  compareWithCurrentVersion: (versionNumber: number) => Promise<void>;
  applyQuickFilter: (filter: VersionHistoryQuickFilter) => void;
  focusReviewQueue: () => Promise<void>;
  focusReviewQueueWithFilter: (filter: "all" | "pending" | "done") => Promise<void>;
  exportPendingReviewQueueText: () => void;
  exportPendingReviewQueueMarkdown: () => void;
  markAllReviewQueueDone: () => void;
  clearCompletedReviewQueueItems: () => void;
  latestBatchActionResultCount: number;
  latestBatchActionResultSummary: string;
  latestBatchActionNeedsReview: boolean;
  reviewQueuePendingCount: number;
  reviewQueueDoneCount: number;
} | null>(null);

function createVersionSnapshot() {
  const label = snapshotLabelDraft.value.trim() || snapshotRecommendation.value?.suggestedLabel || "";
  pendingSnapshotLabel.value = label;
  emit(
    "create-trip-version-snapshot",
    label,
  );
  snapshotLabelDraft.value = "";
}

const collapsedSections = ref<Record<SectionKey, boolean>>({
  overview: false,
  "next-step": false,
  checklist: false,
  changes: false,
  timeline: false,
  versions: false,
  precheck: false,
  reservations: false,
});

hydrateCollapsedSections();

watch(
  collapsedSections,
  (value) => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(COLLAPSED_SECTIONS_STORAGE_KEY, JSON.stringify(value));
  },
  { deep: true },
);

const completionOverview = computed(() =>
  buildWorkspaceCompletionOverview({
    workspace: props.workspace,
    jobs: props.recentPlanningJobs,
    dayReadinessSummary: props.dayReadinessSummary,
    dayReadinessItems: props.dayReadinessItems,
    reservationCoverageSummary: props.reservationCoverageSummary,
    reservationCoverageItems: props.reservationCoverageItems,
    departurePrecheckSummary: props.departurePrecheckSummary,
  }),
);

const retryableFailedJobs = computed(() =>
  props.workspace
    ? props.recentPlanningJobs.filter(
        (job) => job.trip_id === props.workspace?.id && canRetryPlanningJob(job),
      )
    : [],
);

const incompleteDays = computed(() =>
  props.dayReadinessItems.filter((item) => item.status !== "ready"),
);

const unresolvedReservationCount = computed(
  () => props.reservationCoverageSummary.unresolved + props.reservationCoverageSummary.pending,
);

const latestChangedDaysCount = computed(
  () =>
    (props.workspace?.last_replan_summary?.items ?? []).filter(
      (item) => Boolean(item.changes?.length) || Boolean(item.highlights.length),
    ).length,
);

const precheckAttentionCount = computed(() =>
  props.workspace?.last_precheck_summary
    ? countPrecheckAttentionItems(props.workspace.last_precheck_summary)
    : 0,
);

const hasPrecheckJobRunning = computed(() =>
  props.workspace
    ? hasRunningPrecheckJob(props.workspace.id, props.recentPlanningJobs)
    : false,
);

const precheckNeedsRefresh = computed(() => {
  return shouldRefreshPrecheck(props.workspace, props.recentPlanningJobs);
});

const incompleteDayNumbers = computed(() =>
  sortUniqueNumbers(incompleteDays.value.map((item) => item.dayNumber)),
);

const unresolvedReservationDayNumbers = computed(() => {
  if (!props.workspace) return [];
  return sortUniqueNumbers(
    props.reservationCoverageItems
      .filter((item) => item.status === "unresolved" || item.status === "pending")
      .flatMap((item) => getReservationTargetDaysById(item.id, props.workspace as TripWorkspace)),
  );
});

const precheckAttentionDayNumbers = computed(() =>
  props.workspace ? collectPrecheckAffectedDays(props.workspace) : [],
);

const recentChangedDayNumbers = computed(() =>
  sortUniqueNumbers(
    (props.workspace?.last_replan_summary?.items ?? [])
      .filter((item) => Boolean(item.changes?.length) || Boolean(item.highlights.length))
      .map((item) => item.day_number),
  ),
);

const latestSnapshotVersion = computed(() =>
  props.tripVersions.find((item) => item.version_origin_kind === "snapshot" && !item.is_current) ?? null,
);

const latestStarredVersion = computed(() =>
  props.tripVersions.find((item) => item.is_starred && !item.is_current) ?? null,
);

const latestArchivedVersion = computed(() =>
  props.tripVersions.find((item) => item.is_archived && !item.is_current) ?? null,
);

const snapshotVersionCount = computed(
  () => props.tripVersions.filter((item) => item.version_origin_kind === "snapshot").length,
);

const starredVersionCount = computed(
  () => props.tripVersions.filter((item) => item.is_starred).length,
);

const archivedVersionCount = computed(
  () => props.tripVersions.filter((item) => item.is_archived).length,
);

watch(
  () => [props.workspace?.version, props.savingTripVersionLabel, props.tripVersions.length] as const,
  ([version, savingVersion]) => {
    if (!version || savingVersion !== null || !pendingSnapshotLabel.value) {
      return;
    }

    latestCreatedSnapshot.value = {
      versionNumber: version,
      versionLabel: pendingSnapshotLabel.value || `v${version}`,
    };
    pendingSnapshotLabel.value = "";
  },
);

const snapshotRecommendation = computed<SnapshotRecommendation | null>(() => {
  if (!props.workspace) return null;

  if (latestChangedDaysCount.value > 0) {
    return {
      badge: "建议留档",
      title: `最近有 ${latestChangedDaysCount.value} 天行程发生变化`,
      summary: "重规划后先保存一个快照，后续对比和回退会更直接。",
      suggestedLabel:
        recentChangedDayNumbers.value.length > 0
          ? `重规划后 D${recentChangedDayNumbers.value.join("-")}`
          : "重规划后留档",
      panelClass: "border-sky-200 bg-sky-50/80",
      badgeClass: "border-sky-200 bg-white text-sky-700",
    };
  }

  if (precheckAttentionCount.value > 0) {
    return {
      badge: "建议留档",
      title: `预检仍有 ${precheckAttentionCount.value} 项关注`,
      summary: "在继续处理出发前风险前先留档，能保留当前可回看的检查版本。",
      suggestedLabel: "预检关注处理前",
      panelClass: "border-rose-200 bg-rose-50/80",
      badgeClass: "border-rose-200 bg-white text-rose-700",
    };
  }

  if (unresolvedReservationCount.value > 0) {
    return {
      badge: "建议留档",
      title: `还有 ${unresolvedReservationCount.value} 项预订待落地`,
      summary: "在继续补齐交通、酒店或门票前保存当前版本，方便锁定一个阶段方案。",
      suggestedLabel: "预订待确认版",
      panelClass: "border-amber-200 bg-amber-50/80",
      badgeClass: "border-amber-200 bg-white text-amber-700",
    };
  }

  if (precheckNeedsRefresh.value) {
    return {
      badge: "建议留档",
      title: "工作区内容已更新，预检结果待刷新",
      summary: "刷新预检前先保存当前版本，后面更容易核对是哪次修改影响了结果。",
      suggestedLabel: "预检刷新前",
      panelClass: "border-violet-200 bg-violet-50/80",
      badgeClass: "border-violet-200 bg-white text-violet-700",
    };
  }

  if (snapshotVersionCount.value === 0) {
    return {
      badge: "推荐起点",
      title: "当前还没有手动快照",
      summary: "先建立一个基线版本，后面无论重规划还是微调都更容易比较。",
      suggestedLabel: "初版基线",
      panelClass: "border-[#d7e2ec] bg-white",
      badgeClass: "border-[#d7e2ec] bg-[#f8fbfd] text-[#35516b]",
    };
  }

  return null;
});

const versionTimelineEntries = computed<VersionTimelineEntry[]>(() => {
  const entries: VersionTimelineEntry[] = [];

  if (props.workspace) {
    entries.push({
      key: "current",
      title: "当前版本",
      detail: `v${props.workspace.version} · 现在正在编辑的工作区`,
      version: null,
      toneClass: "border-[#d7e2ec] bg-white",
      badgeClass: "border-[#d7e2ec] bg-[#f8fbfd] text-[#35516b]",
      action: "filter",
      filter: "all",
    });
  }

  if (latestCreatedSnapshot.value) {
    entries.push({
      key: "created-snapshot",
      title: "刚创建的快照",
      detail: `v${latestCreatedSnapshot.value.versionNumber} · ${latestCreatedSnapshot.value.versionLabel}`,
      version: {
        version: latestCreatedSnapshot.value.versionNumber,
        version_label: latestCreatedSnapshot.value.versionLabel,
      } as TripWorkspaceVersionSummary,
      toneClass: "border-emerald-200 bg-emerald-50/80",
      badgeClass: "border-emerald-200 bg-white text-emerald-700",
      action: "compare",
    });
  } else if (latestSnapshotVersion.value) {
    entries.push({
      key: "latest-snapshot",
      title: "最近快照",
      detail: `v${latestSnapshotVersion.value.version} · ${versionQuickTag(latestSnapshotVersion.value)}`,
      version: latestSnapshotVersion.value,
      toneClass: "border-sky-200 bg-sky-50/80",
      badgeClass: "border-sky-200 bg-white text-sky-700",
      action: "compare",
    });
  }

  if (latestStarredVersion.value) {
    entries.push({
      key: "latest-starred",
      title: "最近星标",
      detail: `v${latestStarredVersion.value.version} · ${versionQuickTag(latestStarredVersion.value)}`,
      version: latestStarredVersion.value,
      toneClass: "border-amber-200 bg-amber-50/80",
      badgeClass: "border-amber-200 bg-white text-amber-700",
      action: "compare",
    });
  }

  if (latestArchivedVersion.value) {
    entries.push({
      key: "latest-archived",
      title: "最近归档",
      detail: `v${latestArchivedVersion.value.version} · ${versionQuickTag(latestArchivedVersion.value)}`,
      version: latestArchivedVersion.value,
      toneClass: "border-slate-200 bg-slate-50/90",
      badgeClass: "border-slate-200 bg-white text-slate-600",
      action: "compare",
    });
  }

  if (props.tripVersions.length > 0) {
    const oldestVersion = props.tripVersions[props.tripVersions.length - 1] ?? null;
    if (oldestVersion) {
      entries.push({
        key: "oldest",
        title: "最早留档",
        detail: `v${oldestVersion.version} · ${versionQuickTag(oldestVersion)}`,
        version: oldestVersion,
        toneClass: "border-violet-200 bg-violet-50/80",
        badgeClass: "border-violet-200 bg-white text-violet-700",
        action: "compare",
      });
    }
  }

  return entries.slice(0, 5);
});

const latestBatchActionOverview = computed(() => {
  const panel = versionHistoryPanelRef.value;
  if (
    !panel ||
    (panel.latestBatchActionResultCount <= 0 &&
      panel.reviewQueuePendingCount <= 0 &&
      panel.reviewQueueDoneCount <= 0)
  ) {
    return null;
  }
  return {
    count: panel.latestBatchActionResultCount,
    summary: panel.latestBatchActionResultSummary,
    needsReview: panel.latestBatchActionNeedsReview,
    reviewQueuePendingCount: panel.reviewQueuePendingCount,
    reviewQueueDoneCount: panel.reviewQueueDoneCount,
  };
});

const versionSectionBadge = computed(() => {
  if (!props.tripVersions.length) {
    return { badge: "暂无", tone: "neutral" as const };
  }
  if (latestBatchActionOverview.value?.needsReview) {
    return {
      badge: `批量复查 ${latestBatchActionOverview.value.count}`,
      tone: "warning" as const,
    };
  }
  if (latestBatchActionOverview.value) {
    return {
      badge: `批量记录 ${latestBatchActionOverview.value.count}`,
      tone: "success" as const,
    };
  }
  return {
    badge: `${props.tripVersions.length} 个版本`,
    tone: "info" as const,
  };
});

const workspaceFocusShortcuts = computed(() =>
  [
    {
      key: "day-readiness" as const,
      label: "待补日程",
      days: incompleteDayNumbers.value,
      section: "overview" as const,
      tone: "border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100",
    },
    {
      key: "reservation" as const,
      label: "预订待落地",
      days: unresolvedReservationDayNumbers.value,
      section: "reservations" as const,
      tone: "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100",
    },
    {
      key: "precheck" as const,
      label: "预检关注",
      days: precheckAttentionDayNumbers.value,
      section: "precheck" as const,
      tone: "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100",
    },
    {
      key: "changes" as const,
      label: "最近改动",
      days: recentChangedDayNumbers.value,
      section: "changes" as const,
      tone: "border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]",
    },
  ].filter((item) => item.days.length > 0),
);

const checklistCount = computed(() => {
  let count = 0;
  if (retryableFailedJobs.value.length) count += 1;
  if (precheckNeedsRefresh.value) count += 1;
  if (unresolvedReservationCount.value > 0) count += 1;
  if (incompleteDays.value.length > 0) count += 1;
  return count;
});

const activityCount = computed(
  () => (props.workspace?.timeline.length ?? 0) + props.recentPlanningJobs.length,
);

const sectionMeta = computed<
  Array<{
    key: SectionKey;
    title: string;
    summary: string;
    badge: string;
    tone: SectionTone;
  }>
>(() => [
  {
    key: "overview",
    title: "完成度",
    summary: "先看整体分数，再决定从哪里深入。",
    badge: props.workspace
      ? `${completionOverview.value?.score ?? 0} 分`
      : "未保存",
    tone: resolveScoreTone(completionOverview.value?.score ?? 0),
  },
  {
    key: "next-step",
    title: "下一步",
    summary: "系统给出当前最值得优先处理的一件事。",
    badge: retryableFailedJobs.value.length
      ? `${retryableFailedJobs.value.length} 阻塞`
      : precheckNeedsRefresh.value
        ? "待预检"
        : incompleteDays.value.length
          ? `${incompleteDays.value.length} 天待补`
          : "已就绪",
    tone: retryableFailedJobs.value.length || precheckNeedsRefresh.value ? "warning" : "success",
  },
  {
    key: "checklist",
    title: "待办",
    summary: "把未收口的问题拆成可执行动作。",
    badge: checklistCount.value ? `${checklistCount.value} 项` : "已清空",
    tone: checklistCount.value ? "warning" : "success",
  },
  {
    key: "changes",
    title: "变更",
    summary: "查看最近改了什么，影响到了哪些天。",
    badge: latestChangedDaysCount.value
      ? `${latestChangedDaysCount.value} 天变更`
      : "无新增",
    tone: latestChangedDaysCount.value ? "info" : "neutral",
  },
  {
    key: "timeline",
    title: "时间线",
    summary: "统一回看工作区事件和后台任务历史。",
    badge: activityCount.value ? `${activityCount.value} 条` : "暂无",
    tone: activityCount.value ? "neutral" : "success",
  },
  {
    key: "versions",
    title: "版本",
    summary: "查看工作区历史快照，并在需要时恢复到较早版本。",
    badge: versionSectionBadge.value.badge,
    tone: versionSectionBadge.value.tone,
  },
  {
    key: "precheck",
    title: "预检",
    summary: "处理出发前风险并确认是否可以导出。",
    badge: hasPrecheckJobRunning.value
      ? "进行中"
      : precheckAttentionCount.value
        ? `${precheckAttentionCount.value} 项关注`
        : precheckNeedsRefresh.value
          ? "待刷新"
          : props.workspace?.status === "draft"
            ? "未启用"
            : "稳定",
    tone: hasPrecheckJobRunning.value
      ? "info"
      : precheckAttentionCount.value || precheckNeedsRefresh.value
        ? "warning"
        : "success",
  },
  {
    key: "reservations",
    title: "预订",
    summary: "管理固定预订和外部安排。",
    badge: unresolvedReservationCount.value
      ? `${unresolvedReservationCount.value} 待落地`
      : props.reservations.length
        ? `${props.reservations.length} 条`
        : "暂无",
    tone: unresolvedReservationCount.value ? "warning" : "neutral",
  },
]);

function sectionId(key: SectionKey) {
  return `workspace-section-${key}`;
}

function hydrateCollapsedSections() {
  if (typeof window === "undefined") return;
  const rawValue = window.localStorage.getItem(COLLAPSED_SECTIONS_STORAGE_KEY);
  if (!rawValue) return;

  try {
    const parsed = JSON.parse(rawValue) as Partial<Record<SectionKey, boolean>>;
    collapsedSections.value = {
      ...collapsedSections.value,
      overview: parsed.overview ?? collapsedSections.value.overview,
      "next-step": parsed["next-step"] ?? collapsedSections.value["next-step"],
      checklist: parsed.checklist ?? collapsedSections.value.checklist,
      changes: parsed.changes ?? collapsedSections.value.changes,
      timeline: parsed.timeline ?? collapsedSections.value.timeline,
      versions: parsed.versions ?? collapsedSections.value.versions,
      precheck: parsed.precheck ?? collapsedSections.value.precheck,
      reservations: parsed.reservations ?? collapsedSections.value.reservations,
    };
  } catch {
    window.localStorage.removeItem(COLLAPSED_SECTIONS_STORAGE_KEY);
  }
}

function toggleSection(key: SectionKey) {
  collapsedSections.value[key] = !collapsedSections.value[key];
}

function expandAllSections() {
  for (const key of Object.keys(collapsedSections.value) as SectionKey[]) {
    collapsedSections.value[key] = false;
  }
}

function collapseAllSections() {
  for (const key of Object.keys(collapsedSections.value) as SectionKey[]) {
    collapsedSections.value[key] = true;
  }
}

async function jumpToSection(key: SectionKey) {
  collapsedSections.value[key] = false;
  await nextTick();
  document.getElementById(sectionId(key))?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

async function openVersionHistory() {
  await jumpToSection("versions");
}

async function openVersionReviewQueue(filter: "all" | "pending" | "done" = "all") {
  await jumpToSection("versions");
  await nextTick();
  await versionHistoryPanelRef.value?.focusReviewQueueWithFilter(filter);
}

function exportPendingReviewQueueText() {
  versionHistoryPanelRef.value?.exportPendingReviewQueueText();
}

function exportPendingReviewQueueMarkdown() {
  versionHistoryPanelRef.value?.exportPendingReviewQueueMarkdown();
}

function markAllPendingReviewQueueDone() {
  versionHistoryPanelRef.value?.markAllReviewQueueDone();
}

function clearCompletedReviewQueueItems() {
  versionHistoryPanelRef.value?.clearCompletedReviewQueueItems();
}

async function openVersionHistoryWithFilter(filter: VersionHistoryQuickFilter) {
  await jumpToSection("versions");
  await nextTick();
  versionHistoryPanelRef.value?.applyQuickFilter(filter);
}

function dismissSnapshotFollowup() {
  latestCreatedSnapshot.value = null;
}

async function compareLatestCreatedSnapshot() {
  if (!latestCreatedSnapshot.value) return;
  await jumpToSection("versions");
  await nextTick();
  await versionHistoryPanelRef.value?.compareWithCurrentVersion(latestCreatedSnapshot.value.versionNumber);
}

async function reviewLatestCreatedSnapshot() {
  if (!latestCreatedSnapshot.value) return;
  await openVersionHistoryWithFilter("snapshot");
}

async function openVersionTimelineEntry(entry: VersionTimelineEntry) {
  if (entry.action === "filter") {
    await openVersionHistoryWithFilter(entry.filter ?? "all");
    return;
  }
  if (entry.version) {
    await compareVersionFromQuickCard(entry.version);
  }
}

async function compareVersionFromQuickCard(version: TripWorkspaceVersionSummary | null) {
  if (!version) return;
  await jumpToSection("versions");
  await nextTick();
  await versionHistoryPanelRef.value?.compareWithCurrentVersion(version.version);
}

async function focusShortcut(shortcut: {
  key: WorkspaceFocusShortcutKey;
  days: number[];
  section: SectionKey;
}) {
  const isActive =
    shortcut.days.length === props.focusedWorkspaceDays.length &&
    shortcut.days.every((day, index) => props.focusedWorkspaceDays[index] === day);

  if (isActive) {
    emit("clear-workspace-focus");
    return;
  }

  emit("focus-workspace-days", shortcut.days);
  await jumpToSection(shortcut.section);
}

function isShortcutActive(days: number[]) {
  return (
    days.length > 0 &&
    days.length === props.focusedWorkspaceDays.length &&
    days.every((day, index) => props.focusedWorkspaceDays[index] === day)
  );
}

function resolveScoreTone(score: number): SectionTone {
  if (score >= 85) return "success";
  if (score >= 60) return "info";
  if (score > 0) return "warning";
  return "neutral";
}

function sectionBadgeClass(tone: SectionTone) {
  if (tone === "success") {
    return "border-emerald-100 bg-emerald-50 text-emerald-700";
  }
  if (tone === "info") {
    return "border-sky-100 bg-sky-50 text-sky-700";
  }
  if (tone === "warning") {
    return "border-amber-100 bg-amber-50 text-amber-700";
  }
  return "border-[#d7e2ec] bg-[#f8fbfd] text-[#35516b]";
}

function versionQuickTag(version: TripWorkspaceVersionSummary | null) {
  if (!version) return "暂无";
  return version.version_label.trim() || version.title || `v${version.version}`;
}

function formatDateTime(value?: string | null) {
  return formatDateTimeZhCn(value);
}
</script>

<template>
  <article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7">
    <div
      v-if="busyMessage"
      class="mb-5 rounded-[20px] border border-[#d9e5ef] bg-[#f3f8fc] px-4 py-3 text-sm text-[#35516b]"
    >
      {{ busyMessage }}
    </div>

    <div
      v-if="focusedWorkspaceDays.length"
      class="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-900"
    >
      <div>
        当前正在高亮第 {{ focusedWorkspaceDays.join("、") }} 天，可直接在下方查看对应改动和日程。
      </div>
      <button
        type="button"
        class="rounded-full border border-amber-300 bg-white px-3 py-1 text-xs text-amber-800 transition hover:bg-amber-100"
        @click="emit('clear-workspace-focus')"
      >
        清除高亮
      </button>
    </div>

    <div class="mb-6 rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="font-medium text-ink">工作区导航</div>
          <div class="mt-1 text-xs text-slate-500">
            直接跳到需要处理的区域，减少在长页面里来回滚动。
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
            @click="expandAllSections"
          >
            展开全部
          </button>
          <button
            type="button"
            class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
            @click="collapseAllSections"
          >
            收起全部
          </button>
        </div>
      </div>

      <div class="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <button
          v-for="section in sectionMeta"
          :key="section.key"
          type="button"
          class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3 text-left transition hover:-translate-y-0.5 hover:bg-[#fdfefe] hover:shadow-sm"
          @click="jumpToSection(section.key)"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="font-medium text-ink">{{ section.title }}</div>
            <span
              class="rounded-full border px-2.5 py-1 text-[11px] font-medium"
              :class="sectionBadgeClass(section.tone)"
            >
              {{ section.badge }}
            </span>
          </div>
          <div class="mt-2 text-xs leading-5 text-slate-500">{{ section.summary }}</div>
        </button>
      </div>

      <div v-if="workspaceFocusShortcuts.length" class="mt-4 border-t border-[#dfe8f1] pt-4">
        <div class="text-xs text-slate-500">问题日期快捷入口</div>
        <div class="mt-2 flex flex-wrap gap-2 text-xs">
          <button
            v-for="shortcut in workspaceFocusShortcuts"
            :key="shortcut.key"
            type="button"
            class="rounded-full border px-3 py-1 transition"
            :class="
              isShortcutActive(shortcut.days)
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : shortcut.tone
            "
            @click="focusShortcut(shortcut)"
          >
            {{
              isShortcutActive(shortcut.days)
                ? `${shortcut.label} · 已聚焦`
                : `${shortcut.label} · ${shortcut.days.map((day) => `D${day}`).join("、")}`
            }}
          </button>
        </div>
      </div>

      <div
        v-if="tripVersions.length"
        class="mt-4 border-t border-[#dfe8f1] pt-4"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="text-xs text-slate-500">版本提醒</div>
          <button
            type="button"
            class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-[11px] text-[#35516b] transition hover:bg-[#eef4f9]"
            @click="openVersionHistoryWithFilter('snapshot')"
          >
            查看全部 {{ tripVersions.length }} 个版本
          </button>
        </div>

        <div class="mt-2 flex flex-wrap gap-2 text-xs">
          <button
            type="button"
            class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-sky-700 transition hover:bg-sky-100"
            @click="openVersionHistoryWithFilter('starred')"
          >
            手动快照 {{ snapshotVersionCount }} 个
          </button>
          <button
            type="button"
            class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-amber-700 transition hover:bg-amber-100"
            @click="openVersionHistoryWithFilter('archived')"
          >
            星标版本 {{ starredVersionCount }} 个
          </button>
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-slate-600 transition hover:bg-slate-200"
            @click="openVersionHistory"
          >
            已归档 {{ archivedVersionCount }} 个
          </button>
          <button
            v-if="latestBatchActionOverview"
            type="button"
            class="rounded-full border px-3 py-1 transition"
            :class="
              latestBatchActionOverview.needsReview
                ? 'border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100'
                : 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
            "
            @click="openVersionHistory"
          >
            {{
              latestBatchActionOverview.needsReview
                ? `待复查批量记录 ${latestBatchActionOverview.count} 条`
                : `批量记录 ${latestBatchActionOverview.count} 条`
            }}
          </button>
          <button
            v-if="latestBatchActionOverview?.reviewQueuePendingCount"
            type="button"
            class="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-rose-700 transition hover:bg-rose-100"
            @click="openVersionReviewQueue('pending')"
          >
            {{ `待复查 ${latestBatchActionOverview.reviewQueuePendingCount} 项` }}
          </button>
        </div>

        <div
          v-if="latestBatchActionOverview"
          class="mt-2 text-xs"
          :class="latestBatchActionOverview.needsReview ? 'text-rose-700' : 'text-emerald-700'"
        >
          {{ latestBatchActionOverview.summary }}
        </div>

        <div class="mt-3 grid gap-2 xl:grid-cols-3">
          <button
            type="button"
            class="rounded-[16px] border border-sky-100 bg-white px-3 py-3 text-left transition hover:-translate-y-0.5 hover:bg-sky-50/60 hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!latestSnapshotVersion"
            @click="compareVersionFromQuickCard(latestSnapshotVersion)"
          >
            <div class="text-[11px] text-slate-500">最近手动快照</div>
            <div class="mt-1 font-medium text-ink">
              {{ latestSnapshotVersion ? `v${latestSnapshotVersion.version}` : "暂无" }}
            </div>
            <div class="mt-1 text-xs text-[#35516b]">
              {{ versionQuickTag(latestSnapshotVersion) }}
            </div>
          </button>

          <button
            type="button"
            class="rounded-[16px] border border-amber-100 bg-white px-3 py-3 text-left transition hover:-translate-y-0.5 hover:bg-amber-50/60 hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!latestStarredVersion"
            @click="compareVersionFromQuickCard(latestStarredVersion)"
          >
            <div class="text-[11px] text-slate-500">最近星标版本</div>
            <div class="mt-1 font-medium text-ink">
              {{ latestStarredVersion ? `v${latestStarredVersion.version}` : "暂无" }}
            </div>
            <div class="mt-1 text-xs text-[#35516b]">
              {{ versionQuickTag(latestStarredVersion) }}
            </div>
          </button>

          <button
            type="button"
            class="rounded-[16px] border border-slate-200 bg-white px-3 py-3 text-left transition hover:-translate-y-0.5 hover:bg-slate-50/70 hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!latestArchivedVersion"
            @click="compareVersionFromQuickCard(latestArchivedVersion)"
          >
            <div class="text-[11px] text-slate-500">最近归档版本</div>
            <div class="mt-1 font-medium text-ink">
              {{ latestArchivedVersion ? `v${latestArchivedVersion.version}` : "暂无" }}
            </div>
            <div class="mt-1 text-xs text-[#35516b]">
              {{ versionQuickTag(latestArchivedVersion) }}
            </div>
          </button>
        </div>
      </div>
    </div>

    <PlannerWorkspaceSummary
      :workspace="workspace"
      :notes="notes"
      :share-link="shareLink"
      :saving="saving"
      :replanning="replanning"
      :reservations-count="reservations.length"
      :highlighted-replan-days="focusedWorkspaceDays"
      :recent-planning-jobs="recentPlanningJobs"
      @update:notes="(value) => emit('update:notes', value)"
      @save-notes="emit('save-notes')"
      @copy-share="emit('copy-share')"
      @revoke-share="emit('revoke-share')"
      @regenerate-share="emit('regenerate-share')"
      @export-calendar="(scope) => emit('export-calendar', scope)"
      @replan-trip="emit('replan-trip')"
    />

    <section class="mt-6 rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="font-medium text-ink">手动版本快照</div>
          <div class="mt-1 text-xs text-slate-500">
            在关键节点主动留档，方便稍后对比、恢复或标记候选方案。
          </div>
        </div>
        <div class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b]">
          当前 v{{ workspace?.version ?? "--" }}
        </div>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-3">
        <div
          v-if="snapshotRecommendation"
          class="w-full rounded-[20px] border px-4 py-3"
          :class="snapshotRecommendation.panelClass"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <span
                  class="rounded-full border px-2.5 py-1 text-[11px]"
                  :class="snapshotRecommendation.badgeClass"
                >
                  {{ snapshotRecommendation.badge }}
                </span>
                <span class="text-sm font-medium text-ink">{{ snapshotRecommendation.title }}</span>
              </div>
              <div class="mt-2 text-xs leading-5 text-slate-600">
                {{ snapshotRecommendation.summary }}
              </div>
            </div>
            <button
              type="button"
              class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
              @click="snapshotLabelDraft = snapshotRecommendation.suggestedLabel"
            >
              使用推荐标签
            </button>
          </div>
          <div class="mt-3 text-xs text-slate-500">
            推荐标签：{{ snapshotRecommendation.suggestedLabel }}
          </div>
        </div>
        <input
          v-model="snapshotLabelDraft"
          type="text"
          maxlength="40"
          class="min-w-[220px] flex-1 rounded-full border border-[#d7e2ec] bg-white px-4 py-2 text-sm text-ink"
          placeholder="可选：例如 出发前确认版 / 酒店已锁定版"
        />
        <button
          type="button"
          class="rounded-full border border-[#16324d] bg-[#16324d] px-4 py-2 text-sm text-white transition hover:bg-[#22486d] disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="!workspace || savingTripVersionLabel === workspace.version"
          @click="createVersionSnapshot"
        >
          {{
            workspace && savingTripVersionLabel === workspace.version
              ? "保存中..."
              : "保存当前为新版本"
          }}
        </button>
      </div>

      <div class="mt-3 text-xs leading-5 text-slate-500">
        快照会复制当前工作区状态并生成新的当前版本，不会覆盖现有历史版本。
      </div>
      <div
        v-if="latestCreatedSnapshot"
        class="mt-4 rounded-[20px] border border-emerald-200 bg-emerald-50/80 px-4 py-3"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-[11px] text-emerald-700">
                已创建快照
              </span>
              <span class="text-sm font-medium text-ink">
                已保存为 v{{ latestCreatedSnapshot.versionNumber }}
              </span>
            </div>
            <div class="mt-2 text-xs leading-5 text-slate-600">
              当前版本已留档为“{{ latestCreatedSnapshot.versionLabel }}”，你可以立刻去对比当前版，或打开版本历史继续整理。
            </div>
          </div>
          <button
            type="button"
            class="rounded-full border border-emerald-200 bg-white px-3 py-1 text-xs text-emerald-700 transition hover:bg-emerald-100"
            @click="dismissSnapshotFollowup"
          >
            关闭
          </button>
        </div>
        <div class="mt-3 flex flex-wrap gap-2 text-xs">
          <button
            type="button"
            class="rounded-full border border-[#16324d] bg-[#16324d] px-3 py-1 text-white transition hover:bg-[#22486d]"
            @click="compareLatestCreatedSnapshot"
          >
            对比当前版
          </button>
          <button
            type="button"
            class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-[#35516b] transition hover:bg-[#eef4f9]"
            @click="reviewLatestCreatedSnapshot"
          >
            打开版本历史
          </button>
        </div>
      </div>
    </section>

    <section class="mt-6 rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="font-medium text-ink">版本速览</div>
          <div class="mt-1 text-xs text-slate-500">
            快速查看最近留档的关键版本，不用先展开完整历史列表。
          </div>
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="jumpToSection('versions')"
        >
          打开版本历史
        </button>
      </div>

      <div class="mt-4 grid gap-3 md:grid-cols-3">
        <button
          type="button"
          class="rounded-[18px] border border-sky-100 bg-white px-4 py-4 text-left transition hover:-translate-y-0.5 hover:bg-sky-50/60 hover:shadow-sm"
          @click="compareVersionFromQuickCard(latestSnapshotVersion)"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="font-medium text-ink">最近手动快照</div>
            <span class="rounded-full border border-sky-100 bg-sky-50 px-2.5 py-1 text-[11px] text-sky-700">
              {{ latestSnapshotVersion ? `v${latestSnapshotVersion.version}` : "暂无" }}
            </span>
          </div>
          <div class="mt-2 text-sm text-[#35516b]">{{ versionQuickTag(latestSnapshotVersion) }}</div>
          <div class="mt-2 text-xs text-slate-500">
            {{ latestSnapshotVersion ? formatDateTime(latestSnapshotVersion.updated_at) : "创建快照后会显示在这里" }}
          </div>
          <div class="mt-3 text-xs text-sky-700">
            {{ latestSnapshotVersion ? "点击后对比当前版" : "暂无可对比快照" }}
          </div>
        </button>

        <button
          type="button"
          class="rounded-[18px] border border-amber-100 bg-white px-4 py-4 text-left transition hover:-translate-y-0.5 hover:bg-amber-50/60 hover:shadow-sm"
          @click="compareVersionFromQuickCard(latestStarredVersion)"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="font-medium text-ink">最近星标版本</div>
            <span class="rounded-full border border-amber-100 bg-amber-50 px-2.5 py-1 text-[11px] text-amber-700">
              {{ latestStarredVersion ? `v${latestStarredVersion.version}` : "暂无" }}
            </span>
          </div>
          <div class="mt-2 text-sm text-[#35516b]">{{ versionQuickTag(latestStarredVersion) }}</div>
          <div class="mt-2 text-xs text-slate-500">
            {{ latestStarredVersion ? formatDateTime(latestStarredVersion.updated_at) : "给关键版本标星后会显示在这里" }}
          </div>
          <div class="mt-3 text-xs text-amber-700">
            {{ latestStarredVersion ? "点击后对比当前版" : "暂无可对比星标版" }}
          </div>
        </button>

        <button
          type="button"
          class="rounded-[18px] border border-slate-200 bg-white px-4 py-4 text-left transition hover:-translate-y-0.5 hover:bg-slate-50/70 hover:shadow-sm"
          @click="compareVersionFromQuickCard(latestArchivedVersion)"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="font-medium text-ink">最近归档版本</div>
            <span class="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600">
              {{ latestArchivedVersion ? `v${latestArchivedVersion.version}` : "暂无" }}
            </span>
          </div>
          <div class="mt-2 text-sm text-[#35516b]">{{ versionQuickTag(latestArchivedVersion) }}</div>
          <div class="mt-2 text-xs text-slate-500">
            {{ latestArchivedVersion ? formatDateTime(latestArchivedVersion.updated_at) : "归档旧版本后会显示在这里" }}
          </div>
          <div class="mt-3 text-xs text-slate-600">
            {{ latestArchivedVersion ? "点击后对比当前版" : "暂无可对比归档版" }}
          </div>
        </button>
      </div>

      <div v-if="versionTimelineEntries.length" class="mt-4 rounded-[20px] border border-[#dfe8f1] bg-white/90 px-4 py-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div class="font-medium text-ink">版本摘要时间线</div>
            <div class="mt-1 text-xs text-slate-500">
              把最值得关注的几个版本节点压缩出来，减少在完整历史里来回查找。
            </div>
          </div>
          <button
            type="button"
            class="rounded-full border border-[#d7e2ec] bg-[#f8fbfd] px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
            @click="openVersionHistoryWithFilter('all')"
          >
            查看完整历史
          </button>
        </div>

        <div class="mt-4 grid gap-3 xl:grid-cols-5">
          <button
            v-for="entry in versionTimelineEntries"
            :key="entry.key"
            type="button"
            class="rounded-[18px] border px-3 py-3 text-left transition hover:-translate-y-0.5 hover:shadow-sm"
            :class="entry.toneClass"
            @click="openVersionTimelineEntry(entry)"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="text-sm font-medium text-ink">{{ entry.title }}</div>
              <span class="rounded-full border px-2.5 py-1 text-[11px]" :class="entry.badgeClass">
                {{ entry.version ? `v${entry.version.version}` : "当前" }}
              </span>
            </div>
            <div class="mt-2 text-xs leading-5 text-slate-600">
              {{ entry.detail }}
            </div>
            <div class="mt-3 text-[11px] text-[#35516b]">
              {{ entry.action === "compare" ? "点击后对比当前版" : "点击后打开版本历史" }}
            </div>
          </button>
        </div>
      </div>

      <button
        v-if="latestBatchActionOverview"
        type="button"
        class="mt-4 w-full rounded-[20px] border border-emerald-200 bg-emerald-50/80 px-4 py-4 text-left transition hover:-translate-y-0.5 hover:bg-emerald-50 hover:shadow-sm"
        @click="
          latestBatchActionOverview.reviewQueuePendingCount > 0
            ? openVersionReviewQueue('pending')
            : openVersionHistory()
        "
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="font-medium text-emerald-900">最近批量处理</div>
            <div class="mt-1 text-xs text-emerald-700">
              {{
                latestBatchActionOverview.count > 0
                  ? `已保留 ${latestBatchActionOverview.count} 条批量处理记录`
                  : "暂无新的批量处理记录"
              }}
            </div>
            <div
              v-if="
                latestBatchActionOverview.reviewQueuePendingCount ||
                latestBatchActionOverview.reviewQueueDoneCount
              "
              class="mt-1 text-xs text-emerald-700"
            >
              {{
                `复查队列：待复查 ${latestBatchActionOverview.reviewQueuePendingCount} 项，已复查 ${latestBatchActionOverview.reviewQueueDoneCount} 项`
              }}
            </div>
          </div>
          <div class="flex flex-wrap items-start justify-end gap-2">
            <button
              v-if="latestBatchActionOverview.reviewQueuePendingCount > 0"
              type="button"
              class="rounded-full border border-rose-200 bg-white px-2.5 py-1 text-[11px] text-rose-700 transition hover:bg-rose-100"
              @click.stop="markAllPendingReviewQueueDone"
            >
              全部标记已复查
            </button>
            <button
              v-if="latestBatchActionOverview.reviewQueueDoneCount > 0"
              type="button"
              class="rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-[11px] text-emerald-700 transition hover:bg-emerald-100"
              @click.stop="clearCompletedReviewQueueItems"
            >
              清空已复查
            </button>
            <button
              v-if="latestBatchActionOverview.reviewQueuePendingCount > 0"
              type="button"
              class="rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-[11px] text-emerald-700 transition hover:bg-emerald-100"
              @click.stop="exportPendingReviewQueueText"
            >
              导出文本
            </button>
            <button
              v-if="latestBatchActionOverview.reviewQueuePendingCount > 0"
              type="button"
              class="rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-[11px] text-emerald-700 transition hover:bg-emerald-100"
              @click.stop="exportPendingReviewQueueMarkdown"
            >
              导出 Markdown
            </button>
            <span
              class="rounded-full border px-2.5 py-1 text-[11px]"
              :class="
                latestBatchActionOverview.needsReview ||
                latestBatchActionOverview.reviewQueuePendingCount > 0
                  ? 'border-amber-200 bg-white text-amber-700'
                  : 'border-emerald-200 bg-white text-emerald-700'
              "
            >
              {{
                latestBatchActionOverview.needsReview ||
                latestBatchActionOverview.reviewQueuePendingCount > 0
                  ? "有待复查"
                  : "已记录"
              }}
            </span>
          </div>
        </div>
        <div v-if="latestBatchActionOverview.summary" class="mt-2 text-sm text-emerald-900">
          {{ latestBatchActionOverview.summary }}
        </div>
        <div class="mt-3 text-xs text-emerald-700">
          {{
            latestBatchActionOverview.reviewQueuePendingCount > 0
              ? "点击后直接定位到待复查队列"
              : "点击后打开版本历史并查看批量处理记录"
          }}
        </div>
      </button>
    </section>

    <section :id="sectionId('overview')" class="mt-6">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium text-ink">完成度概览</div>
          <div class="text-xs text-slate-500">先看整体，再决定要往哪一块深入。</div>
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="toggleSection('overview')"
        >
          {{ collapsedSections.overview ? "展开" : "收起" }}
        </button>
      </div>
      <WorkspaceCompletionOverview
        v-if="!collapsedSections.overview"
        :workspace="workspace"
        :jobs="recentPlanningJobs"
        :prechecking="prechecking"
        :day-readiness-summary="dayReadinessSummary"
        :day-readiness-items="dayReadinessItems"
        :reservation-coverage-summary="reservationCoverageSummary"
        :reservation-coverage-items="reservationCoverageItems"
        :departure-precheck-summary="departurePrecheckSummary"
        @focus-days="(dayNumbers) => emit('focus-workspace-days', dayNumbers)"
        @refresh-precheck="emit('refresh-precheck')"
      />
    </section>

    <section :id="sectionId('next-step')" class="mt-6">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium text-ink">下一步建议</div>
          <div class="text-xs text-slate-500">如果只做一件事，优先做这里。</div>
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="toggleSection('next-step')"
        >
          {{ collapsedSections['next-step'] ? "展开" : "收起" }}
        </button>
      </div>
      <WorkspaceNextStepCard
        v-if="!collapsedSections['next-step']"
        :workspace="workspace"
        :jobs="recentPlanningJobs"
        :prechecking="prechecking"
        :retrying-job-id="retryingJobId"
        @focus-days="(dayNumbers) => emit('focus-workspace-days', dayNumbers)"
        @retry-job="(job) => emit('retry-planning-job', job)"
        @refresh-precheck="emit('refresh-precheck')"
        @export-calendar="(scope) => emit('export-calendar', scope)"
      />
    </section>

    <section :id="sectionId('checklist')" class="mt-6">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium text-ink">待办清单</div>
          <div class="text-xs text-slate-500">把没收口的问题拆成任务，逐个处理。</div>
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="toggleSection('checklist')"
        >
          {{ collapsedSections.checklist ? "展开" : "收起" }}
        </button>
      </div>
      <WorkspaceActionChecklist
        v-if="!collapsedSections.checklist"
        :workspace="workspace"
        :jobs="recentPlanningJobs"
        :prechecking="prechecking"
        :retrying-job-id="retryingJobId"
        :replanning-days="replanningDays"
        :reservation-coverage-summary="reservationCoverageSummary"
        :reservation-coverage-items="reservationCoverageItems"
        :day-readiness-summary="dayReadinessSummary"
        :day-readiness-items="dayReadinessItems"
        @focus-days="(dayNumbers) => emit('focus-workspace-days', dayNumbers)"
        @retry-job="(job) => emit('retry-planning-job', job)"
        @refresh-precheck="emit('refresh-precheck')"
        @repair-day-gap="(payload) => emit('repair-day-gap', payload)"
      />
    </section>

    <section :id="sectionId('changes')" class="mt-6">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium text-ink">最近变更</div>
          <div class="text-xs text-slate-500">看刚刚发生了什么变化，以及它影响了哪些天。</div>
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="toggleSection('changes')"
        >
          {{ collapsedSections.changes ? "展开" : "收起" }}
        </button>
      </div>
      <WorkspaceChangeDigest
        v-if="!collapsedSections.changes"
        :workspace="workspace"
        :jobs="recentPlanningJobs"
        :highlighted-replan-days="focusedWorkspaceDays"
        :retrying-job-id="retryingJobId"
        :prechecking="prechecking"
        @focus-days="(dayNumbers) => emit('focus-workspace-days', dayNumbers)"
        @retry-job="(job) => emit('retry-planning-job', job)"
        @refresh-precheck="emit('refresh-precheck')"
      />
    </section>

    <section :id="sectionId('timeline')" class="mt-6">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium text-ink">活动时间线</div>
          <div class="text-xs text-slate-500">回看工作区事件和后台任务历史。</div>
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="toggleSection('timeline')"
        >
          {{ collapsedSections.timeline ? "展开" : "收起" }}
        </button>
      </div>
      <WorkspaceActivityTimeline
        v-if="!collapsedSections.timeline"
        :workspace="workspace"
        :jobs="recentPlanningJobs"
        :loading="recentPlanningJobsLoading"
        :error="recentPlanningJobsError"
        :retrying-job-id="retryingJobId"
        :highlighted-replan-days="focusedWorkspaceDays"
        @retry="(job) => emit('retry-planning-job', job)"
        @focus-days="(dayNumbers) => emit('focus-workspace-days', dayNumbers)"
      />
    </section>

    <section :id="sectionId('versions')" class="mt-6">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium text-ink">版本历史</div>
          <div class="text-xs text-slate-500">查看最近保存的工作区版本，并按需恢复。</div>
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="toggleSection('versions')"
        >
          {{ collapsedSections.versions ? "展开" : "收起" }}
        </button>
      </div>
      <WorkspaceVersionHistoryPanel
        v-if="!collapsedSections.versions"
        ref="versionHistoryPanelRef"
        :workspace="workspace"
        :versions="tripVersions"
        :loading="tripVersionsLoading"
        :error="tripVersionsError"
        :has-more-versions="tripVersionsHasMore"
        :restoring-version="restoringTripVersion"
        :saving-version-label="savingTripVersionLabel"
        @restore="(version) => emit('restore-trip-version', version)"
        @save-label="(version, versionLabel) => emit('save-trip-version-label', version, versionLabel)"
        @toggle-star="(version) => emit('toggle-trip-version-star', version)"
        @toggle-archive="(version) => emit('toggle-trip-version-archive', version)"
        @batch-update="(versions, action) => emit('batch-trip-version-update', versions, action)"
        @load-more="emit('load-more-trip-versions')"
        @load-all="emit('load-all-trip-versions')"
        @delete="(version) => emit('delete-trip-version', version)"
        @focus-days="(dayNumbers) => emit('focus-workspace-days', dayNumbers)"
      />
    </section>

    <section :id="sectionId('precheck')" class="mt-6">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium text-ink">出发前预检</div>
          <div class="text-xs text-slate-500">处理天气、路线和预订落地的最后确认。</div>
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="toggleSection('precheck')"
        >
          {{ collapsedSections.precheck ? "展开" : "收起" }}
        </button>
      </div>
      <div v-if="!collapsedSections.precheck">
        <DeparturePrecheckPanel
          :summary="departurePrecheckSummary"
          :items="departurePrecheckItems"
          :refreshing="prechecking"
          :enabled="Boolean(workspace && workspace.status !== 'draft')"
          @refresh="emit('refresh-precheck')"
        />
        <DeparturePrecheckSummaryCard
          :summary="workspace?.last_precheck_summary"
          :replanning-days="replanningDays"
          @repair-day-gap="(payload) => emit('repair-day-gap', payload)"
        />
      </div>
    </section>

    <section :id="sectionId('reservations')" class="mt-6">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="font-medium text-ink">固定预订与外部安排</div>
          <div class="text-xs text-slate-500">管理酒店、车票、餐厅和其它固定安排。</div>
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="toggleSection('reservations')"
        >
          {{ collapsedSections.reservations ? "展开" : "收起" }}
        </button>
      </div>
      <PlannerReservationPanel
        v-if="!collapsedSections.reservations"
        :workspace="workspace"
        :saving="saving"
        :replanning-days="replanningDays"
        :reservations="reservations"
        :reservation-alerts="reservationAlerts"
        :reservation-coverage-summary="reservationCoverageSummary"
        :reservation-coverage-items="reservationCoverageItems"
        :day-readiness-summary="dayReadinessSummary"
        :day-readiness-items="dayReadinessItems"
        @repair-day-gap="(payload) => emit('repair-day-gap', payload)"
        @add-reservation="(value) => emit('add-reservation', value)"
        @remove-reservation="(id) => emit('remove-reservation', id)"
      />
    </section>
  </article>
</template>
