import type {
  DayPOI,
  GeoPoint,
  MapRenderConfig,
  RouteSummary,
} from "../types/planning"

const DEFAULT_CENTER: [number, number] = [121.4737, 31.2304]
const DETAIL_KIND_LABELS: Record<DayPOI["kind"], string> = {
  stay: "\u4f4f\u5bbf\u70b9\u4f4d",
  meal: "\u9910\u996e\u70b9\u4f4d",
  activity: "\u6d3b\u52a8\u70b9\u4f4d",
}

export function filterRenderablePois(pois: DayPOI[]) {
  return pois.filter((item) => item.poi.longitude != null && item.poi.latitude != null)
}

export function hasRenderableMapData(pois: DayPOI[], routes: RouteSummary[]) {
  return pois.length > 0 || routes.some((route) => route.polyline.length > 1)
}

export function buildMapSignature(
  mapConfig: MapRenderConfig,
  pois: DayPOI[],
  routes: RouteSummary[],
) {
  return JSON.stringify({
    key: mapConfig.js_api_key,
    security: mapConfig.security_js_code,
    enabled: mapConfig.enabled,
    pois: pois.map((item) => [
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
    routes: routes.map((route) => [
      route.day_number,
      route.title,
      route.from_name,
      route.to_name,
      route.mode,
      route.distance_text,
      route.duration_text,
      route.polyline.map((point) => [point.longitude, point.latitude]),
    ]),
  })
}

export function resolveMapCenter(center: GeoPoint | null, pois: DayPOI[]) {
  if (center) return [center.longitude, center.latitude]
  const firstPoi = pois[0]?.poi
  if (firstPoi?.longitude != null && firstPoi?.latitude != null) {
    return [firstPoi.longitude, firstPoi.latitude]
  }
  return DEFAULT_CENTER
}

export function buildMarkerContent(item: DayPOI) {
  const style = markerStyle(item.kind)
  const label = truncateText(item.label || item.poi.name, item.kind === "stay" ? 16 : 14)
  return `
    <div style="position:relative;transform:translate(-50%, -100%);pointer-events:auto;">
      <div style="display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border-radius:999px;background:${style.background};border:1px solid ${style.border};color:${style.color};font-size:12px;font-weight:600;line-height:1;white-space:nowrap;box-shadow:0 14px 28px rgba(15,23,42,0.18);backdrop-filter:blur(10px);">
        <span style="width:10px;height:10px;border-radius:999px;background:${style.dot};box-shadow:0 0 0 3px ${style.dotGlow};"></span>
        <span>${escapeHtml(label)}</span>
      </div>
      <div style="width:12px;height:12px;margin:-2px auto 0;background:${style.background};border-right:1px solid ${style.border};border-bottom:1px solid ${style.border};transform:rotate(45deg);box-shadow:8px 8px 18px rgba(15,23,42,0.08);"></div>
    </div>
  `
}

export function buildPoiDetailContent(item: DayPOI) {
  const title = item.label || item.poi.name
  const kindLabel = DETAIL_KIND_LABELS[item.kind]
  const readableTags = item.poi.tags.filter((tag) => !/^\d+$/.test(tag.trim()))
  const ratingLine =
    item.poi.rating != null
      ? `<div style="margin-top:8px;color:#465468;font-size:12px;">评分：${escapeHtml(String(item.poi.rating))}</div>`
      : ""
  const tagLine = readableTags.length
    ? `<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;">${readableTags
        .slice(0, 4)
        .map(
          (tag) =>
            `<span style="padding:3px 8px;border-radius:999px;background:#edf2f7;color:#506176;font-size:11px;">${escapeHtml(tag)}</span>`,
        )
        .join("")}</div>`
    : ""
  const openingLine = item.poi.opening_hours
    ? `<div style="margin-top:8px;color:#465468;font-size:12px;">开放时间：${escapeHtml(item.poi.opening_hours)}</div>`
    : ""
  const unresolvedHint = isWeakPoi(item)
    ? `<div style="margin-top:10px;padding:8px 10px;border-radius:12px;background:#fff4e5;color:#8a5a16;font-size:12px;">该点位仍处于近似匹配状态，建议结合详细行程再次确认。</div>`
    : ""

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
  `
}

export function routePolylinePath(route: RouteSummary) {
  return route.polyline.map((point) => [point.longitude, point.latitude])
}

function markerStyle(kind: DayPOI["kind"]) {
  if (kind === "stay") {
    return {
      background: "#0f4c5c",
      border: "#08323d",
      color: "#f8fbff",
      dot: "#8be9ff",
      dotGlow: "rgba(139, 233, 255, 0.28)",
    }
  }
  return {
    background: "#d46a1f",
    border: "#8e4108",
    color: "#fffaf5",
    dot: "#ffe0b6",
    dotGlow: "rgba(255, 224, 182, 0.28)",
  }
}

function isWeakPoi(item: DayPOI) {
  const source = (item.poi.source ?? "").toLowerCase()
  return source === "manual_placeholder" || source === "activity_fallback" || source === "stay_fallback"
}

function truncateText(value: string, limit: number) {
  const text = value.trim()
  if (text.length <= limit) return text
  return `${text.slice(0, Math.max(0, limit - 1))}\u2026`
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}
