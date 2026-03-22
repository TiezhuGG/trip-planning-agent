import type { IntegrationStatus, PlanningResponse, TripPlanningRequest } from '../types/planning'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export async function getIntegrationStatus(): Promise<IntegrationStatus> {
  const response = await fetch(`${API_BASE_URL}/api/v1/plans/integrations/status`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || '获取集成状态失败')
  }
  return response.json() as Promise<IntegrationStatus>
}

export async function generatePlan(payload: TripPlanningRequest): Promise<PlanningResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/plans/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || '生成旅行计划失败')
  }

  return response.json() as Promise<PlanningResponse>
}
