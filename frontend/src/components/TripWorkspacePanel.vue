<script setup lang="ts">
import { reactive } from "vue";

import type { ReservationItem, ReservationType, TripWorkspace } from "../types/planning";

interface ReservationCoverageSummary {
  total: number;
  covered: number;
  unresolved: number;
  pending: number;
}

interface ReservationCoverageItem {
  id: string;
  title: string;
  status: "covered" | "unresolved" | "pending";
  detail: string;
}

defineProps<{
  workspace: TripWorkspace | null;
  notes: string;
  shareLink: string;
  saving: boolean;
  replanning: boolean;
  reservations: ReservationItem[];
  reservationAlerts: string[];
  reservationCoverageSummary: ReservationCoverageSummary;
  reservationCoverageItems: ReservationCoverageItem[];
}>();

const emit = defineEmits<{
  (event: "update:notes", value: string): void;
  (event: "save-notes"): void;
  (event: "copy-share"): void;
  (event: "replan-trip"): void;
  (event: "add-reservation", value: Omit<ReservationItem, "id">): void;
  (event: "remove-reservation", id: string): void;
}>();

const reservationDraft = reactive<{
  type: ReservationType;
  title: string;
  start_at: string;
  end_at: string;
  location: string;
  notes: string;
  source: string;
  confirmation_code: string;
}>({
  type: "other",
  title: "",
  start_at: "",
  end_at: "",
  location: "",
  notes: "",
  source: "",
  confirmation_code: "",
});

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

function onNotesInput(event: Event) {
  emit("update:notes", (event.target as HTMLTextAreaElement).value);
}

function submitReservation() {
  if (!reservationDraft.title.trim()) return;
  emit("add-reservation", {
    type: reservationDraft.type,
    title: reservationDraft.title.trim(),
    start_at: reservationDraft.start_at || null,
    end_at: reservationDraft.end_at || null,
    location: reservationDraft.location.trim(),
    notes: reservationDraft.notes.trim(),
    source: reservationDraft.source.trim(),
    confirmation_code: reservationDraft.confirmation_code.trim(),
  });
  reservationDraft.type = "other";
  reservationDraft.title = "";
  reservationDraft.start_at = "";
  reservationDraft.end_at = "";
  reservationDraft.location = "";
  reservationDraft.notes = "";
  reservationDraft.source = "";
  reservationDraft.confirmation_code = "";
}
</script>

