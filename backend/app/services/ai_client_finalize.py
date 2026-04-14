from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.planning import PlanningContext, TravelPlan, TripPlanningRequest

NormalizeComposePayload = Callable[[dict[str, Any], TripPlanningRequest, PlanningContext], dict[str, Any]]
NormalizePlanDays = Callable[[TripPlanningRequest, TravelPlan, PlanningContext], TravelPlan]
EnsureFinalPlanIntegrity = Callable[[TripPlanningRequest, TravelPlan, bool], None]
ApplyDeterministicBudget = Callable[[TripPlanningRequest, TravelPlan], TravelPlan]
RequestJsonPayload = Callable[..., Awaitable[dict[str, Any]]]


def finalize_composed_plan(
    *,
    request: TripPlanningRequest,
    context: PlanningContext,
    payload: dict[str, Any],
    normalize_compose_payload_fn: NormalizeComposePayload,
    normalize_plan_days_fn: NormalizePlanDays,
    ensure_final_plan_integrity_fn: EnsureFinalPlanIntegrity,
    apply_deterministic_budget_fn: ApplyDeterministicBudget,
) -> TravelPlan:
    normalized_payload = normalize_compose_payload_fn(payload, request, context)
    plan = TravelPlan.model_validate(normalized_payload)
    plan = normalize_plan_days_fn(request, plan, context)
    ensure_final_plan_integrity_fn(request, plan, bool(context.routes))
    return apply_deterministic_budget_fn(request, plan)


def finalize_plan_with_routes(
    *,
    request: TripPlanningRequest,
    plan: TravelPlan,
    context: PlanningContext,
    normalize_plan_days_fn: NormalizePlanDays,
    ensure_final_plan_integrity_fn: EnsureFinalPlanIntegrity,
    apply_deterministic_budget_fn: ApplyDeterministicBudget,
) -> TravelPlan:
    plan = normalize_plan_days_fn(request, plan, context)
    ensure_final_plan_integrity_fn(request, plan, True)
    return apply_deterministic_budget_fn(request, plan)


async def repair_compose_payload(
    *,
    request: TripPlanningRequest,
    raw_payload: dict[str, Any],
    schema_hint: dict[str, Any],
    client: Any | None,
    model: str | None,
    request_json_payload_fn: RequestJsonPayload,
) -> dict[str, Any] | None:
    try:
        return await request_json_payload_fn(
            system_prompt=(
                "You are a JSON repair assistant for travel plans. "
                "Return JSON only. Keep natural Chinese text. "
                "Fix the plan so days contains exactly request.days records "
                "with unique day_number from 1..request.days."
            ),
            user_payload={
                "request": request.model_dump(mode="json"),
                "broken_plan": raw_payload,
                "response_schema_hint": schema_hint,
            },
            temperature=0,
            max_tokens=8192,
            client=client,
            model=model,
        )
    except Exception:
        return None
