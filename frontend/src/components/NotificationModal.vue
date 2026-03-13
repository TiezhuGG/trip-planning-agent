<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from "vue";

type NoticeTone = "success" | "warning" | "error";

const props = defineProps<{
  open: boolean;
  tone: NoticeTone;
  title: string;
  messages: string[];
}>();

const emit = defineEmits<{
  (event: "close"): void;
}>();

let autoCloseTimer: number | null = null;

const toneConfig = computed(() => {
  if (props.tone === "success") {
    return {
      label: "Success",
      panel: "border-[#cfe3d4] bg-white",
      badge: "bg-[#eef8f0] text-[#2f6b43] border-[#cfe3d4]",
      message: "border-[#dfeee3] bg-[#f6fbf7] text-[#42614c]",
      button: "bg-[#1d5b38] hover:bg-[#17492d]",
      close: "text-[#5c8a69] hover:bg-[#eef8f0] hover:text-[#2f6b43]",
      autoCloseMs: 2400,
    };
  }
  if (props.tone === "error") {
    return {
      label: "Error",
      panel: "border-[#ecd2d2] bg-white",
      badge: "bg-[#fff3f3] text-[#9a3d3d] border-[#ecd2d2]",
      message: "border-[#f2dddd] bg-[#fff7f7] text-[#7b5252]",
      button: "bg-[#8b2f2f] hover:bg-[#742626]",
      close: "text-[#a56a6a] hover:bg-[#fff3f3] hover:text-[#8b2f2f]",
      autoCloseMs: 0,
    };
  }
  return {
    label: "Notice",
    panel: "border-[#d8e3ee] bg-white",
    badge: "bg-[#f5f8fb] text-[#35516b] border-[#d8e3ee]",
    message: "border-[#e3ebf2] bg-[#f5f8fb] text-slate-600",
    button: "bg-[#16324d] hover:bg-[#102a43]",
    close: "text-[#6f8397] hover:bg-[#f5f8fb] hover:text-[#16324d]",
    autoCloseMs: 4200,
  };
});

function closeModal() {
  emit("close");
}

function clearAutoCloseTimer() {
  if (autoCloseTimer) {
    window.clearTimeout(autoCloseTimer);
    autoCloseTimer = null;
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    closeModal();
  }
}

watch(
  () => props.open,
  (open) => {
    clearAutoCloseTimer();
    if (!open) {
      window.removeEventListener("keydown", onKeydown);
      return;
    }
    window.addEventListener("keydown", onKeydown);
    if (toneConfig.value.autoCloseMs > 0) {
      autoCloseTimer = window.setTimeout(() => {
        closeModal();
      }, toneConfig.value.autoCloseMs);
    }
  },
  { immediate: true },
);

watch(
  () => props.tone,
  () => {
    if (!props.open) return;
    clearAutoCloseTimer();
    if (toneConfig.value.autoCloseMs > 0) {
      autoCloseTimer = window.setTimeout(() => {
        closeModal();
      }, toneConfig.value.autoCloseMs);
    }
  },
);

onBeforeUnmount(() => {
  clearAutoCloseTimer();
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[100] flex items-center justify-center bg-[#102a43]/45 px-4 backdrop-blur-sm"
      @click.self="closeModal"
    >
      <div
        class="w-full max-w-lg rounded-[28px] border p-6 shadow-[0_24px_80px_rgba(16,42,67,0.22)] sm:p-7"
        :class="toneConfig.panel"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <div
              class="inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-[0.2em]"
              :class="toneConfig.badge"
            >
              {{ toneConfig.label }}
            </div>
            <h3 class="mt-3 text-2xl font-semibold text-ink">{{ title }}</h3>
          </div>
          <button
            type="button"
            class="flex h-10 w-10 items-center justify-center rounded-full text-xl leading-none transition"
            :class="toneConfig.close"
            aria-label="关闭提醒"
            @click="closeModal"
          >
            ×
          </button>
        </div>
        <div class="mt-4 space-y-3">
          <div
            v-for="message in messages"
            :key="message"
            class="rounded-[20px] border px-4 py-3 text-sm leading-7"
            :class="toneConfig.message"
          >
            {{ message }}
          </div>
        </div>
        <button
          type="button"
          class="mt-6 w-full rounded-[20px] px-4 py-3 text-sm font-semibold text-white transition"
          :class="toneConfig.button"
          @click="closeModal"
        >
          我知道了
        </button>
      </div>
    </div>
  </teleport>
</template>
