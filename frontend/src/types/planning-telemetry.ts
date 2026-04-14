export interface StageTimingPoint {
  at: string
  value_ms: number
}

export interface StageTimingStats {
  count: number
  p50_ms: number
  p95_ms: number
  max_ms: number
  last_ms: number
  recent_ms: number[]
  recent_points: StageTimingPoint[]
}

export interface PlanningTelemetry {
  enabled: boolean
  window_size: number
  total_requests: number
  cache_hits: number
  cache_misses: number
  stages: Record<string, StageTimingStats>
  updated_at: string | null
  warnings: string[]
}
