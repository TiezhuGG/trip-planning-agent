<script setup lang="ts">
import type {
  CompareCategoryFilter,
  CompareChangeFilter,
  CompareImpactFilter,
  CompareSignalFocus,
  CompareSortMode,
} from "./workspaceVersionCompareTypes";

defineProps<{
  compareCategoryFilter: CompareCategoryFilter;
  compareChangeFilter: CompareChangeFilter;
  compareSortMode: CompareSortMode;
  compareImpactFilter: CompareImpactFilter;
  compareSignalFocus: CompareSignalFocus;
  compareHighImpactThreshold: number;
  compareRecommendedHighImpactThreshold: number;
  compareManualHighImpactThreshold: number | null;
  compareRouteDiffDayCount: number;
  compareStayDiffDayCount: number;
  compareTimelineDiffDayCount: number;
}>();

const emit = defineEmits<{
  (event: "update:compare-category-filter", value: CompareCategoryFilter): void;
  (event: "update:compare-change-filter", value: CompareChangeFilter): void;
  (event: "update:compare-sort-mode", value: CompareSortMode): void;
  (event: "update:compare-impact-filter", value: CompareImpactFilter): void;
  (event: "update:compare-signal-focus", value: CompareSignalFocus): void;
  (event: "update:compare-manual-high-impact-threshold", value: number | null): void;
  (event: "focus-route-diffs"): void;
  (event: "focus-stay-diffs"): void;
  (event: "focus-timeline-diffs"): void;
}>();
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap gap-2 text-xs">
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareCategoryFilter === 'all' ? 'border border-[#d7e2ec] bg-[#eef4f9] text-[#1f3448]' : 'border border-[#d7e2ec] bg-white text-[#35516b]'" @click="emit('update:compare-category-filter', 'all')">全部</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareCategoryFilter === 'activities' ? 'border border-amber-200 bg-amber-100 text-amber-800' : 'border border-amber-200 bg-amber-50 text-amber-700'" @click="emit('update:compare-category-filter', 'activities')">活动</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareCategoryFilter === 'meals' ? 'border border-emerald-200 bg-emerald-100 text-emerald-800' : 'border border-emerald-200 bg-emerald-50 text-emerald-700'" @click="emit('update:compare-category-filter', 'meals')">餐饮</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareCategoryFilter === 'stay' ? 'border border-slate-300 bg-slate-200 text-slate-800' : 'border border-slate-200 bg-slate-100 text-slate-700'" @click="emit('update:compare-category-filter', 'stay')">住宿</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareCategoryFilter === 'route' ? 'border border-sky-200 bg-sky-100 text-sky-800' : 'border border-sky-200 bg-sky-50 text-sky-700'" @click="emit('update:compare-category-filter', 'route')">路线</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareChangeFilter === 'all' ? 'border border-[#d7e2ec] bg-[#eef4f9] text-[#1f3448]' : 'border border-[#d7e2ec] bg-white text-[#35516b]'" @click="emit('update:compare-change-filter', 'all')">全部变更</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareChangeFilter === 'added' ? 'border border-emerald-200 bg-emerald-100 text-emerald-800' : 'border border-emerald-200 bg-emerald-50 text-emerald-700'" @click="emit('update:compare-change-filter', 'added')">整天新增</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareChangeFilter === 'removed' ? 'border border-rose-200 bg-rose-100 text-rose-800' : 'border border-rose-200 bg-rose-50 text-rose-700'" @click="emit('update:compare-change-filter', 'removed')">整天移除</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareChangeFilter === 'changed' ? 'border border-amber-200 bg-amber-100 text-amber-800' : 'border border-amber-200 bg-amber-50 text-amber-700'" @click="emit('update:compare-change-filter', 'changed')">内容变更</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareSortMode === 'day' ? 'border border-[#d7e2ec] bg-[#eef4f9] text-[#1f3448]' : 'border border-[#d7e2ec] bg-white text-[#35516b]'" @click="emit('update:compare-sort-mode', 'day')">按天排序</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareSortMode === 'impact' ? 'border border-violet-200 bg-violet-100 text-violet-800' : 'border border-violet-200 bg-violet-50 text-violet-700'" @click="emit('update:compare-sort-mode', 'impact')">按强度排序</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareImpactFilter === 'all' ? 'border border-[#d7e2ec] bg-[#eef4f9] text-[#1f3448]' : 'border border-[#d7e2ec] bg-white text-[#35516b]'" @click="emit('update:compare-impact-filter', 'all')">全部强度</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareImpactFilter === 'high' ? 'border border-rose-200 bg-rose-100 text-rose-800' : 'border border-rose-200 bg-rose-50 text-rose-700'" @click="emit('update:compare-impact-filter', 'high')">仅看高强度</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareSignalFocus === 'all' ? 'border border-[#d7e2ec] bg-[#eef4f9] text-[#1f3448]' : 'border border-[#d7e2ec] bg-white text-[#35516b]'" @click="emit('update:compare-signal-focus', 'all')">全部信号</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareSignalFocus === 'time' ? 'border border-amber-200 bg-amber-100 text-amber-800' : 'border border-amber-200 bg-amber-50 text-amber-700'" @click="emit('update:compare-signal-focus', 'time')">时间信号</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareSignalFocus === 'location' ? 'border border-slate-300 bg-slate-200 text-slate-800' : 'border border-slate-200 bg-slate-100 text-slate-700'" @click="emit('update:compare-signal-focus', 'location')">地点信号</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareSignalFocus === 'route' ? 'border border-sky-200 bg-sky-100 text-sky-800' : 'border border-sky-200 bg-sky-50 text-sky-700'" @click="emit('update:compare-signal-focus', 'route')">路线信号</button>
      <button type="button" class="rounded-full px-3 py-1.5" :class="compareSignalFocus === 'structure' ? 'border border-violet-200 bg-violet-100 text-violet-800' : 'border border-violet-200 bg-violet-50 text-violet-700'" @click="emit('update:compare-signal-focus', 'structure')">结构信号</button>
    </div>

    <div class="flex flex-wrap items-center gap-3 rounded-2xl border border-[#eef4f9] bg-[#f8fbfd] px-3 py-2 text-xs text-slate-600">
      <span>{{ `高强度阈值 ${compareHighImpactThreshold}` }}</span>
      <span>{{ `推荐值 ${compareRecommendedHighImpactThreshold}` }}</span>
      <label class="flex items-center gap-2">
        <span>手动阈值</span>
        <input
          :value="compareManualHighImpactThreshold ?? ''"
          type="number"
          min="1"
          class="w-20 rounded-full border border-[#d7e2ec] bg-white px-3 py-1 text-[#35516b] outline-none"
          placeholder="自动"
          @input="emit('update:compare-manual-high-impact-threshold', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : null)"
        />
      </label>
      <button
        v-if="compareManualHighImpactThreshold !== null"
        type="button"
        class="rounded-full border border-slate-200 bg-white px-3 py-1 text-slate-700"
        @click="emit('update:compare-manual-high-impact-threshold', null)"
      >
        恢复自动
      </button>
    </div>

    <div class="flex flex-wrap gap-2 text-xs">
      <button
        v-if="compareRouteDiffDayCount > 0"
        type="button"
        class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-sky-700"
        @click="emit('focus-route-diffs')"
      >
        {{ `只看路线差异 ${compareRouteDiffDayCount} 天` }}
      </button>
      <button
        v-if="compareStayDiffDayCount > 0"
        type="button"
        class="rounded-full border border-slate-200 bg-slate-100 px-3 py-1.5 text-slate-700"
        @click="emit('focus-stay-diffs')"
      >
        {{ `只看住宿差异 ${compareStayDiffDayCount} 天` }}
      </button>
      <button
        v-if="compareTimelineDiffDayCount > 0"
        type="button"
        class="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-amber-700"
        @click="emit('focus-timeline-diffs')"
      >
        {{ `只看时间线差异 ${compareTimelineDiffDayCount} 天` }}
      </button>
    </div>
  </div>
</template>
