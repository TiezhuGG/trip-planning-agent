<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

import { buildWorkspaceCompletionOverview } from "../composables/tripWorkspaceCompletionOverview";
import {
  collectPrecheckAffectedDays,
  countPrecheckAttentionItems,
  hasRunningPrecheckJob,
  isPrecheckSummaryStale,
} from "../composables/tripWorkspaceExportReadiness";
import { getReservationTargetDaysById } from "../composables/tripWorkspaceReservationCoverageHelpers";
import type {
  CalendarExportScope,
  PlanningJobSummary,
  ReservationItem,
  TripWorkspace,
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
import { sortUniqueNumbers } from "../utils/workspaceFormatting";

import DeparturePrecheckPanel from "./DeparturePrecheckPanel.vue";
import DeparturePrecheckSummaryCard from "./DeparturePrecheckSummaryCard.vue";
import PlannerReservationPanel from "./PlannerReservationPanel.vue";
import PlannerWorkspaceSummary from "./PlannerWorkspaceSummary.vue";
import WorkspaceActionChecklist from "./WorkspaceActionChecklist.vue";
import WorkspaceActivityTimeline from "./WorkspaceActivityTimeline.vue";
import WorkspaceChangeDigest from "./WorkspaceChangeDigest.vue";
import WorkspaceCompletionOverview from "./WorkspaceCompletionOverview.vue";
import WorkspaceNextStepCard from "./WorkspaceNextStepCard.vue";

type SectionKey =
  | "overview"
  | "next-step"
  | "checklist"
  | "changes"
  | "timeline"
  | "precheck"
  | "reservations";

type SectionTone = "neutral" | "info" | "warning" | "success";
type WorkspaceFocusShortcutKey = "day-readiness" | "reservation" | "precheck" | "changes";

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
  (event: "focus-workspace-days", dayNumbers: number[]): void;
  (event: "clear-workspace-focus"): void;
  (event: "replan-trip"): void;
  (event: "refresh-precheck"): void;
  (event: "retry-planning-job", job: PlanningJobSummary): void;
  (event: "repair-day-gap", payload: DayGapRepairPayload): void;
  (event: "add-reservation", value: Omit<ReservationItem, "id">): void;
  (event: "remove-reservation", id: string): void;
}>();

const collapsedSections = ref<Record<SectionKey, boolean>>({
  overview: false,
  "next-step": false,
  checklist: false,
  changes: false,
  timeline: false,
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
  if (!props.workspace || props.workspace.status === "draft") return false;
  if (hasPrecheckJobRunning.value) return false;
  if (!props.workspace.last_precheck_summary) return true;
  return isPrecheckSummaryStale(props.workspace) || precheckAttentionCount.value > 0;
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
