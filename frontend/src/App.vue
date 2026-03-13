<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'

import { generatePlan, getIntegrationStatus } from './api/planning'
import AgentTrace from './components/AgentTrace.vue'
import AmapMap from './components/AmapMap.vue'
import type { DayPlan, IntegrationStatus, MealRecommendation, POIRecommendation, PlanningResponse, RouteSummary, TripPlanningRequest, TravelerProfile } from './types/planning'

const showDevPanels = import.meta.env.VITE_SHOW_DEV_PANELS === 'true'
const interestOptions = ['自然风光', '历史文化', '美食探索', '拍照打卡', '夜游休闲', '艺术展览']
const transportOptions = ['公共交通', '打车', '自驾', '步行', '骑行']
const hotelOptions = ['经济型酒店', '舒适型酒店', '精品民宿', '高端度假酒店']
const paceOptions: Array<{ label: string; value: TripPlanningRequest['pace'] }> = [{ label: '轻松', value: 'relaxed' }, { label: '均衡', value: 'balanced' }, { label: '紧凑', value: 'intense' }]
const budgetOptions: Array<{ label: string; value: TripPlanningRequest['budget_level'] }> = [{ label: '经济型', value: 'economy' }, { label: '舒适型', value: 'comfort' }, { label: '品质型', value: 'luxury' }]
const stageOptions = ['生成初步计划', '搜索景点与餐饮', '获取天气与路线', '整合最终行程']
const storyCards = [
  { title: '理解偏好', text: '先整理节奏、预算、必去点和同行画像。' },
  { title: '编排行程', text: '把景点、天气、餐饮与路线整成每日动线。' },
  { title: '直接出发', text: '结果页围绕“今天怎么走”来展示。' },
]

const today = formatDate(new Date())
const form = reactive<TripPlanningRequest>({
  origin: '',
  destination: '',
  start_date: today,
  days: 3,
  interests: [],
  must_visit: [],
  pace: 'balanced',
  budget_level: 'comfort',
  transport_preferences: [],
  hotel_style: '',
  dining_preferences: [],
  travelers: { adults: 1, children: 0, seniors: 0 },
  notes: '',
})

const startDate = ref(form.start_date)
const endDate = ref(addDays(form.start_date, form.days - 1))
const mustVisitText = ref(form.must_visit.join('、'))
const diningText = ref(form.dining_preferences.join('、'))
const loading = ref(false)
const progress = ref(0)
const progressLabel = ref(stageOptions[0])
const errorMessage = ref('')
const result = ref<PlanningResponse | null>(null)
const exportRoot = ref<HTMLElement | null>(null)
const integrationStatus = ref<IntegrationStatus>(createEmptyIntegrationStatus())
const integrationLoading = ref(false)
const integrationError = ref('')
const expandedDays = ref<number[]>([])
let progressTimer: number | null = null

const currentIntegrationStatus = computed(() => result.value?.integration_status ?? integrationStatus.value)
const travelerSummary = computed(() => formatTravelers(form.travelers))
const resultWarnings = computed(() => result.value?.meta.warnings.filter(Boolean) ?? [])
const budgetCards = computed(() => {
  const budget = result.value?.plan.estimated_budget
  return budget ? [['景点门票', budget.tickets], ['酒店住宿', budget.accommodation], ['餐饮费用', budget.food], ['交通费用', budget.transport]] : []
})
const inputSummary = computed(() => [
  { label: '路线', value: `${form.origin?.trim() || '本地出发'} → ${form.destination || '待填写'}` },
  { label: '日期', value: `${startDate.value} - ${endDate.value}` },
  { label: '同行', value: travelerSummary.value },
  { label: '节奏', value: paceLabel(form.pace) },
  { label: '预算', value: budgetLabel(form.budget_level) },
  { label: '住宿', value: form.hotel_style || '未设置' },
])
const summaryTags = computed(() => [...new Set([...form.interests.slice(0, 3), ...form.transport_preferences.slice(0, 2)])].slice(0, 5))
const combinedWarnings = computed(() => [...new Set([...currentIntegrationStatus.value.warnings.filter(Boolean), ...(integrationError.value ? [integrationError.value] : [])])])

