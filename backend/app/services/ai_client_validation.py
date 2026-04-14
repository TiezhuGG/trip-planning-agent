from __future__ import annotations

from app.schemas.planning import InitialPlanDraft, TravelPlan, TripPlanningRequest


def ensure_initial_plan_integrity(
    request: TripPlanningRequest,
    draft: InitialPlanDraft,
) -> None:
    if len(draft.days) != request.days:
        raise ValueError(f"初步规划天数不匹配: 期望 {request.days} 天，实际 {len(draft.days)} 天。")

    day_numbers = [day.day_number for day in draft.days]
    if len(day_numbers) != len(set(day_numbers)):
        raise ValueError("初步规划包含重复 day_number。")

    expected = set(range(1, request.days + 1))
    if set(day_numbers) != expected:
        raise ValueError("初步规划的 day_number 必须覆盖 1..request.days。")


def ensure_final_plan_integrity(
    request: TripPlanningRequest,
    plan: TravelPlan,
    require_routes: bool = True,
) -> None:
    if len(plan.days) != request.days:
        raise ValueError(f"最终行程天数不匹配: 期望 {request.days} 天，实际 {len(plan.days)} 天。")

    day_numbers = [day.day_number for day in plan.days]
    if len(day_numbers) != len(set(day_numbers)):
        raise ValueError("最终行程包含重复 day_number。")

    expected = set(range(1, request.days + 1))
    if set(day_numbers) != expected:
        raise ValueError("最终行程的 day_number 必须覆盖 1..request.days。")

    for day in plan.days:
        if not day.activities:
            raise ValueError(f"第 {day.day_number} 天缺少 activities。")
        if not day.meals:
            raise ValueError(f"第 {day.day_number} 天缺少 meals。")
        if require_routes and not day.route_summaries:
            raise ValueError(f"第 {day.day_number} 天缺少 route_summaries。")
        for route in day.route_summaries:
            if route.day_number not in (None, day.day_number):
                raise ValueError(f"第 {day.day_number} 天 route_summaries.day_number 不一致。")
        expected_total = (
            day.cost_breakdown.accommodation_per_person_cny
            + day.cost_breakdown.transport_per_person_cny
            + day.cost_breakdown.food_per_person_cny
            + day.cost_breakdown.tickets_per_person_cny
            + day.cost_breakdown.extras_per_person_cny
        )
        if day.cost_breakdown.total_per_person_cny != expected_total:
            raise ValueError(f"第 {day.day_number} 天 cost_breakdown.total_per_person_cny 不一致。")
