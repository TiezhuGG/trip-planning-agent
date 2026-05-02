<script setup lang="ts">
import { computed, ref } from "vue";

import type { TripSummary } from "../types/planning";
import { formatDateTimeZhCn } from "../utils/workspaceFormatting";
import {
  formatWorkspaceResultLabel,
  formatWorkspaceShareLabel,
  formatWorkspaceStatusLabel,
  resolveWorkspaceStatusBadgeClass,
  resolveWorkspaceStatusFilterTone,
} from "../utils/workspaceStatus";

const props = defineProps<{
  trips: TripSummary[];
  loading: boolean;
  error: string;
}>();

const emit = defineEmits<{
  (event: "open", tripId: string): void;
  (event: "refresh"): void;
}>();

type StatusFilter = {
  key: "all" | TripSummary["status"];
  label: string;
  count: number;
  activeTone: string;
};

type QuickFilterKey = "all" | "editable" | "attention";

const filterText = ref("");
const activeStatus = ref<"all" | TripSummary["status"]>("all");
const activeQuickFilter = ref<QuickFilterKey>("all");
const sortMode = ref<"updated" | "departure">("updated");

function formatDateTime(value: string) {
  return formatDateTimeZhCn(value);
}

function formatStatusLabel(value: TripSummary["status"]) {
  return formatWorkspaceStatusLabel(value);
}

function statusBadgeClass(value: TripSummary["status"]) {
  return resolveWorkspaceStatusBadgeClass(value);
}

const sortedTrips = computed(() =>
  [...props.trips].sort((left, right) => {
    if (sortMode.value === "departure") {
      const startDiff = left.start_date.localeCompare(right.start_date);
      if (startDiff !== 0) return startDiff;
    }
    const leftTime = new Date(left.updated_at).getTime();
    const rightTime = new Date(right.updated_at).getTime();
    if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime) && leftTime !== rightTime) {
      return rightTime - leftTime;
    }
    return right.created_at.localeCompare(left.created_at);
  }),
);

const statusSummary = computed(() => {
  const summary: Record<TripSummary["status"], number> = {
    draft: 0,
    ready: 0,
    action_required: 0,
    generating: 0,
    error: 0,
  };
  for (const trip of props.trips) {
    summary[trip.status] += 1;
  }
  return summary;
});

const statusFilters = computed<StatusFilter[]>(() =>
  [
    {
      key: "all" as const,
      label: "全部",
      count: props.trips.length,
      activeTone: "border-[#16324d] bg-[#16324d] text-white",
    },
    {
      key: "ready" as const,
      label: "已就绪",
      count: statusSummary.value.ready,
      activeTone: resolveWorkspaceStatusFilterTone("ready"),
    },
    {
      key: "action_required" as const,
      label: "待处理",
      count: statusSummary.value.action_required,
      activeTone: resolveWorkspaceStatusFilterTone("action_required"),
    },
    {
      key: "draft" as const,
      label: "草稿",
      count: statusSummary.value.draft,
      activeTone: resolveWorkspaceStatusFilterTone("draft"),
    },
    {
      key: "generating" as const,
      label: "生成中",
      count: statusSummary.value.generating,
      activeTone: resolveWorkspaceStatusFilterTone("generating"),
    },
    {
      key: "error" as const,
      label: "异常",
      count: statusSummary.value.error,
      activeTone: resolveWorkspaceStatusFilterTone("error"),
    },
  ].filter((item) => item.key === "all" || item.count > 0),
);

const quickFilterSummary = computed(() => {
  const editable = props.trips.filter((trip) =>
    ["draft", "ready", "action_required"].includes(trip.status),
  ).length;
  const attention = props.trips.filter(
    (trip) =>
      trip.status === "action_required" ||
      trip.status === "error" ||
      !trip.share_enabled ||
      !trip.has_result,
  ).length;

  return {
    editable,
    attention,
  };
});

const filteredTrips = computed(() => {
  const keyword = filterText.value.trim().toLowerCase();
  return sortedTrips.value.filter((trip) => {
    if (activeStatus.value !== "all" && trip.status !== activeStatus.value) {
      return false;
    }
    if (
      activeQuickFilter.value === "editable" &&
      !["draft", "ready", "action_required"].includes(trip.status)
    ) {
      return false;
    }
    if (
      activeQuickFilter.value === "attention" &&
      !(
        trip.status === "action_required" ||
        trip.status === "error" ||
        !trip.share_enabled ||
        !trip.has_result
      )
    ) {
      return false;
    }
    if (!keyword) {
      return true;
    }
    return [trip.title, trip.destination, trip.start_date].some((value) =>
      value.toLowerCase().includes(keyword),
    );
  });
});

const hasActiveFilters = computed(
  () =>
    activeStatus.value !== "all" ||
    activeQuickFilter.value !== "all" ||
    sortMode.value !== "updated" ||
    Boolean(filterText.value.trim()),
);

function resetFilters() {
  filterText.value = "";
  activeStatus.value = "all";
  activeQuickFilter.value = "all";
  sortMode.value = "updated";
}

function formatDepartureHint(value: string) {
  const start = new Date(`${value}T12:00:00`);
  if (Number.isNaN(start.getTime())) return value;
  const today = new Date();
  const base = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 12, 0, 0);
  const diffDays = Math.round((start.getTime() - base.getTime()) / 86400000);
  if (diffDays === 0) return "今天出发";
  if (diffDays === 1) return "明天出发";
  if (diffDays > 1) return `${diffDays} 天后出发`;
  if (diffDays === -1) return "昨天出发";
  return `${Math.abs(diffDays)} 天前出发`;
}
</script>

