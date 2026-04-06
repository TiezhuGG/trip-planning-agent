<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import type {
  DayPOI,
  GeoPoint,
  MapRenderConfig,
  RouteSummary,
} from "../types/planning";

const props = defineProps<{
  mapConfig: MapRenderConfig;
  pois: DayPOI[];
  routes: RouteSummary[];
}>();

const mapRoot = ref<HTMLDivElement | null>(null);
const loading = ref(false);
const errorMessage = ref("");

let mapInstance: any = null;
let markerLayer: any[] = [];
let routeLayer: any[] = [];
let infoWindow: any = null;

const validPois = computed(() =>
  props.pois.filter((item) => item.poi.longitude != null && item.poi.latitude != null),
);

const hasRenderableData = computed(
  () =>
    validPois.value.length > 0 ||
    props.routes.some((route) => route.polyline.length > 1),
);

const mapSignature = computed(() =>
  JSON.stringify({
    key: props.mapConfig.js_api_key,
    security: props.mapConfig.security_js_code,
    enabled: props.mapConfig.enabled,
    pois: validPois.value.map((item) => [
      item.kind,
      item.label,
      item.poi.name,
      item.poi.address,
      item.poi.poi_id,
      item.poi.rating,
      item.poi.tags,
      item.poi.source,
      item.poi.longitude,
      item.poi.latitude,
    ]),
    routes: props.routes.map((route) => [
      route.day_number,
      route.mode,
      route.polyline.length,
    ]),
  }),
);

onMounted(async () => {
  await nextTick();
  await renderMap();
});

watch(mapSignature, async () => {
  await nextTick();
  await renderMap();
});

onBeforeUnmount(() => {
  clearLayers();
  if (mapInstance?.destroy) mapInstance.destroy();
});

async function renderMap() {
  if (!mapRoot.value) return;

  if (!props.mapConfig.enabled) {
    errorMessage.value = "后端尚未启用高德地图配置。";
    clearLayers();
    return;
  }
  if (!props.mapConfig.js_api_key) {
    errorMessage.value = "缺少高德地图 JS Key，暂时无法渲染地图。";
    clearLayers();
    return;
  }
  if (!hasRenderableData.value) {
    errorMessage.value = "当前结果缺少可渲染的坐标数据。";
    clearLayers();
    return;
  }

  loading.value = true;
  errorMessage.value = "";

  try {
    const AMap = await ensureAmap(props.mapConfig);
    await nextTick();

    if (!mapInstance) {
      mapInstance = new AMap.Map(mapRoot.value, {
        viewMode: "2D",
        zoom: 11,
        center: resolveCenter(props.mapConfig.center, validPois.value),
      });
      mapInstance.on("click", () => infoWindow?.close?.());
    } else {
      mapInstance.setCenter(resolveCenter(props.mapConfig.center, validPois.value));
    }

    clearLayers();
    infoWindow = new AMap.InfoWindow({
      offset: new AMap.Pixel(0, -30),
      closeWhenClickMap: true,
      autoMove: true,
      isCustom: false,
    });

    markerLayer = validPois.value.map((item) => {
      const marker = new AMap.Marker({
        position: [item.poi.longitude, item.poi.latitude],
        title: item.poi.name,
        content: buildMarkerContent(item),
      });
      marker.on("click", () => openPoiDetail(item, marker));
      marker.setMap(mapInstance);
      return marker;
    });

    routeLayer = props.routes
      .filter((route) => route.polyline.length > 1)
      .map((route) => {
        const polyline = new AMap.Polyline({
          path: route.polyline.map((point) => [point.longitude, point.latitude]),
          strokeColor: "#2f79a8",
          strokeOpacity: 0.92,
          strokeWeight: 5,
          strokeStyle: "solid",
          lineJoin: "round",
        });
        polyline.setMap(mapInstance);
        return polyline;
      });

    const layers = [...markerLayer, ...routeLayer].filter(Boolean);
    if (layers.length) mapInstance.setFitView(layers);
    window.setTimeout(() => mapInstance?.resize?.(), 60);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "地图渲染失败";
  } finally {
    loading.value = false;
  }
}

