import type {
  CalendarExportScope,
  IntegrationStatus,
  PlanningJob,
  PlanningJobSummary,
  PrecheckRefreshRequest,
  PlanningTelemetry,
  PlanningResponse,
  ReplanRequest,
  TripSummary,
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

function resolveDownloadFilename(response: Response, fallbackName: string): string {
  const contentDisposition = response.headers.get("Content-Disposition") ?? "";
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const basicMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
  return basicMatch?.[1] ?? fallbackName;
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

export async function startGeneratePlanJob(
  payload: TripPlanningRequest,
  options: { debug?: boolean } = {},
): Promise<PlanningJob> {
  const params = new URLSearchParams();
  if (options.debug) params.set("debug", "true");
  const query = params.toString();
  const response = await fetch(
    `${API_BASE_URL}/api/v1/jobs/plans/generate${query ? `?${query}` : ""}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "创建规划任务失败"));
  }
  return response.json() as Promise<PlanningJob>;
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

export async function listRecentTripWorkspaces(
  options: { limit?: number } = {},
): Promise<TripSummary[]> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  const query = params.toString();
  const response = await fetch(
    `${API_BASE_URL}/api/v1/trips${query ? `?${query}` : ""}`,
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "读取最近工作区失败"));
  }
  return response.json() as Promise<TripSummary[]>;
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

export async function startUpdateTripWorkspaceJob(
  tripId: string,
  payload: TripWorkspacePatchRequest,
): Promise<PlanningJob> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/jobs/trips/${encodeURIComponent(tripId)}/update`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "创建工作区更新任务失败"));
  }
  return response.json() as Promise<PlanningJob>;
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

export async function startReplanTripWorkspaceJob(
  tripId: string,
  payload: ReplanRequest,
): Promise<PlanningJob> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/jobs/trips/${encodeURIComponent(tripId)}/replan`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "创建重规划任务失败"));
  }
  return response.json() as Promise<PlanningJob>;
}

export async function refreshTripWorkspacePrecheck(
  tripId: string,
  payload: PrecheckRefreshRequest = {},
): Promise<TripWorkspace> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/trips/${encodeURIComponent(tripId)}/precheck`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "刷新出发前校验失败"));
  }
  return response.json() as Promise<TripWorkspace>;
}

export async function startTripWorkspacePrecheckJob(
  tripId: string,
  payload: PrecheckRefreshRequest = {},
): Promise<PlanningJob> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/jobs/trips/${encodeURIComponent(tripId)}/precheck`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "创建预检任务失败"));
  }
  return response.json() as Promise<PlanningJob>;
}

export async function getPlanningJob(jobId: string): Promise<PlanningJob> {
  const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "读取任务状态失败"));
  }
  return response.json() as Promise<PlanningJob>;
}

export async function listPlanningJobs(
  options: { limit?: number; tripId?: string } = {},
): Promise<PlanningJobSummary[]> {
  const params = new URLSearchParams();
  if (options.limit) params.set("limit", String(options.limit));
  if (options.tripId) params.set("trip_id", options.tripId);
  const query = params.toString();
  const response = await fetch(`${API_BASE_URL}/api/v1/jobs${query ? `?${query}` : ""}`);
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "读取任务列表失败"));
  }
  return response.json() as Promise<PlanningJobSummary[]>;
}

export async function revokeTripWorkspaceShare(
  tripId: string,
): Promise<TripWorkspace> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/trips/${encodeURIComponent(tripId)}/share/revoke`,
    {
      method: "POST",
    },
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "撤销分享链接失败"));
  }
  return response.json() as Promise<TripWorkspace>;
}

export async function regenerateTripWorkspaceShare(
  tripId: string,
): Promise<TripWorkspace> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/trips/${encodeURIComponent(tripId)}/share/regenerate`,
    {
      method: "POST",
    },
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "重新生成分享链接失败"));
  }
  return response.json() as Promise<TripWorkspace>;
}

export async function downloadTripWorkspaceCalendar(
  tripId: string,
  scope: CalendarExportScope = "full",
): Promise<{ blob: Blob; filename: string }> {
  const query = new URLSearchParams({ scope }).toString();
  const response = await fetch(
    `${API_BASE_URL}/api/v1/trips/${encodeURIComponent(tripId)}/export/ics?${query}`,
  );
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, "导出日历失败"));
  }
  return {
    blob: await response.blob(),
    filename: resolveDownloadFilename(response, "trip-workspace.ics"),
  };
}
