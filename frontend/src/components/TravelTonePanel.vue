<script setup lang="ts">
defineProps<{
  destination: string;
  interests: string[];
  hotelStyle: string;
  transportPreferences: string[];
}>();
</script>

<template>
  <article class="rounded-[36px] border border-[#d8e3ee] bg-white p-6 shadow-card">
    <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Travel Tone</div>
    <h3 class="mt-3 text-2xl font-semibold text-ink">这趟行程会偏向什么感觉</h3>
    <div class="mt-5 space-y-3 text-sm leading-7 text-slate-600">
      <div class="rounded-[24px] border border-[#e4ebf2] bg-[#f5f8fb] px-4 py-4">
        重点会围绕
        <span class="font-medium text-ink">{{ destination || "目的地" }}</span>
        的
        <span class="font-medium text-ink">{{ interests.join(" / ") || "城市体验" }}</span>
        展开。
      </div>
      <div class="rounded-[24px] border border-[#e4ebf2] bg-[#f5f8fb] px-4 py-4">
        住宿倾向
        <span class="font-medium text-ink">{{ hotelStyle || "舒适型酒店" }}</span>
        ，交通优先
        <span class="font-medium text-ink">{{ transportPreferences.join(" / ") || "系统推荐" }}</span>
        。
      </div>
      <div class="rounded-[24px] border border-[#e4ebf2] bg-[#eef4f9] px-4 py-4 text-[#51687c]">
        系统会尽量把必去点和饮食偏好编进每日路线，而不是只堆列表。
      </div>
    </div>
  </article>
</template>