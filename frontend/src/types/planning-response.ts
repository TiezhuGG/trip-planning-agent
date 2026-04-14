import type {
  AgentExecution,
  IntegrationStatus,
  MapRenderConfig,
  PlanDiagnostics,
  PlanGenerationMeta,
} from "./planning-diagnostics"
import type {
  InitialPlanDraft,
  PlanningContext,
  ToolCallRecord,
  TravelPlan,
} from "./planning-domain"
import type { TripPlanningRequest } from "./planning-request"

export interface PlanningResponse {
  status: "success" | "partial_success" | "fallback_success"
  generated_at: string
  request_echo: TripPlanningRequest
  initial_plan: InitialPlanDraft
  planning_context: PlanningContext
  agent_trace: AgentExecution[]
  tool_trace: ToolCallRecord[]
  meta: PlanGenerationMeta
  diagnostics: PlanDiagnostics
  map_config: MapRenderConfig
  integration_status: IntegrationStatus
  plan: TravelPlan
}
