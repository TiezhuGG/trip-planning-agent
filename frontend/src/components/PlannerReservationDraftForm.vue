<script setup lang="ts">
import { computed, watch } from "vue";

import { useReservationDraft } from "../composables/useReservationDraft";
import { addDays } from "../utils/tripPlannerForm";

import type { ReservationItem, ReservationType, TripWorkspace } from "../types/planning";

const props = defineProps<{
  workspace: TripWorkspace | null;
  saving: boolean;
  templateReservation?: ReservationItem | null;
}>();

const emit = defineEmits<{
  (event: "add-reservation", value: Omit<ReservationItem, "id">): void;
  (event: "clear-template"): void;
}>();

const {
  reservationDraft,
  validationMessage,
  canSubmit,
  resetDraft,
  toReservationPayload,
} = useReservationDraft();

watch(
  () => props.templateReservation,
  (value) => {
    if (!value) return;
    reservationDraft.type = value.type;
    reservationDraft.title = value.title;
    reservationDraft.start_at = value.start_at ?? "";
    reservationDraft.end_at = value.end_at ?? "";
    reservationDraft.location = value.location ?? "";
    reservationDraft.notes = value.notes ?? "";
    reservationDraft.source = value.source ?? "";
    reservationDraft.confirmation_code = value.confirmation_code ?? "";
  },
);

function submitReservation() {
  if (!canSubmit.value) return;
  emit("add-reservation", toReservationPayload());
  resetDraftAndTemplate();
}

function resetDraftAndTemplate() {
  resetDraft();
  emit("clear-template");
}

const RESERVATION_TYPE_OPTIONS: Array<{ value: ReservationType; label: string }> = [
  { value: "hotel", label: "酒店" },
  { value: "train", label: "火车" },
  { value: "flight", label: "航班" },
  { value: "restaurant", label: "餐厅预订" },
  { value: "ticket", label: "门票 / 活动" },
  { value: "other", label: "其他安排" },
];

const RESERVATION_TYPE_COPY: Record<
  ReservationType,
  {
    titlePlaceholder: string;
    locationPlaceholder: string;
    sourcePlaceholder: string;
    notesPlaceholder: string;
    helper: string;
  }
> = {
  hotel: {
    titlePlaceholder: "标题，例如：杭州四季酒店",
    locationPlaceholder: "酒店名称或地址",
    sourcePlaceholder: "来源，例如：酒店官网 / Booking / OTA",
    notesPlaceholder: "房型、入住人数、早餐、延迟入住或其他备注",
    helper: "酒店预订最好同时带上入住和退房时间，后续生成与重排会更稳定。",
  },
  train: {
    titlePlaceholder: "标题，例如：虹桥 -> 杭州东 G7311",
    locationPlaceholder: "出发站和到达站",
    sourcePlaceholder: "来源，例如：12306 / OTA",
    notesPlaceholder: "座位、换乘缓冲、行李或接送说明",
    helper: "火车预订建议填写准确出发时间，避免和当天活动或餐饮安排冲突。",
  },
  flight: {
    titlePlaceholder: "标题，例如：MU5123 SHA -> CAN",
    locationPlaceholder: "机场或航站楼",
    sourcePlaceholder: "来源，例如：航司官网 / OTA",
    notesPlaceholder: "航站楼、值机、行李、登机口或其他提醒",
    helper: "航班预订最好补齐起飞时间、机场和航站楼，方便后续预留缓冲。",
  },
  restaurant: {
    titlePlaceholder: "标题，例如：新荣记 19:00 晚餐",
    locationPlaceholder: "餐厅名称或商圈",
    sourcePlaceholder: "来源，例如：电话 / App / 点评站点",
    notesPlaceholder: "人数、忌口、包间需求或庆祝说明",
    helper: "餐厅预订会作为固定时间窗插入行程，时间越明确越好。",
  },
  ticket: {
    titlePlaceholder: "标题，例如：博物馆 09:30 入场",
    locationPlaceholder: "场馆或景点名称",
    sourcePlaceholder: "来源，例如：官方小程序 / OTA / 直订",
    notesPlaceholder: "场次、取票、证件要求或入场说明",
    helper: "门票和活动最好带具体入场时点，系统更容易串联附近活动。",
  },
  other: {
    titlePlaceholder: "标题，例如：客户拜访 / 家庭聚会 / 取车",
    locationPlaceholder: "地点或集合点",
    sourcePlaceholder: "来源，例如：邮件 / 聊天 / 口头确认",
    notesPlaceholder: "背景、联系人或执行说明",
    helper: "任何后续行程必须尊重的时间地点约束，都可以作为固定安排录入。",
  },
};

