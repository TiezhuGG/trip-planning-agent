<script setup lang="ts">
import type { PlanningResponse } from "../types/planning";

defineProps<{
  result: PlanningResponse;
  budgetLabel: (value: PlanningResponse["request_echo"]["budget_level"]) => string;
  paceLabel: (value: PlanningResponse["request_echo"]["pace"]) => string;
}>();
</script>

<template>
  <article
    class="rounded-[36px] border border-[#16324d] bg-[#16324d] p-6 text-white shadow-[0_30px_90px_rgba(22,50,77,0.14)] sm:p-8"
  >
    <div class="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-white/55">Overview</div>
        <h2 class="mt-3 text-3xl font-semibold sm:text-[38px]">
          {{ result.plan.title }}
        </h2>
        <p class="mt-4 max-w-3xl text-sm leading-7 text-white/78">
          {{ result.plan.summary }}
        </p>
        <div class="mt-6 flex flex-wrap gap-2 text-sm">
          <span class="rounded-full border border-white/16 bg-white/10 px-4 py-2">
            {{ result.request_echo.days }} 天
          </span>
          <span class="rounded-full border border-white/16 bg-white/10 px-4 py-2">
            {{ result.request_echo.destination }}
          </span>
          <span class="rounded-full border border-white/16 bg-white/10 px-4 py-2">
            {{ paceLabel(result.request_echo.pace) }}
          </span>
          <span class="rounded-full border border-white/16 bg-white/10 px-4 py-2">
            {{ budgetLabel(result.request_echo.budget_level) }}
          </span>
        </div>
      </div>
      <div class="grid gap-4 sm:grid-cols-2">
        <div class="rounded-[24px] border border-white/10 bg-white/10 px-4 py-4">
          <div class="text-xs uppercase tracking-[0.18em] text-white/55">
            Budget Total
          </div>
          <div class="mt-3 text-2xl font-semibold">
            {{ result.plan.estimated_budget.total_estimate }}
          </div>
        </div>
        <div class="rounded-[24px] border border-white/10 bg-white/10 px-4 py-4">
          <div class="text-xs uppercase tracking-[0.18em] text-white/55">
            City Tips
          </div>
          <div class="mt-3 text-sm leading-6 text-white/80">
            {{ result.plan.city_tips.join(", ") || "No city tips" }}
          </div>
        </div>
        <div class="rounded-[24px] border border-white/10 bg-white/10 px-4 py-4 sm:col-span-2">
          <div class="text-xs uppercase tracking-[0.18em] text-white/55">
            Packing List
          </div>
          <div class="mt-3 text-sm leading-6 text-white/80">
            {{ result.plan.packing_list.join(", ") || "No packing suggestions" }}
          </div>
        </div>
      </div>
    </div>
  </article>
</template>
