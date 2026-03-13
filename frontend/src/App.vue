<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";

import { generatePlan, getIntegrationStatus } from "./api/planning";
import AgentTrace from "./components/AgentTrace.vue";
import AmapMap from "./components/AmapMap.vue";
import DailyItinerarySection from "./components/DailyItinerarySection.vue";
import LandingHero from "./components/LandingHero.vue";
import IntegrationPrecheckPanel from "./components/IntegrationPrecheckPanel.vue";
import NotificationModal from "./components/NotificationModal.vue";
import PlannerLaunchPanel from "./components/PlannerLaunchPanel.vue";
import ResultSidebar from "./components/ResultSidebar.vue";
import TravelTonePanel from "./components/TravelTonePanel.vue";
import type {
  IntegrationStatus,
  PlanningResponse,
  TripPlanningRequest,
  TravelerProfile,
} from "./types/planning";

const showDevPanels = import.meta.env.VITE_SHOW_DEV_PANELS === "true";
const interestOptions = [
  "自然风光",
  "历史文化",
  "美食探索",
  "拍照打卡",
  "夜游休闲",
  "艺术展览",
];
const transportOptions = ["公共交通", "打车", "自驾", "步行", "骑行"];
const hotelOptions = ["经济型酒店", "舒适型酒店", "精品民宿", "高端度假酒店"];
const paceOptions: Array<{
  label: string;
  value: TripPlanningRequest["pace"];
}> = [
  { label: "轻松", value: "relaxed" },
  { label: "均衡", value: "balanced" },
  { label: "紧凑", value: "intense" },
];
const budgetOptions: Array<{
  label: string;
  value: TripPlanningRequest["budget_level"];
}> = [
  { label: "经济型", value: "economy" },
  { label: "舒适型", value: "comfort" },
  { label: "品质型", value: "luxury" },
];
const stageOptions = [
  "生成初步计划",
  "搜索景点与餐饮",
  "获取天气与路线",
  "整合最终行程",
];

const today = formatDate(new Date());
const form = reactive<TripPlanningRequest>({
  origin: "",
  destination: "",
  start_date: today,
  days: 3,
  interests: ["自然风光"],
  must_visit: [],
  pace: "balanced",
  budget_level: "comfort",
  transport_preferences: [],
  hotel_style: "舒适型酒店",
  dining_preferences: [],
  travelers: { adults: 1, children: 0, seniors: 0 },
  notes: "",
});

const startDate = ref(form.start_date);
const endDate = ref(addDays(form.start_date, form.days - 1));
const mustVisitText = ref(form.must_visit.join("、"));
const diningText = ref(form.dining_preferences.join("、"));
const loading = ref(false);
const progress = ref(0);
const progressLabel = ref(stageOptions[0]);
const result = ref<PlanningResponse | null>(null);
const exportRoot = ref<HTMLElement | null>(null);
const integrationStatus = ref<IntegrationStatus>(
  createEmptyIntegrationStatus(),
);
const integrationLoading = ref(false);
const integrationError = ref("");
const expandedDays = ref<number[]>([]);
const noticeModal = reactive({
  open: false,
  tone: "warning" as "success" | "warning" | "error",
  title: "",
  messages: [] as string[],
});
let progressTimer: number | null = null;

const currentIntegrationStatus = computed(
  () => result.value?.integration_status ?? integrationStatus.value,
);
const travelerSummary = computed(() => formatTravelers(form.travelers));
const budgetCards = computed<Array<[string, string]>>(() => {
  const budget = result.value?.plan.estimated_budget;
  return budget
    ? [
        ["景点门票", budget.tickets],
        ["酒店住宿", budget.accommodation],
        ["餐饮费用", budget.food],
        ["交通费用", budget.transport],
      ]
    : [];
});
const inputSummary = computed(() => [
  {
    label: "路线",
    value: `${form.origin?.trim() || "本地出发"} → ${form.destination || "待填写"}`,
  },
  { label: "日期", value: `${startDate.value} - ${endDate.value}` },
  { label: "同行", value: travelerSummary.value },
  { label: "节奏", value: paceLabel(form.pace) },
  { label: "预算", value: budgetLabel(form.budget_level) },
  { label: "住宿", value: form.hotel_style || "未设置" },
]);
const summaryTags = computed(() =>
  [
    ...new Set([
      ...form.interests.slice(0, 3),
      ...form.transport_preferences.slice(0, 2),
    ]),
  ].slice(0, 5),
);