const activeTypeCopy = computed(() => RESERVATION_TYPE_COPY[reservationDraft.type]);

const tripDayPresets = computed(() => {
  if (!props.workspace) return [];
  const startDate = props.workspace.request_brief.start_date;
  const totalDays = Math.max(props.workspace.request_brief.days, 0);
  return Array.from({ length: totalDays }, (_, index) => {
    const date = addDays(startDate, index);
    return {
      dayNumber: index + 1,
      date,
      label: `D${index + 1} ${date.slice(5)}`,
    };
  });
});

const timeSlotPresets = computed<
  Array<{ label: string; startHour: number; startMinute: number; endHour: number; endMinute: number }>
>(() => {
  if (reservationDraft.type === "hotel") {
    return [{ label: "入住 / 退房", startHour: 15, startMinute: 0, endHour: 12, endMinute: 0 }];
  }
  if (reservationDraft.type === "restaurant") {
    return [
      { label: "午餐", startHour: 12, startMinute: 30, endHour: 14, endMinute: 0 },
      { label: "晚餐", startHour: 18, startMinute: 30, endHour: 20, endMinute: 0 },
    ];
  }
  if (reservationDraft.type === "ticket") {
    return [
      { label: "上午场", startHour: 9, startMinute: 30, endHour: 12, endMinute: 0 },
      { label: "下午场", startHour: 14, startMinute: 0, endHour: 17, endMinute: 0 },
      { label: "夜场", startHour: 19, startMinute: 0, endHour: 21, endMinute: 0 },
    ];
  }
  if (reservationDraft.type === "train") {
    return [
      { label: "上午车次", startHour: 9, startMinute: 0, endHour: 12, endMinute: 0 },
      { label: "下午车次", startHour: 14, startMinute: 0, endHour: 17, endMinute: 0 },
    ];
  }
  if (reservationDraft.type === "flight") {
    return [
      { label: "早班机", startHour: 8, startMinute: 0, endHour: 11, endMinute: 0 },
      { label: "午后航班", startHour: 13, startMinute: 0, endHour: 16, endMinute: 0 },
      { label: "晚班机", startHour: 18, startMinute: 0, endHour: 21, endMinute: 0 },
    ];
  }
  return [
    { label: "上午", startHour: 9, startMinute: 0, endHour: 11, endMinute: 0 },
    { label: "下午", startHour: 14, startMinute: 0, endHour: 16, endMinute: 0 },
    { label: "晚上", startHour: 19, startMinute: 0, endHour: 21, endMinute: 0 },
  ];
});

const sourceSuggestions = computed(() => {
  if (reservationDraft.type === "hotel") return ["酒店官网", "Booking", "OTA"];
  if (reservationDraft.type === "train") return ["12306", "OTA", "飞猪"];
  if (reservationDraft.type === "flight") return ["航司官网", "OTA", "飞猪"];
  if (reservationDraft.type === "restaurant") return ["电话", "点评 App", "小程序"];
  if (reservationDraft.type === "ticket") return ["官网", "小程序", "OTA"];
  return ["邮件", "聊天", "电话"];
});

const noteSuggestions = computed(() => {
  if (reservationDraft.type === "hotel") return ["双早", "延迟入住", "高楼层", "亲子友好"];
  if (reservationDraft.type === "train") return ["靠窗", "预留换乘缓冲", "提前取票", "大件行李"];
  if (reservationDraft.type === "flight") return ["线上值机", "托运行李", "留意航站楼", "预留安检时间"];
  if (reservationDraft.type === "restaurant") return ["2 人", "不吃辣", "靠窗位", "生日聚餐"];
  if (reservationDraft.type === "ticket") return ["携带证件", "不可迟到", "需要取票", "优先走官方入口"];
  return ["到场前再确认", "时间尽量别变", "到达前联系"];
});

const submissionHint = computed(() => {
  if (!props.workspace) {
    return "请先创建工作区，再录入固定预订和外部安排。";
  }
  if (props.saving) {
    return "工作区正在保存，保存完成后可继续添加。";
  }
  return validationMessage.value || activeTypeCopy.value.helper;
});