function clearLayers() {
  infoWindow?.close?.();
  markerLayer.forEach((marker) => marker?.setMap?.(null));
  routeLayer.forEach((route) => route?.setMap?.(null));
  markerLayer = [];
  routeLayer = [];
}

function resolveCenter(center: GeoPoint | null, pois: DayPOI[]) {
  if (center) return [center.longitude, center.latitude];
  const firstPoi = pois[0]?.poi;
  if (firstPoi?.longitude != null && firstPoi?.latitude != null) {
    return [firstPoi.longitude, firstPoi.latitude];
  }
  return [121.4737, 31.2304];
}

function buildMarkerContent(item: DayPOI) {
  const style = markerStyle(item.kind);
  const label = truncateText(item.label || item.poi.name, item.kind === "stay" ? 16 : 14);
  return `
    <div style="position:relative;transform:translate(-50%, -100%);pointer-events:auto;">
      <div style="display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border-radius:999px;background:${style.background};border:1px solid ${style.border};color:${style.color};font-size:12px;font-weight:600;line-height:1;white-space:nowrap;box-shadow:0 14px 28px rgba(15,23,42,0.18);backdrop-filter:blur(10px);">
        <span style="width:10px;height:10px;border-radius:999px;background:${style.dot};box-shadow:0 0 0 3px ${style.dotGlow};"></span>
        <span>${escapeHtml(label)}</span>
      </div>
      <div style="width:12px;height:12px;margin:-2px auto 0;background:${style.background};border-right:1px solid ${style.border};border-bottom:1px solid ${style.border};transform:rotate(45deg);box-shadow:8px 8px 18px rgba(15,23,42,0.08);"></div>
    </div>
  `;
}

function markerStyle(kind: DayPOI["kind"]) {
  if (kind === "stay") {
    return {
      background: "#0f4c5c",
      border: "#08323d",
      color: "#f8fbff",
      dot: "#8be9ff",
      dotGlow: "rgba(139, 233, 255, 0.28)",
    };
  }
  return {
    background: "#d46a1f",
    border: "#8e4108",
    color: "#fffaf5",
    dot: "#ffe0b6",
    dotGlow: "rgba(255, 224, 182, 0.28)",
  };
}

function openPoiDetail(item: DayPOI, marker: any) {
  if (!infoWindow || !mapInstance) return;
  infoWindow.setContent(buildPoiDetailContent(item));
  const position = marker.getPosition?.() ?? [item.poi.longitude, item.poi.latitude];
  infoWindow.open(mapInstance, position);
}

function buildPoiDetailContent(item: DayPOI) {
  const title = item.label || item.poi.name;
  const kindLabel = item.kind === "stay" ? "住宿点位" : item.kind === "meal" ? "餐饮点位" : "活动点位";
  const readableTags = item.poi.tags.filter((tag) => !/^\d+$/.test(tag.trim()));
  const ratingLine =
    item.poi.rating != null
      ? `<div style="margin-top:8px;color:#465468;font-size:12px;">评分：${escapeHtml(String(item.poi.rating))}</div>`
      : "";
  const tagLine = readableTags.length
    ? `<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;">${readableTags
        .slice(0, 4)
        .map(
          (tag) =>
            `<span style="padding:3px 8px;border-radius:999px;background:#edf2f7;color:#506176;font-size:11px;">${escapeHtml(tag)}</span>`,
        )
        .join("")}</div>`
    : "";
  const openingLine = item.poi.opening_hours
    ? `<div style="margin-top:8px;color:#465468;font-size:12px;">开放时间：${escapeHtml(item.poi.opening_hours)}</div>`
    : "";
  const unresolvedHint = isWeakPoi(item)
    ? `<div style="margin-top:10px;padding:8px 10px;border-radius:12px;background:#fff4e5;color:#8a5a16;font-size:12px;">该点位仍处于近似匹配状态，建议结合详细行程再次确认。</div>`
    : "";

  return `
    <div style="min-width:220px;max-width:300px;padding:2px 2px 4px;">
      <div style="display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;background:${item.kind === "stay" ? "#17344c" : "#fff4de"};color:${item.kind === "stay" ? "#f8fbff" : "#8a5a16"};font-size:11px;font-weight:700;">
        ${kindLabel}
      </div>
      <div style="margin-top:10px;color:#132238;font-size:16px;font-weight:700;line-height:1.4;">
        ${escapeHtml(title)}
      </div>
      <div style="margin-top:6px;color:#5c6d82;font-size:12px;line-height:1.6;">
        ${escapeHtml(item.poi.name)}
      </div>
      ${
        item.poi.address
          ? `<div style="margin-top:8px;color:#465468;font-size:12px;line-height:1.6;">地址：${escapeHtml(item.poi.address)}</div>`
          : ""
      }
      ${ratingLine}
      ${openingLine}
      ${tagLine}
      ${unresolvedHint}
    </div>
  `;
}

