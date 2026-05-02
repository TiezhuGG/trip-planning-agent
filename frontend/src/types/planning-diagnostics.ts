import type { GeoPoint } from "./planning-domain"

export interface AgentExecution {
  agent_name: string
  success: boolean
  summary: string
  used_llm: boolean
  used_tools: string[]
  warnings: string[]
}

export interface PlanGenerationMeta {
  llm_used: boolean
  fallback_used: boolean
  model_name: string
  warnings: string[]
  stage_timings_ms: Record<string, number>
}

export interface StageDiagnostic {
  stage: string
  status: "ok" | "warning" | "fallback" | "error"
  summary: string
  code: string
  warnings: string[]
  fallback_used: boolean
  used_llm: boolean
  provider: string
}

export interface ReservationCoverageDiagnostic {
  reservation_id: string
  title: string
  status: "covered" | "unresolved" | "pending"
  target_days: number[]
  matched_days: number[]
  auto_anchored_days: number[]
  coordinated_days: number[]
  coordination_tip: string
  reason_code:
    | "generated_match"
    | "runtime_fallback"
    | "missing_time_window"
    | "day_conflict"
    | "no_explicit_match"
  reason_summary: string
  conflict_items: ReservationConflictItem[]
  detail: string
}

export interface ReservationConflictItem {
  day_number: number
  kind: "activity" | "meal" | "stay"
  label: string
  time_text: string
  summary: string
}

export interface PlanDiagnostics {
  llm: StageDiagnostic[]
  mcp: StageDiagnostic[]
  warnings: string[]
  fallbacks_used: string[]
  reservation_coverage: ReservationCoverageDiagnostic[]
  error_code: string
}

export interface MapRenderConfig {
  provider: "amap"
  enabled: boolean
  js_api_key: string | null
  security_js_code: string | null
  center: GeoPoint | null
}

export interface IntegrationStatus {
  mcp_enabled: boolean
  mcp_connected: boolean
  mcp_command: string
  llm_enabled: boolean
  llm_reachable: boolean
  llm_model: string
  llm_base_url: string
  available_tools: string[]
  resolved_tools: Record<string, string>
  missing_tools: string[]
  map_rendering_enabled: boolean
  map_js_key_configured: boolean
  security_js_code_configured: boolean
  warnings: string[]
}
