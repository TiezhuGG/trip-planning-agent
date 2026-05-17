<script setup lang="ts">
import { computed } from "vue";

import {
  exportReadinessClass,
  hasRunningPrecheckJob,
  isPrecheckSummaryStale,
  resolveTripWorkspaceExportReadiness,
} from "../composables/tripWorkspaceExportReadiness";
import type {
  CalendarExportScope,
  PlanningJobSummary,
  TripWorkspace,
} from "../types/planning";
import { formatDayGapLabel } from "../utils/dayGapLabels";
import { resolveWorkspacePrecheckState } from "../utils/workspacePrecheckState";
import { formatDateTimeZhCn } from "../utils/workspaceFormatting";
import {
  formatWorkspaceStatusLabel,
  resolveWorkspaceStatusTextClass,
} from "../utils/workspaceStatus";

const props = defineProps<{
  workspace: TripWorkspace | null;
  notes: string;
  shareLink: string;
  saving: boolean;
  replanning: boolean;
  reservationsCount: number;
  highlightedReplanDays: number[];
  recentPlanningJobs: PlanningJobSummary[];
}>();

const emit = defineEmits<{
  (event: "update:notes", value: string): void;
  (event: "save-notes"): void;
  (event: "copy-share"): void;
  (event: "revoke-share"): void;
  (event: "regenerate-share"): void;
  (event: "export-calendar", scope: CalendarExportScope): void;
  (event: "replan-trip"): void;
}>();

const exportReadiness = computed(() =>
  resolveTripWorkspaceExportReadiness(props.workspace, props.recentPlanningJobs),
);

const workspaceNoteSuggestions = [
  "优先少走路",
  "晚餐留自由活动",
  "酒店尽量靠近地铁",
  "减少跨城区往返",
];

const noteDraftChanged = computed(
  () => (props.notes ?? "").trim() !== (props.workspace?.manual_notes ?? "").trim(),
);

const precheckStateLabel = computed(() => {
  if (!props.workspace || props.workspace.status === "draft") return "未启用";
  if (hasRunningPrecheckJob(props.workspace.id, props.recentPlanningJobs)) return "刷新中";
  if (!props.workspace.last_precheck_summary) return "待检查";
  if (isPrecheckSummaryStale(props.workspace)) return "已过期";
  if (exportReadiness.value.attentionCount > 0) return "需关注";
  return "稳定";
});

const precheckStateClass = computed(() => {
  if (!props.workspace || props.workspace.status === "draft") {
    return "border-slate-200 bg-slate-50 text-slate-600";
  }
  if (hasRunningPrecheckJob(props.workspace.id, props.recentPlanningJobs)) {
    return "border-sky-100 bg-sky-50 text-sky-700";
  }
  if (!props.workspace.last_precheck_summary || isPrecheckSummaryStale(props.workspace)) {
    return "border-amber-100 bg-amber-50 text-amber-700";
  }
  if (exportReadiness.value.attentionCount > 0) {
    return "border-amber-100 bg-amber-50 text-amber-700";
  }
  return "border-emerald-100 bg-emerald-50 text-emerald-700";
});

const sharedPrecheckState = computed(() =>
  resolveWorkspacePrecheckState(props.workspace, props.recentPlanningJobs),
);

const shareStateLabel = computed(() => {
  if (!props.workspace) return "未保存";
  return props.workspace.share_enabled ? "已开启" : "未开启";
});

const shareStateClass = computed(() => {
  if (!props.workspace) return "text-slate-500";
  return props.workspace.share_enabled ? "text-emerald-700" : "text-amber-700";
});

const calendarExportDisabled = computed(
  () => !props.workspace || props.saving || exportReadiness.value.tone === "progress",
);

const copyShareTitle = computed(() => {
  if (!props.workspace) return "请先保存工作区";
  if (!props.workspace.share_enabled) return "分享当前未开启，请先生成新链接";
  if (props.saving) return "工作区保存中，稍后再复制";
  return "复制当前分享链接";
});

