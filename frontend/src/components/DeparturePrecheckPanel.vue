<script setup lang="ts">
import { computed } from "vue";

import type {
  DeparturePrecheckItem,
  DeparturePrecheckSummary,
} from "../composables/useTripWorkspaceInsights";
import {
  formatPrecheckStatusLabel,
  resolvePrecheckStatusBadgeClass,
} from "../utils/precheckSummary";

const props = defineProps<{
  summary: DeparturePrecheckSummary;
  items: DeparturePrecheckItem[];
  refreshing: boolean;
  enabled: boolean;
}>();

const emit = defineEmits<{
  (event: "refresh"): void;
}>();

const headline = computed(() => {
  if (props.summary.warning > 0) {
    return `当前有 ${props.summary.warning} 项需要关注`;
  }
  if (props.summary.pending > 0) {
    return `当前有 ${props.summary.pending} 项待补充`;
  }
  return "当前预检状态稳定";
});

</script>

<template>
  <section
    v-if="summary.total"
    class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600"
  >
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">Precheck</div>
        <div class="mt-1 font-medium text-ink">出发前校验</div>
        <div class="mt-1 text-xs text-slate-500">{{ headline }}</div>
      </div>
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span class="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
          正常 {{ summary.ok }}
        </span>
        <span class="rounded-full bg-amber-50 px-3 py-1 text-amber-700">
          关注 {{ summary.warning }}
        </span>
        <span class="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
          待补充 {{ summary.pending }}
        </span>
        <button
          type="button"
          class="rounded-full border border-slate-200 bg-white px-3 py-1 text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="!enabled || refreshing"
          @click="emit('refresh')"
        >
          {{ refreshing ? "刷新中..." : "刷新校验" }}
        </button>
      </div>
    </div>

    <div class="mt-4 grid gap-3 md:grid-cols-2">
      <article
        v-for="item in items"
        :key="item.key"
        class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="font-medium text-ink">{{ item.title }}</div>
          <span class="rounded-full px-3 py-1 text-xs" :class="resolvePrecheckStatusBadgeClass(item.status)">
            {{ formatPrecheckStatusLabel(item.status) }}
          </span>
        </div>
        <div class="mt-3 text-sm text-slate-700">{{ item.summary }}</div>
        <div class="mt-2 text-xs leading-5 text-slate-500">{{ item.detail }}</div>
      </article>
    </div>
  </section>
</template>
