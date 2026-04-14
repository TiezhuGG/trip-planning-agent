<script setup lang="ts">
import type { TripWorkspace } from "../types/planning";

defineProps<{
  workspace: TripWorkspace | null;
  notes: string;
  shareLink: string;
  saving: boolean;
  replanning: boolean;
  reservationsCount: number;
}>();

const emit = defineEmits<{
  (event: "update:notes", value: string): void;
  (event: "save-notes"): void;
  (event: "copy-share"): void;
  (event: "replan-trip"): void;
}>();

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

function onNotesInput(event: Event) {
  emit("update:notes", (event.target as HTMLTextAreaElement).value);
}
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">
          Workspace
        </div>
        <h2 class="mt-3 text-2xl font-semibold text-ink">行程工作区</h2>
      </div>
      <div
        class="rounded-full border border-[#d7e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b]"
      >
        {{ workspace ? `v${workspace.version}` : "未保存" }}
      </div>
    </div>

    <div class="grid gap-3 lg:grid-cols-4">
      <div
        class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">状态</div>
        <div class="mt-2 font-medium text-ink">
          {{ workspace ? (workspace.status === "draft" ? "草稿" : "已生成结果") : "未保存" }}
        </div>
      </div>
      <div
        class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">最近更新</div>
        <div class="mt-2 font-medium text-ink">{{ formatDateTime(workspace?.updated_at) }}</div>
      </div>
      <div
        class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">已锁定日程</div>
        <div class="mt-2 font-medium text-ink">
          {{ workspace?.locked_day_numbers.length ? `${workspace.locked_day_numbers.length} 天` : "未锁定" }}
        </div>
      </div>
      <div
        class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">预订锚点</div>
        <div class="mt-2 font-medium text-ink">
          {{ reservationsCount ? `${reservationsCount} 条` : "未添加" }}
        </div>
      </div>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">行程备注</span>
        <textarea
          :value="notes"
          rows="4"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          placeholder="例如：第二天晚餐希望安排更安静的餐厅，第三天尽量减少步行。"
          @input="onNotesInput"
        />
      </label>

      <div class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600">
        <div class="font-medium text-ink">分享与重规划</div>
        <div class="mt-3 rounded-[18px] border border-[#dfe8f1] bg-white px-3 py-3 text-xs text-slate-500">
          {{ shareLink || "保存完成后可生成分享链接" }}
        </div>
        <div class="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!workspace || saving"
            @click="emit('copy-share')"
          >
            复制分享链接
          </button>
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!workspace || saving"
            @click="emit('save-notes')"
          >
            {{ saving ? "保存中..." : "保存备注与锁定状态" }}
          </button>
          <button
            type="button"
            class="rounded-full border border-[#16324d] bg-[#16324d] px-4 py-2 text-sm text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!workspace || replanning || workspace.status === 'draft'"
            @click="emit('replan-trip')"
          >
            {{ replanning ? "重规划中..." : "重排未锁定日程" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
