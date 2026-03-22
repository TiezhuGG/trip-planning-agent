import type { IntegrationStatus, PlanningResponse, TripPlanningRequest } from '../types/planning'

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, '')
}

function resolveApiBaseUrl() {
  const explicitBase = String(import.meta.env.VITE_API_BASE_URL ?? '').trim()
  if (explicitBase) return trimTrailingSlash(explicitBase)

  const publicBase = String(import.meta.env.BASE_URL ?? '').trim()
  if (!publicBase || publicBase === '/') return ''

  return trimTrailingSlash(publicBase)
}

const API_BASE_URL = resolveApiBaseUrl()

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
