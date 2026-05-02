<script setup lang="ts">
import { computed } from "vue";

import { collectPrecheckAffectedDays } from "../composables/tripWorkspaceExportReadiness";
import type {
  PlanningJobSummary,
  PrecheckSummaryItem,
  ReplanDaySummary,
  TripWorkspace,
} from "../types/planning";
import {
  canRetryPlanningJob,
  formatPlanningJobKind,
  formatPlanningJobStatus,
  isPlanningJobActive,
  resolvePlanningJobStatusBadgeClass,
} from "../utils/planningJobs";
import {
  formatPrecheckStatusLabel,
  resolvePrecheckStatusBadgeClass,
} from "../utils/precheckSummary";
import { formatDateTimeZhCn, sortUniqueNumbers } from "../utils/workspaceFormatting";

const props = defineProps<{
  workspace: TripWorkspace | null;
  jobs: PlanningJobSummary[];
  highlightedReplanDays: number[];
  retryingJobId: string;
  prechecking: boolean;
}>();

const emit = defineEmits<{
  (event: "focus-days", dayNumbers: number[]): void;
  (event: "retry-job", job: PlanningJobSummary): void;
  (event: "refresh-precheck"): void;
}>();

const latestReplan = computed(() => props.workspace?.last_replan_summary ?? null);
const latestPrecheck = computed(() => props.workspace?.last_precheck_summary ?? null);

const changedReplanDays = computed(() =>
  (latestReplan.value?.items ?? []).filter(
    (item) => Boolean(item.changes?.length) || Boolean(item.highlights.length),
  ),
);

const precheckDeltaItems = computed(() =>
  (latestPrecheck.value?.items ?? []).filter(
    (item) => item.before_status !== item.after_status,
  ),
);

const precheckAttentionItems = computed(() =>
  (latestPrecheck.value?.items ?? []).filter(
    (item) => item.after_status === "warning" || item.after_status === "pending",
  ),
);

const activeJobs = computed(() =>
  props.jobs.filter((job) => isPlanningJobActive(job)),
);

const failedJobs = computed(() => props.jobs.filter((job) => job.status === "failed"));

const retryableFailedJobs = computed(() =>
  failedJobs.value.filter((job) => canRetry(job)),
);

const visiblePrecheckItems = computed(() =>
  (
    precheckDeltaItems.value.length ? precheckDeltaItems.value : precheckAttentionItems.value
  ).slice(0, 4),
);

const changedDayNumbers = computed(() =>
  uniqueSorted(changedReplanDays.value.map((item) => item.day_number)),
);

const precheckAffectedDayNumbers = computed(() =>
  props.workspace ? collectPrecheckAffectedDays(props.workspace) : [],
);

const needsPrecheckRefresh = computed(() => {
  if (!props.workspace || props.workspace.status === "draft") return false;
  if (!latestPrecheck.value) return true;
  return precheckAttentionItems.value.length > 0;
});

function uniqueSorted(dayNumbers: number[]) {
  return sortUniqueNumbers(dayNumbers);
}

function canRetry(job: PlanningJobSummary) {
  return canRetryPlanningJob(job);
}

function focusDays(dayNumbers: number[]) {
  const normalized = uniqueSorted(dayNumbers);
  if (!normalized.length) return;
  emit("focus-days", normalized);
}

function retryJob(job: PlanningJobSummary) {
  emit("retry-job", job);
}

function formatDateTime(value?: string | null) {
  return formatDateTimeZhCn(value);
}

function formatDayLabel(dayNumber: number) {
  return `第 ${dayNumber} 天`;
}

function isHighlightedDay(dayNumber: number) {
  return props.highlightedReplanDays.includes(dayNumber);
}

function formatReplanModeLabel(mode?: "replace" | "fill_gaps") {
  return mode === "fill_gaps" ? "补齐缺口" : "重排内容";
}

function summarizeDayChanges(item: ReplanDaySummary) {
  if (item.changes?.length) {
    return item.changes
      .slice(0, 2)
      .map((change) => `${change.label}：${change.after || "已更新"}`)
      .join("；");
  }
  if (item.highlights.length) {
    return item.highlights.slice(0, 2).join("；");
  }
  return "该日日程已有更新。";
}

function changeLabel(item: PrecheckSummaryItem) {
  if (item.before_status !== "ok" && item.after_status === "ok") return "已恢复";
  if (item.before_status === "ok" && item.after_status === "warning") return "新增风险";
  if (item.before_status === "pending" && item.after_status === "warning") return "仍需处理";
  if (item.before_status !== item.after_status) return "状态变化";
  return "结果未变";
}

function jobKindLabel(kind: PlanningJobSummary["kind"]) {
  return formatPlanningJobKind(kind);
}

function jobStatusClass(status: PlanningJobSummary["status"]) {
  return resolvePlanningJobStatusBadgeClass(status);
}

