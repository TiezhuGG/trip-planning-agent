import type {
  IntegrationStatus,
  PlanningTelemetry,
  PlanningResponse,
  ReplanRequest,
  TripCreateRequest,
  TripPlanningRequest,
  TripWorkspace,
  TripWorkspacePatchRequest,
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

export async function getIntegrationStatus(
  options: { refresh?: boolean } = {},
): Promise<IntegrationStatus> {
  const params = new URLSearchParams();
  if (options.refresh) params.set("refresh", "true");
  const query = params.toString();
  const response = await fetch(
    `${API_BASE_URL}/api/v1/plans/integrations/status${query ? `?${query}` : ""}`,
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "获取集成状态失败"));
  }
  return response.json() as Promise<IntegrationStatus>;
}

export async function getPlanningTelemetry(): Promise<PlanningTelemetry> {
  const response = await fetch(`${API_BASE_URL}/api/v1/plans/telemetry`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "获取性能统计失败"));
  }
  return response.json() as Promise<PlanningTelemetry>;
}

export async function generatePlan(
  payload: TripPlanningRequest,
  options: { debug?: boolean } = {},
): Promise<PlanningResponse> {
  const params = new URLSearchParams();
  if (options.debug) params.set("debug", "true");
  const query = params.toString();
  const response = await fetch(
    `${API_BASE_URL}/api/v1/plans/generate${query ? `?${query}` : ""}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "生成旅行计划失败"));
  }

  return response.json() as Promise<PlanningResponse>;
}

export async function createTripWorkspace(
  payload: TripCreateRequest,
): Promise<TripWorkspace> {
  const response = await fetch(`${API_BASE_URL}/api/v1/trips`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "保存行程工作区失败"));
  }
  return response.json() as Promise<TripWorkspace>;
}

export async function getTripWorkspace(tripId: string): Promise<TripWorkspace> {
  const response = await fetch(`${API_BASE_URL}/api/v1/trips/${encodeURIComponent(tripId)}`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "获取行程工作区失败"));
  }
  return response.json() as Promise<TripWorkspace>;
}

export async function getTripWorkspaceByShareToken(
  shareToken: string,
): Promise<TripWorkspace> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/trips/share/${encodeURIComponent(shareToken)}`,
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "获取分享行程失败"));
  }
  return response.json() as Promise<TripWorkspace>;
}

export async function patchTripWorkspace(
  tripId: string,
  payload: TripWorkspacePatchRequest,
): Promise<TripWorkspace> {
  const response = await fetch(`${API_BASE_URL}/api/v1/trips/${encodeURIComponent(tripId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "更新行程工作区失败"));
  }
  return response.json() as Promise<TripWorkspace>;
}

export async function replanTripWorkspace(
  tripId: string,
  payload: ReplanRequest,
): Promise<TripWorkspace> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/trips/${encodeURIComponent(tripId)}/replan`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "重规划行程失败"));
  }
  return response.json() as Promise<TripWorkspace>;
}
