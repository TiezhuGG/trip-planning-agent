<script setup lang="ts">
import { computed, ref } from "vue";

import type { PlanningJobSummary } from "../types/planning";
import {
  canRetryPlanningJob,
  formatPlanningJobDuration,
  formatPlanningJobKind,
  formatPlanningJobStatus,
  humanizePlanningJobProgress,
  resolvePlanningJobStatusBadgeClass,
} from "../utils/planningJobs";
import { formatDateTimeZhCn } from "../utils/workspaceFormatting";

const props = defineProps<{
  jobs: PlanningJobSummary[];
  loading: boolean;
  error: string;
  retryingJobId: string;
}>();

const emit = defineEmits<{
  (event: "retry", job: PlanningJobSummary): void;
}>();

const expandedJobIds = ref<string[]>([]);
const searchText = ref("");
const activeStatus = ref<"all" | PlanningJobSummary["status"]>("all");
const activeKind = ref<"all" | PlanningJobSummary["kind"]>("all");

const statusFilters = computed(() => {
  const counts: Record<PlanningJobSummary["status"], number> = {
    queued: 0,
    running: 0,
    succeeded: 0,
    failed: 0,
  };
  for (const job of props.jobs) {
    counts[job.status] += 1;
  }
  return [
    { key: "all" as const, label: "全部", count: props.jobs.length },
    { key: "running" as const, label: "进行中", count: counts.running },
    { key: "queued" as const, label: "排队中", count: counts.queued },
    { key: "failed" as const, label: "失败", count: counts.failed },
    { key: "succeeded" as const, label: "已完成", count: counts.succeeded },
  ].filter((item) => item.key === "all" || item.count > 0);
});

const kindFilters = computed(() => {
  const counts: Record<PlanningJobSummary["kind"], number> = {
    generate_plan: 0,
    update_trip: 0,
    replan_trip: 0,
    precheck_trip: 0,
  };
  for (const job of props.jobs) {
    counts[job.kind] += 1;
  }
  return [
    { key: "all" as const, label: "全部类型", count: props.jobs.length },
    { key: "update_trip" as const, label: "更新工作区", count: counts.update_trip },
    { key: "precheck_trip" as const, label: "出发前预检", count: counts.precheck_trip },
    { key: "replan_trip" as const, label: "重规划", count: counts.replan_trip },
    { key: "generate_plan" as const, label: "生成规划", count: counts.generate_plan },
  ].filter((item) => item.key === "all" || item.count > 0);
});

const filteredJobs = computed(() => {
  const keyword = searchText.value.trim().toLowerCase();
  return props.jobs.filter((job) => {
    if (activeStatus.value !== "all" && job.status !== activeStatus.value) {
      return false;
    }
    if (activeKind.value !== "all" && job.kind !== activeKind.value) {
      return false;
    }
    if (!keyword) {
      return true;
    }
    return [
      job.id,
      formatJobKind(job.kind),
      formatJobStatus(job.status),
      humanizePlanningJobProgress(job),
      job.error_code,
      job.error_message,
    ]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(keyword));
  });
});

const hasActiveFilters = computed(
  () =>
    activeStatus.value !== "all" ||
    activeKind.value !== "all" ||
    Boolean(searchText.value.trim()),
);

function formatDateTime(value?: string | null) {
  return formatDateTimeZhCn(value);
}

function formatJobKind(kind: PlanningJobSummary["kind"]) {
  return formatPlanningJobKind(kind);
}

function formatJobStatus(status: PlanningJobSummary["status"]) {
  return formatPlanningJobStatus(status);
}

function resolveStatusClass(status: PlanningJobSummary["status"]) {
  return resolvePlanningJobStatusBadgeClass(status);
}

function isExpanded(jobId: string) {
  return expandedJobIds.value.includes(jobId);
}

function toggleExpanded(jobId: string) {
  expandedJobIds.value = isExpanded(jobId)
    ? expandedJobIds.value.filter((id) => id !== jobId)
    : [...expandedJobIds.value, jobId];
}

function canRetry(job: PlanningJobSummary) {
  return canRetryPlanningJob(job);
}

function resetFilters() {
  searchText.value = "";
  activeStatus.value = "all";
  activeKind.value = "all";
}

function resolveEmptyMessage() {
  if (props.loading) return "正在读取最近后台任务。";
  if (props.error) return props.error;
  return "当前工作区还没有后台任务记录。";
}

function resolveFilteredEmptyMessage() {
  if (props.loading) return "正在读取最近后台任务。";
  if (props.error) return props.error;
  return "当前筛选条件下没有匹配的后台任务。";
}
</script>

