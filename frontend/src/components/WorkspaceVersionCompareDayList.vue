<script setup lang="ts">
import type { CompareDayDiffItem } from "./workspaceVersionCompareTypes";

defineProps<{
  items: CompareDayDiffItem[];
  extendedHighlightsByDay: Record<number, string[]>;
}>();

const emit = defineEmits<{
  (event: "focus-day", dayNumber: number): void;
}>();
</script>

<template>
  <article v-for="day in items" :key="day.dayNumber" class="rounded-3xl border border-[#eef4f9] bg-[#fbfdff] p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <div class="text-sm font-semibold text-ink">{{ `D${day.dayNumber}` }}</div>
        <span class="rounded-full border px-2 py-1 text-[11px]" :class="day.changeDetailKind === 'added' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : day.changeDetailKind === 'removed' ? 'border-rose-200 bg-rose-50 text-rose-700' : day.changeDetailKind === 'route' ? 'border-sky-200 bg-sky-50 text-sky-700' : day.changeDetailKind === 'location' ? 'border-slate-300 bg-slate-100 text-slate-700' : 'border-amber-200 bg-amber-50 text-amber-700'">
          {{ day.changeLabel }}
        </span>
        <span class="rounded-full border border-violet-200 bg-violet-50 px-2 py-1 text-[11px] text-violet-700">{{ `强度 ${day.impactScore}` }}</span>
      </div>
      <button type="button" class="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs text-sky-700" @click="emit('focus-day', day.dayNumber)">聚焦这一天</button>
    </div>

    <div class="mt-3 rounded-2xl border px-3 py-3 text-sm" :class="day.changeDetailKind === 'added' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : day.changeDetailKind === 'removed' ? 'border-rose-200 bg-rose-50 text-rose-800' : day.changeDetailKind === 'route' ? 'border-sky-200 bg-sky-50 text-sky-800' : day.changeDetailKind === 'location' ? 'border-slate-300 bg-slate-100 text-slate-800' : 'border-amber-200 bg-amber-50 text-amber-800'">
      {{ day.changeSummary }}
    </div>

    <div class="mt-2 grid gap-2 md:grid-cols-4">
      <div class="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        <div class="font-semibold">时间</div>
        <div class="mt-1">{{ day.changeSignals.time }}</div>
      </div>
      <div class="rounded-2xl border border-slate-300 bg-slate-100 px-3 py-2 text-xs text-slate-800">
        <div class="font-semibold">地点/住宿</div>
        <div class="mt-1">{{ day.changeSignals.location }}</div>
      </div>
      <div class="rounded-2xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
        <div class="font-semibold">路线</div>
        <div class="mt-1">{{ day.changeSignals.route }}</div>
      </div>
      <div class="rounded-2xl border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-800">
        <div class="font-semibold">结构</div>
        <div class="mt-1">{{ day.changeSignals.collection + day.changeSignals.meta }}</div>
      </div>
    </div>

    <div class="mt-3 grid gap-3 lg:grid-cols-2">
      <article v-for="field in day.fields" :key="`${day.dayNumber}-${field.label}`" class="rounded-2xl border border-[#e6eef5] bg-white p-3">
        <div class="text-xs font-semibold text-slate-400">{{ field.label }}</div>
        <div class="mt-2 grid gap-2 text-sm">
          <div class="rounded-2xl border border-sky-100 bg-sky-50 px-3 py-2">
            <div class="text-[11px] text-sky-600">当前</div>
            <div class="mt-1 text-sky-900">{{ field.current }}</div>
          </div>
          <div class="rounded-2xl border border-amber-100 bg-amber-50 px-3 py-2">
            <div class="text-[11px] text-amber-700">对比版本</div>
            <div class="mt-1 text-amber-900">{{ field.target }}</div>
          </div>
        </div>
      </article>
    </div>

    <div v-if="day.highlights.length" class="mt-3 rounded-2xl border border-[#d7e2ec] bg-white px-3 py-3">
      <div class="text-xs font-semibold text-slate-400">快速摘要</div>
      <ul class="mt-2 grid gap-2 text-sm text-slate-600">
        <li v-for="highlight in day.highlights" :key="highlight">{{ highlight }}</li>
      </ul>
    </div>

    <div v-if="extendedHighlightsByDay[day.dayNumber]?.length" class="mt-3 rounded-2xl border border-[#d7e2ec] bg-[#f8fbfd] px-3 py-3">
      <div class="text-xs font-semibold text-slate-400">变更细节</div>
      <ul class="mt-2 grid gap-2 text-sm text-slate-600">
        <li v-for="highlight in extendedHighlightsByDay[day.dayNumber]" :key="`${day.dayNumber}-${highlight}`">{{ highlight }}</li>
      </ul>
    </div>

    <div v-if="day.timelineEntries.length" class="mt-3 rounded-2xl border border-[#d7e2ec] bg-white px-3 py-3">
      <div class="text-xs font-semibold text-slate-400">时间线差异</div>
      <div class="mt-2 grid gap-2">
        <article v-for="entry in day.timelineEntries" :key="entry.key" class="rounded-2xl border border-[#eef4f9] bg-[#fbfdff] p-3">
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="rounded-full border px-2 py-1" :class="entry.kind === 'activity' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'">
              {{ entry.kind === "activity" ? "活动" : "餐饮" }}
            </span>
            <span class="font-semibold text-ink">{{ entry.label }}</span>
          </div>
          <div class="mt-2 grid gap-2 text-sm">
            <div class="rounded-2xl border border-sky-100 bg-sky-50 px-3 py-2">
              <div class="text-[11px] text-sky-600">当前</div>
              <div class="mt-1 text-sky-900">{{ entry.current }}</div>
            </div>
            <div class="rounded-2xl border border-amber-100 bg-amber-50 px-3 py-2">
              <div class="text-[11px] text-amber-700">对比版本</div>
              <div class="mt-1 text-amber-900">{{ entry.target }}</div>
            </div>
          </div>
        </article>
      </div>
    </div>
  </article>
</template>
