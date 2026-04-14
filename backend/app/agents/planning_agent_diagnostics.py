from __future__ import annotations

from collections.abc import Callable

from app.schemas.planning import AgentExecution, IntegrationStatus, PlanDiagnostics, StageDiagnostic


def apply_llm_status_to_integration(integration_status: IntegrationStatus, llm_status) -> IntegrationStatus:
    integration_status.llm_enabled = llm_status.enabled
    integration_status.llm_reachable = llm_status.reachable
    integration_status.llm_model = llm_status.model
    integration_status.llm_base_url = llm_status.base_url
    integration_status.warnings.extend(llm_status.warnings)
    return integration_status


def resolve_response_status(
    *,
    fallback_used: bool,
    diagnostics: PlanDiagnostics,
) -> str:
    if fallback_used:
        return "fallback_success"
    if any(item.status == "error" for item in [*diagnostics.llm, *diagnostics.mcp]):
        return "partial_success"
    return "success"


def build_plan_diagnostics(
    *,
    integration_status: IntegrationStatus,
    warnings: list[str],
    seed_trace: AgentExecution,
    seed_fallback_used: bool,
    seed_llm_used: bool,
    compose_trace: AgentExecution,
    compose_fallback_used: bool,
    compose_llm_used: bool,
    weather_trace: AgentExecution,
    poi_trace: AgentExecution,
    hotel_trace: AgentExecution,
    hotel_binding_trace: AgentExecution,
    meal_candidate_trace: AgentExecution,
    meal_binding_trace: AgentExecution,
    route_trace: AgentExecution,
    truth_trace: AgentExecution,
    plan,
) -> PlanDiagnostics:
    llm_diagnostics = [
        StageDiagnostic(
            stage="initial_planning",
            status="fallback" if seed_fallback_used else ("warning" if seed_trace.warnings else "ok"),
            summary=seed_trace.summary,
            warnings=seed_trace.warnings,
            fallback_used=seed_fallback_used,
            used_llm=seed_llm_used,
            provider=integration_status.llm_model,
        ),
        StageDiagnostic(
            stage="final_composition",
            status="fallback" if compose_fallback_used else ("warning" if compose_trace.warnings else "ok"),
            summary=compose_trace.summary,
            warnings=compose_trace.warnings,
            fallback_used=compose_fallback_used,
            used_llm=compose_llm_used,
            provider=integration_status.llm_model,
        ),
    ]
    mcp_diagnostics = [
        trace_to_stage("poi_collection", poi_trace),
        trace_to_stage("hotel_candidates", hotel_trace),
        trace_to_stage("weather", weather_trace),
        trace_to_stage("meal_candidates", meal_candidate_trace),
        trace_to_stage("daily_hotel_binding", hotel_binding_trace),
        trace_to_stage("daily_meal_binding", meal_binding_trace),
        trace_to_stage("route_generation", route_trace),
        trace_to_stage("plan_truth_binding", truth_trace),
    ]
    fallback_sources = [item.stage for item in llm_diagnostics if item.fallback_used]
    fallback_sources.extend(
        fallback
        for day in getattr(plan, "days", [])
        for fallback in getattr(day, "fallbacks", [])
    )
    return PlanDiagnostics(
        llm=llm_diagnostics,
        mcp=mcp_diagnostics,
        warnings=list(dict.fromkeys(item for item in warnings if item)),
        fallbacks_used=list(dict.fromkeys(fallback_sources)),
        error_code="LLM_TEMPLATE_FALLBACK" if (seed_fallback_used or compose_fallback_used) else "",
    )


def trace_to_stage(stage: str, trace: AgentExecution) -> StageDiagnostic:
    status = "ok"
    if not trace.success:
        status = "error"
    elif trace.warnings:
        status = "warning"
    return StageDiagnostic(
        stage=stage,
        status=status,
        summary=trace.summary,
        warnings=trace.warnings,
        fallback_used=False,
        used_llm=trace.used_llm,
    )


def collect_stage_tool_warnings(
    *,
    stage_trace: list,
    fallback_message: str,
    is_rate_limit_text: Callable[[str], bool],
) -> list[str]:
    if not stage_trace:
        return []

    warnings: list[str] = []
    rate_limited = False
    for item in stage_trace:
        if getattr(item, "success", True):
            continue
        summary = getattr(item, "summary", "")
        if not summary:
            continue
        if is_rate_limit_text(summary):
            rate_limited = True
            continue
        warnings.append(summary)

    if rate_limited:
        warnings.append(fallback_message)
    return list(dict.fromkeys(warnings))
