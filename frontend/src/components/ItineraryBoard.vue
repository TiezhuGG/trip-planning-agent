<script setup lang="ts">
import type { PlanningResponse } from '../types/planning'

defineProps<{
  result: PlanningResponse
}>()
</script>

<template>
  <section class="space-y-4">
    <div
      v-for="day in result.plan.days"
      :key="day.day_number"
      class="rounded-4xl border border-white/60 bg-white/85 p-5"
    >
      <div class="flex flex-col gap-3 border-b border-slate-200/80 pb-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p class="text-xs uppercase tracking-[0.25em] text-lagoon/60">Day {{ day.day_number }}</p>
          <h3 class="mt-1 font-display text-2xl text-ink">{{ day.theme }}</h3>
          <p class="mt-2 text-sm text-slate-600">{{ day.date }} · {{ day.overview }}</p>
        </div>
        <div class="rounded-3xl bg-sand/80 px-4 py-3 text-sm text-slate-700">
          <div>住宿片区：{{ day.hotel_area }}</div>
          <div class="mt-1">活动数：{{ day.activities.length }}</div>
        </div>
      </div>

      <div class="mt-5 grid gap-5 xl:grid-cols-[1.7fr_1fr]">
        <div class="space-y-4">
          <article
            v-for="activity in day.activities"
            :key="`${day.day_number}-${activity.start_time}-${activity.title}`"
            class="rounded-3xl bg-mist px-4 py-4"
          >
            <div class="flex items-start justify-between gap-4">
              <div>
                <div class="text-sm font-medium text-lagoon">
                  {{ activity.start_time }} - {{ activity.end_time }}
                </div>
                <h4 class="mt-2 text-lg font-medium text-slate-800">{{ activity.title }}</h4>
              </div>
              <span class="rounded-full bg-white px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-500">
                {{ activity.category }}
              </span>
            </div>
            <p class="mt-3 text-sm leading-7 text-slate-600">{{ activity.description }}</p>
            <div class="mt-3 grid gap-2 text-sm text-slate-600 md:grid-cols-3">
              <div>地点：{{ activity.location_name }}</div>
              <div>交通：{{ activity.transport_from_previous || '现场决定' }}</div>
              <div>费用：{{ activity.expected_cost || '待定' }}</div>
            </div>
            <div v-if="activity.booking_tip" class="mt-3 text-sm text-coral">
              {{ activity.booking_tip }}
            </div>
          </article>
        </div>

        <div class="space-y-4">
          <div class="rounded-3xl bg-sand/70 px-4 py-4">
            <h4 class="font-display text-lg text-ink">餐饮安排</h4>
            <div class="mt-3 space-y-3">
              <article
                v-for="meal in day.meals"
                :key="`${day.day_number}-${meal.meal_type}-${meal.venue_name}`"
                class="rounded-3xl bg-white/80 px-4 py-3"
              >
                <div class="text-sm uppercase tracking-[0.2em] text-slate-500">{{ meal.meal_type }}</div>
                <div class="mt-1 font-medium text-slate-800">{{ meal.venue_name }}</div>
                <div class="mt-2 text-sm text-slate-600">{{ meal.suggestion }}</div>
                <div class="mt-2 text-sm text-coral">{{ meal.estimated_cost }}</div>
              </article>
            </div>
          </div>

          <div class="rounded-3xl bg-white/80 px-4 py-4">
            <h4 class="font-display text-lg text-ink">交通建议</h4>
            <ul class="mt-3 space-y-2 text-sm leading-6 text-slate-600">
              <li v-for="tip in day.transport_tips" :key="tip" class="rounded-2xl bg-mist px-3 py-2">
                {{ tip }}
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
