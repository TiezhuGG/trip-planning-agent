<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import type { GeoPoint, MapRenderConfig, POIRecommendation, RouteSummary } from '../types/planning'

const props = defineProps<{
  mapConfig: MapRenderConfig
  pois: POIRecommendation[]
  routes: RouteSummary[]
}>()

const mapRoot = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const errorMessage = ref('')
let mapInstance: any = null
let markerLayer: any[] = []
let routeLayer: any[] = []

const validPois = computed(() => props.pois.filter((poi) => poi.longitude != null && poi.latitude != null))
const hasRenderableData = computed(
  () => validPois.value.length > 0 || props.routes.some((route) => route.polyline.length > 1),
)

watch(
  () => [props.mapConfig.js_api_key, props.mapConfig.security_js_code, validPois.value.length, props.routes.length],
  async () => {
    await renderMap()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  clearLayers()
  if (mapInstance?.destroy) {
    mapInstance.destroy()
  }
})

async function renderMap() {
  if (!mapRoot.value) return
  if (!props.mapConfig.enabled) {
    errorMessage.value = '后端未启用高德地图配置。'
    return
  }
  if (!props.mapConfig.js_api_key) {
    errorMessage.value = '缺少高德地图 JS Key，暂时无法渲染真实地图。'
    return
  }
  if (!hasRenderableData.value) {
    errorMessage.value = '当前结果缺少可渲染的坐标数据。'
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const AMap = await ensureAmap(props.mapConfig)
    if (!mapInstance) {
      mapInstance = new AMap.Map(mapRoot.value, {
        viewMode: '2D',
        zoom: 11,
        center: resolveCenter(props.mapConfig.center, validPois.value),
      })
    }

    clearLayers()

    markerLayer = validPois.value.map((poi, index) => {
      const marker = new AMap.Marker({
        position: [poi.longitude, poi.latitude],
        title: poi.name,
        label: {
          direction: 'top',
          content: `<div style="padding:4px 8px;border-radius:999px;background:#ffffff;border:1px solid #d7def8;color:#1f2a44;font-size:12px;box-shadow:0 8px 24px rgba(31,42,68,0.12)">${index + 1}. ${poi.name}</div>`,
        },
      })
      marker.setMap(mapInstance)
      return marker
    })

    routeLayer = props.routes
      .filter((route) => route.polyline.length > 1)
      .map((route) => {
        const polyline = new AMap.Polyline({
          path: route.polyline.map((point) => [point.longitude, point.latitude]),
          strokeColor: '#5b7df7',
          strokeOpacity: 0.9,
          strokeWeight: 5,
          strokeStyle: 'solid',
          lineJoin: 'round',
        })
        polyline.setMap(mapInstance)
        return polyline
      })

    const boundsTargets = [
      ...validPois.value.map((poi) => [poi.longitude as number, poi.latitude as number]),
      ...props.routes.flatMap((route) => route.polyline.map((point) => [point.longitude, point.latitude])),
    ]
    if (boundsTargets.length > 0) {
      mapInstance.setFitView([...markerLayer, ...routeLayer])
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '地图渲染失败'
  } finally {
    loading.value = false
  }
}

function clearLayers() {
  markerLayer.forEach((marker) => marker?.setMap?.(null))
  routeLayer.forEach((route) => route?.setMap?.(null))
  markerLayer = []
  routeLayer = []
}

function resolveCenter(center: GeoPoint | null, pois: POIRecommendation[]) {
  if (center) return [center.longitude, center.latitude]
  const firstPoi = pois[0]
  if (firstPoi?.longitude != null && firstPoi?.latitude != null) {
    return [firstPoi.longitude, firstPoi.latitude]
  }
  return [121.4737, 31.2304]
}

async function ensureAmap(mapConfig: MapRenderConfig) {
  if ((window as any).AMap) return (window as any).AMap

  const existing = document.querySelector<HTMLScriptElement>('script[data-amap-sdk="true"]')
  if (existing) {
    await waitForAmap()
    return (window as any).AMap
  }

  if (mapConfig.security_js_code) {
    ;(window as any)._AMapSecurityConfig = {
      securityJsCode: mapConfig.security_js_code,
    }
  }

  const script = document.createElement('script')
  script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(mapConfig.js_api_key ?? '')}`
  script.async = true
  script.dataset.amapSdk = 'true'
  document.head.appendChild(script)

  await new Promise<void>((resolve, reject) => {
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('高德地图 SDK 加载失败'))
  })
  await waitForAmap()
  return (window as any).AMap
}

function waitForAmap() {
  return new Promise<void>((resolve, reject) => {
    let attempts = 0
    const timer = window.setInterval(() => {
      if ((window as any).AMap) {
        window.clearInterval(timer)
        resolve()
        return
      }
      attempts += 1
      if (attempts > 40) {
        window.clearInterval(timer)
        reject(new Error('高德地图 SDK 初始化超时'))
      }
    }, 150)
  })
}
</script>

<template>
  <div class="overflow-hidden rounded-[28px] border border-slate-100 bg-[#edf2ff] p-3">
    <div v-if="errorMessage" class="flex h-[430px] items-center justify-center rounded-[24px] border border-dashed border-slate-200 bg-white px-6 text-center text-sm leading-7 text-slate-500">
      {{ errorMessage }}
    </div>
    <div v-else-if="loading" class="flex h-[430px] items-center justify-center rounded-[24px] bg-white text-sm text-slate-500">
      正在加载高德地图...
    </div>
    <div v-else ref="mapRoot" class="h-[430px] rounded-[24px]"></div>
  </div>
</template>