function padTime(value: number) {
  return String(value).padStart(2, "0");
}

function toDateTimeLocal(date: string, hour: number, minute: number) {
  return `${date}T${padTime(hour)}:${padTime(minute)}`;
}

function resolvePrimaryDate() {
  if (reservationDraft.start_at.includes("T")) {
    return reservationDraft.start_at.slice(0, 10);
  }
  return tripDayPresets.value[0]?.date ?? "";
}

function defaultDaySpan() {
  return reservationDraft.type === "hotel" ? 1 : 0;
}

function applyTripDayPreset(date: string) {
  const activeSlot = timeSlotPresets.value[0] ?? {
    startHour: 9,
    startMinute: 0,
    endHour: 11,
    endMinute: 0,
  };
  reservationDraft.start_at = toDateTimeLocal(date, activeSlot.startHour, activeSlot.startMinute);
  reservationDraft.end_at = toDateTimeLocal(
    addDays(date, defaultDaySpan()),
    activeSlot.endHour,
    activeSlot.endMinute,
  );
}

function applyTimeSlotPreset(preset: {
  startHour: number;
  startMinute: number;
  endHour: number;
  endMinute: number;
}) {
  const activeDate = resolvePrimaryDate();
  if (!activeDate) return;
  reservationDraft.start_at = toDateTimeLocal(activeDate, preset.startHour, preset.startMinute);
  reservationDraft.end_at = toDateTimeLocal(
    addDays(activeDate, defaultDaySpan()),
    preset.endHour,
    preset.endMinute,
  );
}

function resolveTripDayLabel(dateTime: string) {
  if (!props.workspace || !dateTime.includes("T")) return "";
  const datePart = dateTime.slice(0, 10);
  const startDate = props.workspace.request_brief.start_date;
  for (let index = 0; index < props.workspace.request_brief.days; index += 1) {
    if (addDays(startDate, index) === datePart) {
      return `D${index + 1}`;
    }
  }
  return "";
}

const scheduleSummary = computed(() => {
  if (!reservationDraft.start_at) return "";
  const startDay = resolveTripDayLabel(reservationDraft.start_at);
  const endDay = reservationDraft.end_at ? resolveTripDayLabel(reservationDraft.end_at) : "";
  const startLabel = reservationDraft.start_at.replace("T", " ");
  const endLabel = reservationDraft.end_at ? reservationDraft.end_at.replace("T", " ") : "";
  if (reservationDraft.end_at) {
    return `${startDay || "已选"} ${startLabel} -> ${endDay || ""} ${endLabel}`.trim();
  }
  return `${startDay || "已选"} ${startLabel}`.trim();
});

function applySourceSuggestion(value: string) {
  reservationDraft.source = value;
}

