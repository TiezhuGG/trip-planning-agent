<script setup lang="ts">
import { computed, ref } from "vue";

import type {
  PlanningJobSummary,
  TripWorkspace,
  WorkspaceTimelineEvent,
} from "../types/planning";
import {
  canRetryPlanningJob,
  formatPlanningJobDuration,
  formatPlanningJobKind,
  formatPlanningJobStatus,
  humanizePlanningJobProgress,
  isPlanningJobActive,
  resolvePlanningJobStatusBadgeClass,
} from "../utils/planningJobs";
import { formatDateTimeZhCn, sortUniqueNumbers } from "../utils/workspaceFormatting";

const props = defineProps<{
  workspace: TripWorkspace | null;
  jobs: PlanningJobSummary[];
  loading: boolean;
  error: string;
  retryingJobId: string;
  highlightedReplanDays: number[];
}>();

const emit = defineEmits<{
  (event: "retry", job: PlanningJobSummary): void;
  (event: "focus-days", dayNumbers: number[]): void;
}>();

type ActivityTimelineItem =
  | {
      id: string;
      type: "workspace";
      sortTime: number;
      event: WorkspaceTimelineEvent;
    }
  | {
      id: string;
      type: "job";
      sortTime: number;
      job: PlanningJobSummary;
    };

type ActivityFilter = "all" | "workspace" | "jobs" | "running" | "failed";

const DEFAULT_VISIBLE_COUNT = 6;

const activeFilter = ref<ActivityFilter>("all");
const expanded = ref(false);

const activityItems = computed<ActivityTimelineItem[]>(() => {
  const workspaceItems: ActivityTimelineItem[] = (props.workspace?.timeline ?? []).map((event) => ({
    id: `workspace-${event.id}`,
    type: "workspace",
    sortTime: resolveSortTime(event.created_at),
    event,
  }));

  const jobItems: ActivityTimelineItem[] = props.jobs.map((job) => ({
    id: `job-${job.id}`,
    type: "job",
    sortTime: resolveSortTime(job.completed_at || job.updated_at || job.created_at),
    job,
  }));

  return [...workspaceItems, ...jobItems].sort((left, right) => right.sortTime - left.sortTime);
});

const filterOptions = computed(() => [
  { key: "all" as const, label: "全部", count: activityItems.value.length },
  {
    key: "workspace" as const,
    label: "工作区",
    count: activityItems.value.filter((item) => item.type === "workspace").length,
  },
  {
    key: "jobs" as const,
    label: "任务",
    count: activityItems.value.filter((item) => item.type === "job").length,
  },
  {
    key: "running" as const,
    label: "进行中",
    count: activityItems.value.filter(
      (item) => item.type === "job" && isPlanningJobActive(item.job),
    ).length,
  },
  {
    key: "failed" as const,
    label: "失败",
    count: activityItems.value.filter(
      (item) => item.type === "job" && item.job.status === "failed",
    ).length,
  },
]);

const filteredItems = computed(() =>
  activityItems.value.filter((item) => {
    if (activeFilter.value === "all") return true;
    if (activeFilter.value === "workspace") return item.type === "workspace";
    if (activeFilter.value === "jobs") return item.type === "job";
    if (activeFilter.value === "running") {
      return item.type === "job" && isPlanningJobActive(item.job);
    }
    return item.type === "job" && item.job.status === "failed";
  }),
);

const visibleItems = computed(() =>
  expanded.value ? filteredItems.value : filteredItems.value.slice(0, DEFAULT_VISIBLE_COUNT),
);

const hiddenItemCount = computed(() =>
  Math.max(filteredItems.value.length - visibleItems.value.length, 0),
);