<template>
  <section class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600">
    <div class="flex items-center justify-between gap-3">
      <div class="font-medium text-ink">最近后台任务</div>
      <div class="text-xs text-slate-500">
        {{ jobs.length ? `最近 ${jobs.length} 条` : "暂无记录" }}
      </div>
    </div>

    <div v-if="!jobs.length" class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3">
      {{ resolveEmptyMessage() }}
    </div>

    <div v-else class="mt-4">
      <div class="flex flex-wrap gap-2 text-xs">
        <button
          v-for="item in statusFilters"
          :key="item.key"
          type="button"
          class="rounded-full border px-3 py-1 transition"
          :class="
            activeStatus === item.key
              ? 'border-[#16324d] bg-[#16324d] text-white'
              : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
          "
          @click="activeStatus = item.key"
        >
          {{ item.label }} {{ item.count }}
        </button>
      </div>

      <div class="mt-3 flex flex-wrap gap-2 text-xs">
        <button
          v-for="item in kindFilters"
          :key="item.key"
          type="button"
          class="rounded-full border px-3 py-1 transition"
          :class="
            activeKind === item.key
              ? 'border-sky-200 bg-sky-50 text-sky-700'
              : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
          "
          @click="activeKind = item.key"
        >
          {{ item.label }} {{ item.count }}
        </button>
      </div>

      <div class="mt-3 flex flex-wrap items-center gap-3">
        <input
          v-model="searchText"
          type="text"
          class="min-w-0 flex-1 rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
          placeholder="搜索任务类型、状态、任务 ID 或错误信息"
        />
        <button
          v-if="hasActiveFilters"
          type="button"
          class="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="resetFilters"
        >
          清空筛选
        </button>
      </div>

      <div class="mt-3 text-xs text-slate-500">
        当前显示 {{ filteredJobs.length }} / {{ jobs.length }} 条任务
      </div>

      <div
        v-if="!filteredJobs.length"
        class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3"
      >
        {{ resolveFilteredEmptyMessage() }}
      </div>

      <div v-else class="mt-4 space-y-3">
      <article
        v-for="job in filteredJobs"
        :key="job.id"
        class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="font-medium text-ink">{{ formatJobKind(job.kind) }}</div>
            <div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
              <span>任务 ID: {{ job.id.slice(0, 8) }}</span>
              <span>执行时长: {{ formatPlanningJobDuration(job) }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <div
              class="rounded-full border px-3 py-1 text-xs font-medium"
              :class="resolveStatusClass(job.status)"
            >
              {{ formatJobStatus(job.status) }}
            </div>
            <button
              type="button"
              class="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 transition hover:bg-slate-50"
              @click="toggleExpanded(job.id)"
            >
              {{ isExpanded(job.id) ? "收起" : "详情" }}
            </button>
            <button
              v-if="canRetry(job)"
              type="button"
              class="rounded-full border border-[#16324d] px-3 py-1 text-xs text-[#16324d] transition hover:bg-[#eef4f9] disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="retryingJobId === job.id"
              @click="emit('retry', job)"
            >
              {{ retryingJobId === job.id ? "重试中..." : "重试" }}
            </button>
          </div>
        </div>

        <div class="mt-3 text-sm text-slate-600">
          {{ humanizePlanningJobProgress(job) }}
        </div>

        <div
          v-if="isExpanded(job.id)"
          class="mt-4 grid gap-3 rounded-[16px] bg-[#f8fbfd] p-3 text-xs text-slate-500 sm:grid-cols-2"
        >
          <div>
            <div class="uppercase tracking-[0.14em] text-slate-400">创建时间</div>
            <div class="mt-1 text-sm text-slate-700">{{ formatDateTime(job.created_at) }}</div>
          </div>
          <div>
            <div class="uppercase tracking-[0.14em] text-slate-400">更新时间</div>
            <div class="mt-1 text-sm text-slate-700">{{ formatDateTime(job.updated_at) }}</div>
          </div>
          <div>
            <div class="uppercase tracking-[0.14em] text-slate-400">开始时间</div>
            <div class="mt-1 text-sm text-slate-700">{{ formatDateTime(job.started_at) }}</div>
          </div>
          <div>
            <div class="uppercase tracking-[0.14em] text-slate-400">完成时间</div>
            <div class="mt-1 text-sm text-slate-700">{{ formatDateTime(job.completed_at) }}</div>
          </div>
          <div>
            <div class="uppercase tracking-[0.14em] text-slate-400">执行时长</div>
            <div class="mt-1 text-sm text-slate-700">{{ formatPlanningJobDuration(job) }}</div>
          </div>
          <div>
            <div class="uppercase tracking-[0.14em] text-slate-400">任务类型</div>
            <div class="mt-1 text-sm text-slate-700">{{ formatJobKind(job.kind) }}</div>
          </div>
          <div v-if="job.error_code" class="sm:col-span-2">
            <div class="uppercase tracking-[0.14em] text-slate-400">错误代码</div>
            <div class="mt-1 text-sm text-rose-700">{{ job.error_code }}</div>
          </div>
          <div v-if="job.error_message" class="sm:col-span-2">
            <div class="uppercase tracking-[0.14em] text-slate-400">错误信息</div>
            <div class="mt-1 text-sm text-rose-700">{{ job.error_message }}</div>
          </div>
        </div>
      </article>
      </div>
    </div>
  </section>
</template>