watch([startDate, endDate], ([start, end]) => {
  if (!start) return;
  if (!end || end < start) {
    endDate.value = start;
    form.days = 1;
    form.start_date = start;
    return;
  }
  form.start_date = start;
  form.days = Math.min(14, Math.max(1, diffDays(start, end)));
});
watch(
  () => form.days,
  (days) => {
    const safe = Math.min(14, Math.max(1, Number(days) || 1));
    if (safe !== days) {
      form.days = safe;
      return;
    }
    endDate.value = addDays(startDate.value, safe - 1);
  },
);

onMounted(() => {
  if (showDevPanels) void loadIntegrationStatus();
});

function openNotice(
  tone: "success" | "warning" | "error",
  title: string,
  messages: string[],
) {
  if (!messages.length) return;
  noticeModal.tone = tone;
  noticeModal.title = title;
  noticeModal.messages = [...new Set(messages.filter(Boolean))];
  noticeModal.open = true;
}
function closeNotice() {
  noticeModal.open = false;
  noticeModal.tone = "warning";
  noticeModal.title = "";
  noticeModal.messages = [];
}
function toUserNotice(message: string) {
  const lower = message.toLowerCase();
  if (
    lower.includes("weather_agent") ||
    lower.includes("maps_weather") ||
    lower.includes("forecast") ||
    lower.includes("天气")
  ) {
    return "天气数据暂时不可用，系统已使用现有信息继续完成本次规划。";
  }
  if (
    lower.includes("route") ||
    lower.includes("driving") ||
    lower.includes("walking") ||
    lower.includes("transit") ||
    lower.includes("路线")
  ) {
    return "部分路线数据暂时不可用，系统已保留基础行程安排。";
  }
  if (lower.includes("hotel") || lower.includes("住宿")) {
    return "住宿推荐数据暂时不完整，系统已提供当前可用建议。";
  }
  if (
    lower.includes("poi") ||
    lower.includes("restaurant") ||
    lower.includes("maps_text_search") ||
    lower.includes("景点") ||
    lower.includes("餐饮")
  ) {
    return "部分景点或餐饮数据暂时不可用，系统已尽量补全本次规划。";
  }
  if (lower.includes("llm") || lower.includes("大模型")) {
    return "智能生成阶段使用了备用方案，但行程仍已成功生成。";
  }
  return "本次规划过程中有部分数据暂时不可用，系统已尽量完成行程。";
}
function toUserError(message: string) {
  const lower = message.toLowerCase();
  if (
    lower.includes("timeout") ||
    lower.includes("connection") ||
    lower.includes("network") ||
    lower.includes("connect")
  ) {
    return "当前网络或服务连接异常，请稍后重试。";
  }
  return "行程暂时生成失败，请稍后重试。";
}
function buildPlanNotices(response: PlanningResponse) {
  const warnings = [
    ...response.meta.warnings,
    ...response.integration_status.warnings,
  ].filter(Boolean);
  return [...new Set(warnings.map(toUserNotice))];
}

