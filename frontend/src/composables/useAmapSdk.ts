import type { MapRenderConfig } from "../types/planning";

export async function ensureAmap(mapConfig: MapRenderConfig) {
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