const shareMutationTitle = computed(() => {
  if (!props.workspace) return "请先保存工作区";
  if (props.saving) return "工作区保存中，稍后再试";
  return props.workspace.share_enabled ? "撤销当前分享链接" : "生成新的分享链接";
});

const openShareTitle = computed(() => {
  if (!props.workspace) return "请先保存工作区";
  if (!props.workspace.share_enabled || !props.shareLink) {
    return "请先生成可用的分享链接";
  }
  return "在新窗口预览当前分享页";
});

const exportCalendarTitle = computed(() => {
  if (!props.workspace) return "请先保存工作区";
  if (props.saving) return "工作区保存中，稍后再导出";
  if (exportReadiness.value.tone === "progress") return exportReadiness.value.detail;
  return "导出当前工作区日历";
});

const saveWorkspaceTitle = computed(() => {
  if (!props.workspace) return "请先保存工作区";
  if (props.saving) return "工作区保存中";
  return "保存备注与锁定状态";
});

const replanTitle = computed(() => {
  if (!props.workspace) return "请先保存工作区";
  if (props.workspace.status === "draft") return "先生成行程结果，再开始重规划";
  if (props.replanning) return "重规划任务执行中";
  return "重新编排未锁定日期";
});

function formatDateTime(value?: string | null) {
  return formatDateTimeZhCn(value);
}

function onNotesInput(event: Event) {
  emit("update:notes", (event.target as HTMLTextAreaElement).value);
}

