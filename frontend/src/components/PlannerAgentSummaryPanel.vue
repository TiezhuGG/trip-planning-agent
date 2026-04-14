<script setup lang="ts">
import type { PlanningResponse } from "../types/planning";

defineProps<{
  result: PlanningResponse;
}>();
</script>

<template>
  <div class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7">
    <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">
      Agent Trace
    </div>
    <h2 class="mt-3 text-2xl font-semibold text-ink">Agent 调用轨迹</h2>
    <div class="mt-5 space-y-3">
      <div
        v-for="item in result.agent_trace"
        :key="item.agent_name"
        class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4 text-sm text-slate-600"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="font-medium text-ink">
              {{ item.agent_name }}
            </div>
            <div class="mt-2">{{ item.summary }}</div>
          </div>
          <span
            class="rounded-full px-3 py-1 text-xs"
            :class="
              item.success
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-rose-100 text-rose-700'
            "
          >
            {{ item.success ? "SUCCESS" : "FAILED" }}
          </span>
        </div>
        <div class="mt-3 flex flex-wrap gap-2">
          <span class="rounded-full bg-white px-3 py-1 text-xs shadow-sm">
            {{ item.used_llm ? "LLM" : "RULE" }}
          </span>
          <span
            v-for="tool in item.used_tools"
            :key="tool"
            class="rounded-full bg-white px-3 py-1 text-xs shadow-sm"
          >
            {{ tool }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
