<script setup lang="ts">
import type { IntegrationStatus, TravelPlan } from "../types/planning";

defineProps<{
  budgetCards: Array<[string, string]>;
  plan: TravelPlan;
  showDevPanels: boolean;
  integrationStatus: IntegrationStatus;
}>();
</script>

<template>
  <aside class="space-y-6">
    <article class="rounded-[36px] border border-[#d8e3ee] bg-white p-6 shadow-card sm:p-7">
      <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Stay & Budget</div>
      <h2 class="mt-3 text-2xl font-semibold text-ink">住宿与预算</h2>
      <div class="mt-5 grid gap-3">
        <div
          v-for="card in budgetCards"
          :key="card[0]"
          class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
        >
          <div class="text-xs text-slate-500">{{ card[0] }}</div>
          <div class="mt-2 text-lg font-semibold text-ink">{{ card[1] }}</div>
        </div>
      </div>
      <div class="mt-5 space-y-3">
        <div
          v-for="stay in plan.stay_recommendations"
          :key="`${stay.area}-${stay.hotel_name}`"
          class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
        >
          <div class="font-medium text-ink">{{ stay.area }}</div>
          <div class="mt-2">{{ stay.hotel_name }}</div>
          <div class="mt-2 text-xs leading-6 text-slate-500">{{ stay.reason }}</div>
          <div class="mt-3 text-xs text-[#2f5a81]">{{ stay.nightly_budget }}</div>
        </div>
      </div>
    </article>

    <article class="rounded-[36px] border border-[#d8e3ee] bg-white p-6 shadow-card sm:p-7">
      <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">City Notes</div>
      <h2 class="mt-3 text-2xl font-semibold text-ink">城市提醒与打包建议</h2>
      <div class="mt-5 space-y-3">
        <div
          v-for="tip in plan.city_tips"
          :key="tip"
          class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm leading-7 text-slate-600"
        >
          {{ tip }}
        </div>
      </div>
      <div class="mt-5 flex flex-wrap gap-2">
        <span
          v-for="item in plan.packing_list"
          :key="item"
          class="rounded-full border border-[#d7e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b]"
        >
          {{ item }}
        </span>
      </div>
    </article>

    <article
      v-if="showDevPanels"
      class="rounded-[36px] border border-[#d8e3ee] bg-white p-6 shadow-card sm:p-7"
    >
      <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Developer</div>
      <h2 class="mt-3 text-2xl font-semibold text-ink">MCP 与地图集成状态</h2>
      <div class="mt-5 rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="font-medium text-ink">MCP 启动命令</div>
        <div class="mt-2 break-all rounded-[18px] bg-white px-3 py-2 text-xs shadow-sm">
          {{ integrationStatus.mcp_command || "未配置" }}
        </div>
      </div>
      <div class="mt-4 rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="font-medium text-ink">LLM 配置</div>
        <div class="mt-3 rounded-[18px] bg-white px-3 py-3 text-xs shadow-sm">
          <div class="font-medium text-ink">
            {{ integrationStatus.llm_model || "未配置模型名" }}
          </div>
          <div class="mt-2 break-all text-slate-600">
            {{ integrationStatus.llm_base_url || "未配置 Base URL" }}
          </div>
        </div>
      </div>
      <div
        v-if="integrationStatus.available_tools.length"
        class="mt-4 rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
      >
        <div class="font-medium text-ink">可用工具</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <span
            v-for="tool in integrationStatus.available_tools"
            :key="tool"
            class="rounded-full bg-white px-3 py-1 text-xs shadow-sm"
          >
            {{ tool }}
          </span>
        </div>
      </div>
    </article>
  </aside>
</template>