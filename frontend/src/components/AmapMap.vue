<script setup lang="ts">
import { computed } from "vue";

import { useAmapMapRuntime } from "../composables/useAmapMapRuntime";
import type { DayPOI, MapRenderConfig, RouteSummary } from "../types/planning";

const props = defineProps<{
  mapConfig: MapRenderConfig;
  pois: DayPOI[];
  routes: RouteSummary[];
}>();

const { mapRoot, loading, errorMessage } = useAmapMapRuntime({
  mapConfig: computed(() => props.mapConfig),
  pois: computed(() => props.pois),
  routes: computed(() => props.routes),
});
</script>

<template>
  <div class="relative overflow-hidden rounded-[28px] border border-slate-100 bg-[#edf2ff] p-3">
    <div ref="mapRoot" class="h-[430px] rounded-[24px] bg-[#dfe8f3]"></div>
    <div class="pointer-events-none absolute left-6 top-6 flex flex-wrap gap-2">
      <span class="rounded-full border border-[#8e4108] bg-[#d46a1f] px-3 py-1 text-xs text-[#fffaf5] shadow-sm">
        浅色点位：当日活动
      </span>
      <span class="rounded-full border border-[#08323d] bg-[#0f4c5c] px-3 py-1 text-xs text-[#f8fbff] shadow-sm">
        深色点位：酒店住宿
      </span>
    </div>
    <div
      v-if="loading"
      class="absolute inset-3 flex items-center justify-center rounded-[24px] bg-white/72 text-sm text-slate-600 backdrop-blur-sm"
    >
      正在加载高德地图...
    </div>
    <div
      v-else-if="errorMessage"
      class="absolute inset-3 flex items-center justify-center rounded-[24px] bg-white/82 px-6 text-center text-sm leading-7 text-slate-500 backdrop-blur-sm"
    >
      {{ errorMessage }}
    </div>
  </div>
</template>