function appendWorkspaceNoteSnippet(snippet: string) {
  const currentNotes = (props.notes ?? "")
    .split(/[\n，。！？!?]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (currentNotes.includes(snippet)) return;
  emit("update:notes", [...currentNotes, snippet].join("，"));
}

function openSharePreview() {
  if (!props.workspace?.share_enabled || !props.shareLink || typeof window === "undefined") return;
  window.open(props.shareLink, "_blank", "noopener,noreferrer");
}

function formatStatusLabel(value?: TripWorkspace["status"]) {
  return formatWorkspaceStatusLabel(value);
}

function resolveStatusClass(value?: TripWorkspace["status"]) {
  return resolveWorkspaceStatusTextClass(value);
}

function formatChangeValue(value?: string | null) {
  return value?.trim() ? value : "未安排";
}

function isHighlightedDay(dayNumber: number) {
  return props.highlightedReplanDays.includes(dayNumber);
}
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Workspace</div>
        <h2 class="mt-3 text-2xl font-semibold text-ink">行程工作区</h2>
      </div>
      <div
        class="rounded-full border border-[#d7e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b]"
      >
        {{ props.workspace ? `v${props.workspace.version}` : "未保存" }}
      </div>
    </div>

    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <div
        class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">状态</div>
        <div class="mt-2 font-medium" :class="resolveStatusClass(props.workspace?.status)">
          {{ formatStatusLabel(props.workspace?.status) }}
        </div>
      </div>

      <div
        class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">最近更新</div>
        <div class="mt-2 font-medium text-ink">
          {{ formatDateTime(props.workspace?.updated_at) }}
        </div>
      </div>

      <div
        class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">已锁定日期</div>
        <div class="mt-2 font-medium text-ink">
          {{
            props.workspace?.locked_day_numbers.length
              ? `${props.workspace.locked_day_numbers.length} 天`
              : "未锁定"
          }}
        </div>
      </div>

      <div
        class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">分享状态</div>
        <div class="mt-2 font-medium" :class="shareStateClass">
          {{ shareStateLabel }}
        </div>
        <div class="mt-2 text-xs text-slate-500">
          {{
            props.workspace?.share_enabled
              ? "当前链接可直接复制或预览使用"
              : "可在保存后生成新的分享链接"
          }}
        </div>
      </div>

      <div
        class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">固定预订</div>
        <div class="mt-2 font-medium text-ink">
          {{ props.reservationsCount ? `${props.reservationsCount} 条` : "未添加" }}
        </div>
      </div>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">行程备注</span>
        <textarea
          :value="props.notes"
          rows="4"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          placeholder="例如：第二天晚餐希望安排更安静的餐厅，第三天尽量减少步行。"
          @input="onNotesInput"
        />
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="item in workspaceNoteSuggestions"
            :key="item"
            type="button"
            class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500 transition hover:bg-[#eef4f9]"
            @click="appendWorkspaceNoteSnippet(item)"
          >
            + {{ item }}
          </button>
        </div>
        <div
          class="mt-2 rounded-[16px] border px-3 py-2 text-xs"
          :class="
            noteDraftChanged
              ? 'border-amber-200 bg-amber-50 text-amber-800'
              : 'border-[#dfe8f1] bg-[#f8fbfd] text-slate-500'
          "
        >
          {{
            noteDraftChanged
              ? "当前备注有未保存修改，保存后会同步到工作区。"
              : "备注内容已与当前工作区同步。"
          }}
        </div>
      </label>

      <div class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600">
        <div class="font-medium text-ink">分享、导出与重规划</div>
        <div class="mt-3 rounded-[18px] border border-[#dfe8f1] bg-white px-3 py-3 text-xs text-slate-500">
          {{ props.shareLink || "保存完成后可生成分享链接" }}
        </div>

        <div class="mt-3 grid gap-3 lg:grid-cols-2">
          <div
            class="rounded-[18px] border px-3 py-3 text-xs leading-5"
            :class="sharedPrecheckState.className"
          >
            <div class="font-medium">预检状态：{{ sharedPrecheckState.label }}</div>
            <div class="mt-1">
              {{
                !props.workspace || props.workspace.status === "draft"
                  ? "生成并保存工作区后，会自动补充出发前预检。"
                  : exportReadiness.detail
              }}
            </div>
          </div>
          <div class="rounded-[18px] border border-[#dfe8f1] bg-white px-3 py-3 text-xs leading-5 text-slate-500">
            <div class="font-medium text-ink">工作区时间点</div>
            <div class="mt-1">创建：{{ formatDateTime(props.workspace?.created_at) }}</div>
            <div class="mt-1">最近保存：{{ formatDateTime(props.workspace?.updated_at) }}</div>
            <div v-if="props.workspace?.last_precheck_summary" class="mt-1">
              最近预检：{{ formatDateTime(props.workspace.last_precheck_summary.created_at) }}
            </div>
          </div>
        </div>

        <div
          v-if="props.workspace"
          class="mt-3 rounded-[18px] border px-3 py-3 text-xs leading-5"
          :class="exportReadinessClass(exportReadiness.tone)"
        >
          <div class="font-medium">{{ exportReadiness.title }}</div>
          <div class="mt-1">{{ exportReadiness.detail }}</div>
        </div>

        <div class="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!props.workspace || !props.workspace.share_enabled || props.saving"
            :title="copyShareTitle"
            @click="emit('copy-share')"
          >
            复制分享链接
          </button>

          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!props.workspace || !props.workspace.share_enabled || !props.shareLink"
            :title="openShareTitle"
            @click="openSharePreview"
          >
            预览分享页
          </button>

          <button
            v-if="props.workspace?.share_enabled"
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!props.workspace || props.saving"
            :title="shareMutationTitle"
            @click="emit('revoke-share')"
          >
            撤销分享
          </button>

          <button
            v-else
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!props.workspace || props.saving"
            :title="shareMutationTitle"
            @click="emit('regenerate-share')"
          >
            生成新链接
          </button>

          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="calendarExportDisabled"
            :title="exportCalendarTitle"
            @click="emit('export-calendar', 'full')"
          >
            {{ exportReadiness.tone === "progress" ? "预检刷新中..." : "导出完整日历" }}
          </button>

          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="calendarExportDisabled"
            :title="exportCalendarTitle"
            @click="emit('export-calendar', 'reservations')"
          >
            仅预订
          </button>

          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="calendarExportDisabled"
            :title="exportCalendarTitle"
            @click="emit('export-calendar', 'itinerary')"
          >
            仅行程
          </button>

          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!props.workspace || props.saving"
            :title="saveWorkspaceTitle"
            @click="emit('save-notes')"
          >
            {{ props.saving ? "保存中..." : "保存备注与锁定状态" }}
          </button>

          <button
            type="button"
            class="rounded-full border border-[#16324d] bg-[#16324d] px-4 py-2 text-sm text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!props.workspace || props.replanning || props.workspace.status === 'draft'"
            :title="replanTitle"
            @click="emit('replan-trip')"
          >
            {{ props.replanning ? "重规划中..." : "重排未锁定日程" }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="props.workspace?.last_replan_summary"
      class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="font-medium text-ink">最近一次重规划</div>
          <div class="mt-1 text-xs text-slate-500">
            {{ props.workspace.last_replan_summary.title }}
          </div>
        </div>
        <div class="text-xs text-slate-500">
          {{ formatDateTime(props.workspace.last_replan_summary.created_at) }}
        </div>
      </div>

      <div class="mt-3 flex flex-wrap gap-2 text-xs">
        <span class="rounded-full bg-white px-3 py-1 text-slate-600">
          {{
            props.workspace.last_replan_summary.repair_mode === "fill_gaps"
              ? "补齐缺口"
              : "重新生成"
          }}
        </span>
        <span class="rounded-full bg-white px-3 py-1 text-slate-600">
          目标 {{ props.workspace.last_replan_summary.target_days.length }} 天
        </span>
        <span
          v-if="props.workspace.last_replan_summary.repair_gap"
          class="rounded-full bg-white px-3 py-1 text-slate-600"
        >
          类型 {{ formatDayGapLabel(props.workspace.last_replan_summary.repair_gap) }}
        </span>
      </div>

      <div class="mt-4 space-y-3">
        <div
          v-for="item in props.workspace.last_replan_summary.items"
          :key="item.day_number"
          class="rounded-[18px] border bg-white px-4 py-3 transition"
          :class="
            isHighlightedDay(item.day_number)
              ? 'border-[#f0c36a] bg-amber-50/60 shadow-[0_0_0_1px_rgba(245,158,11,0.18)]'
              : 'border-[#dfe8f1]'
          "
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="font-medium text-ink">第 {{ item.day_number }} 天</div>
            <span
              v-if="isHighlightedDay(item.day_number)"
              class="rounded-full bg-white px-2.5 py-1 text-[11px] text-amber-700"
            >
              刚刚更新
            </span>
          </div>

          <div v-if="item.changes?.length" class="mt-3 space-y-2">
            <div
              v-for="change in item.changes"
              :key="`${item.day_number}-${change.kind}-${change.label}-${change.after}`"
              class="rounded-[14px] bg-slate-50 px-3 py-3 text-xs text-slate-600"
            >
              <div class="font-medium text-[#35516b]">{{ change.label }}</div>
              <div class="mt-2 grid gap-2 md:grid-cols-2">
                <div class="rounded-[12px] bg-white px-3 py-2">
                  <div class="text-[11px] uppercase tracking-[0.12em] text-slate-400">调整前</div>
                  <div class="mt-1">{{ formatChangeValue(change.before) }}</div>
                </div>
                <div class="rounded-[12px] bg-white px-3 py-2">
                  <div class="text-[11px] uppercase tracking-[0.12em] text-slate-400">调整后</div>
                  <div class="mt-1">{{ formatChangeValue(change.after) }}</div>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="mt-2 flex flex-wrap gap-2">
            <span
              v-for="highlight in item.highlights"
              :key="`${item.day_number}-${highlight}`"
              class="rounded-full bg-[#eef4f9] px-3 py-1 text-xs text-[#35516b]"
            >
              {{ highlight }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