function isWeakPoi(item: DayPOI) {
  const source = (item.poi.source ?? "").toLowerCase();
  return source === "manual_placeholder" || source === "activity_fallback" || source === "stay_fallback";
}

function truncateText(value: string, limit: number) {
  const text = value.trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 1))}…`;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function ensureAmap(mapConfig: MapRenderConfig) {
  if ((window as any).AMap) return (window as any).AMap;

  const existing = document.querySelector<HTMLScriptElement>(
    'script[data-amap-sdk="true"]',
  );
  if (existing) {
    await waitForAmap();
    return (window as any).AMap;
  }

  if (mapConfig.security_js_code) {
    (window as any)._AMapSecurityConfig = {
      securityJsCode: mapConfig.security_js_code,
    };
  }

  const script = document.createElement("script");
  script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(
    mapConfig.js_api_key ?? "",
  )}`;
  script.async = true;
  script.dataset.amapSdk = "true";

  const ready = new Promise<void>((resolve, reject) => {
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("高德地图 SDK 加载失败"));
  });

  document.head.appendChild(script);
  await ready;
  await waitForAmap();
  return (window as any).AMap;
}

function waitForAmap() {
  return new Promise<void>((resolve, reject) => {
    let attempts = 0;
    const timer = window.setInterval(() => {
      if ((window as any).AMap) {
        window.clearInterval(timer);
        resolve();
        return;
      }
      attempts += 1;
      if (attempts > 40) {
        window.clearInterval(timer);
        reject(new Error("高德地图 SDK 初始化超时"));
      }
    }, 150);
  });
}
</script>

<template>
  <div class="relative overflow-hidden rounded-[28px] border border-slate-100 bg-[#edf2ff] p-3">
    <div ref="mapRoot" class="h-[430px] rounded-[24px] bg-[#dfe8f3]"></div>
    <div class="pointer-events-none absolute left-6 top-6 flex flex-wrap gap-2">
      <span class="rounded-full border border-[#8e4108] bg-[#d46a1f] px-3 py-1 text-xs text-[#fffaf5] shadow-sm">
        浅色点位：当日活动
      </span>
      <span class="rounded-full border border-[#08323d] bg-[#0f4c5c] px-3 py-1 text-xs text-[#f8fbff] shadow-sm">
        深色点位：酒店住宿
      </span>
    </div>
    <div
      v-if="loading"
      class="absolute inset-3 flex items-center justify-center rounded-[24px] bg-white/72 text-sm text-slate-600 backdrop-blur-sm"
    >
      正在加载高德地图...
    </div>
    <div
      v-else-if="errorMessage"
      class="absolute inset-3 flex items-center justify-center rounded-[24px] bg-white/82 px-6 text-center text-sm leading-7 text-slate-500 backdrop-blur-sm"
    >
      {{ errorMessage }}
    </div>
  </div>
</template>
