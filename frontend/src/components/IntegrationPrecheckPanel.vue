<script setup lang="ts">
import type { IntegrationStatus } from "../types/planning";

defineProps<{
  integrationStatus: IntegrationStatus;
  integrationLoading: boolean;
  warnings: string[];
}>();

const emit = defineEmits<{
  (event: "refresh"): void;
}>();
</script>

<template>
  <article class="rounded-[36px] border border-[#d8e4ed] bg-white/82 p-6 shadow-card">
    <div class="flex items-center justify-between gap-3">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Developer</div>
        <h3 class="mt-2 text-xl font-semibold text-ink">集成预检查</h3>
      </div>
      <button
        type="button"
        class="rounded-full border border-slate-200 px-4 py-2 text-sm text-slate-600"
        @click="emit('refresh')"
      >
        {{ integrationLoading ? "检查中..." : "刷新" }}
      </button>
    </div>

    <div class="mt-5 grid gap-3 sm:grid-cols-2">
      <div class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">MCP</div>
        <div class="mt-2 font-medium text-ink">
          {{ integrationStatus.mcp_connected ? "已连接" : "未连接" }}
        </div>
      </div>
      <div class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">LLM</div>
        <div class="mt-2 font-medium text-ink">
          {{
            integrationStatus.llm_reachable
              ? "可用"
              : integrationStatus.llm_enabled
                ? "未连通"
                : "未配置"
          }}
        </div>
      </div>
      <div class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">地图</div>
        <div class="mt-2 font-medium text-ink">
          {{ integrationStatus.map_js_key_configured ? "已配置 JS Key" : "缺少 JS Key" }}
        </div>
      </div>
      <div class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600">
        <div class="text-xs text-slate-500">Mock</div>
        <div class="mt-2 font-medium text-ink">
          {{ integrationStatus.mock_enabled ? "已开启" : "已关闭" }}
        </div>
      </div>
    </div>

    <div
      v-if="warnings.length"
      class="mt-4 rounded-[22px] border border-amber-200 bg-amber-50 px-4 py-4 text-xs leading-6 text-amber-800"
    >
      <div v-for="warning in warnings" :key="warning">
        {{ warning }}
      </div>
    </div>
  </article>
</template>