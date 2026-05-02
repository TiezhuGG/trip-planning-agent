<script setup lang="ts">
import { computed } from "vue";

import type { PlannerInputCheck } from "../composables/usePlannerDerivedState";
import { createInitialTripPlanningRequest } from "../composables/plannerPageOptions";
import type { TripPlanningRequest } from "../types/planning";
import { addDays, formatDate, splitText } from "../utils/tripPlannerForm";

type PlannerOption<T> = {
  label: string;
  value: T;
};

type TravelerPreset = {
  label: string;
  adults: number;
  children: number;
  seniors: number;
};

type PlanningScenarioPreset = {
  label: string;
  summary: string;
  interests: string[];
  pace: TripPlanningRequest["pace"];
  budgetLevel: TripPlanningRequest["budget_level"];
  transportPreferences: string[];
  hotelStyle: string;
  notes: string;
};

const props = defineProps<{
  form: TripPlanningRequest;
  interestOptions: string[];
  transportOptions: string[];
  hotelOptions: string[];
  paceOptions: PlannerOption<TripPlanningRequest["pace"]>[];
  budgetOptions: PlannerOption<TripPlanningRequest["budget_level"]>[];
  planningChecks: PlannerInputCheck[];
  canSubmit: boolean;
  submitHint: string;
  paceLabel: (value: TripPlanningRequest["pace"]) => string;
  toggleSelection: (list: string[], value: string) => void;
}>();

const startDate = defineModel<string>("startDate", { required: true });
const endDate = defineModel<string>("endDate", { required: true });
const mustVisitText = defineModel<string>("mustVisitText", { required: true });
const diningText = defineModel<string>("diningText", { required: true });

const datePresets = [
  { label: "周末 2 天", days: 2 },
  { label: "短途 3 天", days: 3 },
  { label: "深度 5 天", days: 5 },
  { label: "长线 7 天", days: 7 },
];

const travelerPresets: TravelerPreset[] = [
  { label: "单人", adults: 1, children: 0, seniors: 0 },
  { label: "双人", adults: 2, children: 0, seniors: 0 },
  { label: "亲子", adults: 2, children: 1, seniors: 0 },
  { label: "三代同行", adults: 2, children: 1, seniors: 2 },
];

const mustVisitSuggestions = ["老城核心", "地标景点", "博物馆", "夜景机位", "本地市场"];
const diningSuggestions = ["本地小馆", "咖啡店", "夜宵", "不吃辣", "亲子友好", "少排队"];
const noteSuggestions = [
  "尽量少排队",
  "酒店靠近地铁",
  "每天留出午休时间",
  "晚上预留自由活动",
  "减少跨城区往返",
];

const scenarioPresets: PlanningScenarioPreset[] = [
  {
    label: "城市周末",
    summary: "适合 2 到 3 天高效串联城市核心体验。",
    interests: ["历史文化", "美食探索", "拍照打卡"],
    pace: "balanced",
    budgetLevel: "comfort",
    transportPreferences: ["公共交通", "步行"],
    hotelStyle: "舒适型酒店",
    notes: "优先串联城市核心区域，减少折返。",
  },
  {
    label: "亲子慢游",
    summary: "更重视节奏舒缓、交通轻松和停留体验。",
    interests: ["自然风光", "艺术展览", "拍照打卡"],
    pace: "relaxed",
    budgetLevel: "comfort",
    transportPreferences: ["打车", "公共交通"],
    hotelStyle: "舒适型酒店",
    notes: "尽量减少暴走和频繁换点，优先安排亲子友好场所。",
  },
  {
    label: "美食打卡",
    summary: "把城市味觉体验和街区漫游放在前面。",
    interests: ["美食探索", "夜游休闲", "拍照打卡"],
    pace: "balanced",
    budgetLevel: "comfort",
    transportPreferences: ["步行", "打车"],
    hotelStyle: "精品民宿",
    notes: "每天下午和晚上多预留餐饮与街区探索时间。",
  },
  {
    label: "长者轻松",
    summary: "控制步行和换乘强度，优先舒适和稳定。",
    interests: ["历史文化", "自然风光"],
    pace: "relaxed",
    budgetLevel: "comfort",
    transportPreferences: ["打车", "公共交通"],
    hotelStyle: "舒适型酒店",
    notes: "优先安排少换乘、休息点充足、步行距离更短的路线。",
  },
];

