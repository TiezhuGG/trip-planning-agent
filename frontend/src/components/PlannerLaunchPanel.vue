<script setup lang="ts">
withDefaults(
  defineProps<{
    inputSummary: Array<{ label: string; value: string }>;
    progress: number;
    progressLabel: string;
    loading: boolean;
    canSubmit: boolean;
    errorMessage: string;
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
  <article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-8">
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
            class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"
          >
            <div class="text-xs uppercase tracking-[0.16em] text-slate-400">
              {{ item.label }}
            </div>
            <div class="mt-2 font-medium text-ink">{{ item.value }}</div>
          </div>
        </div>
      </div>

      <div class="rounded-[28px] border border-[#dbe7ef] bg-[#f4f7fa] p-5 text-[#244761] shadow-sm sm:p-6">
        <div class="flex items-center justify-between gap-4 text-sm text-[#587189]">
          <span>生成进度</span>
          <span>{{ progress ? `${progress}%` : "准备就绪" }}</span>
        </div>
        <div class="mt-3 h-2 rounded-full bg-white">
          <div
            class="h-2 rounded-full bg-[linear-gradient(90deg,#29597d,#d0a569)] transition-all duration-300"
            :style="{ width: `${progress}%` }"
          ></div>
        </div>
        <div class="mt-4 text-sm leading-6 text-[#587189]">
          {{
            loading
              ? progressLabel
              : "一键生成后，结果页会把地图、每日路线和餐饮天气整合到一起。"
          }}
        </div>
        <button
          type="button"
          class="mt-6 w-full rounded-[22px] bg-[#29597d] px-5 py-4 text-sm font-semibold text-white transition hover:bg-[#234b69] disabled:cursor-not-allowed disabled:bg-[#a3b6c5]"
          :disabled="loading || !canSubmit"
          @click="emit('submit')"
        >
          {{ loading ? "规划中..." : "开始规划" }}
        </button>
      </div>
    </div>

    <div
      v-if="errorMessage"
      class="mt-5 rounded-[22px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"
    >
      {{ errorMessage }}
    </div>
  </article>
</template>