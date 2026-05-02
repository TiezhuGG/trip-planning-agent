<script setup lang="ts">
import { computed } from "vue";

import type { IntegrationStatus } from "../types/planning";

const props = defineProps<{
  integrationStatus: IntegrationStatus;
  integrationLoading: boolean;
}>();

const emit = defineEmits<{
  (event: "refresh"): void;
}>();

const summaryCards = computed(() => [
  {
    title: "MCP 服务",
    status: props.integrationStatus.mcp_connected
      ? "已连接"
      : props.integrationStatus.mcp_enabled
        ? "未连接"
        : "未启用",
    detail: props.integrationStatus.mcp_enabled
      ? props.integrationStatus.mcp_command || "已启用但未提供启动命令"
      : "当前未启用 MCP 集成",
    tone: props.integrationStatus.mcp_connected
      ? "border-emerald-100 bg-emerald-50"
      : props.integrationStatus.mcp_enabled
        ? "border-amber-200 bg-amber-50"
        : "border-slate-200 bg-slate-50",
  },
  {
    title: "模型连通状态",
    status: props.integrationStatus.llm_reachable
      ? "可用"
      : props.integrationStatus.llm_enabled
        ? "未连通"
        : "未配置",
    detail: props.integrationStatus.llm_model
      ? `模型：${props.integrationStatus.llm_model}`
      : "尚未配置模型名称",
    tone: props.integrationStatus.llm_reachable
      ? "border-emerald-100 bg-emerald-50"
      : props.integrationStatus.llm_enabled
        ? "border-amber-200 bg-amber-50"
        : "border-slate-200 bg-slate-50",
  },
  {
    title: "地图渲染",
    status: props.integrationStatus.map_rendering_enabled
      ? "可渲染"
      : props.integrationStatus.map_js_key_configured
        ? "待启用"
        : "缺少密钥",
    detail: props.integrationStatus.map_js_key_configured
      ? props.integrationStatus.security_js_code_configured
        ? "JS Key 与安全码已配置"
        : "已配置 JS Key，缺少安全码"
      : "尚未配置地图 JS Key",
    tone: props.integrationStatus.map_rendering_enabled
      ? "border-emerald-100 bg-emerald-50"
      : props.integrationStatus.map_js_key_configured
        ? "border-amber-200 bg-amber-50"
        : "border-slate-200 bg-slate-50",
  },
]);

const resolvedToolEntries = computed(() =>
  Object.entries(props.integrationStatus.resolved_tools ?? {}).sort(([left], [right]) =>
    left.localeCompare(right, "zh-CN"),
  ),
);

const hasDiagnostics = computed(
  () =>
    resolvedToolEntries.value.length > 0 ||
    props.integrationStatus.available_tools.length > 0 ||
    props.integrationStatus.missing_tools.length > 0 ||
    props.integrationStatus.warnings.length > 0,
);
</script>

<template>
  <article class="rounded-[36px] border border-[#d8e3ee] bg-white p-6 shadow-card">
    <div class="flex items-center justify-between gap-3">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">
          开发环境
        </div>
        <h3 class="mt-2 text-xl font-semibold text-ink">集成预检</h3>
      </div>
      <button
        type="button"
        class="rounded-full border border-[#c9d6e2] bg-[#f5f8fb] px-4 py-2 text-sm text-[#35516b]"
        @click="emit('refresh')"
      >
        {{ integrationLoading ? "检查中..." : "刷新" }}
      </button>
    </div>

    <div class="mt-5 grid gap-3 sm:grid-cols-3">
      <div
        v-for="card in summaryCards"
        :key="card.title"
        class="rounded-[22px] border px-4 py-4 text-sm text-slate-600"
        :class="card.tone"
      >
        <div class="text-xs text-slate-500">{{ card.title }}</div>
        <div class="mt-2 font-medium text-ink">{{ card.status }}</div>
        <div class="mt-2 text-xs leading-5 text-slate-500">{{ card.detail }}</div>
      </div>
    </div>

    <div v-if="hasDiagnostics" class="mt-4 space-y-4">
      <div
        v-if="integrationStatus.warnings.length"
        class="rounded-[22px] border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-800"
      >
        <div class="font-medium">预检提醒</div>
        <div class="mt-2 space-y-1 text-xs leading-5">
          <div v-for="warning in integrationStatus.warnings" :key="warning">{{ warning }}</div>
        </div>
      </div>

      <div class="grid gap-4 xl:grid-cols-2">
        <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
          <div class="flex items-center justify-between gap-3">
            <div class="font-medium text-ink">模型与服务配置</div>
            <span class="rounded-full bg-white px-3 py-1 text-xs text-slate-500 shadow-sm">
              {{ integrationStatus.llm_enabled ? "已启用" : "未启用" }}
            </span>
          </div>
          <div class="mt-3 space-y-3">
            <div class="rounded-[18px] bg-white px-3 py-3 shadow-sm">
              <div class="text-xs text-slate-500">模型名称</div>
              <div class="mt-1 font-medium text-ink">
                {{ integrationStatus.llm_model || "未配置模型名称" }}
              </div>
            </div>
            <div class="rounded-[18px] bg-white px-3 py-3 shadow-sm">
              <div class="text-xs text-slate-500">服务地址</div>
              <div class="mt-1 break-all text-xs leading-5 text-slate-600">
                {{ integrationStatus.llm_base_url || "未配置服务地址" }}
              </div>
            </div>
            <div class="rounded-[18px] bg-white px-3 py-3 shadow-sm">
              <div class="text-xs text-slate-500">MCP 启动命令</div>
              <div class="mt-1 break-all text-xs leading-5 text-slate-600">
                {{ integrationStatus.mcp_command || "未配置启动命令" }}
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
          <div class="flex items-center justify-between gap-3">
            <div class="font-medium text-ink">工具解析结果</div>
            <span class="rounded-full bg-white px-3 py-1 text-xs text-slate-500 shadow-sm">
              可用 {{ integrationStatus.available_tools.length }}
            </span>
          </div>
          <div
            v-if="resolvedToolEntries.length"
            class="mt-3 space-y-2"
          >
            <div
              v-for="[tool, resolved] in resolvedToolEntries"
              :key="tool"
              class="rounded-[18px] bg-white px-3 py-3 shadow-sm"
            >
              <div class="font-medium text-ink">{{ tool }}</div>
              <div class="mt-1 text-xs leading-5 text-slate-500">
                {{ resolved }}
              </div>
            </div>
          </div>
          <div v-else class="mt-3 rounded-[18px] bg-white px-3 py-3 text-xs text-slate-500 shadow-sm">
            暂无工具解析明细。
          </div>
          <div
            v-if="integrationStatus.missing_tools.length"
            class="mt-3 rounded-[18px] border border-rose-200 bg-rose-50 px-3 py-3 text-xs leading-5 text-rose-700"
          >
            缺失工具：{{ integrationStatus.missing_tools.join("、") }}
          </div>
        </div>
      </div>
    </div>
  </article>
</template>
