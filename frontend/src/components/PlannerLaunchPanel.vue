<script setup lang="ts">
withDefaults(
  defineProps<{
    inputSummary: Array<{ label: string; value: string }>;
    progress: number;
    progressLabel: string;
    loading: boolean;
    canSubmit: boolean;
    compact?: boolean;
  }>(),
  {
    compact: false,
  },
);

const emit = defineEmits<{
  (event: "submit"): void;
}>();
</script>

<template>
  <article class="rounded-[36px] border border-[#d8e3ee] bg-white p-6 shadow-card sm:p-8">
    <div :class="compact ? 'space-y-5' : 'grid gap-6 xl:grid-cols-[0.98fr_1.02fr] xl:items-end'">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Planner</div>
        <h2 class="mt-3 text-2xl font-semibold text-ink sm:text-[30px]">
          开始规划和本次输入摘要
        </h2>
        <div :class="compact ? 'mt-5 grid gap-3 sm:grid-cols-2' : 'mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3'">
          <div
            v-for="item in inputSummary"
            :key="item.label"
            class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600"
          >
            <div class="text-xs uppercase tracking-[0.16em] text-slate-400">
              {{ item.label }}
            </div>
            <div class="mt-2 font-medium text-ink">{{ item.value }}</div>
          </div>
        </div>
      </div>

      <div class="rounded-[28px] border border-[#16324d] bg-[#16324d] p-5 text-white shadow-sm sm:p-6">
        <div class="flex items-center justify-between gap-4 text-sm text-white/72">
          <span>生成进度</span>
          <span>{{ progress ? `${progress}%` : "准备就绪" }}</span>
        </div>
        <div class="mt-3 h-2 rounded-full bg-white/12">
          <div
            class="h-2 rounded-full bg-white transition-all duration-300"
            :style="{ width: `${progress}%` }"
          ></div>
        </div>
        <div class="mt-4 text-sm leading-6 text-white/72">
          {{
            loading
              ? progressLabel
              : "一键生成后，结果页会把地图、每日路线和餐饮天气整合到一起。"
          }}
        </div>
        <button
          type="button"
          class="mt-6 w-full rounded-[22px] border border-white/16 bg-white px-5 py-4 text-sm font-semibold text-[#16324d] transition hover:bg-[#edf3f8] disabled:cursor-not-allowed disabled:border-white/8 disabled:bg-white/55 disabled:text-[#6d8294]"
          :disabled="loading || !canSubmit"
          @click="emit('submit')"
        >
          {{ loading ? "规划中..." : "开始规划" }}
        </button>
      </div>
    </div>
  </article>
</template>