const defaultRequest = createInitialTripPlanningRequest();
const mustVisitItems = computed(() => splitText(mustVisitText.value));
const diningPreferenceItems = computed(() => splitText(diningText.value));

function applyDatePreset(days: number) {
  const safeStartDate = startDate.value || formatDate(new Date());
  startDate.value = safeStartDate;
  endDate.value = addDays(safeStartDate, Math.max(days, 1) - 1);
}

function isDatePresetActive(days: number) {
  return props.form.days === days;
}

function applyTravelerPreset(preset: TravelerPreset) {
  props.form.travelers.adults = preset.adults;
  props.form.travelers.children = preset.children;
  props.form.travelers.seniors = preset.seniors;
}

function isTravelerPresetActive(preset: TravelerPreset) {
  return (
    props.form.travelers.adults === preset.adults &&
    props.form.travelers.children === preset.children &&
    props.form.travelers.seniors === preset.seniors
  );
}

function normalizeTravelerCount(
  key: keyof TripPlanningRequest["travelers"],
  min: number,
  max: number,
) {
  const currentValue = Number(props.form.travelers[key]);
  if (Number.isNaN(currentValue)) {
    props.form.travelers[key] = min;
    return;
  }
  props.form.travelers[key] = Math.min(max, Math.max(min, currentValue));
}

function resetPreferenceProfile() {
  props.form.interests = [...defaultRequest.interests];
  props.form.transport_preferences = [...defaultRequest.transport_preferences];
  props.form.pace = defaultRequest.pace;
  props.form.budget_level = defaultRequest.budget_level;
  props.form.hotel_style = defaultRequest.hotel_style;
  props.form.travelers = { ...defaultRequest.travelers };
  props.form.notes = "";
  props.form.must_visit = [];
  props.form.dining_preferences = [];
  mustVisitText.value = "";
  diningText.value = "";
}

function clearMustVisitAndDining() {
  props.form.must_visit = [];
  props.form.dining_preferences = [];
  props.form.notes = "";
  mustVisitText.value = "";
  diningText.value = "";
}

function swapRoute() {
  const origin = (props.form.origin ?? "").trim();
  const destination = props.form.destination.trim();
  props.form.origin = destination;
  props.form.destination = origin;
}

function syncDelimitedText(model: "must-visit" | "dining", items: string[]) {
  const nextValue = items.join("、");
  if (model === "must-visit") {
    mustVisitText.value = nextValue;
    props.form.must_visit = [...items];
    return;
  }
  diningText.value = nextValue;
  props.form.dining_preferences = [...items];
}

function removeDelimitedItem(model: "must-visit" | "dining", item: string) {
  const source = model === "must-visit" ? mustVisitItems.value : diningPreferenceItems.value;
  syncDelimitedText(
    model,
    source.filter((current) => current !== item),
  );
}

function appendDelimitedItem(model: "must-visit" | "dining", item: string) {
  const source = model === "must-visit" ? mustVisitItems.value : diningPreferenceItems.value;
  if (source.includes(item)) return;
  syncDelimitedText(model, [...source, item]);
}

function hasDelimitedItem(model: "must-visit" | "dining", item: string) {
  const source = model === "must-visit" ? mustVisitItems.value : diningPreferenceItems.value;
  return source.includes(item);
}

function toggleDelimitedItem(model: "must-visit" | "dining", item: string) {
  if (hasDelimitedItem(model, item)) {
    removeDelimitedItem(model, item);
    return;
  }
  appendDelimitedItem(model, item);
}

