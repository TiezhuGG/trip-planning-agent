import type {
  IntegrationStatus,
  PlanningResponse,
  TripPlanningRequest,
} from "../types/planning";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function extractErrorMessage(
  response: Response,
  fallbackMessage: string,
): Promise<string> {
  const text = await response.text();
  if (!text) return fallbackMessage;
  try {
    const payload = JSON.parse(text) as {
      detail?: string | { code?: string; message?: string };
    };
    if (typeof payload.detail === "string" && payload.detail) return payload.detail;
    if (
      payload.detail &&
      typeof payload.detail === "object" &&
      payload.detail.message
    ) {
      return payload.detail.message;
    }
  } catch {
    // Fall back to the raw response text.
  }
  return text;
}

export async function getIntegrationStatus(): Promise<IntegrationStatus> {
  const response = await fetch(`${API_BASE_URL}/api/v1/plans/integrations/status`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "获取集成状态失败"));
  }
  return response.json() as Promise<IntegrationStatus>;
}

export async function generatePlan(
  payload: TripPlanningRequest,
): Promise<PlanningResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/plans/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "生成旅行计划失败"));
  }

  return response.json() as Promise<PlanningResponse>;
}