function jobStatusLabel(status: PlanningJobSummary["status"]) {
  return formatPlanningJobStatus(status);
}
</script>

<template>
  <section class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="font-medium text-ink">最近发生了什么</div>
        <div class="mt-1 text-xs text-slate-500">
          汇总最近一次重规划、预检变化和后台任务状态，支持直接定位或处理。
        </div>
      </div>
      <div class="text-xs text-slate-500">
        {{ props.workspace ? `工作区 v${props.workspace.version}` : "尚未保存工作区" }}
      </div>
    </div>

    <div class="mt-4 grid gap-3 md:grid-cols-4">
      <div class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3">
        <div class="text-[11px] uppercase tracking-[0.14em] text-slate-400">变更天数</div>
        <div class="mt-2 text-xl font-semibold text-ink">{{ changedReplanDays.length }}</div>
        <div class="mt-1 text-xs text-slate-500">最近一次重规划覆盖的变更日期数</div>
      </div>

      <div class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3">
        <div class="text-[11px] uppercase tracking-[0.14em] text-slate-400">预检关注项</div>
        <div class="mt-2 text-xl font-semibold text-ink">{{ precheckAttentionItems.length }}</div>
        <div class="mt-1 text-xs text-slate-500">最近预检仍需关注的项目</div>
      </div>

      <div class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3">
        <div class="text-[11px] uppercase tracking-[0.14em] text-slate-400">运行中任务</div>
        <div class="mt-2 text-xl font-semibold text-ink">{{ activeJobs.length }}</div>
        <div class="mt-1 text-xs text-slate-500">后台仍在处理的工作区任务</div>
      </div>

      <div class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-3">
        <div class="text-[11px] uppercase tracking-[0.14em] text-slate-400">失败记录</div>
        <div class="mt-2 text-xl font-semibold text-ink">{{ failedJobs.length }}</div>
        <div class="mt-1 text-xs text-slate-500">最近失败且可能需要重试的后台任务</div>
      </div>
    </div>

    <div
      v-if="!latestReplan && !latestPrecheck && !activeJobs.length && !failedJobs.length"
      class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-xs text-slate-500"
    >
      当前还没有足够的工作区变更记录。保存、重规划或刷新预检后，这里会自动汇总影响。
    </div>

    <div v-else class="mt-4 grid gap-4 xl:grid-cols-[1.15fr_0.95fr]">
      <article
        v-if="latestReplan"
        class="rounded-[20px] border border-[#dfe8f1] bg-white px-4 py-4"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="font-medium text-ink">最近一次重规划</div>
            <div class="mt-1 text-xs text-slate-500">{{ latestReplan.title }}</div>
          </div>
          <div class="text-xs text-slate-500">{{ formatDateTime(latestReplan.created_at) }}</div>
        </div>

        <div class="mt-3 flex flex-wrap gap-2 text-xs">
          <span class="rounded-full bg-[#eef4f9] px-3 py-1 text-[#35516b]">
            {{ formatReplanModeLabel(latestReplan.repair_mode) }}
          </span>
          <span class="rounded-full bg-[#eef4f9] px-3 py-1 text-[#35516b]">
            {{ latestReplan.target_days.length }} 天纳入处理
          </span>
          <button
            v-if="changedDayNumbers.length"
            type="button"
            class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-[#35516b] transition hover:bg-[#eef4f9]"
            @click="focusDays(changedDayNumbers)"
          >
            查看变更日期
          </button>
        </div>

        <div class="mt-4 space-y-3">
          <div
            v-for="item in changedReplanDays.slice(0, 4)"
            :key="item.day_number"
            class="rounded-[16px] border px-3 py-3"
            :class="
              isHighlightedDay(item.day_number)
                ? 'border-amber-200 bg-amber-50/60'
                : 'border-[#dfe8f1] bg-[#f8fbfd]'
            "
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="font-medium text-ink">{{ formatDayLabel(item.day_number) }}</div>
              <div class="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-[11px] text-[#35516b] transition hover:bg-[#eef4f9]"
                  @click="focusDays([item.day_number])"
                >
                  定位这一天
                </button>
                <span
                  v-if="isHighlightedDay(item.day_number)"
                  class="rounded-full bg-white px-2.5 py-1 text-[11px] text-amber-700"
                >
                  当前高亮
                </span>
              </div>
            </div>
            <div class="mt-2 text-xs leading-5 text-slate-600">
              {{ summarizeDayChanges(item) }}
            </div>
          </div>
        </div>
      </article>

      <div class="space-y-4">
        <article
          v-if="latestPrecheck || needsPrecheckRefresh"
          class="rounded-[20px] border border-[#dfe8f1] bg-white px-4 py-4"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="font-medium text-ink">最近一次预检变化</div>
              <div class="mt-1 text-xs text-slate-500">
                {{ latestPrecheck?.title || "当前还没有可用的预检结果" }}
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <div v-if="latestPrecheck" class="text-xs text-slate-500">
                {{ formatDateTime(latestPrecheck.created_at) }}
              </div>
              <button
                v-if="needsPrecheckRefresh"
                type="button"
                class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9] disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="props.prechecking"
                @click="emit('refresh-precheck')"
              >
                {{ props.prechecking ? "刷新中..." : "刷新预检" }}
              </button>
            </div>
          </div>

          <div class="mt-3 flex flex-wrap gap-2 text-xs">
            <button
              v-if="precheckAffectedDayNumbers.length"
              type="button"
              class="rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-[#35516b] transition hover:bg-[#eef4f9]"
              @click="focusDays(precheckAffectedDayNumbers)"
            >
              查看影响日期
            </button>
          </div>

          <div v-if="visiblePrecheckItems.length" class="mt-4 space-y-3">
            <div
              v-for="item in visiblePrecheckItems"
              :key="item.key"
              class="rounded-[16px] border border-[#dfe8f1] bg-[#f8fbfd] px-3 py-3"
            >
              <div class="flex flex-wrap items-center gap-2">
                <div class="font-medium text-ink">{{ item.title }}</div>
                <span class="rounded-full px-2.5 py-1 text-[11px]" :class="resolvePrecheckStatusBadgeClass(item.after_status)">
                  {{ formatPrecheckStatusLabel(item.after_status) }}
                </span>
                <span class="rounded-full bg-white px-2.5 py-1 text-[11px] text-slate-500">
                  {{ changeLabel(item) }}
                </span>
              </div>
              <div class="mt-2 text-xs leading-5 text-slate-600">{{ item.after_summary }}</div>
              <div v-if="item.after_days.length" class="mt-2 flex flex-wrap gap-2">
                <button
                  v-for="dayNumber in item.after_days.slice(0, 4)"
                  :key="`${item.key}-${dayNumber}`"
                  type="button"
                  class="rounded-full border border-[#d7e2ec] bg-white px-2.5 py-1 text-[11px] text-slate-600 transition hover:bg-[#eef4f9]"
                  @click="focusDays([dayNumber])"
                >
                  {{ formatDayLabel(dayNumber) }}
                </button>
              </div>
            </div>
          </div>

          <div
            v-else
            class="mt-4 rounded-[16px] border border-[#dfe8f1] bg-[#f8fbfd] px-3 py-3 text-xs text-slate-500"
          >
            {{
              latestPrecheck
                ? "本次预检没有识别出新的状态变化。"
                : "建议先运行一次预检，再决定是否导出或继续调整行程。"
            }}
          </div>
        </article>

        <article
          v-if="activeJobs.length || failedJobs.length"
          class="rounded-[20px] border border-[#dfe8f1] bg-white px-4 py-4"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="font-medium text-ink">后台任务状态</div>
            <div v-if="retryableFailedJobs.length" class="text-xs text-slate-500">
              可重试 {{ retryableFailedJobs.length }} 项
            </div>
          </div>

          <div v-if="activeJobs.length" class="mt-3 space-y-2">
            <div
              v-for="job in activeJobs.slice(0, 3)"
              :key="job.id"
              class="rounded-[16px] border border-sky-100 bg-sky-50/70 px-3 py-3"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="font-medium text-ink">{{ jobKindLabel(job.kind) }}</div>
                <span class="rounded-full px-2.5 py-1 text-[11px]" :class="jobStatusClass(job.status)">
                  {{ jobStatusLabel(job.status) }}
                </span>
              </div>
              <div class="mt-1 text-xs text-slate-600">
                创建于 {{ formatDateTime(job.created_at) }}
              </div>
            </div>
          </div>

          <div v-if="failedJobs.length" class="mt-3 space-y-2">
            <div
              v-for="job in failedJobs.slice(0, 2)"
              :key="job.id"
              class="rounded-[16px] border border-rose-100 bg-rose-50/70 px-3 py-3"
            >
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <div class="font-medium text-ink">{{ jobKindLabel(job.kind) }}</div>
                    <span class="rounded-full px-2.5 py-1 text-[11px]" :class="jobStatusClass(job.status)">
                      {{ jobStatusLabel(job.status) }}
                    </span>
                  </div>
                  <div class="mt-1 text-xs text-slate-600">
                    {{ job.error_message || "任务执行失败，可重新发起。" }}
                  </div>
                </div>
                <button
                  v-if="canRetry(job)"
                  type="button"
                  class="rounded-full border border-[#16324d] bg-white px-3 py-1 text-xs text-[#16324d] transition hover:bg-[#eef4f9] disabled:cursor-not-allowed disabled:opacity-60"
                  :disabled="props.retryingJobId === job.id"
                  @click="retryJob(job)"
                >
                  {{ props.retryingJobId === job.id ? "重试中..." : "重试" }}
                </button>
              </div>
            </div>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>
