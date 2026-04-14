<script setup lang="ts">
const emit = defineEmits<{
  (e: "edit-current-trip"): void;
  (e: "reset"): void;
  (e: "export", format: "png" | "pdf"): void;
}>();
</script>

<template>
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div class="flex flex-wrap gap-3">
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
        @click="emit('edit-current-trip')"
      >
        修改条件
      </button>
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
        @click="emit('reset')"
      >
        新建规划
      </button>
    </div>
    <div class="flex flex-wrap gap-3">
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
        @click="emit('export', 'png')"
      >
        导出图片
      </button>
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
        @click="emit('export', 'pdf')"
      >
        导出 PDF
      </button>
    </div>
  </div>
</template>
