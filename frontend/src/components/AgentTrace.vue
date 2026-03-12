<script setup lang="ts">
import type { PlanningResponse } from '../types/planning'

defineProps<{
  result: PlanningResponse
}>()
</script>

<template>
  <section class="rounded-4xl border border-white/60 bg-white/80 p-5">
    <div class="flex items-center justify-between">
      <div>
        <p class="text-xs uppercase tracking-[0.25em] text-lagoon/60">Agent Trace</p>
        <h3 class="mt-1 font-display text-xl text-ink">工具调用轨迹</h3>
      </div>
      <div class="text-sm text-slate-500">{{ result.tool_trace.length }} 次调用</div>
    </div>

    <div class="mt-4 space-y-3">
      <article
        v-for="item in result.tool_trace"
        :key="`${item.tool_name}-${JSON.stringify(item.arguments)}`"
        class="rounded-3xl bg-mist px-4 py-4"
      >
        <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div class="font-medium text-slate-800">{{ item.tool_name }}</div>
            <pre class="mt-2 overflow-auto rounded-2xl bg-slate-900 px-3 py-2 text-xs text-slate-100">{{ JSON.stringify(item.arguments, null, 2) }}</pre>
          </div>
          <span
            class="rounded-full px-3 py-1 text-xs font-medium"
            :class="item.success ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'"
          >
            {{ item.success ? 'SUCCESS' : 'FAILED' }}
          </span>
        </div>
        <p class="mt-3 text-sm text-slate-600">{{ item.summary }}</p>
      </article>
    </div>
  </section>
</template>