<template>
  <article class="rounded-[30px] border border-[#d8e3ee] bg-white/92 px-6 py-5 shadow-card">
    <div class="flex items-center justify-between gap-4">
      <div>
        <div class="text-xs uppercase tracking-[0.24em] text-[#6f7f92]">Recent Workspaces</div>
        <div class="mt-2 text-lg font-semibold text-ink">最近工作区</div>
      </div>
      <button
        type="button"
        class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm shadow-sm"
        :disabled="loading"
        @click="emit('refresh')"
      >
        {{ loading ? "刷新中..." : "刷新" }}
      </button>
    </div>

    <div v-if="statusFilters.length" class="mt-4 flex flex-wrap gap-2 text-xs">
      <button
        v-for="item in statusFilters"
        :key="item.key"
        type="button"
        class="rounded-full border px-3 py-1 transition"
        :class="
          activeStatus === item.key
            ? item.activeTone
            : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
        "
        @click="activeStatus = item.key"
      >
        {{ item.label }} {{ item.count }}
      </button>
    </div>

    <div v-if="props.trips.length" class="mt-4 flex flex-wrap gap-2 text-xs">
      <button
        type="button"
        class="rounded-full border px-3 py-1 transition"
        :class="
          activeQuickFilter === 'all'
            ? 'border-[#16324d] bg-[#16324d] text-white'
            : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
        "
        @click="activeQuickFilter = 'all'"
      >
        全部视图
      </button>
      <button
        type="button"
        class="rounded-full border px-3 py-1 transition"
        :class="
          activeQuickFilter === 'editable'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
        "
        @click="activeQuickFilter = 'editable'"
      >
        可继续编辑 {{ quickFilterSummary.editable }}
      </button>
      <button
        type="button"
        class="rounded-full border px-3 py-1 transition"
        :class="
          activeQuickFilter === 'attention'
            ? 'border-amber-200 bg-amber-50 text-amber-700'
            : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
        "
        @click="activeQuickFilter = 'attention'"
      >
        需关注 {{ quickFilterSummary.attention }}
      </button>
    </div>

    <div v-if="props.trips.length" class="mt-4 flex flex-wrap items-center gap-3">
      <input
        v-model="filterText"
        type="text"
        class="min-w-0 flex-1 rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
        placeholder="搜索工作区标题、目的地或出发日期"
      />
      <button
        v-if="hasActiveFilters"
        type="button"
        class="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
        @click="resetFilters"
      >
        清空筛选
      </button>
    </div>

    <div v-if="sortedTrips.length" class="mt-4 flex flex-wrap items-center justify-between gap-3">
      <div class="text-xs text-slate-500">
        当前显示 {{ filteredTrips.length }} / {{ sortedTrips.length }} 个工作区
      </div>
      <div class="flex flex-wrap gap-2 text-xs">
        <button
          type="button"
          class="rounded-full border px-3 py-1 transition"
          :class="
            sortMode === 'updated'
              ? 'border-[#16324d] bg-[#16324d] text-white'
              : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
          "
          @click="sortMode = 'updated'"
        >
          最近更新
        </button>
        <button
          type="button"
          class="rounded-full border px-3 py-1 transition"
          :class="
            sortMode === 'departure'
              ? 'border-[#16324d] bg-[#16324d] text-white'
              : 'border-[#d7e2ec] bg-white text-[#35516b] hover:bg-[#eef4f9]'
          "
          @click="sortMode = 'departure'"
        >
          出发日期
        </button>
      </div>
    </div>

    <div
      v-if="props.error"
      class="mt-4 rounded-[18px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      {{ props.error }}
    </div>

    <div v-else-if="!sortedTrips.length" class="mt-4 text-sm text-slate-500">
      暂无最近工作区。保存一次草稿或生成结果后，这里会显示可继续编辑的行程。
    </div>

    <div v-else-if="!filteredTrips.length" class="mt-4 text-sm text-slate-500">
      当前筛选条件下没有匹配的工作区。
    </div>

    <div v-else class="mt-4 grid gap-3 md:grid-cols-2">
      <button
        v-for="trip in filteredTrips"
        :key="trip.id"
        type="button"
        class="rounded-[20px] border border-[#dfe8f1] bg-[#f8fbfd] px-4 py-4 text-left transition hover:border-[#bfd0df] hover:bg-white"
        @click="emit('open', trip.id)"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="font-medium text-ink">{{ trip.title }}</div>
          <span
            class="rounded-full border px-2.5 py-1 text-[11px]"
            :class="statusBadgeClass(trip.status)"
          >
            {{ formatStatusLabel(trip.status) }}
          </span>
        </div>
        <div class="mt-2 text-sm text-slate-600">
          {{ trip.destination }} · {{ trip.days }} 天 · {{ trip.start_date }}
        </div>
        <div class="mt-2 text-xs text-slate-500">
          {{ formatDepartureHint(trip.start_date) }}
        </div>
        <div class="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
          <span class="rounded-full bg-white px-3 py-1">v{{ trip.version }}</span>
          <span class="rounded-full bg-white px-3 py-1">
            {{ formatWorkspaceResultLabel(trip.has_result) }}
          </span>
          <span class="rounded-full bg-white px-3 py-1">
            {{ trip.reservations_count }} 条预订
          </span>
          <span class="rounded-full bg-white px-3 py-1">
            {{ trip.locked_day_count }} 个锁定日
          </span>
          <span class="rounded-full bg-white px-3 py-1">
            {{ formatWorkspaceShareLabel(trip.share_enabled) }}
          </span>
        </div>
        <div class="mt-3 text-xs text-slate-500">
          最近更新：{{ formatDateTime(trip.updated_at) }}
        </div>
      </button>
    </div>
  </article>
</template>
