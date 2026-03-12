<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'

import { generatePlan } from './api/planning'
import AgentTrace from './components/AgentTrace.vue'
import AmapMap from './components/AmapMap.vue'
import type { PlanningResponse, TripPlanningRequest } from './types/planning'

const interestOptions = ['自然风光', '历史文化', '美食探索', '拍照打卡', '夜游休闲', '艺术展览']
const transportOptions = ['公共交通', '打车', '自驾', '步行', '骑行']
const hotelOptions = ['经济型酒店', '舒适型酒店', '精品民宿', '高端度假酒店']
const paceOptions: Array<{ label: string; value: TripPlanningRequest['pace'] }> = [
  { label: '轻松', value: 'relaxed' },
  { label: '均衡', value: 'balanced' },
  { label: '紧凑', value: 'intense' },
]
const budgetOptions: Array<{ label: string; value: TripPlanningRequest['budget_level'] }> = [
  { label: '经济型', value: 'economy' },
  { label: '舒适型', value: 'comfort' },
  { label: '品质型', value: 'luxury' },
]
const stageOptions = ['生成初步计划', '搜索景点与餐饮', '获取天气与路线', '整合最终行程']

const today = formatDate(new Date())
const form = reactive<TripPlanningRequest>({
  origin: '上海',
  destination: '北京',
  start_date: today,
  days: 3,
  interests: ['历史文化', '美食探索'],
  must_visit: ['故宫', '天坛'],
  pace: 'balanced',
  budget_level: 'comfort',
  transport_preferences: ['公共交通'],
  hotel_style: '舒适型酒店',
  dining_preferences: ['本地风味', '夜市小吃'],
  travelers: { adults: 2, children: 0, seniors: 0 },
  notes: '希望兼顾经典地标、美食体验和适合拍照的路线。',
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
let progressTimer: number | null = null

const budgetCards = computed(() => {
  const budget = result.value?.plan.estimated_budget
  if (!budget) return []
  return [
    ['景点门票', budget.tickets],
    ['酒店住宿', budget.accommodation],
    ['餐饮费用', budget.food],
    ['交通费用', budget.transport],
  ]
})

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

watch(
  () => form.days,
  (days) => {
    const safe = Math.min(14, Math.max(1, Number(days) || 1))
    if (safe !== days) {
      form.days = safe
      return
    }
    endDate.value = addDays(startDate.value, safe - 1)
  },
)

function formatDate(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
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
  if (success) window.setTimeout(() => (progress.value = 0), 900)
}

async function submitPlan() {
  loading.value = true
  errorMessage.value = ''
  form.must_visit = splitText(mustVisitText.value)
  form.dining_preferences = splitText(diningText.value)
  startProgress()
  try {
    result.value = await generatePlan({
      ...form,
      origin: form.origin?.trim() || null,
      interests: [...form.interests],
      must_visit: [...form.must_visit],
      transport_preferences: [...form.transport_preferences],
      dining_preferences: [...form.dining_preferences],
      travelers: {
        adults: Number(form.travelers.adults) || 1,
        children: Number(form.travelers.children) || 0,
        seniors: Number(form.travelers.seniors) || 0,
      },
    })
    stopProgress(true)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '生成行程失败，请稍后重试。'
    stopProgress(false)
  } finally {
    loading.value = false
  }
}

async function exportAs(type: 'png' | 'pdf') {
  if (!exportRoot.value || !result.value) return
  const canvas = await html2canvas(exportRoot.value, { scale: 2, backgroundColor: '#edf1fb' })
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

function mealLabel(type: string) {
  return { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' }[type] ?? type
}

function routeModeLabel(mode: string) {
  return { driving: '驾车', transit: '公共交通', walking: '步行', bicycling: '骑行' }[mode] ?? mode
}
</script>

<template>
  <div class="min-h-screen bg-[#e9eef9] text-ink">
    <div class="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
      <header class="rounded-[36px] bg-gradient-to-br from-[#6072f2] via-[#6a64de] to-[#7a4fbc] px-6 py-8 text-white shadow-glow sm:px-8">
        <div class="grid gap-6 xl:grid-cols-[1.1fr_0.9fr] xl:items-end">
          <div>
            <div class="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm">
              <span class="h-2 w-2 rounded-full bg-emerald-300"></span>
              多 Agent 高德旅行规划
            </div>
            <h1 class="mt-5 font-display text-4xl font-semibold sm:text-5xl">智能旅行助手</h1>
            <p class="mt-4 max-w-3xl text-sm leading-7 text-white/85 sm:text-base">
              点击开始规划后，系统会先生成初步计划，再自动调用景点、餐饮、天气和路线 Agent，最后整合成完整行程并在高德地图上展示标记和路线。
            </p>
          </div>
          <div class="grid gap-4 sm:grid-cols-3 xl:grid-cols-1">
            <div class="rounded-[24px] border border-white/15 bg-white/10 p-4">初步计划草案</div>
            <div class="rounded-[24px] border border-white/15 bg-white/10 p-4">高德检索与路线</div>
            <div class="rounded-[24px] border border-white/15 bg-white/10 p-4">最终每日行程</div>
          </div>
        </div>
      </header>

      <section v-if="!result" class="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div class="space-y-6 rounded-[32px] bg-white/90 p-6 shadow-card">
          <div class="grid gap-4 lg:grid-cols-4">
            <label class="text-sm text-slate-600 lg:col-span-2"><span class="mb-2 block">目的地城市</span><input v-model="form.destination" class="w-full rounded-2xl border border-slate-200 px-4 py-3" /></label>
            <label class="text-sm text-slate-600"><span class="mb-2 block">出发城市</span><input v-model="form.origin" class="w-full rounded-2xl border border-slate-200 px-4 py-3" /></label>
            <label class="text-sm text-slate-600"><span class="mb-2 block">开始日期</span><input v-model="startDate" type="date" class="w-full rounded-2xl border border-slate-200 px-4 py-3" /></label>
          </div>
          <div class="grid gap-4 lg:grid-cols-4">
            <label class="text-sm text-slate-600"><span class="mb-2 block">结束日期</span><input v-model="endDate" type="date" class="w-full rounded-2xl border border-slate-200 px-4 py-3" /></label>
            <label class="text-sm text-slate-600"><span class="mb-2 block">成人</span><input v-model.number="form.travelers.adults" type="number" min="1" max="10" class="w-full rounded-2xl border border-slate-200 px-4 py-3" /></label>
            <label class="text-sm text-slate-600"><span class="mb-2 block">儿童</span><input v-model.number="form.travelers.children" type="number" min="0" max="6" class="w-full rounded-2xl border border-slate-200 px-4 py-3" /></label>
            <label class="text-sm text-slate-600"><span class="mb-2 block">老人</span><input v-model.number="form.travelers.seniors" type="number" min="0" max="4" class="w-full rounded-2xl border border-slate-200 px-4 py-3" /></label>
          </div>
          <div>
            <div class="text-sm font-medium text-slate-600">兴趣偏好</div>
            <div class="mt-3 flex flex-wrap gap-2"><button v-for="item in interestOptions" :key="item" type="button" class="rounded-full border px-4 py-2 text-sm" :class="form.interests.includes(item) ? 'border-iris bg-iris text-white' : 'border-slate-200 bg-white text-slate-600'" @click="toggleSelection(form.interests, item)">{{ item }}</button></div>
          </div>
          <div class="grid gap-4 lg:grid-cols-2">
            <label class="text-sm text-slate-600"><span class="mb-2 block">必打卡景点</span><textarea v-model="mustVisitText" rows="3" class="w-full rounded-2xl border border-slate-200 px-4 py-3"></textarea></label>
            <label class="text-sm text-slate-600"><span class="mb-2 block">餐饮偏好</span><textarea v-model="diningText" rows="3" class="w-full rounded-2xl border border-slate-200 px-4 py-3"></textarea></label>
          </div>
          <div class="grid gap-4 lg:grid-cols-3">
            <div>
              <div class="text-sm font-medium text-slate-600">交通方式</div>
              <div class="mt-3 flex flex-wrap gap-2"><button v-for="item in transportOptions" :key="item" type="button" class="rounded-full border px-4 py-2 text-sm" :class="form.transport_preferences.includes(item) ? 'border-iris bg-iris text-white' : 'border-slate-200 bg-white text-slate-600'" @click="toggleSelection(form.transport_preferences, item)">{{ item }}</button></div>
            </div>
            <div>
              <div class="text-sm font-medium text-slate-600">住宿类型</div>
              <select v-model="form.hotel_style" class="mt-3 w-full rounded-2xl border border-slate-200 px-4 py-3"><option v-for="item in hotelOptions" :key="item">{{ item }}</option></select>
            </div>
            <div>
              <div class="text-sm font-medium text-slate-600">旅行节奏</div>
              <div class="mt-3 flex flex-wrap gap-2"><button v-for="item in paceOptions" :key="item.value" type="button" class="rounded-full border px-4 py-2 text-sm" :class="form.pace === item.value ? 'border-iris bg-iris text-white' : 'border-slate-200 bg-white text-slate-600'" @click="form.pace = item.value">{{ item.label }}</button></div>
            </div>
          </div>
          <div>
            <div class="text-sm font-medium text-slate-600">预算档位</div>
            <div class="mt-3 flex flex-wrap gap-2"><button v-for="item in budgetOptions" :key="item.value" type="button" class="rounded-full border px-4 py-2 text-sm" :class="form.budget_level === item.value ? 'border-iris bg-iris text-white' : 'border-slate-200 bg-white text-slate-600'" @click="form.budget_level = item.value">{{ item.label }}</button></div>
          </div>
          <label class="text-sm text-slate-600"><span class="mb-2 block">补充说明</span><textarea v-model="form.notes" rows="4" class="w-full rounded-2xl border border-slate-200 px-4 py-3"></textarea></label>
        </div>

        <aside class="space-y-5">
          <div class="rounded-[28px] bg-white/90 p-5 shadow-card">
            <div class="text-xs uppercase tracking-[0.28em] text-iris/70">Planning Flow</div>
            <div class="mt-3 text-2xl font-semibold text-ink">开始规划</div>
            <div class="mt-4 rounded-full bg-slate-100 p-1"><div class="h-3 rounded-full bg-gradient-to-r from-iris to-irisDark transition-all" :style="{ width: `${progress}%` }"></div></div>
            <div class="mt-3 text-sm text-slate-500">{{ loading ? progressLabel : '等待开始' }}</div>
            <button type="button" class="mt-5 w-full rounded-[22px] bg-gradient-to-r from-iris to-irisDark px-5 py-4 text-sm font-medium text-white shadow-glow disabled:opacity-60" :disabled="loading || !form.destination" @click="submitPlan">{{ loading ? '规划中...' : '开始规划' }}</button>
          </div>
          <div class="rounded-[28px] bg-white/90 p-5 shadow-card text-sm text-slate-600">
            <div class="font-medium text-ink">本次输入摘要</div>
            <div class="mt-3 flex items-center justify-between"><span>目的地</span><span class="font-medium text-ink">{{ form.destination }}</span></div>
            <div class="mt-3 flex items-center justify-between"><span>日期</span><span class="font-medium text-ink">{{ startDate }} - {{ endDate }}</span></div>
            <div class="mt-3 flex items-center justify-between"><span>天数</span><span class="font-medium text-ink">{{ form.days }} 天</span></div>
          </div>
          <div v-if="errorMessage" class="rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{{ errorMessage }}</div>
        </aside>
      </section>

      <section v-else ref="exportRoot" class="mt-8 space-y-6">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <button type="button" class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card" @click="result = null">重新规划</button>
          <div class="flex flex-wrap gap-3">
            <button type="button" class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card" @click="exportAs('png')">导出图片</button>
            <button type="button" class="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm shadow-card" @click="exportAs('pdf')">导出 PDF</button>
          </div>
        </div>

        <article class="rounded-[32px] bg-white/90 p-6 shadow-card">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div class="text-xs uppercase tracking-[0.32em] text-iris/70">Overview</div>
              <h2 class="mt-3 text-3xl font-semibold text-ink">{{ result.plan.title }}</h2>
              <p class="mt-4 max-w-3xl text-sm leading-7 text-slate-600">{{ result.plan.summary }}</p>
            </div>
            <div class="rounded-[24px] bg-gradient-to-br from-[#eff2ff] to-[#f6f0ff] px-4 py-4 text-sm text-slate-600">
              <div class="font-medium text-ink">模型状态</div>
              <div class="mt-2 flex flex-wrap gap-2">
                <span class="rounded-full px-3 py-1 text-xs" :class="result.meta.llm_used ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'">{{ result.meta.llm_used ? '已调用大模型' : '未调用大模型' }}</span>
                <span class="rounded-full px-3 py-1 text-xs" :class="result.meta.fallback_used ? 'bg-amber-100 text-amber-700' : 'bg-sky-100 text-sky-700'">{{ result.meta.fallback_used ? '包含 fallback' : '无 fallback' }}</span>
              </div>
              <div class="mt-3">{{ result.meta.model_name || '未配置模型名' }}</div>
            </div>
          </div>
          <div class="mt-6 grid gap-4 md:grid-cols-4">
            <div class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4"><div class="text-sm text-slate-500">天气摘要</div><div class="mt-2 text-sm leading-6 text-ink">{{ result.plan.weather_summary }}</div></div>
            <div class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4"><div class="text-sm text-slate-500">预算总计</div><div class="mt-2 text-2xl font-semibold text-ink">{{ result.plan.estimated_budget.total_estimate }}</div></div>
            <div class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4"><div class="text-sm text-slate-500">天数</div><div class="mt-2 text-2xl font-semibold text-ink">{{ result.request_echo.days }} 天</div></div>
            <div class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4"><div class="text-sm text-slate-500">交通偏好</div><div class="mt-2 text-sm leading-6 text-ink">{{ result.request_echo.transport_preferences.join(' / ') || '系统推荐' }}</div></div>
          </div>
        </article>

        <section class="grid gap-6 xl:grid-cols-[1fr_340px]">
          <article class="rounded-[32px] bg-white/90 p-6 shadow-card">
            <div class="text-xs uppercase tracking-[0.32em] text-iris/70">Initial Draft</div>
            <h2 class="mt-3 text-2xl font-semibold text-ink">初步计划</h2>
            <p class="mt-4 text-sm leading-7 text-slate-600">{{ result.initial_plan.summary }}</p>
            <div class="mt-5 grid gap-4 lg:grid-cols-2">
              <div v-for="day in result.initial_plan.days" :key="day.day_number" class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4 text-sm text-slate-600">
                <div class="font-medium text-ink">第 {{ day.day_number }} 天 · {{ day.theme }}</div>
                <div class="mt-2">重点：{{ day.focus }}</div>
                <div class="mt-2 text-xs text-slate-500">景点检索词：{{ day.poi_query }}</div>
                <div class="mt-1 text-xs text-slate-500">餐饮检索词：{{ day.dining_query }}</div>
              </div>
            </div>
          </article>
          <article class="rounded-[32px] bg-white/90 p-6 shadow-card">
            <div class="text-xs uppercase tracking-[0.32em] text-iris/70">Budget</div>
            <h2 class="mt-3 text-2xl font-semibold text-ink">预算明细</h2>
            <div class="mt-5 grid gap-4">
              <div v-for="item in budgetCards" :key="item[0]" class="rounded-[22px] border border-slate-100 bg-panel px-4 py-4"><div class="text-sm text-slate-500">{{ item[0] }}</div><div class="mt-2 text-2xl font-semibold text-ink">{{ item[1] }}</div></div>
            </div>
          </article>
        </section>

        <article class="rounded-[32px] bg-white/90 p-6 shadow-card">
          <div class="flex items-center justify-between gap-4"><div><div class="text-xs uppercase tracking-[0.32em] text-iris/70">Map</div><h2 class="mt-3 text-2xl font-semibold text-ink">景点信息和地图标记</h2></div><span class="rounded-full bg-mist px-4 py-2 text-sm text-slate-600">{{ result.planning_context.attractions.length }} 个点位</span></div>
          <div class="mt-5"><AmapMap :map-config="result.map_config" :pois="result.planning_context.attractions" :routes="result.planning_context.routes" /></div>
        </article>

        <section class="grid gap-6 xl:grid-cols-2">
          <article class="rounded-[32px] bg-white/90 p-6 shadow-card">
            <div class="text-xs uppercase tracking-[0.32em] text-iris/70">Routes</div>
            <h2 class="mt-3 text-2xl font-semibold text-ink">交通路线规划</h2>
            <div class="mt-5 space-y-4">
              <div v-for="route in result.planning_context.routes" :key="`${route.day_number}-${route.from_name}`" class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4 text-sm text-slate-600">
                <div class="flex items-center justify-between gap-3"><div class="font-medium text-ink">{{ route.title || `第 ${route.day_number} 天路线` }}</div><span class="rounded-full bg-white px-3 py-1 text-xs shadow-sm">{{ routeModeLabel(route.mode) }}</span></div>
                <div class="mt-2">{{ route.from_name }} → {{ route.to_name }}</div>
                <div class="mt-2 text-xs text-slate-500">{{ route.distance_text }} {{ route.duration_text ? `· ${route.duration_text}` : '' }}</div>
                <div class="mt-3 space-y-2"><div v-for="(step, index) in route.steps" :key="index" class="rounded-[18px] bg-white px-3 py-2 shadow-sm">{{ step.instruction }}</div></div>
              </div>
            </div>
          </article>
          <article class="rounded-[32px] bg-white/90 p-6 shadow-card">
            <div class="text-xs uppercase tracking-[0.32em] text-iris/70">Weather & Dining</div>
            <h2 class="mt-3 text-2xl font-semibold text-ink">每日天气与餐饮推荐</h2>
            <div class="mt-5 space-y-4">
              <div v-for="item in result.planning_context.weather.daily_forecasts" :key="item.date" class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4 text-sm text-slate-600">
                <div class="font-medium text-ink">{{ item.date }}</div>
                <div class="mt-2">白天 {{ item.day_weather }} / 夜间 {{ item.night_weather }}</div>
                <div class="mt-2 text-xs text-slate-500">{{ item.low_temperature }}° - {{ item.high_temperature }}°</div>
                <div class="mt-2">{{ item.advice }}</div>
              </div>
              <div class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4 text-sm text-slate-600">
                <div class="font-medium text-ink">餐饮候选</div>
                <div class="mt-3 space-y-2"><div v-for="restaurant in result.planning_context.restaurants" :key="restaurant.name" class="rounded-[18px] bg-white px-3 py-2 shadow-sm">{{ restaurant.name }}<span class="ml-2 text-xs text-slate-500">{{ restaurant.address }}</span></div></div>
              </div>
            </div>
          </article>
        </section>

        <article class="rounded-[32px] bg-white/90 p-6 shadow-card">
          <div class="text-xs uppercase tracking-[0.32em] text-iris/70">Daily Itinerary</div>
          <h2 class="mt-3 text-2xl font-semibold text-ink">每日详细行程</h2>
          <div class="mt-5 space-y-4">
            <div v-for="day in result.plan.days" :key="day.day_number" class="rounded-[24px] border border-slate-100 bg-panel px-5 py-5">
              <div class="flex flex-wrap items-start justify-between gap-4">
                <div><div class="text-lg font-semibold text-ink">第 {{ day.day_number }} 天 · {{ day.theme }}</div><div class="mt-2 text-sm text-slate-500">{{ day.date }}</div></div>
                <div class="rounded-[20px] bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">{{ day.weather?.day_weather || '--' }} {{ day.weather ? `${day.weather.low_temperature}°-${day.weather.high_temperature}°` : '' }}</div>
              </div>
              <p class="mt-4 text-sm leading-7 text-slate-600">{{ day.overview }}</p>
              <div class="mt-4 grid gap-4 xl:grid-cols-2">
                <div class="space-y-3">
                  <div v-for="activity in day.activities" :key="`${day.day_number}-${activity.start_time}-${activity.title}`" class="rounded-[20px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm">
                    <div class="font-medium text-ink">{{ activity.start_time }} - {{ activity.end_time }} · {{ activity.title }}</div>
                    <div class="mt-2">{{ activity.description }}</div>
                    <div class="mt-2 text-xs text-slate-500">{{ activity.transport_from_previous }}</div>
                  </div>
                </div>
                <div class="space-y-3">
                  <div class="rounded-[20px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm">
                    <div class="font-medium text-ink">路线摘要</div>
                    <div class="mt-2">{{ day.route_summary?.distance_text || '待补充' }} {{ day.route_summary?.duration_text ? `· ${day.route_summary.duration_text}` : '' }}</div>
                  </div>
                  <div class="rounded-[20px] bg-white px-4 py-4 text-sm text-slate-600 shadow-sm">
                    <div class="font-medium text-ink">餐饮安排</div>
                    <div class="mt-3 space-y-2"><div v-for="meal in day.meals" :key="`${day.day_number}-${meal.meal_type}-${meal.venue_name}`" class="rounded-[18px] bg-mist px-3 py-2">{{ mealLabel(meal.meal_type) }} · {{ meal.venue_name }}</div></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </article>

        <section class="grid gap-6 xl:grid-cols-2">
          <div class="rounded-[32px] bg-white/90 p-6 shadow-card">
            <div class="text-xs uppercase tracking-[0.32em] text-iris/70">Agent Trace</div>
            <h2 class="mt-3 text-2xl font-semibold text-ink">Agent 调用轨迹</h2>
            <div class="mt-5 space-y-3">
              <div v-for="item in result.agent_trace" :key="item.agent_name" class="rounded-[24px] border border-slate-100 bg-panel px-4 py-4 text-sm text-slate-600">
                <div class="flex items-start justify-between gap-4"><div><div class="font-medium text-ink">{{ item.agent_name }}</div><div class="mt-2">{{ item.summary }}</div></div><span class="rounded-full px-3 py-1 text-xs" :class="item.success ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'">{{ item.success ? 'SUCCESS' : 'FAILED' }}</span></div>
                <div class="mt-3 flex flex-wrap gap-2"><span class="rounded-full bg-white px-3 py-1 text-xs shadow-sm">{{ item.used_llm ? 'LLM' : 'RULE' }}</span><span v-for="tool in item.used_tools" :key="tool" class="rounded-full bg-white px-3 py-1 text-xs shadow-sm">{{ tool }}</span></div>
              </div>
            </div>
          </div>
          <AgentTrace :result="result" />
        </section>
      </section>
    </div>
  </div>
</template>
