from __future__ import annotations

from typing import Any

from app.schemas.planning import (
    InitialPlanDraft,
    PlanningContext,
    RouteSummary,
    ToolCallRecord,
    TravelPlan,
    TripPlanningRequest,
)
from app.services.ai_client_compose import normalize_compose_payload
from app.services.ai_client_finalize import (
    finalize_composed_plan as finalize_composed_plan_runtime,
    finalize_plan_with_routes as finalize_plan_with_routes_runtime,
    repair_compose_payload as repair_compose_payload_runtime,
)
from app.services.ai_client_models import FinalPlanBuildResult, InitialPlanBuildResult
from app.services.ai_client_orchestration import (
    build_initial_plan as build_initial_plan_runtime,
    compose_plan as compose_plan_runtime,
)
from app.services.ai_client_payloads import (
    build_compose_user_payload as build_compose_user_payload_runtime,
    compact_tool_arguments as compact_tool_arguments_runtime,
    serialize_context_for_llm as serialize_context_for_llm_runtime,
    serialize_poi_for_llm as serialize_poi_for_llm_runtime,
    serialize_route_for_llm as serialize_route_for_llm_runtime,
    serialize_tool_trace_for_llm as serialize_tool_trace_for_llm_runtime,
)
from app.services.ai_client_runtime import format_exception
from app.services.ai_client_validation import (
    ensure_final_plan_integrity as ensure_final_plan_integrity_runtime,
    ensure_initial_plan_integrity as ensure_initial_plan_integrity_runtime,
)


class TravelAIClientPlanAdapterMixin:
    async def build_initial_plan(self, request: TripPlanningRequest) -> InitialPlanBuildResult:
        return await build_initial_plan_runtime(
            request=request,
            providers=self._configured_providers(),
            build_initial_plan_with_provider_fn=self._build_initial_plan_with_provider,
            should_switch_to_backup_model_fn=self._should_switch_to_backup_model,
            should_fallback_to_template_fn=self._should_fallback_to_template,
            format_exception_fn=format_exception,
            fallback_initial_plan_fn=self._fallback_initial_plan,
        )

    async def compose_plan(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
        tool_trace: list[ToolCallRecord],
    ) -> FinalPlanBuildResult:
        return await compose_plan_runtime(
            request=request,
            initial_plan=initial_plan,
            context=context,
            tool_trace=tool_trace,
            providers=self._configured_providers(),
            compose_with_provider_fn=self._compose_with_provider,
            should_switch_to_backup_model_fn=self._should_switch_to_backup_model,
            should_fallback_to_template_fn=self._should_fallback_to_template,
            format_exception_fn=format_exception,
            build_fallback_final_plan_fn=self._build_fallback_final_plan,
        )

    def _finalize_composed_plan(
        self,
        request: TripPlanningRequest,
        context: PlanningContext,
        payload: dict[str, Any],
    ) -> TravelPlan:
        return finalize_composed_plan_runtime(
            request=request,
            context=context,
            payload=payload,
            normalize_compose_payload_fn=self._normalize_compose_payload,
            normalize_plan_days_fn=self._normalize_plan_days,
            ensure_final_plan_integrity_fn=self._ensure_final_plan_integrity,
            apply_deterministic_budget_fn=self._apply_deterministic_budget,
        )

    def finalize_plan_with_routes(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        context: PlanningContext,
    ) -> TravelPlan:
        return finalize_plan_with_routes_runtime(
            request=request,
            plan=plan,
            context=context,
            normalize_plan_days_fn=self._normalize_plan_days,
            ensure_final_plan_integrity_fn=self._ensure_final_plan_integrity,
            apply_deterministic_budget_fn=self._apply_deterministic_budget,
        )

    def _normalize_compose_payload(
        self,
        payload: dict[str, Any],
        request: TripPlanningRequest,
        context: PlanningContext,
    ) -> dict[str, Any]:
        return normalize_compose_payload(payload, request, context)

    async def _repair_compose_payload(
        self,
        request: TripPlanningRequest,
        raw_payload: dict[str, Any],
        schema_hint: dict[str, Any],
        client: Any | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        return await repair_compose_payload_runtime(
            request=request,
            raw_payload=raw_payload,
            schema_hint=schema_hint,
            client=client,
            model=model,
            request_json_payload_fn=self._request_json_payload,
        )

    def _build_compose_user_payload(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        context: PlanningContext,
        tool_trace: list[ToolCallRecord],
    ) -> dict[str, Any]:
        return build_compose_user_payload_runtime(
            request_payload=request.model_dump(mode="json"),
            initial_plan_payload=initial_plan.model_dump(mode="json"),
            context=context,
            tool_trace=tool_trace,
        )

    def _serialize_context_for_llm(self, context: PlanningContext, detail_level: str) -> dict[str, Any]:
        return serialize_context_for_llm_runtime(context, detail_level)

    def _serialize_tool_trace_for_llm(
        self,
        tool_trace: list[ToolCallRecord],
        detail_level: str,
    ) -> list[dict[str, Any]]:
        return serialize_tool_trace_for_llm_runtime(tool_trace, detail_level)

    def _serialize_poi_for_llm(self, poi: Any) -> dict[str, Any]:
        return serialize_poi_for_llm_runtime(poi)

    def _serialize_route_for_llm(self, route: RouteSummary, step_limit: int) -> dict[str, Any]:
        return serialize_route_for_llm_runtime(route, step_limit)

    def _compact_tool_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return compact_tool_arguments_runtime(arguments)

    def _ensure_initial_plan_integrity(
        self,
        request: TripPlanningRequest,
        draft: InitialPlanDraft,
    ) -> None:
        ensure_initial_plan_integrity_runtime(request, draft)

    def _ensure_final_plan_integrity(
        self,
        request: TripPlanningRequest,
        plan: TravelPlan,
        require_routes: bool = True,
    ) -> None:
        ensure_final_plan_integrity_runtime(request, plan, require_routes)
