import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type ComputedRef } from "vue"

import type { DayPOI, MapRenderConfig, RouteSummary } from "../types/planning"
import { ensureAmap } from "./useAmapSdk"
import {
  buildMapSignature,
  buildMarkerContent,
  buildPoiDetailContent,
  filterRenderablePois,
  hasRenderableMapData,
  resolveMapCenter,
  routePolylinePath,
} from "../components/amapMapHelpers"

interface UseAmapMapRuntimeOptions {
  mapConfig: ComputedRef<MapRenderConfig>
  pois: ComputedRef<DayPOI[]>
  routes: ComputedRef<RouteSummary[]>
}

export function useAmapMapRuntime(options: UseAmapMapRuntimeOptions) {
  const mapRoot = ref<HTMLDivElement | null>(null)
  const loading = ref(false)
  const errorMessage = ref("")

  let mapInstance: any = null
  let markerLayer: any[] = []
  let routeLayer: any[] = []
  let infoWindow: any = null

  const validPois = computed(() => filterRenderablePois(options.pois.value))
  const hasRenderableData = computed(() =>
    hasRenderableMapData(validPois.value, options.routes.value),
  )
  const mapSignature = computed(() =>
    buildMapSignature(options.mapConfig.value, validPois.value, options.routes.value),
  )

  onMounted(async () => {
    await nextTick()
    await renderMap()
  })

  watch(mapSignature, async () => {
    await nextTick()
    await renderMap()
  })

  onBeforeUnmount(() => {
    clearLayers()
    if (mapInstance?.destroy) mapInstance.destroy()
  })

  async function renderMap() {
    if (!mapRoot.value) return

    if (!options.mapConfig.value.enabled) {
      errorMessage.value = "\u540e\u7aef\u5c1a\u672a\u542f\u7528\u9ad8\u5fb7\u5730\u56fe\u914d\u7f6e\u3002"
      clearLayers()
      return
    }
    if (!options.mapConfig.value.js_api_key) {
      errorMessage.value = "\u7f3a\u5c11\u9ad8\u5fb7\u5730\u56fe JS Key\uff0c\u6682\u65f6\u65e0\u6cd5\u6e32\u67d3\u5730\u56fe\u3002"
      clearLayers()
      return
    }
    if (!hasRenderableData.value) {
      errorMessage.value = "\u5f53\u524d\u7ed3\u679c\u7f3a\u5c11\u53ef\u6e32\u67d3\u7684\u5750\u6807\u6570\u636e\u3002"
      clearLayers()
      return
    }

    loading.value = true
    errorMessage.value = ""

    try {
      const AMap = await ensureAmap(options.mapConfig.value)
      await nextTick()

      if (!mapInstance) {
        mapInstance = new AMap.Map(mapRoot.value, {
          viewMode: "2D",
          zoom: 11,
          center: resolveMapCenter(options.mapConfig.value.center, validPois.value),
        })
        mapInstance.on("click", () => infoWindow?.close?.())
      } else {
        mapInstance.setCenter(resolveMapCenter(options.mapConfig.value.center, validPois.value))
      }

      clearLayers()
      infoWindow = new AMap.InfoWindow({
        offset: new AMap.Pixel(0, -30),
        closeWhenClickMap: true,
        autoMove: true,
        isCustom: false,
      })

      markerLayer = validPois.value.map((item) => {
        const marker = new AMap.Marker({
          position: [item.poi.longitude, item.poi.latitude],
          title: item.poi.name,
          content: buildMarkerContent(item),
        })
        marker.on("click", () => openPoiDetail(item, marker))
        marker.setMap(mapInstance)
        return marker
      })

      routeLayer = options.routes.value
        .filter((route) => route.polyline.length > 1)
        .map((route) => {
          const polyline = new AMap.Polyline({
            path: routePolylinePath(route),
            strokeColor: "#2f79a8",
            strokeOpacity: 0.92,
            strokeWeight: 5,
            strokeStyle: "solid",
            lineJoin: "round",
          })
          polyline.setMap(mapInstance)
          return polyline
        })

      const layers = [...markerLayer, ...routeLayer].filter(Boolean)
      if (layers.length) mapInstance.setFitView(layers)
      window.setTimeout(() => mapInstance?.resize?.(), 60)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "\u5730\u56fe\u6e32\u67d3\u5931\u8d25"
    } finally {
      loading.value = false
    }
  }

  function clearLayers() {
    infoWindow?.close?.()
    markerLayer.forEach((marker) => marker?.setMap?.(null))
    routeLayer.forEach((route) => route?.setMap?.(null))
    markerLayer = []
    routeLayer = []
  }

  function openPoiDetail(item: DayPOI, marker: any) {
    if (!infoWindow || !mapInstance) return
    infoWindow.setContent(buildPoiDetailContent(item))
    const position = marker.getPosition?.() ?? [item.poi.longitude, item.poi.latitude]
    infoWindow.open(mapInstance, position)
  }

  return {
    mapRoot,
    loading,
    errorMessage,
  }
}