function resolveSortTime(value?: string | null) {
  if (!value) return 0;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function formatDateTime(value?: string | null) {
  return formatDateTimeZhCn(value);
}

function formatJobKind(kind: PlanningJobSummary["kind"]) {
  return formatPlanningJobKind(kind);
}

function formatJobStatus(status: PlanningJobSummary["status"]) {
  return formatPlanningJobStatus(status);
}

function resolveJobStatusClass(status: PlanningJobSummary["status"]) {
  return resolvePlanningJobStatusBadgeClass(status);
}

function canRetry(job: PlanningJobSummary) {
  return canRetryPlanningJob(job);
}

function isHighlightedDay(dayNumber: number) {
  return props.highlightedReplanDays.includes(dayNumber);
}

function focusDays(dayNumbers: number[]) {
  const normalized = sortUniqueNumbers(dayNumbers);
  if (!normalized.length) return;
  emit("focus-days", normalized);
}

function selectFilter(filter: ActivityFilter) {
  activeFilter.value = filter;
  expanded.value = false;
}

function toggleExpanded() {
  expanded.value = !expanded.value;
}

function resolveEmptyMessage() {
  if (props.loading) return "正在加载活动记录。";
  if (props.error && !activityItems.value.length) return props.error;
  if (activeFilter.value === "workspace") return "当前没有工作区变更记录。";
  if (activeFilter.value === "jobs") return "当前没有后台任务记录。";
  if (activeFilter.value === "running") return "当前没有进行中的后台任务。";
  if (activeFilter.value === "failed") return "最近没有失败任务。";
  return "当前工作区还没有活动记录。";
}
</script>

<template>
  <section class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="font-medium text-ink">活动时间线</div>
        <div class="mt-1 text-xs text-slate-500">
          把工作区事件和后台任务放在同一条时间线里，方便回看最近发生了什么。
        </div>
      </div>
      <div class="text-xs text-slate-500">
        {{ activityItems.length ? `共 ${activityItems.length} 条记录` : "暂无记录" }}
      </div>
    </div>

    <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap gap-2">
        <button
          v-for="filter in filterOptions"
          :key="filter.key"
          type="button"
          class="rounded-full border px-3 py-1 text-xs transition"
          :class="
            activeFilter === filter.key
              ? 'border-[#16324d] bg-[#16324d] text-white'
              : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
          "
          @click="selectFilter(filter.key)"
        >
          {{ filter.label }} {{ filter.count }}
        </button>
      </div>

      <button
        v-if="filteredItems.length > DEFAULT_VISIBLE_COUNT"
        type="button"
        class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
        @click="toggleExpanded"
      >
        {{ expanded ? "收起" : `展开剩余 ${hiddenItemCount} 条` }}
      </button>
    </div>

    <div
      v-if="props.error && activityItems.length"
      class="mt-4 rounded-[18px] border border-amber-200 bg-amber-50 px-4 py-3 text-amber-800"
    >
      {{ props.error }}
    </div>

    <div
      v-if="!visibleItems.length"
      class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3"
    >
      {{ resolveEmptyMessage() }}
    </div>

    <div v-else class="mt-4 space-y-3">
      <article
        v-for="item in visibleItems"
        :key="item.id"
        class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3"
      >
        <template v-if="item.type === 'workspace'">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full bg-[#eef4f9] px-2.5 py-1 text-[11px] text-[#35516b]">
                  工作区
                </span>
                <div class="font-medium text-ink">{{ item.event.title }}</div>
              </div>
              <div v-if="item.event.summary" class="mt-2 text-sm text-slate-600">
                {{ item.event.summary }}
              </div>
            </div>
            <div class="text-xs text-slate-500">
              v{{ item.event.version }} · {{ formatDateTime(item.event.created_at) }}
            </div>
          </div>

          <div v-if="item.event.target_days.length" class="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
              @click="focusDays(item.event.target_days)"
            >
              查看影响日期
            </button>
            <button
              v-for="dayNumber in item.event.target_days"
              :key="`${item.event.id}-${dayNumber}`"
              type="button"
              class="rounded-full px-3 py-1 text-xs transition"
              :class="
                isHighlightedDay(dayNumber)
                  ? 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200'
                  : 'bg-[#eef4f9] text-[#35516b] hover:bg-white'
              "
              @click="focusDays([dayNumber])"
            >
              第 {{ dayNumber }} 天
            </button>
          </div>
        </template>

        <template v-else>
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600">
                  后台任务
                </span>
                <div class="font-medium text-ink">{{ formatJobKind(item.job.kind) }}</div>
                <span
                  class="rounded-full border px-3 py-1 text-xs font-medium"
                  :class="resolveJobStatusClass(item.job.status)"
                >
                  {{ formatJobStatus(item.job.status) }}
                </span>
              </div>
              <div class="mt-2 text-sm text-slate-600">
                {{ humanizePlanningJobProgress(item.job) }}
              </div>
              <div v-if="item.job.error_message" class="mt-2 text-sm text-rose-700">
                {{ item.job.error_message }}
              </div>
            </div>

            <button
              v-if="canRetry(item.job)"
              type="button"
              class="rounded-full border border-[#16324d] px-3 py-1 text-xs text-[#16324d] transition hover:bg-[#eef4f9] disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="props.retryingJobId === item.job.id"
              @click="emit('retry', item.job)"
            >
              {{ props.retryingJobId === item.job.id ? "重试中..." : "重试" }}
            </button>
          </div>

          <div class="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
            <div class="rounded-[14px] bg-[#f8fbfd] px-3 py-2">
              <div class="uppercase tracking-[0.12em] text-slate-400">创建</div>
              <div class="mt-1 text-sm text-slate-700">{{ formatDateTime(item.job.created_at) }}</div>
            </div>
            <div class="rounded-[14px] bg-[#f8fbfd] px-3 py-2">
              <div class="uppercase tracking-[0.12em] text-slate-400">更新</div>
              <div class="mt-1 text-sm text-slate-700">{{ formatDateTime(item.job.updated_at) }}</div>
            </div>
            <div class="rounded-[14px] bg-[#f8fbfd] px-3 py-2">
              <div class="uppercase tracking-[0.12em] text-slate-400">完成</div>
              <div class="mt-1 text-sm text-slate-700">{{ formatDateTime(item.job.completed_at) }}</div>
            </div>
            <div class="rounded-[14px] bg-[#f8fbfd] px-3 py-2">
              <div class="uppercase tracking-[0.12em] text-slate-400">执行时长</div>
              <div class="mt-1 text-sm text-slate-700">{{ formatPlanningJobDuration(item.job) }}</div>
            </div>
          </div>
        </template>
      </article>
    </div>
  </section>
</template>
