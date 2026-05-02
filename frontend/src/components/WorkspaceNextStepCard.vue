<script setup lang="ts">
import { computed } from "vue";

import {
  resolveTripWorkspaceNextStep,
  workspaceNextStepClass,
  type WorkspaceNextStepAction,
} from "../composables/tripWorkspaceExportReadiness";
import type {
  CalendarExportScope,
  PlanningJobSummary,
  TripWorkspace,
} from "../types/planning";

const props = defineProps<{
  workspace: TripWorkspace | null;
  jobs: PlanningJobSummary[];
  prechecking: boolean;
  retryingJobId: string;
}>();

const emit = defineEmits<{
  (event: "focus-days", dayNumbers: number[]): void;
  (event: "retry-job", job: PlanningJobSummary): void;
  (event: "refresh-precheck"): void;
  (event: "export-calendar", scope: CalendarExportScope): void;
}>();

const nextStep = computed(() => resolveTripWorkspaceNextStep(props.workspace, props.jobs));

function triggerAction(action: WorkspaceNextStepAction) {
  switch (action.kind) {
    case "focus-days":
      emit("focus-days", action.dayNumbers);
      return;
    case "retry-job":
      emit("retry-job", action.job);
      return;
    case "refresh-precheck":
      emit("refresh-precheck");
      return;
    case "export-calendar":
      emit("export-calendar", action.scope);
  }
}

function actionClass(action: WorkspaceNextStepAction) {
  return action.emphasis === "primary"
    ? "border-[#16324d] bg-[#16324d] text-white hover:bg-[#22486d]"
    : "border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]";
}

function actionDisabled(action: WorkspaceNextStepAction) {
  if (action.kind === "retry-job") {
    return props.retryingJobId === action.job.id;
  }
  if (action.kind === "refresh-precheck") {
    return props.prechecking;
  }
  return false;
}

function actionLabel(action: WorkspaceNextStepAction) {
  if (action.kind === "retry-job" && props.retryingJobId === action.job.id) {
    return "重试中...";
  }
  if (action.kind === "refresh-precheck" && props.prechecking) {
    return "刷新中...";
  }
  return action.label;
}

function actionCountLabel(count: number) {
  return count ? `${count} 个建议动作` : "暂无动作";
}
</script>

<template>
  <section
    v-if="nextStep"
    class="rounded-[24px] border p-4 text-sm"
    :class="workspaceNextStepClass(nextStep.tone)"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="text-xs uppercase tracking-[0.18em] opacity-70">Next Step</div>
        <div class="mt-2 font-medium">{{ nextStep.title }}</div>
        <div class="mt-1 text-sm opacity-90">{{ nextStep.detail }}</div>
      </div>
      <div class="text-xs opacity-70">{{ actionCountLabel(nextStep.actions.length) }}</div>
    </div>

    <div v-if="nextStep.actions.length" class="mt-4 flex flex-wrap gap-3">
      <button
        v-for="action in nextStep.actions"
        :key="`${action.kind}-${action.label}`"
        type="button"
        class="rounded-full border px-4 py-2 text-sm transition disabled:cursor-not-allowed disabled:opacity-60"
        :class="actionClass(action)"
        :disabled="actionDisabled(action)"
        @click="triggerAction(action)"
      >
        {{ actionLabel(action) }}
      </button>
    </div>
  </section>
</template>
