<script setup lang="ts">
import { useReservationDraft } from "../composables/useReservationDraft";

import type { ReservationItem, TripWorkspace } from "../types/planning";

defineProps<{
  workspace: TripWorkspace | null;
  saving: boolean;
}>();

const emit = defineEmits<{
  (event: "add-reservation", value: Omit<ReservationItem, "id">): void;
}>();

const {
  reservationDraft,
  validationMessage,
  canSubmit,
  resetDraft,
  toReservationPayload,
} = useReservationDraft();

function submitReservation() {
  if (!canSubmit.value) return;
  emit("add-reservation", toReservationPayload());
  resetDraft();
}
</script>

<template>
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
        placeholder="预订号 / 订单号"
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
      <div
        class="rounded-[16px] border px-4 py-3 text-xs leading-5"
        :class="
          validationMessage
            ? 'border-amber-200 bg-amber-50 text-amber-700'
            : 'border-[#dfe8f1] bg-white text-slate-500'
        "
      >
        {{
          validationMessage ||
          "可先录入酒店、门票、交通或餐厅预约，后续生成和重规划会围绕这些固定安排展开。"
        }}
      </div>
      <button
        type="button"
        class="rounded-[18px] border border-[#16324d] bg-[#16324d] px-4 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="!workspace || saving || !canSubmit"
        @click="submitReservation"
      >
        添加到工作区
      </button>
    </div>
  </div>
</template>
