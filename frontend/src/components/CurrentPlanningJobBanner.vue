<script setup lang="ts">
import { computed } from "vue";

import type { PlanningJobSummary } from "../types/planning";
import {
  formatPlanningJobKind,
  humanizePlanningJobProgress,
  isPlanningJobActive,
} from "../utils/planningJobs";
import { formatDateTimeZhCn } from "../utils/workspaceFormatting";

const props = defineProps<{
  jobs: PlanningJobSummary[];
  busyMessage: string;
}>();

const activeJob = computed(() =>
  props.jobs.find((job) => isPlanningJobActive(job)) ?? null,
);

const visible = computed(() => Boolean(props.busyMessage || activeJob.value));

function formatDateTime(value?: string | null) {
  return formatDateTimeZhCn(value);
}

function resolveJobKindLabel(kind?: PlanningJobSummary["kind"] | null) {
  if (!kind) return "后台任务";
  return formatPlanningJobKind(kind);
}
</script>

<template>
  <section
    v-if="visible"
    class="rounded-[28px] border border-sky-100 bg-[linear-gradient(135deg,_rgba(231,244,255,0.94),_rgba(247,251,255,0.96))] px-5 py-4 text-sm text-sky-900 shadow-sm"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="text-xs uppercase tracking-[0.18em] text-sky-600">任务状态</div>
        <div class="mt-2 text-base font-semibold text-slate-900">
          {{ resolveJobKindLabel(activeJob?.kind ?? null) }}
        </div>
        <div class="mt-1 text-sm text-slate-700">
          {{ busyMessage || (activeJob ? humanizePlanningJobProgress(activeJob) : "") }}
        </div>
      </div>
      <div v-if="activeJob" class="rounded-full border border-sky-200 bg-white/80 px-3 py-1 text-xs text-sky-700">
        最近更新：{{ formatDateTime(activeJob.updated_at) }}
      </div>
    </div>
  </section>
</template>
