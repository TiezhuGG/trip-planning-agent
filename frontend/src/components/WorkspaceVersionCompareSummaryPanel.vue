<script setup lang="ts">
import type {
  CompareActiveFilterChip,
  CompareFilterChipKey,
  CompareOverviewItem,
  CompareSummaryItem,
} from "./workspaceVersionCompareTypes";

defineProps<{
  filteredCompareDayCount: number;
  activeFilterChips: CompareActiveFilterChip[];
  overviewItems: CompareOverviewItem[];
  summaryItems: CompareSummaryItem[];
}>();

const emit = defineEmits<{
  (event: "export-text"): void;
  (event: "export-markdown"): void;
  (event: "focus-filtered-days"): void;
  (event: "reset-filters"): void;
  (event: "clear-filter-chip", key: CompareFilterChipKey): void;
}>();
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap gap-2 text-xs">
      <button type="button" class="rounded-full border border-sky-200 bg-white px-3 py-1.5 text-sky-700" @click="emit('export-text')">导出对比文本</button>
      <button type="button" class="rounded-full border border-sky-200 bg-white px-3 py-1.5 text-sky-700" @click="emit('export-markdown')">导出对比 Markdown</button>
      <button v-if="filteredCompareDayCount > 0" type="button" class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-700" @click="emit('focus-filtered-days')">聚焦筛选结果</button>
      <button type="button" class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-slate-700" @click="emit('reset-filters')">重置筛选</button>
      <span v-if="filteredCompareDayCount > 0" class="rounded-full border border-[#d7e2ec] bg-[#f8fbfd] px-3 py-1.5 text-[#35516b]">当前筛选 {{ filteredCompareDayCount }} 天</span>
    </div>

    <div v-if="activeFilterChips.length" class="flex flex-wrap gap-2 text-xs">
      <button
        v-for="chip in activeFilterChips"
        :key="chip.key"
        type="button"
        class="rounded-full border border-[#d7e2ec] bg-[#f8fbfd] px-3 py-1.5 text-[#35516b]"
        @click="emit('clear-filter-chip', chip.key)"
      >
        {{ `${chip.label} ×` }}
      </button>
    </div>

    <div v-if="overviewItems.length" class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
      <article v-for="item in overviewItems" :key="item.key" class="rounded-3xl border p-4" :class="item.toneClass">
        <div class="text-xs font-semibold uppercase tracking-[0.12em] opacity-70">{{ item.label }}</div>
        <div class="mt-3 text-2xl font-semibold">{{ item.value }}</div>
        <div class="mt-2 text-xs leading-5 opacity-80">{{ item.description }}</div>
      </article>
    </div>

    <div v-if="summaryItems.length" class="grid gap-3 md:grid-cols-2">
      <article v-for="item in summaryItems" :key="item.key" class="rounded-3xl border border-[#eef4f9] bg-[#fbfdff] p-4">
        <div class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">{{ item.label }}</div>
        <div class="mt-3 grid gap-3 text-sm">
          <div class="rounded-2xl border border-sky-100 bg-sky-50 px-3 py-2">
            <div class="text-[11px] text-sky-600">当前</div>
            <div class="mt-1 text-sky-900">{{ item.current }}</div>
          </div>
          <div class="rounded-2xl border border-amber-100 bg-amber-50 px-3 py-2">
            <div class="text-[11px] text-amber-700">对比版本</div>
            <div class="mt-1 text-amber-900">{{ item.target }}</div>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>
