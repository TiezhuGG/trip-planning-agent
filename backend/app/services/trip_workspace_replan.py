from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.schemas.planning import (
    DayCostBreakdown,
    DayPOI,
    DayPlan,
    MealRecommendation,
    PlanningResponse,
    ReplanChange,
    ReplanDaySummary,
    ReplanRequest,
    ReplanSummary,
    TripPlanningRequest,
    TripWorkspace,
)
from app.services.trip_workspace_reservations import (
    reservation_matches_day_content,
    reservation_trip_days,
)


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

    if payload.repair_mode == "fill_gaps":
        if payload.scope != "day":
            raise ValueError("缺口补齐仅支持按天触发。")
        if payload.repair_gap is None:
            raise ValueError("缺口补齐时必须指定 repair_gap。")

    if not target_days:
        raise ValueError("当前没有可重新规划的天数。")
    return target_days


def build_replan_warning(
    target_days: set[int],
    reason: str | None,
    payload: ReplanRequest,
) -> str:
    ordered = "、".join(f"第 {day} 天" for day in sorted(target_days))
    action = "补齐缺口" if payload.repair_mode == "fill_gaps" else "重新生成"
    gap = (
        f"（{payload.repair_gap}）"
        if payload.repair_mode == "fill_gaps" and payload.repair_gap
        else ""
    )
    if reason:
        return f"已按请求{action} {ordered}{gap}，原因: {reason}。"
    return f"已按请求{action} {ordered}{gap}。"