function resolveNoteSegments() {
  return (props.form.notes ?? "")
    .split(/[\n，。！？；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function syncNoteSegments(items: string[]) {
  props.form.notes = items.join("；");
}

function hasNoteSnippet(snippet: string) {
  return resolveNoteSegments().includes(snippet);
}

function toggleNoteSnippet(snippet: string) {
  const segments = resolveNoteSegments();
  if (segments.includes(snippet)) {
    syncNoteSegments(segments.filter((item) => item !== snippet));
    return;
  }
  syncNoteSegments([...segments, snippet]);
}

function applyScenarioPreset(preset: PlanningScenarioPreset) {
  props.form.interests = [...preset.interests];
  props.form.pace = preset.pace;
  props.form.budget_level = preset.budgetLevel;
  props.form.transport_preferences = [...preset.transportPreferences];
  props.form.hotel_style = preset.hotelStyle;
  props.form.notes = preset.notes;
}

function isScenarioPresetActive(preset: PlanningScenarioPreset) {
  return (
    JSON.stringify(props.form.interests) === JSON.stringify(preset.interests) &&
    props.form.pace === preset.pace &&
    props.form.budget_level === preset.budgetLevel &&
    JSON.stringify(props.form.transport_preferences) ===
      JSON.stringify(preset.transportPreferences) &&
    props.form.hotel_style === preset.hotelStyle &&
    (props.form.notes ?? "") === preset.notes
  );
}
</script>

<template>
  <article class="rounded-[36px] border border-white/70 bg-white/86 p-6 shadow-card sm:p-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">行程简述</div>
        <h2 class="mt-3 text-2xl font-semibold text-ink sm:text-[30px]">
          先把你的旅行偏好讲清楚
        </h2>
      </div>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <div class="rounded-full border border-[#d7e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b]">
          {{ form.days }} 天 · {{ paceLabel(form.pace) }}节奏
        </div>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-4 py-2 text-sm text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="clearMustVisitAndDining"
        >
          清空景点与备注
        </button>
        <button
          type="button"
          class="rounded-full border border-[#d7e2ec] bg-white px-4 py-2 text-sm text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="resetPreferenceProfile"
        >
          恢复默认偏好
        </button>
      </div>
    </div>

    <div
      class="mt-5 rounded-[24px] border px-4 py-4 text-sm"
      :class="
        canSubmit
          ? 'border-[#dbe5ef] bg-[#f8fbfd] text-slate-600'
          : 'border-amber-200 bg-amber-50 text-amber-900'
      "
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="font-medium text-ink">输入体检</div>
          <div class="mt-1 text-xs leading-5">
            {{ submitHint }}
          </div>
        </div>
        <span
          class="rounded-full px-3 py-1 text-xs"
          :class="
            canSubmit
              ? 'bg-white text-[#35516b]'
              : 'bg-white/80 text-amber-800'
          "
        >
          {{ canSubmit ? "可提交" : "待补全" }}
        </span>
      </div>

      <div class="mt-3 space-y-2">
        <div
          v-for="item in planningChecks"
          :key="`${item.tone}-${item.text}`"
          class="rounded-[18px] px-3 py-3 text-xs leading-5"
          :class="
            item.tone === 'blocking'
              ? 'border border-amber-200 bg-white text-amber-800'
              : item.tone === 'warning'
                ? 'border border-[#dfe8f1] bg-white text-slate-600'
                : 'border border-emerald-100 bg-emerald-50 text-emerald-700'
          "
        >
          {{ item.text }}
        </div>
      </div>
      <div class="mt-3 text-[11px] leading-5 text-slate-500">
        未提交的输入会自动保存在当前浏览器，刷新页面后可继续填写；目的地填写正确后，也可以先保存为服务端草稿。
      </div>
    </div>

    <div class="mt-6 grid gap-4 lg:grid-cols-4">
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">目的地城市</span>
        <input
          v-model="form.destination"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          placeholder="例如：杭州"
        />
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">出发城市</span>
        <input
          v-model="form.origin"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          placeholder="例如：上海"
        />
      </label>
      <div class="flex items-end">
        <button
          type="button"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3 text-sm text-[#35516b] transition hover:bg-[#eef4f9]"
          @click="swapRoute"
        >
          交换出发地与目的地
        </button>
      </div>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">开始日期</span>
        <input
          v-model="startDate"
          type="date"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        />
      </label>
    </div>

    <div class="mt-4 rounded-[24px] border border-[#dfe8f1] bg-[#f8fbfd] px-4 py-4">
      <div class="grid gap-4 lg:grid-cols-2">
        <div>
          <div class="text-sm font-medium text-slate-600">天数快捷模版</div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              v-for="item in datePresets"
              :key="item.days"
              type="button"
              class="rounded-full border px-4 py-2 text-sm transition"
              :class="
                isDatePresetActive(item.days)
                  ? 'border-[#16324d] bg-[#16324d] text-white'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
              "
              @click="applyDatePreset(item.days)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
        <div>
          <div class="text-sm font-medium text-slate-600">同行人模版</div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              v-for="item in travelerPresets"
              :key="item.label"
              type="button"
              class="rounded-full border px-4 py-2 text-sm transition"
              :class="
                isTravelerPresetActive(item)
                  ? 'border-[#16324d] bg-[#16324d] text-white'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
              "
              @click="applyTravelerPreset(item)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-4 rounded-[24px] border border-[#dfe8f1] bg-[#f8fbfd] px-4 py-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="text-sm font-medium text-slate-600">一键场景模版</div>
          <div class="mt-1 text-xs text-slate-500">
            快速套用一组常见偏好组合，再按你的目的地微调。
          </div>
        </div>
      </div>
      <div class="mt-3 grid gap-3 lg:grid-cols-2">
        <button
          v-for="item in scenarioPresets"
          :key="item.label"
          type="button"
          class="rounded-[20px] border px-4 py-4 text-left transition"
          :class="
            isScenarioPresetActive(item)
              ? 'border-[#16324d] bg-[#16324d] text-white shadow-sm'
              : 'border-[#d7e2ec] bg-white text-slate-700 hover:border-[#7f97ad] hover:bg-[#fdfefe]'
          "
          @click="applyScenarioPreset(item)"
        >
          <div class="font-medium">{{ item.label }}</div>
          <div
            class="mt-2 text-xs leading-5"
            :class="isScenarioPresetActive(item) ? 'text-white/80' : 'text-slate-500'"
          >
            {{ item.summary }}
          </div>
        </button>
      </div>
    </div>

    <div class="mt-4 grid gap-4 lg:grid-cols-4">
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">结束日期</span>
        <input
          v-model="endDate"
          type="date"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        />
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">成人</span>
        <input
          v-model.number="form.travelers.adults"
          type="number"
          min="1"
          max="10"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          @blur="normalizeTravelerCount('adults', 1, 10)"
        />
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">儿童</span>
        <input
          v-model.number="form.travelers.children"
          type="number"
          min="0"
          max="6"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          @blur="normalizeTravelerCount('children', 0, 6)"
        />
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">长者</span>
        <input
          v-model.number="form.travelers.seniors"
          type="number"
          min="0"
          max="4"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          @blur="normalizeTravelerCount('seniors', 0, 4)"
        />
      </label>
    </div>

    <div class="mt-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="text-sm font-medium text-slate-600">兴趣偏好</div>
        <button
          v-if="form.interests.length"
          type="button"
          class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500 transition hover:bg-[#eef4f9]"
          @click="form.interests = []"
        >
          清空已选
        </button>
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        <button
          v-for="item in interestOptions"
          :key="item"
          type="button"
          class="rounded-full border px-4 py-2 text-sm transition"
          :class="
            form.interests.includes(item)
              ? 'border-[#16324d] bg-[#16324d] text-white'
              : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
          "
          @click="toggleSelection(form.interests, item)"
        >
          {{ item }}
        </button>
      </div>
    </div>

    <div class="mt-6 grid gap-4 lg:grid-cols-2">
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">必打卡景点</span>
        <textarea
          v-model="mustVisitText"
          rows="3"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          placeholder="例如：灵隐寺、西湖、良渚博物院"
        ></textarea>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="item in mustVisitSuggestions"
            :key="item"
            type="button"
            class="rounded-full border px-3 py-1 text-xs transition"
            :class="
              hasDelimitedItem('must-visit', item)
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-slate-200 bg-white text-slate-500 hover:bg-[#eef4f9]'
            "
            @click="toggleDelimitedItem('must-visit', item)"
          >
            {{ item }}
          </button>
        </div>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="item in mustVisitItems"
            :key="item"
            type="button"
            class="rounded-full bg-[#eef4f9] px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#dde9f3]"
            @click="removeDelimitedItem('must-visit', item)"
          >
            {{ item }} ×
          </button>
          <span v-if="!mustVisitItems.length" class="text-xs text-slate-400">
            支持用换行、逗号或顿号分隔多个必去点。
          </span>
        </div>
      </label>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">餐饮偏好</span>
        <textarea
          v-model="diningText"
          rows="3"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          placeholder="例如：本帮菜、咖啡店、夜宵，不吃辣"
        ></textarea>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="item in diningSuggestions"
            :key="item"
            type="button"
            class="rounded-full border px-3 py-1 text-xs transition"
            :class="
              hasDelimitedItem('dining', item)
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-slate-200 bg-white text-slate-500 hover:bg-[#eef4f9]'
            "
            @click="toggleDelimitedItem('dining', item)"
          >
            {{ item }}
          </button>
        </div>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="item in diningPreferenceItems"
            :key="item"
            type="button"
            class="rounded-full bg-[#eef4f9] px-3 py-1 text-xs text-[#35516b] transition hover:bg-[#dde9f3]"
            @click="removeDelimitedItem('dining', item)"
          >
            {{ item }} ×
          </button>
          <span v-if="!diningPreferenceItems.length" class="text-xs text-slate-400">
            可填写口味、忌口、用餐时段或想去的餐厅类型。
          </span>
        </div>
      </label>
    </div>

    <div class="mt-6 grid gap-4 lg:grid-cols-3">
      <div>
        <div class="text-sm font-medium text-slate-600">出行节奏</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="item in paceOptions"
            :key="item.value"
            type="button"
            class="rounded-full border px-4 py-2 text-sm transition"
            :class="
              form.pace === item.value
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
            "
            @click="form.pace = item.value"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
      <div>
        <div class="text-sm font-medium text-slate-600">预算等级</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="item in budgetOptions"
            :key="item.value"
            type="button"
            class="rounded-full border px-4 py-2 text-sm transition"
            :class="
              form.budget_level === item.value
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
            "
            @click="form.budget_level = item.value"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">住宿风格</span>
        <select
          v-model="form.hotel_style"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
        >
          <option value="">请选择住宿风格</option>
          <option v-for="item in hotelOptions" :key="item" :value="item">
            {{ item }}
          </option>
        </select>
      </label>
    </div>

    <div class="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
      <div>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="text-sm font-medium text-slate-600">交通偏好</div>
          <button
            v-if="form.transport_preferences.length"
            type="button"
            class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500 transition hover:bg-[#eef4f9]"
            @click="form.transport_preferences = []"
          >
            清空已选
          </button>
        </div>
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="item in transportOptions"
            :key="item"
            type="button"
            class="rounded-full border px-4 py-2 text-sm transition"
            :class="
              form.transport_preferences.includes(item)
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:border-[#7f97ad]'
            "
            @click="toggleSelection(form.transport_preferences, item)"
          >
            {{ item }}
          </button>
        </div>
      </div>
      <label class="text-sm text-slate-600">
        <span class="mb-2 block">补充说明</span>
        <textarea
          v-model="form.notes"
          rows="4"
          class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
          placeholder="例如：想减少排队、酒店尽量靠近地铁、第三天晚上预留自由活动"
        ></textarea>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="item in noteSuggestions"
            :key="item"
            type="button"
            class="rounded-full border px-3 py-1 text-xs transition"
            :class="
              hasNoteSnippet(item)
                ? 'border-[#16324d] bg-[#16324d] text-white'
                : 'border-slate-200 bg-white text-slate-500 hover:bg-[#eef4f9]'
            "
            @click="toggleNoteSnippet(item)"
          >
            {{ item }}
          </button>
        </div>
        <div class="mt-2 text-xs text-slate-400">
          适合补充节奏、住宿位置、避坑偏好和自由活动窗口。
        </div>
      </label>
    </div>
  </article>
</template>
