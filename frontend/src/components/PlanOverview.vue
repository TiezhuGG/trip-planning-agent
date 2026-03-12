<script setup lang="ts">
import type { PlanningResponse } from '../types/planning'

defineProps<{
  result: PlanningResponse
}>()
</script>

<template>
  <section class="space-y-6">
    <div class="rounded-4xl border border-white/60 bg-white/85 p-6 shadow-glow backdrop-blur">
      <div class="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p class="text-xs uppercase tracking-[0.3em] text-lagoon/60">AI Itinerary</p>
          <h2 class="mt-2 font-display text-3xl font-semibold text-ink">
            {{ result.plan.title }}
          </h2>
          <p class="mt-3 max-w-3xl text-sm leading-7 text-slate-600">
            {{ result.plan.summary }}
          </p>
        </div>
        <div class="rounded-3xl bg-sand/80 px-4 py-3 text-sm text-slate-700">
          <div>天气：{{ result.planning_context.weather.temperature_range }}</div>
          <div class="mt-1">预算：{{ result.plan.estimated_budget.total_estimate }}</div>
        </div>
      </div>
    </div>

    <div class="grid gap-4 xl:grid-cols-3">
      <div class="rounded-4xl border border-white/60 bg-white/80 p-5">
        <h3 class="font-display text-lg text-ink">天气与预订提醒</h3>
        <p class="mt-3 text-sm leading-7 text-slate-600">{{ result.plan.weather_summary }}</p>
        <p class="mt-3 text-sm leading-7 text-slate-600">{{ result.plan.best_booking_tip }}</p>
        <ul class="mt-4 space-y-2 text-sm text-slate-600">
          <li v-for="tip in result.planning_context.weather.suggestions" :key="tip" class="rounded-2xl bg-mist px-3 py-2">
            {{ tip }}
          </li>
        </ul>
      </div>

      <div class="rounded-4xl border border-white/60 bg-white/80 p-5">
        <h3 class="font-display text-lg text-ink">住宿建议</h3>
        <div class="mt-4 space-y-3">
          <article
            v-for="stay in result.plan.stay_recommendations"
            :key="`${stay.hotel_name}-${stay.area}`"
            class="rounded-3xl bg-mist px-4 py-3"
          >
            <div class="font-medium text-slate-800">{{ stay.hotel_name }}</div>
            <div class="mt-1 text-sm text-slate-600">{{ stay.area }}</div>
            <div class="mt-2 text-sm text-slate-600">{{ stay.reason }}</div>
            <div class="mt-2 text-sm font-medium text-coral">{{ stay.nightly_budget }}</div>
          </article>
        </div>
      </div>

      <div class="rounded-4xl border border-white/60 bg-white/80 p-5">
        <h3 class="font-display text-lg text-ink">预算与携带清单</h3>
        <div class="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-700">
          <div class="rounded-3xl bg-mist px-4 py-3">
            <div class="text-slate-500">住宿</div>
            <div class="mt-1 font-medium">{{ result.plan.estimated_budget.accommodation }}</div>
          </div>
          <div class="rounded-3xl bg-mist px-4 py-3">
            <div class="text-slate-500">交通</div>
            <div class="mt-1 font-medium">{{ result.plan.estimated_budget.transport }}</div>
          </div>
          <div class="rounded-3xl bg-mist px-4 py-3">
            <div class="text-slate-500">餐饮</div>
            <div class="mt-1 font-medium">{{ result.plan.estimated_budget.food }}</div>
          </div>
          <div class="rounded-3xl bg-mist px-4 py-3">
            <div class="text-slate-500">门票</div>
            <div class="mt-1 font-medium">{{ result.plan.estimated_budget.tickets }}</div>
          </div>
        </div>

        <ul class="mt-4 flex flex-wrap gap-2">
          <li
            v-for="item in result.plan.packing_list"
            :key="item"
            class="rounded-full bg-sand px-3 py-1 text-sm text-slate-700"
          >
            {{ item }}
          </li>
        </ul>
      </div>
    </div>

    <div class="rounded-4xl border border-white/60 bg-white/80 p-5">
      <h3 class="font-display text-lg text-ink">城市提示</h3>
      <ul class="mt-4 grid gap-3 md:grid-cols-3">
        <li
          v-for="tip in result.plan.city_tips"
          :key="tip"
          class="rounded-3xl bg-mist px-4 py-3 text-sm leading-6 text-slate-600"
        >
          {{ tip }}
        </li>
      </ul>
    </div>
  </section>
</template>
