import { nextTick, type Ref } from "vue";

import { getIntegrationStatus, getPlanningTelemetry } from "../api/planning";
import type {
  IntegrationStatus,
  PlanningResponse,
  PlanningTelemetry,
} from "../types/planning";

type NoticeTone = "success" | "warning" | "error";

export function createEmptyIntegrationStatus(): IntegrationStatus {
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
    warnings: [],
  };
}

export function createEmptyPlanningTelemetry(): PlanningTelemetry {
  return {
    enabled: false,
    window_size: 0,
    total_requests: 0,
    cache_hits: 0,
    cache_misses: 0,
    stages: {},
    updated_at: null,
    warnings: [],
  };
}

export function usePlanningSupport(options: {
  integrationStatus: Ref<IntegrationStatus>;
  integrationLoading: Ref<boolean>;
  integrationError: Ref<string>;
  telemetry: Ref<PlanningTelemetry>;
  telemetryLoading: Ref<boolean>;
  telemetryError: Ref<string>;
  progress: Ref<number>;
  progressLabel: Ref<string>;
  exportRoot: Ref<HTMLElement | null>;
  result: Ref<PlanningResponse | null>;
  expandedDays: Ref<number[]>;
  showDevPanels: boolean;
  stageOptions: string[];
  openNotice: (tone: NoticeTone, title: string, messages: string[]) => void;
}) {
  const {
    integrationStatus,
    integrationLoading,
    integrationError,
    telemetry,
    telemetryLoading,
    telemetryError,
    progress,
    progressLabel,
    exportRoot,
    result,
    expandedDays,
    showDevPanels,
    stageOptions,
    openNotice,
  } = options;

  let progressTimer: number | null = null;

  async function loadIntegrationStatus(refresh = false) {
    integrationLoading.value = true;
    integrationError.value = "";
    try {
      integrationStatus.value = await getIntegrationStatus({ refresh });
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

  async function loadPlanningTelemetry() {
    telemetryLoading.value = true;
    telemetryError.value = "";
    try {
      telemetry.value = await getPlanningTelemetry();
    } catch (error) {
      telemetryError.value =
        error instanceof Error ? error.message : "获取性能统计失败，请稍后重试。";
      telemetry.value = createEmptyPlanningTelemetry();
    } finally {
      telemetryLoading.value = false;
    }
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
    if (success) {
      window.setTimeout(() => {
        progress.value = 0;
      }, 900);
    }
  }

  function toUserError(message: string) {
    const lower = message.toLowerCase();
    if (lower.includes("destination") || message.includes("城市名")) {
      return "目的地仅支持中文城市名，例如：上海、北京市。";
    }
    if (lower.includes("限流") || lower.includes("rate limit")) {
      return "大模型服务当前限流，请稍后重试。";
    }
    if (lower.includes("地图服务") || lower.includes("mcp")) {
      return "地图服务当前不可用，请检查高德配置或稍后重试。";
    }
    if (lower.includes("network") || lower.includes("timeout")) {
      return "当前网络或外部服务响应较慢，请稍后重试。";
    }
    return message || "生成行程失败，请稍后重试。";
  }

  function buildPlanNotices(response: PlanningResponse) {
    const notices = [...response.meta.warnings, ...response.diagnostics.warnings];
    for (const item of response.meta.warnings) {
      if (item.startsWith("Reservation audit:")) {
        notices.push(item.replace(/^Reservation audit:\s*/, ""));
      }
    }
    return [...new Set(notices)];
  }

  async function exportAs(type: "png" | "pdf") {
    if (!exportRoot.value || !result.value) return;
    const previousExpandedDays = [...expandedDays.value];
    expandedDays.value = result.value.plan.days.map((day) => day.day_number);
    await nextTick();
    try {
      const [{ default: html2canvas }, { default: jsPDF }] = await Promise.all([
        import("html2canvas"),
        import("jspdf"),
      ]);
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

  return {
    buildPlanNotices,
    exportAs,
    loadIntegrationStatus,
    loadPlanningTelemetry,
    startProgress,
    stopProgress,
    toUserError,
  };
}
