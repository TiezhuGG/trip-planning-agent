<script setup lang="ts">
import type { TripPlanningRequest } from "../types/planning";

type PlannerOption<T> = {
  label: string;
  value: T;
};

defineProps<{
  form: TripPlanningRequest;
  interestOptions: string[];
  transportOptions: string[];
  hotelOptions: string[];
  paceOptions: PlannerOption<TripPlanningRequest["pace"]>[];
  budgetOptions: PlannerOption<TripPlanningRequest["budget_level"]>[];
  paceLabel: (value: TripPlanningRequest["pace"]) => string;
  toggleSelection: (list: string[], value: string) => void;
}>();

const startDate = defineModel<string>("startDate", { required: true });
const endDate = defineModel<string>("endDate", { required: true });
const mustVisitText = defineModel<string>("mustVisitText", { required: true });
const diningText = defineModel<string>("diningText", { required: true });
</script>

<template>
  <article class="rounded-[36px] border border-white/70 bg-white/86 p-6 shadow-card sm:p-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Trip Brief</div>
        <h2 class="mt-3 text-2xl font-semibold text-ink sm:text-[30px]">
          先把你的旅行偏好讲清楚
        </h2>
      </div>
      <div class="rounded-full border border-[#d7e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b]">
        {{ form.days }} 天 · {{ paceLabel(form.pace) }}节奏
      </div>
    </div>
    <div class="mt-6 grid gap-4 lg:grid-cols-4">
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">目的地城市</span>
        <input
          v-model="form.destination"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        />
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">出发城市</span>
        <input
          v-model="form.origin"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        />
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">开始日期</span>
        <input
          v-model="startDate"
          type="date"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        />
      </label>
    </div>
    <div class="mt-4 grid gap-4 lg:grid-cols-4">
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">结束日期</span>
        <input
          v-model="endDate"
          type="date"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        />
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">成人</span>
        <input
          v-model.number="form.travelers.adults"
          type="number"
          min="1"
          max="10"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        />
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">儿童</span>
        <input
          v-model.number="form.travelers.children"
          type="number"
          min="0"
          max="6"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        />
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">老人</span>
        <input
          v-model.number="form.travelers.seniors"
          type="number"
          min="0"
          max="4"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        />
      </label>
    </div>
    <div class="mt-6">
      <div class="text-sm font-medium text-slate-600">兴趣偏好</div>
      <div class="mt-3 flex flex-wrap gap-2">
        <button
          v-for="item in interestOptions"
          :key="item"
          type="button"
          class="rounded-full border px-4 py-2 text-sm transition"
          :class="
            form.interests.includes(item)
              ? 'border-[#16324d] bg-[#16324d] text-white'
              : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
          "
          @click="toggleSelection(form.interests, item)"
        >
          {{ item }}
        </button>
      </div>
    </div>
    <div class="mt-6 grid gap-4 lg:grid-cols-2">
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">必打卡景点</span>
        <textarea
          v-model="mustVisitText"
          rows="3"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        ></textarea>
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">餐饮偏好</span>
        <textarea
          v-model="diningText"
          rows="3"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        ></textarea>
      </label>
    </div>
    <div class="mt-6 grid gap-4 lg:grid-cols-3">
      <div>
        <div class="text-sm font-medium text-slate-600">出行节奏</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="item in paceOptions"
            :key="item.value"
            type="button"
            class="rounded-full border px-4 py-2 text-sm transition"
            :class="
              form.pace === item.value
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
            "
            @click="form.pace = item.value"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
      <div>
        <div class="text-sm font-medium text-slate-600">预算等级</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="item in budgetOptions"
            :key="item.value"
            type="button"
            class="rounded-full border px-4 py-2 text-sm transition"
            :class="
              form.budget_level === item.value
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
            "
            @click="form.budget_level = item.value"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">住宿风格</span>
        <select
          v-model="form.hotel_style"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        >
          <option value="">请选择住宿风格</option>
          <option v-for="item in hotelOptions" :key="item" :value="item">
            {{ item }}
          </option>
        </select>
      </label>
    </div>
    <div class="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
      <div>
        <div class="text-sm font-medium text-slate-600">交通偏好</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="item in transportOptions"
            :key="item"
            type="button"
            class="rounded-full border px-4 py-2 text-sm transition"
            :class="
              form.transport_preferences.includes(item)
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
            "
            @click="toggleSelection(form.transport_preferences, item)"
          >
            {{ item }}
          </button>
        </div>
      </div>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">补充说明</span>
        <textarea
          v-model="form.notes"
          rows="4"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        ></textarea>
      </label>
    </div>
  </article>
</template>
