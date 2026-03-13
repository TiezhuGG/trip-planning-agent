<script setup lang="ts">
defineProps<{
  summaryTags: string[];
}>();

const highlights = [
  {
    label: "规划方式",
    value: "多 Agent 协作",
    text: "把偏好、天气、地图和每日安排拆开处理，再汇总成一份完整计划。",
  },
  {
    label: "输出重点",
    value: "可执行路线",
    text: "不只列清单，更强调每天怎么走、看什么、吃什么。",
  },
  {
    label: "结果形式",
    value: "地图联动",
    text: "生成后可直接查看点位、每日详情，并导出图片或 PDF。",
  },
];
</script>

<template>
  <header
    class="rounded-[40px] border border-[#183552] bg-[#102a43] px-6 py-8 text-white shadow-[0_26px_72px_rgba(16,42,67,0.18)] sm:px-8 lg:px-10 lg:py-10"
  >
    <div class="grid gap-8 xl:grid-cols-[1.08fr_0.92fr] xl:items-end">
      <div>
        <div
          class="inline-flex items-center gap-2 rounded-full border border-white/18 bg-white/8 px-4 py-2 text-xs font-medium uppercase tracking-[0.22em] text-white/78"
        >
          <span class="h-2 w-2 rounded-full bg-white"></span>
          AI Travel Planner
        </div>
        <h1
          class="mt-6 max-w-4xl font-display text-4xl font-semibold leading-tight text-white sm:text-5xl xl:text-[56px]"
        >
          让一段旅行，变成一份顺手可执行的城市行动线。
        </h1>
        <p class="mt-5 max-w-3xl text-sm leading-7 text-white/72 sm:text-base">
          输入目的地、日期与偏好后，系统会自动整合景点、餐饮、天气和地图信息，生成更适合直接出发使用的多日行程。
        </p>
        <div class="mt-6 flex flex-wrap gap-2">
          <span
            v-for="tag in summaryTags"
            :key="tag"
            class="rounded-full border border-white/14 bg-white px-4 py-2 text-sm text-[#1b3652]"
          >
            {{ tag }}
          </span>
        </div>
      </div>

      <div class="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
        <article
          v-for="item in highlights"
          :key="item.label"
          class="rounded-[26px] border border-white/14 bg-white px-5 py-5 text-[#1b3652]"
        >
          <div class="text-xs uppercase tracking-[0.22em] text-[#70849a]">
            {{ item.label }}
          </div>
          <div class="mt-3 text-lg font-semibold text-[#17324d]">
            {{ item.value }}
          </div>
          <p class="mt-2 text-sm leading-6 text-[#5c7084]">
            {{ item.text }}
          </p>
        </article>
      </div>
    </div>
  </header>
</template>