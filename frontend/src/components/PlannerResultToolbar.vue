<script setup lang="ts">
import { computed } from "vue";

import { resolveTripWorkspaceExportReadiness } from "../composables/tripWorkspaceExportReadiness";
import type {
  CalendarExportScope,
  PlanningJobSummary,
  TripWorkspace,
} from "../types/planning";

const props = defineProps<{
  workspace: TripWorkspace | null;
  recentPlanningJobs: PlanningJobSummary[];
}>();

const emit = defineEmits<{
  (e: "edit-current-trip"): void;
  (e: "reset"): void;
  (e: "export", format: "png" | "pdf"): void;
  (e: "export-calendar", scope: CalendarExportScope): void;
}>();

const calendarExportReadiness = computed(() =>
  resolveTripWorkspaceExportReadiness(props.workspace, props.recentPlanningJobs),
);

const calendarExportDisabled = computed(
  () => !props.workspace || calendarExportReadiness.value.tone === "progress",
);
</script>

<template>
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap gap-3">
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
        @click="emit('edit-current-trip')"
      >
        修改条件
      </button>
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
        @click="emit('reset')"
      >
        新建规划
      </button>
    </div>
    <div class="flex flex-wrap gap-3">
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
        @click="emit('export', 'png')"
      >
        导出图片
      </button>
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="calendarExportDisabled"
        :title="calendarExportReadiness.tone === 'progress' ? calendarExportReadiness.detail : undefined"
        @click="emit('export-calendar', 'full')"
      >
        {{ calendarExportReadiness.tone === "progress" ? "预检刷新中" : "导出日历" }}
      </button>
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
        @click="emit('export', 'pdf')"
      >
        导出 PDF
      </button>
    </div>
  </div>
</template>
