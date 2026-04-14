from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.schemas.planning import PlanningResponse, ReplanRequest, TripPlanningRequest, TripWorkspace


def resolve_replan_targets(
    *,
    request: TripPlanningRequest,
    locked_day_numbers: list[int],
    payload: ReplanRequest,
    normalize_day_numbers: Callable[[list[int], int], list[int]],
) -> set[int]:
    valid_days = set(range(1, request.days + 1))
    explicit_days = normalize_day_numbers(payload.day_numbers, request.days)
    if payload.scope == "trip":
        target_days = (
            valid_days.difference(locked_day_numbers)
            if payload.preserve_locked_days
            else valid_days
        )
    else:
        if not explicit_days:
            raise ValueError("按天重新规划时必须指定 day_numbers。")
        invalid_days = set(explicit_days).difference(valid_days)
        if invalid_days:
            raise ValueError(f"存在超出行程范围的天数: {sorted(invalid_days)}")
        target_days = set(explicit_days)
    if not target_days:
        raise ValueError("当前没有可重新规划的天数。")
    return target_days


def build_replan_warning(target_days: set[int], reason: str | None) -> str:
    ordered = "、".join(f"第 {day} 天" for day in sorted(target_days))
    if reason:
        return f"已按请求重新生成 {ordered}，原因: {reason}。"
    return f"已按请求重新生成 {ordered}。"


def merge_replanned_response(
    *,
    current: TripWorkspace,
    fresh: PlanningResponse,
    target_days: set[int],
    reason: str | None,
    apply_budget: Callable,
) -> PlanningResponse:
    request = current.request_brief
    if current.response_snapshot is None:
        raise ValueError("当前工作区没有可用于重新规划的已生成结果。")

    current_days = {
        day.day_number: day.model_copy(deep=True)
        for day in current.response_snapshot.plan.days
    }
    fresh_days = {
        day.day_number: day.model_copy(deep=True)
        for day in fresh.plan.days
    }
    merged_days = []
    for day_number in range(1, request.days + 1):
        if day_number in target_days:
            day = fresh_days.get(day_number)
        else:
            day = current_days.get(day_number) or fresh_days.get(day_number)
        if day is not None:
            merged_days.append(day)

    merged_plan = fresh.plan.model_copy(update={"days": merged_days}, deep=True)
    merged_plan = apply_budget(request, merged_plan)
    warning = build_replan_warning(target_days, reason)
    merged_meta = fresh.meta.model_copy(
        update={
            "warnings": list(dict.fromkeys([*fresh.meta.warnings, warning])),
        },
        deep=True,
    )
    merged_diagnostics = fresh.diagnostics.model_copy(
        update={
            "warnings": list(dict.fromkeys([*fresh.diagnostics.warnings, warning])),
        },
        deep=True,
    )
    return fresh.model_copy(
        update={
            "generated_at": datetime.now(timezone.utc),
            "plan": merged_plan,
            "meta": merged_meta,
            "diagnostics": merged_diagnostics,
        },
        deep=True,
    )