function createEmptyIntegrationStatus(): IntegrationStatus {
  return {
    mcp_enabled: false,
    mcp_connected: false,
    mcp_command: "",
    llm_enabled: false,
    llm_reachable: false,
    llm_model: "",
    llm_base_url: "",
    available_tools: [],
    resolved_tools: {},
    missing_tools: [],
    map_rendering_enabled: false,
    map_js_key_configured: false,
    security_js_code_configured: false,
    mock_enabled: true,
    warnings: [],
  };
}
async function loadIntegrationStatus() {
  integrationLoading.value = true;
  integrationError.value = "";
  try {
    integrationStatus.value = await getIntegrationStatus();
  } catch (error) {
    integrationError.value =
      error instanceof Error
        ? error.message
        : "获取集成状态失败，请检查后端服务。";
    integrationStatus.value = createEmptyIntegrationStatus();
    if (showDevPanels) {
      openNotice("warning", "暂时无法获取集成状态", [
        "请检查后端服务和地图配置后再试。",
      ]);
    }
  } finally {
    integrationLoading.value = false;
  }
}
function formatDate(date: Date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
function createDate(dateString: string) {
  const [year, month, day] = dateString.split("-").map(Number);
  return new Date(year, month - 1, day, 12, 0, 0);
}
function addDays(dateString: string, days: number) {
  const base = createDate(dateString);
  base.setDate(base.getDate() + Math.max(0, days));
  return formatDate(base);
}
function diffDays(start: string, end: string) {
  return (
    Math.floor(
      (createDate(end).getTime() - createDate(start).getTime()) / 86400000,
    ) + 1
  );
}
function toggleSelection(list: string[], value: string) {
  const index = list.indexOf(value);
  if (index >= 0) list.splice(index, 1);
  else list.push(value);
}
function splitText(value: string) {
  return value
    .split(/[\n,，、;；]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
function startProgress() {
  progress.value = 8;
  progressLabel.value = stageOptions[0];
  if (progressTimer) window.clearInterval(progressTimer);
  progressTimer = window.setInterval(() => {
    progress.value = Math.min(
      progress.value + (progress.value < 40 ? 8 : progress.value < 74 ? 5 : 3),
      92,
    );
    const stageIndex =
      progress.value > 74
        ? 3
        : progress.value > 52
          ? 2
          : progress.value > 24
            ? 1
            : 0;
    progressLabel.value = stageOptions[stageIndex];
  }, 360);
}
function stopProgress(success = true) {
  if (progressTimer) window.clearInterval(progressTimer);
  progressTimer = null;
  progress.value = success ? 100 : 0;
  progressLabel.value = success ? "规划完成" : "规划失败";
  if (success)
    window.setTimeout(() => {
      progress.value = 0;
    }, 900);
}
async function submitPlan() {
  loading.value = true;
  form.must_visit = splitText(mustVisitText.value);
  form.dining_preferences = splitText(diningText.value);
  startProgress();
  try {
    result.value = await generatePlan({
      ...form,
      origin: form.origin?.trim() || null,
      hotel_style: form.hotel_style || "舒适型酒店",
      interests: [...form.interests],
      must_visit: [...form.must_visit],
      transport_preferences: [...form.transport_preferences],
      dining_preferences: [...form.dining_preferences],
      travelers: {
        adults: Number(form.travelers.adults) || 1,
        children: Number(form.travelers.children) || 0,
        seniors: Number(form.travelers.seniors) || 0,
      },
    });
    integrationStatus.value = result.value.integration_status;
    expandedDays.value = [];
    stopProgress(true);
    const notices = buildPlanNotices(result.value);
    if (notices.length) {
      openNotice("warning", "本次规划已完成", notices);
    }
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "生成行程失败，请稍后重试。";
    stopProgress(false);
    openNotice("error", "规划失败", [toUserError(message)]);
    console.error("plan generation failed", error);
  } finally {
    loading.value = false;
  }
}
function resetPlanner() {
  result.value = null;
  expandedDays.value = [];
}
async function exportAs(type: "png" | "pdf") {
  if (!exportRoot.value || !result.value) return;
  const previousExpandedDays = [...expandedDays.value];
  expandedDays.value = result.value.plan.days.map((day) => day.day_number);
  await nextTick();
  try {
    const canvas = await html2canvas(exportRoot.value, {
      scale: 2,
      backgroundColor: "#eef4f9",
    });
    if (type === "png") {
      const link = document.createElement("a");
      link.download = `${result.value.request_echo.destination}-smart-itinerary.png`;
      link.href = canvas.toDataURL("image/png");
      link.click();
      return;
    }
    const imageData = canvas.toDataURL("image/png");
    const pdf = new jsPDF("p", "mm", "a4");
    const width = pdf.internal.pageSize.getWidth();
    const height = pdf.internal.pageSize.getHeight();
    const imageHeight = (canvas.height * width) / canvas.width;
    let position = 0;
    pdf.addImage(imageData, "PNG", 0, position, width, imageHeight);
    while (imageHeight - position > height) {
      position -= height;
      pdf.addPage();
      pdf.addImage(imageData, "PNG", 0, position, width, imageHeight);
    }
    pdf.save(`${result.value.request_echo.destination}-smart-itinerary.pdf`);
  } finally {
    expandedDays.value = previousExpandedDays;
    await nextTick();
  }
}
function toggleDay(dayNumber: number) {
  expandedDays.value = expandedDays.value.includes(dayNumber)
    ? expandedDays.value.filter((item) => item !== dayNumber)
    : [...expandedDays.value, dayNumber];
}
function formatTravelers(travelers: TravelerProfile) {
  const parts: string[] = [];
  if (travelers.adults) parts.push(`${travelers.adults} 位成人`);
  if (travelers.children) parts.push(`${travelers.children} 位儿童`);
  if (travelers.seniors) parts.push(`${travelers.seniors} 位长者`);
  return parts.join(" · ") || "1 位成人";
}
function paceLabel(value: TripPlanningRequest["pace"]) {
  return paceOptions.find((item) => item.value === value)?.label ?? value;
}
function budgetLabel(value: TripPlanningRequest["budget_level"]) {
  return budgetOptions.find((item) => item.value === value)?.label ?? value;
}
</script>
<template>
  <div class="min-h-screen bg-[#eef4f9] text-ink">
    <div class="mx-auto max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8">
      <section
        v-if="!result"
        class="flex min-h-[calc(100vh-3rem)] flex-col justify-center gap-8"
      >
        <LandingHero :summary-tags="summaryTags" />

        <section class="grid gap-6 xl:grid-cols-[1.18fr_0.82fr]">
          <article
            class="rounded-[36px] border border-white/70 bg-white/86 p-6 shadow-card sm:p-8"
          >
            <div class="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">
                  Trip Brief
                </div>
                <h2 class="mt-3 text-2xl font-semibold text-ink sm:text-[30px]">
                  先把你的旅行偏好讲清楚
                </h2>
              </div>
              <div
                class="rounded-full border border-[#d7e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b]"
              >
                {{ form.days }} 天 · {{ paceLabel(form.pace) }}节奏
              </div>
            </div>
            <div class="mt-6 grid gap-4 lg:grid-cols-4">
              <label class="text-sm text-slate-600 lg:col-span-2"
                ><span class="mb-2 block">目的地城市</span
                ><input
                  v-model="form.destination"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label
              ><label class="text-sm text-slate-600"
                ><span class="mb-2 block">出发城市</span
                ><input
                  v-model="form.origin"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label
              ><label class="text-sm text-slate-600"
                ><span class="mb-2 block">开始日期</span
                ><input
                  v-model="startDate"
                  type="date"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
              /></label>
            </div>
            <div class="mt-4 grid gap-4 lg:grid-cols-4">
              <label class="text-sm text-slate-600"
                ><span class="mb-2 block">结束日期</span
                ><input
                  v-model="endDate"
                  type="date"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label
              ><label class="text-sm text-slate-600"
                ><span class="mb-2 block">成人</span
                ><input
                  v-model.number="form.travelers.adults"
                  type="number"
                  min="1"
                  max="10"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label
              ><label class="text-sm text-slate-600"
                ><span class="mb-2 block">儿童</span
                ><input
                  v-model.number="form.travelers.children"
                  type="number"
                  min="0"
                  max="6"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label
              ><label class="text-sm text-slate-600"
                ><span class="mb-2 block">长者</span
                ><input
                  v-model.number="form.travelers.seniors"
                  type="number"
                  min="0"
                  max="4"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
              /></label>
            </div>
            <div class="mt-6">
              <div class="text-sm font-medium text-slate-600">兴趣偏好</div>
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
              <label class="text-sm text-slate-600"
                ><span class="mb-2 block">必打卡景点</span
                ><textarea
                  v-model="mustVisitText"
                  rows="3"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
                ></textarea></label
              ><label class="text-sm text-slate-600"
                ><span class="mb-2 block">餐饮偏好</span
                ><textarea
                  v-model="diningText"
                  rows="3"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
                ></textarea>
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
              <label class="text-sm text-slate-600"
                ><span class="mb-2 block">住宿风格</span
                ><select
                  v-model="form.hotel_style"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
                >
                  <option value="">请选择住宿风格</option>
                  <option v-for="item in hotelOptions" :key="item" :value="item">
                    {{ item }}
                  </option></select
              ></label>
            </div>
            <div class="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div>
                <div class="text-sm font-medium text-slate-600">交通偏好</div>
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
              <label class="text-sm text-slate-600"
                ><span class="mb-2 block">补充说明</span
                ><textarea
                  v-model="form.notes"
                  rows="4"
                  class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"
                ></textarea>
              </label>
            </div>
          </article>
          <div class="flex flex-col gap-6">
            <TravelTonePanel
              :destination="form.destination"
              :interests="form.interests"
              :hotel-style="form.hotel_style"
              :transport-preferences="form.transport_preferences"
            />
            <PlannerLaunchPanel
              :input-summary="inputSummary"
              :progress="progress"
              :progress-label="progressLabel"
              :loading="loading"
              :can-submit="Boolean(form.destination)"
              compact
              @submit="submitPlan"
            />
            <IntegrationPrecheckPanel
              v-if="showDevPanels"
              :integration-status="currentIntegrationStatus"
              :integration-loading="integrationLoading"
              @refresh="loadIntegrationStatus"
            />
          </div>
        </section>
      </section>
      <section v-else ref="exportRoot" class="space-y-6">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
            @click="resetPlanner"
          >
            重新规划
          </button>
          <div class="flex flex-wrap gap-3">
            <button
              type="button"
              class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
              @click="exportAs('png')"
            >
              导出图片</button
            ><button
              type="button"
              class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card"
              @click="exportAs('pdf')"
            >
              导出 PDF
            </button>
          </div>
        </div>
        <article
          class="rounded-[36px] border border-[#16324d] bg-[#16324d] p-6 text-white shadow-[0_30px_90px_rgba(22,50,77,0.14)] sm:p-8"
        >
          <div class="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div>
              <div class="text-xs uppercase tracking-[0.28em] text-white/55">
                Overview
              </div>
              <h2 class="mt-3 text-3xl font-semibold sm:text-[38px]">
                {{ result.plan.title }}
              </h2>
              <p class="mt-4 max-w-3xl text-sm leading-7 text-white/78">
                {{ result.plan.summary }}
              </p>
              <div class="mt-6 flex flex-wrap gap-2 text-sm">
                <span
                  class="rounded-full border border-white/16 bg-white/10 px-4 py-2"
                  >{{ result.request_echo.days }} 天</span
                ><span
                  class="rounded-full border border-white/16 bg-white/10 px-4 py-2"
                  >{{ result.request_echo.destination }}</span
                ><span
                  class="rounded-full border border-white/16 bg-white/10 px-4 py-2"
                  >{{ paceLabel(result.request_echo.pace) }}</span
                ><span
                  class="rounded-full border border-white/16 bg-white/10 px-4 py-2"
                  >{{ budgetLabel(result.request_echo.budget_level) }}</span
                >
              </div>
            </div>
            <div class="grid gap-4 sm:grid-cols-2">
              <div
                class="rounded-[24px] border border-white/10 bg-white/10 px-4 py-4"
              >
                <div class="text-xs uppercase tracking-[0.18em] text-white/55">
                  预算总计
                </div>
                <div class="mt-3 text-2xl font-semibold">
                  {{ result.plan.estimated_budget.total_estimate }}
                </div>
              </div>
              <div
                class="rounded-[24px] border border-white/10 bg-white/10 px-4 py-4"
              >
                <div class="text-xs uppercase tracking-[0.18em] text-white/55">
                  天气摘要
                </div>
                <div class="mt-3 text-sm leading-6 text-white/80">
                  {{ result.plan.weather_summary }}
                </div>
              </div>
              <div
                class="rounded-[24px] border border-white/10 bg-white/10 px-4 py-4 sm:col-span-2"
              >
                <div class="text-xs uppercase tracking-[0.18em] text-white/55">
                  预订提示
                </div>
                <div class="mt-3 text-sm leading-6 text-white/80">
                  {{ result.plan.best_booking_tip }}
                </div>
              </div>
            </div>
          </div>
        </article>
        <section class="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
          <div class="space-y-6">
            <article
              class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"
            >
              <div class="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div
                    class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]"
                  >
                    Map
                  </div>
                  <h2 class="mt-3 text-2xl font-semibold text-ink">
                    景点信息和地图标记
                  </h2>
                </div>
                <span
                  class="rounded-full border border-[#d6e2ec] bg-[#eef4f9] px-4 py-2 text-sm text-[#35516b]"
                  >{{
                    result.planning_context.attractions.length
                  }}
                  个景点点位</span
                >
              </div>
              <div class="mt-5">
                <AmapMap
                  :map-config="result.map_config"
                  :pois="result.planning_context.attractions"
                  :routes="result.planning_context.routes"
                />
              </div>
            </article>
            <DailyItinerarySection
              :days="result.plan.days"
              :routes="result.planning_context.routes"
              :weather-forecasts="
                result.planning_context.weather.daily_forecasts
              "
              :restaurants="result.planning_context.restaurants"
              :expanded-days="expandedDays"
              @toggle="toggleDay"
            />
          </div>
          <ResultSidebar
            :budget-cards="budgetCards"
            :plan="result.plan"
            :show-dev-panels="showDevPanels"
            :integration-status="currentIntegrationStatus"
          />
        </section>
        <section v-if="showDevPanels" class="grid gap-6 xl:grid-cols-2">
          <div
            class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"
          >
            <div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">
              Agent Trace
            </div>
            <h2 class="mt-3 text-2xl font-semibold text-ink">Agent 调用轨迹</h2>
            <div class="mt-5 space-y-3">
              <div
                v-for="item in result.agent_trace"
                :key="item.agent_name"
                class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4 text-sm text-slate-600"
              >
                <div class="flex items-start justify-between gap-4">
                  <div>
                    <div class="font-medium text-ink">
                      {{ item.agent_name }}
                    </div>
                    <div class="mt-2">{{ item.summary }}</div>
                  </div>
                  <span
                    class="rounded-full px-3 py-1 text-xs"
                    :class="
                      item.success
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-rose-100 text-rose-700'
                    "
                    >{{ item.success ? "SUCCESS" : "FAILED" }}</span
                  >
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                  <span
                    class="rounded-full bg-white px-3 py-1 text-xs shadow-sm"
                    >{{ item.used_llm ? "LLM" : "RULE" }}</span
                  ><span
                    v-for="tool in item.used_tools"
                    :key="tool"
                    class="rounded-full bg-white px-3 py-1 text-xs shadow-sm"
                    >{{ tool }}</span
                  >
                </div>
              </div>
            </div>
          </div>
          <AgentTrace :result="result" />
        </section>
      </section>
    </div>
  </div>
  <NotificationModal
    :open="noticeModal.open"
    :tone="noticeModal.tone"
    :title="noticeModal.title"
    :messages="noticeModal.messages"
    @close="closeNotice"
  />
</template>