<template>
  <article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">
          Workspace
        </div>
        <h2 class="mt-3 text-2xl font-semibold text-ink">行程工作区</h2>
      </div>
      <div class="rounded-full border border-[#d7e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b]">
        {{ workspace ? `v${workspace.version}` : "未保存" }}
      </div>
    </div>

    <div class="mt-5 grid gap-3 lg:grid-cols-4">
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">状态</div>
        <div class="mt-2 font-medium text-ink">
          {{ workspace ? (workspace.status === "draft" ? "草稿" : "已生成结果") : "未保存" }}
        </div>
      </div>
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">最近更新</div>
        <div class="mt-2 font-medium text-ink">{{ formatDateTime(workspace?.updated_at) }}</div>
      </div>
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">已锁定日期</div>
        <div class="mt-2 font-medium text-ink">
          {{ workspace?.locked_day_numbers.length ? `${workspace.locked_day_numbers.length} 天` : "未锁定" }}
        </div>
      </div>
      <div class="rounded-[22px] border border-[#e3ebf2] bg-[#f5f8fb] px-4 py-4 text-sm text-slate-600">
        <div class="text-xs uppercase tracking-[0.16em] text-slate-400">预订锚点</div>
        <div class="mt-2 font-medium text-ink">
          {{ reservations.length ? `${reservations.length} 条` : "未添加" }}
        </div>
      </div>
    </div>

    <div class="mt-5 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">行程备注</span>
        <textarea
          :value="notes"
          rows="4"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          placeholder="例如：第二天晚餐希望安排更安静的餐厅，第三天尽量少步行。"
          @input="onNotesInput"
        />
      </label>

      <div class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4 text-sm text-slate-600">
        <div class="font-medium text-ink">分享与重规划</div>
        <div class="mt-3 rounded-[18px] border border-[#dfe8f1] bg-white px-3 py-3 text-xs text-slate-500">
          {{ shareLink || "保存完成后可生成分享链接" }}
        </div>
        <div class="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!workspace || saving"
            @click="emit('copy-share')"
          >
            复制分享链接
          </button>
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-[#35516b] shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!workspace || saving"
            @click="emit('save-notes')"
          >
            {{ saving ? "保存中..." : "保存备注与锁定状态" }}
          </button>
          <button
            type="button"
            class="rounded-full border border-[#16324d] bg-[#16324d] px-4 py-2 text-sm text-white shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!workspace || replanning || workspace?.status === 'draft'"
            @click="emit('replan-trip')"
          >
            {{ replanning ? "重规划中..." : "重排未锁定日期" }}
          </button>
        </div>
      </div>
    </div>

    <div class="mt-6 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
      <div class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4">
        <div class="font-medium text-ink">固定预订 / 外部锚点</div>
        <div
          v-if="reservationAlerts.length"
          class="mt-4 rounded-[18px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          <div class="font-medium">预约提醒</div>
          <div class="mt-2 space-y-1 text-xs leading-5">
            <div v-for="item in reservationAlerts" :key="item">{{ item }}</div>
          </div>
        </div>
        <div
          v-if="reservationCoverageSummary.total"
          class="mt-4 rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-sm text-slate-600"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="font-medium text-ink">预约覆盖检查</div>
            <div class="flex flex-wrap gap-2 text-xs">
              <span class="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">
                已覆盖 {{ reservationCoverageSummary.covered }}
              </span>
              <span class="rounded-full bg-amber-50 px-3 py-1 text-amber-700">
                待确认 {{ reservationCoverageSummary.unresolved }}
              </span>
              <span class="rounded-full bg-slate-100 px-3 py-1 text-slate-600">
                待生成 {{ reservationCoverageSummary.pending }}
              </span>
            </div>
          </div>
          <div class="mt-3 space-y-2">
            <div
              v-for="item in reservationCoverageItems"
              :key="item.id"
              class="rounded-[14px] border border-slate-100 bg-slate-50 px-3 py-3"
            >
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="font-medium text-ink">{{ item.title }}</div>
                <span
                  class="rounded-full px-3 py-1 text-xs"
                  :class="
                    item.status === 'covered'
                      ? 'bg-emerald-100 text-emerald-700'
                      : item.status === 'unresolved'
                        ? 'bg-amber-100 text-amber-700'
                        : 'bg-slate-200 text-slate-600'
                  "
                >
                  {{
                    item.status === "covered"
                      ? "已覆盖"
                      : item.status === "unresolved"
                        ? "待确认"
                        : "待生成"
                  }}
                </span>
              </div>
              <div class="mt-2 text-xs leading-5 text-slate-500">{{ item.detail }}</div>
            </div>
          </div>
        </div>
        <div v-if="reservations.length" class="mt-4 space-y-3">
          <div
            v-for="item in reservations"
            :key="item.id"
            class="rounded-[18px] border border-[#dfe8f1] bg-white px-4 py-4 text-sm text-slate-600"
          >
            <div class="flex items-start justify-between gap-4">
              <div>
                <div class="font-medium text-ink">{{ item.title }}</div>
                <div class="mt-1 text-xs uppercase tracking-[0.12em] text-slate-400">
                  {{ item.type }}
                </div>
              </div>
              <button
                type="button"
                class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-[#35516b]"
                @click="emit('remove-reservation', item.id)"
              >
                删除
              </button>
            </div>
            <div class="mt-3 text-xs text-slate-500">
              时间：{{ formatDateTime(item.start_at) }}{{ item.end_at ? ` - ${formatDateTime(item.end_at)}` : "" }}
            </div>
            <div v-if="item.location" class="mt-1 text-xs text-slate-500">地点：{{ item.location }}</div>
            <div v-if="item.confirmation_code" class="mt-1 text-xs text-slate-500">
              预订号：{{ item.confirmation_code }}
            </div>
            <div v-if="item.source" class="mt-1 text-xs text-slate-500">来源：{{ item.source }}</div>
            <div v-if="item.notes" class="mt-2 text-sm text-slate-600">{{ item.notes }}</div>
          </div>
        </div>
        <div v-else class="mt-4 text-sm text-slate-500">
          还没有固定安排。可以先录入酒店、车票、预约或门票，后续规划会围绕这些锚点展开。
        </div>
      </div>

      <div class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4">
        <div class="font-medium text-ink">新增锚点</div>
        <div class="mt-4 grid gap-3">
          <select
            v-model="reservationDraft.type"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
          >
            <option value="hotel">酒店</option>
            <option value="train">火车</option>
            <option value="flight">航班</option>
            <option value="restaurant">餐厅预约</option>
            <option value="ticket">门票/活动</option>
            <option value="other">其他</option>
          </select>
          <input
            v-model="reservationDraft.title"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
            placeholder="标题，例如：虹桥站 -> 杭州东 G7311"
          />
          <input
            v-model="reservationDraft.start_at"
            type="datetime-local"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
          />
          <input
            v-model="reservationDraft.end_at"
            type="datetime-local"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
          />
          <input
            v-model="reservationDraft.location"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
            placeholder="地点/站点/酒店"
          />
          <input
            v-model="reservationDraft.confirmation_code"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
            placeholder="预订号/订单号"
          />
          <input
            v-model="reservationDraft.source"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
            placeholder="来源，例如：12306 / 携程 / 酒店官网"
          />
          <textarea
            v-model="reservationDraft.notes"
            rows="3"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
            placeholder="补充说明"
          ></textarea>
          <button
            type="button"
            class="rounded-[18px] border border-[#16324d] bg-[#16324d] px-4 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="!workspace || saving || !reservationDraft.title.trim()"
            @click="submitReservation"
          >
            添加到工作区
          </button>
        </div>
      </div>
    </div>
  </article>
</template>