function appendNoteSuggestion(value: string) {
  const segments = (reservationDraft.notes ?? "")
    .split(/[\n,.;!?，。；？！]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (segments.includes(value)) return;
  reservationDraft.notes = [...segments, value].join("，");
}

function clearScheduleFields() {
  reservationDraft.start_at = "";
  reservationDraft.end_at = "";
}

function clearTemplateMode() {
  resetDraftAndTemplate();
}
</script>

<template>
  <div class="rounded-[24px] border border-[#dbe5ef] bg-[#f8fbfd] p-4">
    <div class="font-medium text-ink">新增固定预订 / 外部安排</div>
    <div class="mt-1 text-xs leading-5 text-slate-500">
      先录入已经确认的预订和不会变化的外部约束，后续生成与重排会优先围绕它们展开。
    </div>
    <div
      v-if="templateReservation"
      class="mt-3 rounded-[16px] border border-sky-100 bg-sky-50 px-4 py-3 text-xs leading-5 text-sky-800"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <span>已加载模板：{{ templateReservation?.title ?? "预订" }}</span>
        <button
          type="button"
          class="rounded-full border border-sky-200 bg-white px-3 py-1 text-xs font-medium text-sky-700 transition hover:bg-sky-100"
          @click="clearTemplateMode"
        >
          回到空白表单
        </button>
      </div>
    </div>
    <div class="mt-4 grid gap-3">
      <label class="grid gap-1 text-sm text-slate-600">
        <span class="text-xs text-slate-500">预订类型</span>
        <select
          v-model="reservationDraft.type"
          class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
        >
          <option v-for="option in RESERVATION_TYPE_OPTIONS" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <input
        v-model="reservationDraft.title"
        class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
        :placeholder="activeTypeCopy.titlePlaceholder"
      />
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="grid gap-1 text-sm text-slate-600">
          <span class="text-xs text-slate-500">开始时间</span>
          <input
            v-model="reservationDraft.start_at"
            type="datetime-local"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
          />
        </label>
        <label class="grid gap-1 text-sm text-slate-600">
          <span class="text-xs text-slate-500">结束时间</span>
          <input
            v-model="reservationDraft.end_at"
            type="datetime-local"
            class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
          />
        </label>
      </div>
      <div v-if="tripDayPresets.length" class="grid gap-3">
        <div>
          <div class="text-xs text-slate-500">按行程日快速填入</div>
          <div class="mt-2 flex flex-wrap gap-2">
            <button
              v-for="item in tripDayPresets"
              :key="item.label"
              type="button"
              class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
              @click="applyTripDayPreset(item.date)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
        <div>
          <div class="text-xs text-slate-500">常用时间段</div>
          <div class="mt-2 flex flex-wrap gap-2">
            <button
              v-for="item in timeSlotPresets"
              :key="item.label"
              type="button"
              class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
              @click="applyTimeSlotPreset(item)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
        <div
          v-if="scheduleSummary"
          class="rounded-[16px] border border-[#dfe8f1] bg-white px-4 py-3 text-xs leading-5 text-slate-500"
        >
          当前时间窗：{{ scheduleSummary }}
        </div>
        <div class="flex justify-end">
          <button
            v-if="reservationDraft.start_at || reservationDraft.end_at"
            type="button"
            class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#eef4f9]"
            @click="clearScheduleFields"
          >
            清空时间
          </button>
        </div>
      </div>
      <input
        v-model="reservationDraft.location"
        class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
        :placeholder="activeTypeCopy.locationPlaceholder"
      />
      <input
        v-model="reservationDraft.confirmation_code"
        class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
        placeholder="确认号或订单号"
      />
      <input
        v-model="reservationDraft.source"
        class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
        :placeholder="activeTypeCopy.sourcePlaceholder"
      />
      <div class="flex flex-wrap gap-2">
        <button
          v-for="item in sourceSuggestions"
          :key="item"
          type="button"
          class="rounded-full border px-3 py-1 text-xs transition"
          :class="
            reservationDraft.source === item
              ? 'border-[#16324d] bg-[#16324d] text-white'
              : 'border-slate-200 bg-white text-[#35516b] hover:bg-[#eef4f9]'
          "
          @click="applySourceSuggestion(item)"
        >
          {{ item }}
        </button>
      </div>
      <textarea
        v-model="reservationDraft.notes"
        rows="3"
        class="rounded-[18px] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
        :placeholder="activeTypeCopy.notesPlaceholder"
      ></textarea>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="item in noteSuggestions"
          :key="item"
          type="button"
          class="rounded-full border px-3 py-1 text-xs transition"
          :class="
            (reservationDraft.notes ?? '').includes(item)
              ? 'border-[#16324d] bg-[#16324d] text-white'
              : 'border-slate-200 bg-white text-[#35516b] hover:bg-[#eef4f9]'
          "
          @click="appendNoteSuggestion(item)"
        >
          {{ item }}
        </button>
      </div>
      <div
        class="rounded-[16px] border px-4 py-3 text-xs leading-5"
        :class="
          !props.workspace || props.saving || validationMessage
            ? 'border-amber-200 bg-amber-50 text-amber-700'
            : 'border-[#dfe8f1] bg-white text-slate-500'
        "
      >
        {{ submissionHint }}
      </div>
      <div class="flex flex-wrap gap-3">
        <button
          type="button"
          class="flex-1 rounded-[18px] border border-[#16324d] bg-[#16324d] px-4 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="!props.workspace || props.saving || !canSubmit"
          @click="submitReservation"
        >
          添加到工作区
        </button>
        <button
          type="button"
          class="rounded-[18px] border border-[#d7e2ec] bg-white px-4 py-3 text-sm font-medium text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="resetDraftAndTemplate"
        >
          清空表单
        </button>
      </div>
    </div>
  </div>
</template>