watch([startDate, endDate], ([start, end]) => {
  if (!start) return
  if (!end || end < start) {
    endDate.value = start
    form.days = 1
    form.start_date = start
    return
  }
  form.start_date = start
  form.days = Math.min(14, Math.max(1, diffDays(start, end)))
})
watch(() => form.days, (days) => {
  const safe = Math.min(14, Math.max(1, Number(days) || 1))
  if (safe !== days) {
    form.days = safe
    return
  }
  endDate.value = addDays(startDate.value, safe - 1)
})

onMounted(() => {
  if (showDevPanels) void loadIntegrationStatus()
})

function createEmptyIntegrationStatus(): IntegrationStatus {
  return { mcp_enabled: false, mcp_connected: false, mcp_command: '', llm_enabled: false, llm_reachable: false, llm_model: '', llm_base_url: '', available_tools: [], resolved_tools: {}, missing_tools: [], map_rendering_enabled: false, map_js_key_configured: false, security_js_code_configured: false, mock_enabled: true, warnings: [] }
}
async function loadIntegrationStatus() {
  integrationLoading.value = true
  integrationError.value = ''
  try {
    integrationStatus.value = await getIntegrationStatus()
  } catch (error) {
    integrationError.value = error instanceof Error ? error.message : '获取集成状态失败，请检查后端服务。'
    integrationStatus.value = createEmptyIntegrationStatus()
  } finally {
    integrationLoading.value = false
  }
}
function formatDate(date: Date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}
function createDate(dateString: string) {
  const [year, month, day] = dateString.split('-').map(Number)
  return new Date(year, month - 1, day, 12, 0, 0)
}
function addDays(dateString: string, days: number) {
  const base = createDate(dateString)
  base.setDate(base.getDate() + Math.max(0, days))
  return formatDate(base)
}
function diffDays(start: string, end: string) {
  return Math.floor((createDate(end).getTime() - createDate(start).getTime()) / 86400000) + 1
}
function toggleSelection(list: string[], value: string) {
  const index = list.indexOf(value)
  if (index >= 0) list.splice(index, 1)
  else list.push(value)
}
function splitText(value: string) {
  return value.split(/[\n,，、;；]/).map((item) => item.trim()).filter(Boolean)
}
function startProgress() {
  progress.value = 8
  progressLabel.value = stageOptions[0]
  if (progressTimer) window.clearInterval(progressTimer)
  progressTimer = window.setInterval(() => {
    progress.value = Math.min(progress.value + (progress.value < 40 ? 8 : progress.value < 74 ? 5 : 3), 92)
    const stageIndex = progress.value > 74 ? 3 : progress.value > 52 ? 2 : progress.value > 24 ? 1 : 0
    progressLabel.value = stageOptions[stageIndex]
  }, 360)
}
function stopProgress(success = true) {
  if (progressTimer) window.clearInterval(progressTimer)
  progressTimer = null
  progress.value = success ? 100 : 0
  progressLabel.value = success ? '规划完成' : '规划失败'
  if (success) window.setTimeout(() => { progress.value = 0 }, 900)
}
async function submitPlan() {
  loading.value = true
  errorMessage.value = ''
  form.must_visit = splitText(mustVisitText.value)
  form.dining_preferences = splitText(diningText.value)
  startProgress()
  try {
    result.value = await generatePlan({ ...form, origin: form.origin?.trim() || null, hotel_style: form.hotel_style || '舒适型酒店', interests: [...form.interests], must_visit: [...form.must_visit], transport_preferences: [...form.transport_preferences], dining_preferences: [...form.dining_preferences], travelers: { adults: Number(form.travelers.adults) || 1, children: Number(form.travelers.children) || 0, seniors: Number(form.travelers.seniors) || 0 } })
    integrationStatus.value = result.value.integration_status
    expandedDays.value = []
    stopProgress(true)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '生成行程失败，请稍后重试。'
    stopProgress(false)
  } finally {
    loading.value = false
  }
}
function resetPlanner() {
  result.value = null
  errorMessage.value = ''
  expandedDays.value = []
}
async function exportAs(type: 'png' | 'pdf') {
  if (!exportRoot.value || !result.value) return
  const canvas = await html2canvas(exportRoot.value, { scale: 2, backgroundColor: '#edf2f5' })
  if (type === 'png') {
    const link = document.createElement('a')
    link.download = `${result.value.request_echo.destination}-智能行程.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
    return
  }
  const imageData = canvas.toDataURL('image/png')
  const pdf = new jsPDF('p', 'mm', 'a4')
  const width = pdf.internal.pageSize.getWidth()
  const height = pdf.internal.pageSize.getHeight()
  const imageHeight = (canvas.height * width) / canvas.width
  let position = 0
  pdf.addImage(imageData, 'PNG', 0, position, width, imageHeight)
  while (imageHeight - position > height) {
    position -= height
    pdf.addPage()
    pdf.addImage(imageData, 'PNG', 0, position, width, imageHeight)
  }
  pdf.save(`${result.value.request_echo.destination}-智能行程.pdf`)
}
function toggleDay(dayNumber: number) {
  expandedDays.value = expandedDays.value.includes(dayNumber) ? expandedDays.value.filter((item) => item !== dayNumber) : [...expandedDays.value, dayNumber]
}
function isDayExpanded(dayNumber: number) {
  return expandedDays.value.includes(dayNumber)
}
function getDayRoute(day: DayPlan): RouteSummary | null {
  return day.route_summary ?? result.value?.planning_context.routes.find((route) => route.day_number === day.day_number) ?? null
}
function getDayWeather(day: DayPlan) {
  return day.weather ?? result.value?.planning_context.weather.daily_forecasts.find((forecast) => forecast.date === day.date) ?? null
}
function getMealRecommendations(day: DayPlan): Array<MealRecommendation | POIRecommendation> {
  if (day.meals.length) return day.meals
  const restaurants = result.value?.planning_context.restaurants ?? []
  if (!restaurants.length) return []
  const take = Math.min(3, restaurants.length)
  const startIndex = ((day.day_number - 1) * take) % restaurants.length
  return Array.from({ length: take }, (_, index) => restaurants[(startIndex + index) % restaurants.length])
}
function isStructuredMeal(item: MealRecommendation | POIRecommendation): item is MealRecommendation { return 'meal_type' in item }
function mealTitle(item: MealRecommendation | POIRecommendation) { return isStructuredMeal(item) ? `${mealLabel(item.meal_type)} · ${item.venue_name}` : item.name }
function mealSubtitle(item: MealRecommendation | POIRecommendation) { return isStructuredMeal(item) ? [item.cuisine, item.suggestion, item.estimated_cost].filter(Boolean).join(' · ') : [item.address, item.tags.join(' / ')].filter(Boolean).join(' · ') }
function formatTravelers(travelers: TravelerProfile) {
  const parts: string[] = []
  if (travelers.adults) parts.push(`${travelers.adults} 位成人`)
  if (travelers.children) parts.push(`${travelers.children} 位儿童`)
  if (travelers.seniors) parts.push(`${travelers.seniors} 位长者`)
  return parts.join(' · ') || '1 位成人'
}
function paceLabel(value: TripPlanningRequest['pace']) { return paceOptions.find((item) => item.value === value)?.label ?? value }
function budgetLabel(value: TripPlanningRequest['budget_level']) { return budgetOptions.find((item) => item.value === value)?.label ?? value }
function mealLabel(type: string) { return { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' }[type] ?? type }
function routeModeLabel(mode: string) { return { driving: '驾车', transit: '公共交通', walking: '步行', bicycling: '骑行' }[mode] ?? mode }
</script>
<template>
  <div class="min-h-screen bg-[#edf2f5] text-ink">
    <div class="mx-auto max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8">
      <section v-if="!result" class="flex min-h-[calc(100vh-3rem)] flex-col justify-center gap-8">
        <header class="rounded-[40px] bg-[linear-gradient(135deg,rgba(18,45,66,0.98),rgba(40,92,126,0.94)_54%,rgba(182,133,72,0.9))] px-6 py-8 text-white shadow-[0_30px_90px_rgba(23,49,73,0.22)] sm:px-8 lg:px-10 lg:py-10">
          <div class="grid gap-8 xl:grid-cols-[1.1fr_0.9fr] xl:items-end">
            <div>
              <div class="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm text-white/90"><span class="h-2 w-2 rounded-full bg-[#f3d18b]"></span>多 Agent 城市旅行规划</div>
              <h1 class="mt-6 max-w-4xl font-display text-4xl font-semibold leading-tight sm:text-5xl xl:text-[56px]">把一次旅行，整理成真正顺手的每日行动线。</h1>
              <p class="mt-5 max-w-3xl text-sm leading-7 text-white/78 sm:text-base">输入目的地、日期和偏好后，系统会自动联动景点、餐饮、天气与路线信息，生成一份更适合直接执行的多日行程。</p>
              <div class="mt-6 flex flex-wrap gap-2 text-sm text-white/80"><span v-for="tag in summaryTags" :key="tag" class="rounded-full border border-white/18 bg-white/10 px-4 py-2">{{ tag }}</span></div>
            </div>
            <div class="grid gap-4 sm:grid-cols-3 xl:grid-cols-1"><article v-for="card in storyCards" :key="card.title" class="rounded-[26px] border border-white/14 bg-white/10 p-5"><div class="text-xs uppercase tracking-[0.28em] text-white/55">Flow</div><div class="mt-3 text-lg font-semibold text-white">{{ card.title }}</div><p class="mt-2 text-sm leading-6 text-white/72">{{ card.text }}</p></article></div>
          </div>
        </header>

        <section class="grid gap-6 xl:grid-cols-[1.18fr_0.82fr]">
          <article class="rounded-[36px] border border-white/70 bg-white/86 p-6 shadow-card sm:p-8">
            <div class="flex flex-wrap items-start justify-between gap-4"><div><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Trip Brief</div><h2 class="mt-3 text-2xl font-semibold text-ink sm:text-[30px]">先把你的旅行偏好讲清楚</h2></div><div class="rounded-full bg-[#eef4f7] px-4 py-2 text-sm text-[#48637b]">{{ form.days }} 天 · {{ paceLabel(form.pace) }}节奏</div></div>
            <div class="mt-6 grid gap-4 lg:grid-cols-4"><label class="text-sm text-slate-600 lg:col-span-2"><span class="mb-2 block">目的地城市</span><input v-model="form.destination" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label><label class="text-sm text-slate-600"><span class="mb-2 block">出发城市</span><input v-model="form.origin" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label><label class="text-sm text-slate-600"><span class="mb-2 block">开始日期</span><input v-model="startDate" type="date" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label></div>
            <div class="mt-4 grid gap-4 lg:grid-cols-4"><label class="text-sm text-slate-600"><span class="mb-2 block">结束日期</span><input v-model="endDate" type="date" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label><label class="text-sm text-slate-600"><span class="mb-2 block">成人</span><input v-model.number="form.travelers.adults" type="number" min="1" max="10" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label><label class="text-sm text-slate-600"><span class="mb-2 block">儿童</span><input v-model.number="form.travelers.children" type="number" min="0" max="6" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label><label class="text-sm text-slate-600"><span class="mb-2 block">长者</span><input v-model.number="form.travelers.seniors" type="number" min="0" max="4" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3" /></label></div>
            <div class="mt-6"><div class="text-sm font-medium text-slate-600">兴趣偏好</div><div class="mt-3 flex flex-wrap gap-2"><button v-for="item in interestOptions" :key="item" type="button" class="rounded-full border px-4 py-2 text-sm transition" :class="form.interests.includes(item) ? 'border-[#29597d] bg-[#29597d] text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-[#89a4b9]'" @click="toggleSelection(form.interests, item)">{{ item }}</button></div></div>
            <div class="mt-6 grid gap-4 lg:grid-cols-2"><label class="text-sm text-slate-600"><span class="mb-2 block">必打卡景点</span><textarea v-model="mustVisitText" rows="3" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"></textarea></label><label class="text-sm text-slate-600"><span class="mb-2 block">餐饮偏好</span><textarea v-model="diningText" rows="3" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"></textarea></label></div>
            <div class="mt-6 grid gap-4 lg:grid-cols-3"><div><div class="text-sm font-medium text-slate-600">出行节奏</div><div class="mt-3 flex flex-wrap gap-2"><button v-for="item in paceOptions" :key="item.value" type="button" class="rounded-full border px-4 py-2 text-sm transition" :class="form.pace === item.value ? 'border-[#29597d] bg-[#29597d] text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-[#89a4b9]'" @click="form.pace = item.value">{{ item.label }}</button></div></div><div><div class="text-sm font-medium text-slate-600">预算等级</div><div class="mt-3 flex flex-wrap gap-2"><button v-for="item in budgetOptions" :key="item.value" type="button" class="rounded-full border px-4 py-2 text-sm transition" :class="form.budget_level === item.value ? 'border-[#b27a46] bg-[#b27a46] text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-[#c9a178]'" @click="form.budget_level = item.value">{{ item.label }}</button></div></div><label class="text-sm text-slate-600"><span class="mb-2 block">住宿风格</span><select v-model="form.hotel_style" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"><option value="">请选择住宿风格</option><option v-for="item in hotelOptions" :key="item" :value="item">{{ item }}</option></select></label></div>
            <div class="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]"><div><div class="text-sm font-medium text-slate-600">交通偏好</div><div class="mt-3 flex flex-wrap gap-2"><button v-for="item in transportOptions" :key="item" type="button" class="rounded-full border px-4 py-2 text-sm transition" :class="form.transport_preferences.includes(item) ? 'border-[#29597d] bg-[#29597d] text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-[#89a4b9]'" @click="toggleSelection(form.transport_preferences, item)">{{ item }}</button></div></div><label class="text-sm text-slate-600"><span class="mb-2 block">补充说明</span><textarea v-model="form.notes" rows="4" class="w-full rounded-[22px] border border-slate-200 bg-white px-4 py-3"></textarea></label></div>
          </article>
          <div class="flex flex-col gap-6"><article class="rounded-[36px] border border-white/70 bg-white/78 p-6 shadow-card"><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Travel Tone</div><h3 class="mt-3 text-2xl font-semibold text-ink">这趟行程会偏向什么感觉</h3><div class="mt-5 space-y-3 text-sm leading-7 text-slate-600"><div class="rounded-[24px] bg-[#f4f7fa] px-4 py-4">重点会围绕 <span class="font-medium text-ink">{{ form.destination || '目的地' }}</span> 的 <span class="font-medium text-ink">{{ form.interests.join(' / ') || '城市体验' }}</span> 展开。</div><div class="rounded-[24px] bg-[#f8f4ee] px-4 py-4">住宿倾向 <span class="font-medium text-ink">{{ form.hotel_style }}</span>，交通优先 <span class="font-medium text-ink">{{ form.transport_preferences.join(' / ') || '系统推荐' }}</span>。</div><div class="rounded-[24px] bg-[#f2f5f8] px-4 py-4">系统会尽量把必去点和饮食偏好编进每日路线，而不是只堆列表。</div></div></article><article v-if="showDevPanels" class="rounded-[36px] border border-[#d8e4ed] bg-white/82 p-6 shadow-card"><div class="flex items-center justify-between gap-3"><div><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Developer</div><h3 class="mt-2 text-xl font-semibold text-ink">集成预检查</h3></div><button type="button" class="rounded-full border border-slate-200 px-4 py-2 text-sm text-slate-600" @click="loadIntegrationStatus">{{ integrationLoading ? '检查中...' : '刷新' }}</button></div><div class="mt-5 grid gap-3 sm:grid-cols-2"><div class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"><div class="text-xs text-slate-500">MCP</div><div class="mt-2 font-medium text-ink">{{ currentIntegrationStatus.mcp_connected ? '已连接' : '未连接' }}</div></div><div class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"><div class="text-xs text-slate-500">LLM</div><div class="mt-2 font-medium text-ink">{{ currentIntegrationStatus.llm_reachable ? '可用' : currentIntegrationStatus.llm_enabled ? '未连通' : '未配置' }}</div></div><div class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"><div class="text-xs text-slate-500">地图</div><div class="mt-2 font-medium text-ink">{{ currentIntegrationStatus.map_js_key_configured ? '已配置 JS Key' : '缺少 JS Key' }}</div></div><div class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"><div class="text-xs text-slate-500">Mock</div><div class="mt-2 font-medium text-ink">{{ currentIntegrationStatus.mock_enabled ? '已开启' : '已关闭' }}</div></div></div><div v-if="combinedWarnings.length" class="mt-4 rounded-[22px] border border-amber-200 bg-amber-50 px-4 py-4 text-xs leading-6 text-amber-800"><div v-for="warning in combinedWarnings" :key="warning">{{ warning }}</div></div></article></div>
        </section>
        <article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-8"><div class="grid gap-6 xl:grid-cols-[0.98fr_1.02fr] xl:items-end"><div><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Planner</div><h2 class="mt-3 text-2xl font-semibold text-ink sm:text-[30px]">开始规划和本次输入摘要</h2><div class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3"><div v-for="item in inputSummary" :key="item.label" class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"><div class="text-xs uppercase tracking-[0.16em] text-slate-400">{{ item.label }}</div><div class="mt-2 font-medium text-ink">{{ item.value }}</div></div></div></div><div class="rounded-[30px] bg-[linear-gradient(145deg,#12324a,#2f5878)] p-5 text-white shadow-[0_24px_70px_rgba(18,50,74,0.22)] sm:p-6"><div class="flex items-center justify-between gap-4 text-sm text-white/72"><span>生成进度</span><span>{{ progress ? `${progress}%` : '准备就绪' }}</span></div><div class="mt-3 h-2 rounded-full bg-white/15"><div class="h-2 rounded-full bg-[linear-gradient(90deg,#9ad3ff,#f3d18b)] transition-all duration-300" :style="{ width: `${progress}%` }"></div></div><div class="mt-4 text-sm text-white/72">{{ loading ? progressLabel : '一键生成后，结果页会把地图、每日路线和餐饮天气整合到一起。' }}</div><button type="button" class="mt-6 w-full rounded-[22px] bg-[linear-gradient(90deg,#f0d39b,#d7a86b)] px-5 py-4 text-sm font-semibold text-[#19324a] disabled:opacity-60" :disabled="loading || !form.destination" @click="submitPlan">{{ loading ? '规划中...' : '开始规划' }}</button></div></div><div v-if="errorMessage" class="mt-5 rounded-[22px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{{ errorMessage }}</div></article>
      </section>
      <section v-else ref="exportRoot" class="space-y-6">
        <div class="flex flex-wrap items-center justify-between gap-3"><button type="button" class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card" @click="resetPlanner">重新规划</button><div class="flex flex-wrap gap-3"><button type="button" class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card" @click="exportAs('png')">导出图片</button><button type="button" class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card" @click="exportAs('pdf')">导出 PDF</button></div></div>
        <article class="rounded-[36px] bg-[linear-gradient(135deg,rgba(19,49,71,0.98),rgba(40,92,126,0.94)_55%,rgba(183,140,83,0.88))] p-6 text-white shadow-[0_30px_90px_rgba(23,49,73,0.2)] sm:p-8"><div class="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]"><div><div class="text-xs uppercase tracking-[0.28em] text-white/55">Overview</div><h2 class="mt-3 text-3xl font-semibold sm:text-[38px]">{{ result.plan.title }}</h2><p class="mt-4 max-w-3xl text-sm leading-7 text-white/78">{{ result.plan.summary }}</p><div class="mt-6 flex flex-wrap gap-2 text-sm"><span class="rounded-full border border-white/16 bg-white/10 px-4 py-2">{{ result.request_echo.days }} 天</span><span class="rounded-full border border-white/16 bg-white/10 px-4 py-2">{{ result.request_echo.destination }}</span><span class="rounded-full border border-white/16 bg-white/10 px-4 py-2">{{ paceLabel(result.request_echo.pace) }}</span><span class="rounded-full border border-white/16 bg-white/10 px-4 py-2">{{ budgetLabel(result.request_echo.budget_level) }}</span></div></div><div class="grid gap-4 sm:grid-cols-2"><div class="rounded-[24px] border border-white/10 bg-white/10 px-4 py-4"><div class="text-xs uppercase tracking-[0.18em] text-white/55">预算总计</div><div class="mt-3 text-2xl font-semibold">{{ result.plan.estimated_budget.total_estimate }}</div></div><div class="rounded-[24px] border border-white/10 bg-white/10 px-4 py-4"><div class="text-xs uppercase tracking-[0.18em] text-white/55">天气摘要</div><div class="mt-3 text-sm leading-6 text-white/80">{{ result.plan.weather_summary }}</div></div><div class="rounded-[24px] border border-white/10 bg-white/10 px-4 py-4 sm:col-span-2"><div class="text-xs uppercase tracking-[0.18em] text-white/55">预订提示</div><div class="mt-3 text-sm leading-6 text-white/80">{{ result.plan.best_booking_tip }}</div></div></div></div><div v-if="resultWarnings.length" class="mt-6 rounded-[24px] border border-amber-200/40 bg-amber-50/90 px-4 py-4 text-sm leading-7 text-amber-900"><div class="font-medium">规划提醒</div><div v-for="warning in resultWarnings" :key="warning" class="mt-2">{{ warning }}</div></div></article>
        <section class="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
          <div class="space-y-6">
            <article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"><div class="flex flex-wrap items-center justify-between gap-4"><div><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Map</div><h2 class="mt-3 text-2xl font-semibold text-ink">景点信息和地图标记</h2></div><span class="rounded-full bg-[#eff5f8] px-4 py-2 text-sm text-[#48637b]">{{ result.planning_context.attractions.length }} 个景点点位</span></div><div class="mt-5"><AmapMap :map-config="result.map_config" :pois="result.planning_context.attractions" :routes="result.planning_context.routes" /></div></article>
            <article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"><div class="flex flex-wrap items-center justify-between gap-4"><div><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Daily Itinerary</div><h2 class="mt-3 text-2xl font-semibold text-ink">每日详细行程</h2></div><span class="rounded-full bg-[#eff5f8] px-4 py-2 text-sm text-[#48637b]">整卡展开后查看当日细节</span></div><div class="mt-5 space-y-4"><article v-for="day in result.plan.days" :key="day.day_number" class="rounded-[28px] border border-slate-100 bg-[linear-gradient(180deg,#f7fafb,#f3f6f8)] px-5 py-5 shadow-sm"><div class="flex flex-wrap items-start justify-between gap-4"><div><div class="text-lg font-semibold text-ink">第 {{ day.day_number }} 天 · {{ day.theme }}</div><div class="mt-2 text-sm text-slate-500">{{ day.date }}</div></div><div class="flex flex-wrap items-center gap-2"><span class="rounded-full bg-white px-4 py-2 text-sm text-slate-600 shadow-sm">{{ getDayWeather(day)?.day_weather || '--' }} {{ getDayWeather(day) ? `${getDayWeather(day)?.low_temperature}°-${getDayWeather(day)?.high_temperature}°` : '' }}</span><button type="button" class="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 shadow-sm" @click="toggleDay(day.day_number)">{{ isDayExpanded(day.day_number) ? '收起详情' : '展开详情' }}</button></div></div><div v-if="isDayExpanded(day.day_number)" class="mt-5 grid gap-4"><p class="text-sm leading-7 text-slate-600">{{ day.overview }}</p><div class="grid gap-4 xl:grid-cols-[1.08fr_0.92fr]"><div class="space-y-3"><div v-for="activity in day.activities" :key="`${day.day_number}-${activity.start_time}-${activity.title}`" class="rounded-[22px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm"><div class="font-medium text-ink">{{ activity.start_time }} - {{ activity.end_time }} · {{ activity.title }}</div><div class="mt-2 leading-6">{{ activity.description }}</div><div v-if="activity.transport_from_previous" class="mt-3 text-xs text-slate-500">{{ activity.transport_from_previous }}</div></div></div><div class="space-y-3"><div class="rounded-[22px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm"><div class="font-medium text-ink">路线概览</div><div class="mt-3 leading-6">{{ getDayRoute(day)?.distance_text || '距离待补充' }}{{ getDayRoute(day)?.duration_text ? ` · ${getDayRoute(day)?.duration_text}` : '' }}</div><div v-if="getDayRoute(day)?.from_name || getDayRoute(day)?.to_name" class="mt-2 text-xs text-slate-500">{{ getDayRoute(day)?.from_name || '起点待定' }} → {{ getDayRoute(day)?.to_name || '终点待定' }}</div></div><div class="rounded-[22px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm"><div class="font-medium text-ink">天气与体感</div><div v-if="getDayWeather(day)" class="mt-3"><div>{{ getDayWeather(day)?.day_weather }} / {{ getDayWeather(day)?.night_weather }}</div><div class="mt-2 text-xs text-slate-500">{{ getDayWeather(day)?.low_temperature }}° - {{ getDayWeather(day)?.high_temperature }}°</div><div class="mt-3 leading-6">{{ getDayWeather(day)?.advice }}</div></div><div v-else class="mt-3 text-slate-500">暂无天气信息</div></div><div class="rounded-[22px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm"><div class="font-medium text-ink">餐饮推荐</div><div v-if="getMealRecommendations(day).length" class="mt-3 space-y-2"><div v-for="meal in getMealRecommendations(day)" :key="`${day.day_number}-${mealTitle(meal)}-${mealSubtitle(meal)}`" class="rounded-[18px] bg-panel px-3 py-3"><div class="font-medium text-ink">{{ mealTitle(meal) }}</div><div class="mt-2 text-xs leading-6 text-slate-500">{{ mealSubtitle(meal) }}</div></div></div><div v-else class="mt-3 text-slate-500">暂无餐饮推荐</div></div></div></div></div></article></div></article>
          </div>
          <aside class="space-y-6"><article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Stay & Budget</div><h2 class="mt-3 text-2xl font-semibold text-ink">住宿与预算</h2><div class="mt-5 grid gap-3"><div v-for="card in budgetCards" :key="card[0]" class="rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"><div class="text-xs text-slate-500">{{ card[0] }}</div><div class="mt-2 text-lg font-semibold text-ink">{{ card[1] }}</div></div></div><div class="mt-5 space-y-3"><div v-for="stay in result.plan.stay_recommendations" :key="`${stay.area}-${stay.hotel_name}`" class="rounded-[22px] bg-[#f8f4ee] px-4 py-4 text-sm text-slate-600"><div class="font-medium text-ink">{{ stay.area }}</div><div class="mt-2">{{ stay.hotel_name }}</div><div class="mt-2 text-xs leading-6 text-slate-500">{{ stay.reason }}</div><div class="mt-3 text-xs text-[#8d673f]">{{ stay.nightly_budget }}</div></div></div></article><article class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">City Notes</div><h2 class="mt-3 text-2xl font-semibold text-ink">城市提醒与打包建议</h2><div class="mt-5 space-y-3"><div v-for="tip in result.plan.city_tips" :key="tip" class="rounded-[22px] bg-panel px-4 py-4 text-sm leading-7 text-slate-600">{{ tip }}</div></div><div class="mt-5 flex flex-wrap gap-2"><span v-for="item in result.plan.packing_list" :key="item" class="rounded-full bg-[#eff5f8] px-4 py-2 text-sm text-[#48637b]">{{ item }}</span></div></article><article v-if="showDevPanels" class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Developer</div><h2 class="mt-3 text-2xl font-semibold text-ink">MCP 与地图集成状态</h2><div class="mt-5 rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"><div class="font-medium text-ink">MCP 启动命令</div><div class="mt-2 break-all rounded-[18px] bg-white px-3 py-2 text-xs shadow-sm">{{ currentIntegrationStatus.mcp_command || '未配置' }}</div></div><div class="mt-4 rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"><div class="font-medium text-ink">LLM 配置</div><div class="mt-3 rounded-[18px] bg-white px-3 py-3 text-xs shadow-sm"><div class="font-medium text-ink">{{ currentIntegrationStatus.llm_model || '未配置模型名' }}</div><div class="mt-2 break-all text-slate-600">{{ currentIntegrationStatus.llm_base_url || '未配置 Base URL' }}</div></div></div><div v-if="currentIntegrationStatus.available_tools.length" class="mt-4 rounded-[22px] bg-panel px-4 py-4 text-sm text-slate-600"><div class="font-medium text-ink">可用工具</div><div class="mt-3 flex flex-wrap gap-2"><span v-for="tool in currentIntegrationStatus.available_tools" :key="tool" class="rounded-full bg-white px-3 py-1 text-xs shadow-sm">{{ tool }}</span></div></div></article></aside>
        </section>
        <section v-if="showDevPanels" class="grid gap-6 xl:grid-cols-2"><div class="rounded-[36px] border border-white/70 bg-white/88 p-6 shadow-card sm:p-7"><div class="text-xs uppercase tracking-[0.28em] text-[#6f7f92]">Agent Trace</div><h2 class="mt-3 text-2xl font-semibold text-ink">Agent 调用轨迹</h2><div class="mt-5 space-y-3"><div v-for="item in result.agent_trace" :key="item.agent_name" class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4 text-sm text-slate-600"><div class="flex items-start justify-between gap-4"><div><div class="font-medium text-ink">{{ item.agent_name }}</div><div class="mt-2">{{ item.summary }}</div></div><span class="rounded-full px-3 py-1 text-xs" :class="item.success ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'">{{ item.success ? 'SUCCESS' : 'FAILED' }}</span></div><div class="mt-3 flex flex-wrap gap-2"><span class="rounded-full bg-white px-3 py-1 text-xs shadow-sm">{{ item.used_llm ? 'LLM' : 'RULE' }}</span><span v-for="tool in item.used_tools" :key="tool" class="rounded-full bg-white px-3 py-1 text-xs shadow-sm">{{ tool }}</span></div></div></div></div><AgentTrace :result="result" /></section>
      </section>
    </div>
  </div>
</template>