def merge_replanned_response(
    *,
    current: TripWorkspace,
    fresh: PlanningResponse,
    target_days: set[int],
    payload: ReplanRequest,
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
            current_day = current_days.get(day_number)
            fresh_day = fresh_days.get(day_number)
            day = _merge_target_day(
                current_day=current_day,
                fresh_day=fresh_day,
                payload=payload,
                workspace=current,
                day_number=day_number,
            )
        else:
            day = current_days.get(day_number) or fresh_days.get(day_number)
        if day is not None:
            merged_days.append(day)

    merged_plan = fresh.plan.model_copy(update={"days": merged_days}, deep=True)
    merged_plan = apply_budget(request, merged_plan)
    warning = build_replan_warning(target_days, payload.reason, payload)
    merged_meta = fresh.meta.model_copy(
        update={"warnings": list(dict.fromkeys([*fresh.meta.warnings, warning]))},
        deep=True,
    )
    merged_diagnostics = fresh.diagnostics.model_copy(
        update={
            "warnings": list(dict.fromkeys([*fresh.diagnostics.warnings, warning]))
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


def build_replan_summary(
    *,
    current: TripWorkspace,
    merged: PlanningResponse,
    target_days: set[int],
    payload: ReplanRequest,
) -> ReplanSummary:
    current_days = {
        day.day_number: day
        for day in (current.response_snapshot.plan.days if current.response_snapshot else [])
    }
    merged_days = {
        day.day_number: day
        for day in merged.plan.days
    }
    items: list[ReplanDaySummary] = []
    for day_number in sorted(target_days):
        before = current_days.get(day_number)
        after = merged_days.get(day_number)
        if before is None or after is None:
            continue
        changes = _build_day_changes(before, after)
        if payload.repair_gap == "reservation":
            changes = _merge_reservation_change_details(
                changes=changes,
                workspace=current,
                before=before,
                after=after,
                day_number=day_number,
            )
        highlights = _build_day_change_highlights(changes)
        if not highlights:
            highlights = ["已刷新当日安排"]
        items.append(
            ReplanDaySummary(
                day_number=day_number,
                highlights=highlights[:4],
                changes=changes[:6],
            )
        )

    return ReplanSummary(
        created_at=datetime.now(timezone.utc),
        scope=payload.scope,
        repair_mode=payload.repair_mode,
        repair_gap=payload.repair_gap,
        target_days=sorted(target_days),
        title=_build_replan_summary_title(payload, target_days),
        items=items,
    )


def _merge_target_day(
    *,
    current_day: DayPlan | None,
    fresh_day: DayPlan | None,
    payload: ReplanRequest,
    workspace: TripWorkspace,
    day_number: int,
) -> DayPlan | None:
    if fresh_day is None:
        return current_day
    if (
        current_day is None
        or payload.repair_mode != "fill_gaps"
        or payload.repair_gap in {None, "day-plan"}
    ):
        return fresh_day

    gap = payload.repair_gap
    if gap == "reservation":
        return _merge_reservation_gap_day(
            current_day=current_day,
            fresh_day=fresh_day,
            workspace=workspace,
            day_number=day_number,
        )

    merged = current_day.model_copy(deep=True)
    merged.transport_tips = current_day.transport_tips or fresh_day.transport_tips
    merged.weather = current_day.weather or fresh_day.weather
    merged.fallbacks = list(dict.fromkeys([*current_day.fallbacks, *fresh_day.fallbacks]))

    if gap == "stay":
        merged.hotel_area = current_day.hotel_area or fresh_day.hotel_area
        merged.stay = (
            current_day.stay
            if _has_stay(current_day)
            else fresh_day.stay.model_copy(deep=True)
        )
        merged.map_pois = _merge_map_pois(current_day, fresh_day, kind="stay")
        merged.cost_breakdown = _merge_cost_breakdown(
            current_day.cost_breakdown,
            fresh_day.cost_breakdown,
            fields=("accommodation_per_person_cny",),
        )
        merged.route_summary = current_day.route_summary or fresh_day.route_summary
        merged.route_summaries = current_day.route_summaries or fresh_day.route_summaries
        merged.route_segments = current_day.route_segments or fresh_day.route_segments
        return merged

    if gap in {"meal", "breakfast", "lunch", "dinner", "snack"}:
        target_meal_types = _target_meal_types_for_gap(gap)
        merged.meals = _merge_gap_meals(
            current_day.meals,
            fresh_day.meals,
            target_meal_types=target_meal_types,
        )
        merged.map_pois = _merge_map_pois(
            current_day,
            fresh_day,
            kind="meal",
            force_merge=bool(_missing_meal_types(current_day.meals, target_meal_types)),
        )
        merged.cost_breakdown = _recalculate_food_cost_breakdown(
            current_day.cost_breakdown,
            merged.meals,
        )
        merged.route_summary = current_day.route_summary or fresh_day.route_summary
        merged.route_summaries = current_day.route_summaries or fresh_day.route_summaries
        merged.route_segments = current_day.route_segments or fresh_day.route_segments
        return merged

    if gap == "activity":
        merged.activities = (
            current_day.activities
            or [item.model_copy(deep=True) for item in fresh_day.activities]
        )
        merged.map_pois = _merge_map_pois(current_day, fresh_day, kind="activity")
        merged.cost_breakdown = _merge_cost_breakdown(
            current_day.cost_breakdown,
            fresh_day.cost_breakdown,
            fields=("tickets_per_person_cny", "transport_per_person_cny"),
        )
        merged.route_summary = current_day.route_summary or fresh_day.route_summary
        merged.route_summaries = current_day.route_summaries or fresh_day.route_summaries
        merged.route_segments = current_day.route_segments or fresh_day.route_segments
        return merged

    return fresh_day


def _merge_reservation_gap_day(
    *,
    current_day: DayPlan,
    fresh_day: DayPlan,
    workspace: TripWorkspace,
    day_number: int,
) -> DayPlan:
    target_reservations = [
        reservation
        for reservation in workspace.reservations
        if day_number in reservation_trip_days(workspace.request_brief, reservation)
    ]
    if not target_reservations:
        return fresh_day

    merged = current_day.model_copy(deep=True)
    used_fresh = False

    for reservation in target_reservations:
        if reservation_matches_day_content(reservation, merged):
            continue
        if not reservation_matches_day_content(reservation, fresh_day):
            return fresh_day

        if reservation.type == "hotel":
            merged.hotel_area = fresh_day.hotel_area
            merged.stay = fresh_day.stay.model_copy(deep=True)
            merged.map_pois = _replace_map_pois_by_kind(merged, fresh_day, kind="stay")
            merged.cost_breakdown = _overwrite_cost_breakdown_fields(
                merged.cost_breakdown,
                fresh_day.cost_breakdown,
                fields=("accommodation_per_person_cny",),
            )
            used_fresh = True
            continue

        if reservation.type == "restaurant":
            merged.meals = [item.model_copy(deep=True) for item in fresh_day.meals]
            merged.map_pois = _replace_map_pois_by_kind(merged, fresh_day, kind="meal")
            merged.cost_breakdown = _overwrite_cost_breakdown_fields(
                merged.cost_breakdown,
                fresh_day.cost_breakdown,
                fields=("food_per_person_cny",),
            )
            used_fresh = True
            continue

        merged.activities = [item.model_copy(deep=True) for item in fresh_day.activities]
        merged.transport_tips = fresh_day.transport_tips or merged.transport_tips
        merged.route_summary = fresh_day.route_summary or merged.route_summary
        merged.route_summaries = [
            item.model_copy(deep=True) for item in fresh_day.route_summaries
        ]
        merged.route_segments = [
            item.model_copy(deep=True) for item in fresh_day.route_segments
        ]
        merged.map_pois = _replace_map_pois_by_kind(merged, fresh_day, kind="activity")
        merged.cost_breakdown = _overwrite_cost_breakdown_fields(
            merged.cost_breakdown,
            fresh_day.cost_breakdown,
            fields=("tickets_per_person_cny", "transport_per_person_cny"),
        )
        used_fresh = True

    if not used_fresh:
        return fresh_day

    merged.weather = merged.weather or fresh_day.weather
    merged.fallbacks = list(dict.fromkeys([*merged.fallbacks, *fresh_day.fallbacks]))
    if not merged.route_summary:
        merged.route_summary = fresh_day.route_summary
    if not merged.route_summaries:
        merged.route_summaries = [
            item.model_copy(deep=True) for item in fresh_day.route_summaries
        ]
    if not merged.route_segments:
        merged.route_segments = [
            item.model_copy(deep=True) for item in fresh_day.route_segments
        ]
    return merged


def _has_stay(day: DayPlan) -> bool:
    return bool(day.stay.hotel_name.strip() or day.stay.area.strip() or day.hotel_area.strip())


def _build_replan_summary_title(payload: ReplanRequest, target_days: set[int]) -> str:
    if payload.repair_mode == "fill_gaps":
        gap_text = _format_gap_label(payload.repair_gap)
        if payload.scope == "day" and len(target_days) == 1:
            day_number = next(iter(target_days))
            return f"第 {day_number} 天已完成{gap_text}补齐"
        return f"已完成 {len(target_days)} 天的{gap_text}补齐"
    if payload.scope == "day" and len(target_days) == 1:
        day_number = next(iter(target_days))
        return f"第 {day_number} 天已重新生成"
    return f"已重新生成 {len(target_days)} 天的行程"


def _format_gap_label(value: str | None) -> str:
    labels = {
        "stay": "住宿",
        "meal": "餐饮",
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "加餐",
        "activity": "活动",
        "reservation": "预约",
        "day-plan": "日程",
    }
    if not value:
        return "缺口"
    return labels.get(value, value)


def _build_day_change_highlights(before: DayPlan, after: DayPlan) -> list[str]:
    highlights: list[str] = []

    stay_highlight = _describe_stay_change(before, after)
    if stay_highlight:
        highlights.append(stay_highlight)

    highlights.extend(_describe_meal_changes(before, after))

    activity_highlight = _describe_activity_change(before, after)
    if activity_highlight:
        highlights.append(activity_highlight)

    route_highlight = _describe_route_change(before, after)
    if route_highlight:
        highlights.append(route_highlight)

    budget_highlight = _describe_budget_change(before, after)
    if budget_highlight:
        highlights.append(budget_highlight)

    return list(dict.fromkeys(item for item in highlights if item))


def _describe_stay_change(before: DayPlan, after: DayPlan) -> str | None:
    before_stay = before.stay.hotel_name.strip() or before.hotel_area.strip()
    after_stay = after.stay.hotel_name.strip() or after.hotel_area.strip()
    if not after_stay or before_stay == after_stay:
        return None
    if not before_stay:
        return f"新增住宿：{after_stay}"
    return f"住宿更新为：{after_stay}"


def _describe_meal_changes(before: DayPlan, after: DayPlan) -> list[str]:
    before_map = {meal.meal_type: meal.venue_name.strip() for meal in before.meals if meal.venue_name.strip()}
    after_map = {meal.meal_type: meal.venue_name.strip() for meal in after.meals if meal.venue_name.strip()}
    labels = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "加餐",
    }
    highlights: list[str] = []
    for meal_type in ("breakfast", "lunch", "dinner", "snack"):
        before_name = before_map.get(meal_type, "")
        after_name = after_map.get(meal_type, "")
        if not after_name or before_name == after_name:
            continue
        prefix = "新增" if not before_name else "更新"
        highlights.append(f"{prefix}{labels[meal_type]}：{after_name}")
    return highlights


def _describe_activity_change(before: DayPlan, after: DayPlan) -> str | None:
    before_titles = [item.title.strip() for item in before.activities if item.title.strip()]
    after_titles = [item.title.strip() for item in after.activities if item.title.strip()]
    if before_titles == after_titles:
        return None
    if not after_titles:
        return None
    if not before_titles:
        return f"新增活动：{after_titles[0]}"
    if len(after_titles) > len(before_titles):
        return f"补充活动：{after_titles[0]}"
    return f"活动更新为：{after_titles[0]}"


def _describe_route_change(before: DayPlan, after: DayPlan) -> str | None:
    before_route = before.route_summary.title.strip() if before.route_summary else ""
    after_route = after.route_summary.title.strip() if after.route_summary else ""
    if not after_route or before_route == after_route:
        return None
    return "路线与动线已刷新"


def _describe_budget_change(before: DayPlan, after: DayPlan) -> str | None:
    before_total = before.cost_breakdown.total_per_person_cny
    after_total = after.cost_breakdown.total_per_person_cny
    if before_total == after_total:
        return None
    return f"人均预算 {before_total} -> {after_total} 元"


def _build_day_changes(before: DayPlan, after: DayPlan) -> list[ReplanChange]:
    changes: list[ReplanChange] = []

    stay_change = _describe_stay_change_details(before, after)
    if stay_change:
        changes.append(stay_change)

    changes.extend(_describe_meal_change_details(before, after))

    activity_change = _describe_activity_change_details(before, after)
    if activity_change:
        changes.append(activity_change)

    route_change = _describe_route_change_details(before, after)
    if route_change:
        changes.append(route_change)

    budget_change = _describe_budget_change_details(before, after)
    if budget_change:
        changes.append(budget_change)

    deduped: list[ReplanChange] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in changes:
        key = (item.kind, item.label, item.before, item.after)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped




def _build_day_change_highlights(changes: list[ReplanChange]) -> list[str]:
    highlights: list[str] = []
    for change in changes:
        if change.kind == "stay":
            if not change.after:
                continue
            if not change.before:
                highlights.append(f"新增住宿：{change.after}")
            else:
                highlights.append(f"住宿更新为：{change.after}")
            continue
        if change.kind == "meal":
            if not change.after:
                continue
            prefix = "新增" if not change.before else "更新"
            highlights.append(f"{prefix}{change.label}：{change.after}")
            continue
        if change.kind == "activity":
            if not change.after:
                continue
            if not change.before:
                highlights.append(f"新增活动：{change.after}")
            else:
                highlights.append(f"活动更新为：{change.after}")
            continue
        if change.kind == "reservation":
            if not change.after:
                continue
            highlights.append(f"{change.label}已落地：{change.after}")
            continue
        if change.kind == "route":
            highlights.append("路线与动线已刷新")
            continue
        if change.kind == "budget" and change.before and change.after:
            before_value = change.before.removesuffix(" 元")
            highlights.append(f"人均预算 {before_value} -> {change.after}")
    return list(dict.fromkeys(item for item in highlights if item))


def _describe_stay_change_details(before: DayPlan, after: DayPlan) -> ReplanChange | None:
    before_stay = before.stay.hotel_name.strip() or before.hotel_area.strip()
    after_stay = after.stay.hotel_name.strip() or after.hotel_area.strip()
    if not after_stay or before_stay == after_stay:
        return None
    return ReplanChange(
        kind="stay",
        label="住宿",
        before=before_stay,
        after=after_stay,
    )


def _describe_meal_change_details(before: DayPlan, after: DayPlan) -> list[ReplanChange]:
    before_map = {
        meal.meal_type: meal.venue_name.strip()
        for meal in before.meals
        if meal.venue_name.strip()
    }
    after_map = {
        meal.meal_type: meal.venue_name.strip()
        for meal in after.meals
        if meal.venue_name.strip()
    }
    labels = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "加餐",
    }
    changes: list[ReplanChange] = []
    for meal_type in ("breakfast", "lunch", "dinner", "snack"):
        before_name = before_map.get(meal_type, "")
        after_name = after_map.get(meal_type, "")
        if not after_name or before_name == after_name:
            continue
        changes.append(
            ReplanChange(
                kind="meal",
                label=labels[meal_type],
                before=before_name,
                after=after_name,
            )
        )
    return changes


def _describe_activity_change_details(before: DayPlan, after: DayPlan) -> ReplanChange | None:
    before_titles = [item.title.strip() for item in before.activities if item.title.strip()]
    after_titles = [item.title.strip() for item in after.activities if item.title.strip()]
    if before_titles == after_titles or not after_titles:
        return None
    return ReplanChange(
        kind="activity",
        label="活动",
        before="、".join(before_titles[:2]),
        after="、".join(after_titles[:2]),
    )


def _describe_route_change_details(before: DayPlan, after: DayPlan) -> ReplanChange | None:
    before_route = before.route_summary.title.strip() if before.route_summary else ""
    after_route = after.route_summary.title.strip() if after.route_summary else ""
    if not after_route or before_route == after_route:
        return None
    return ReplanChange(
        kind="route",
        label="路线",
        before=before_route,
        after=after_route,
    )


def _describe_budget_change_details(before: DayPlan, after: DayPlan) -> ReplanChange | None:
    before_total = before.cost_breakdown.total_per_person_cny
    after_total = after.cost_breakdown.total_per_person_cny
    if before_total == after_total:
        return None
    return ReplanChange(
        kind="budget",
        label="人均预算",
        before=f"{before_total} 元",
        after=f"{after_total} 元",
    )


def _merge_reservation_change_details(
    *,
    changes: list[ReplanChange],
    workspace: TripWorkspace,
    before: DayPlan,
    after: DayPlan,
    day_number: int,
) -> list[ReplanChange]:
    reservation_changes: list[ReplanChange] = []
    for reservation in workspace.reservations:
        if day_number not in reservation_trip_days(workspace.request_brief, reservation):
            continue
        if reservation_matches_day_content(reservation, before):
            continue
        if not reservation_matches_day_content(reservation, after):
            continue
        reservation_changes.append(
            ReplanChange(
                kind="reservation",
                label=_reservation_change_label(reservation.type),
                before="未落地",
                after=reservation.title.strip() or reservation.location.strip(),
            )
        )
    return [*reservation_changes, *changes]


def _reservation_change_label(reservation_type: str) -> str:
    labels = {
        "hotel": "酒店预约",
        "restaurant": "餐厅预约",
        "ticket": "门票预约",
        "flight": "航班预约",
        "train": "火车预约",
        "other": "预约",
    }
    return labels.get(reservation_type, "预约")


def _target_meal_types_for_gap(gap: str) -> tuple[str, ...]:
    if gap == "meal":
        return ("breakfast", "lunch", "dinner", "snack")
    if gap == "breakfast":
        return ("breakfast",)
    if gap == "lunch":
        return ("lunch",)
    if gap == "dinner":
        return ("dinner",)
    if gap == "snack":
        return ("snack",)
    raise ValueError(f"unsupported meal gap: {gap}")


def _missing_meal_types(
    current_meals: list[MealRecommendation],
    target_meal_types: tuple[str, ...],
) -> set[str]:
    existing_types = {meal.meal_type for meal in current_meals}
    return {meal_type for meal_type in target_meal_types if meal_type not in existing_types}


def _merge_gap_meals(
    current_meals: list[MealRecommendation],
    fresh_meals: list[MealRecommendation],
    *,
    target_meal_types: tuple[str, ...],
) -> list[MealRecommendation]:
    missing_types = _missing_meal_types(current_meals, target_meal_types)
    merged = [item.model_copy(deep=True) for item in current_meals]
    if not missing_types:
        return _sort_meals(merged)

    for item in fresh_meals:
        if item.meal_type not in missing_types:
            continue
        merged.append(item.model_copy(deep=True))
    return _sort_meals(merged)


def _sort_meals(meals: list[MealRecommendation]) -> list[MealRecommendation]:
    order = {
        "breakfast": 0,
        "lunch": 1,
        "dinner": 2,
        "snack": 3,
    }
    return sorted(meals, key=lambda item: order.get(item.meal_type, 99))


def _recalculate_food_cost_breakdown(
    current_cost: DayCostBreakdown,
    meals: list[MealRecommendation],
) -> DayCostBreakdown:
    food_per_person_cny = sum(max(item.estimated_cost_cny, 0) for item in meals)
    merged = current_cost.model_copy(
        update={"food_per_person_cny": food_per_person_cny},
        deep=True,
    )
    total_per_person_cny = (
        merged.accommodation_per_person_cny
        + merged.transport_per_person_cny
        + merged.food_per_person_cny
        + merged.tickets_per_person_cny
        + merged.extras_per_person_cny
    )
    return merged.model_copy(
        update={"total_per_person_cny": total_per_person_cny},
        deep=True,
    )


def _merge_map_pois(
    current_day: DayPlan,
    fresh_day: DayPlan,
    *,
    kind: str,
    force_merge: bool = False,
) -> list[DayPOI]:
    current_items = [item.model_copy(deep=True) for item in current_day.map_pois]
    if not force_merge and any(item.kind == kind for item in current_items):
        return current_items

    merged = current_items[:]
    existing_keys = {_day_poi_key(item) for item in current_items}
    for item in fresh_day.map_pois:
        if item.kind != kind:
            continue
        key = _day_poi_key(item)
        if key in existing_keys:
            continue
        merged.append(item.model_copy(deep=True))
        existing_keys.add(key)
    return merged


def _replace_map_pois_by_kind(
    current_day: DayPlan,
    fresh_day: DayPlan,
    *,
    kind: str,
) -> list[DayPOI]:
    preserved = [
        item.model_copy(deep=True) for item in current_day.map_pois if item.kind != kind
    ]
    fresh_items = [
        item.model_copy(deep=True) for item in fresh_day.map_pois if item.kind == kind
    ]
    existing_keys = {_day_poi_key(item) for item in preserved}
    for item in fresh_items:
        key = _day_poi_key(item)
        if key in existing_keys:
            continue
        preserved.append(item)
        existing_keys.add(key)
    return preserved


def _day_poi_key(item: DayPOI) -> tuple[str, str, str]:
    poi_id = item.poi.poi_id or ""
    return (item.kind, item.label, poi_id or item.poi.name)


def _merge_cost_breakdown(
    current_cost: DayCostBreakdown,
    fresh_cost: DayCostBreakdown,
    *,
    fields: tuple[str, ...],
) -> DayCostBreakdown:
    update: dict[str, int] = {}
    for field in fields:
        current_value = getattr(current_cost, field)
        if current_value <= 0:
            update[field] = getattr(fresh_cost, field)
    if not update:
        return current_cost

    merged = current_cost.model_copy(update=update, deep=True)
    total_per_person_cny = (
        merged.accommodation_per_person_cny
        + merged.transport_per_person_cny
        + merged.food_per_person_cny
        + merged.tickets_per_person_cny
        + merged.extras_per_person_cny
    )
    return merged.model_copy(
        update={"total_per_person_cny": total_per_person_cny},
        deep=True,
    )


def _overwrite_cost_breakdown_fields(
    current_cost: DayCostBreakdown,
    fresh_cost: DayCostBreakdown,
    *,
    fields: tuple[str, ...],
) -> DayCostBreakdown:
    update = {field: getattr(fresh_cost, field) for field in fields}
    merged = current_cost.model_copy(update=update, deep=True)
    total_per_person_cny = (
        merged.accommodation_per_person_cny
        + merged.transport_per_person_cny
        + merged.food_per_person_cny
        + merged.tickets_per_person_cny
        + merged.extras_per_person_cny
    )
    return merged.model_copy(
        update={"total_per_person_cny": total_per_person_cny},
        deep=True,
    )
