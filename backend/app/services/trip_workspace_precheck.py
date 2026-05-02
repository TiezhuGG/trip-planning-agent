from __future__ import annotations

from datetime import datetime

from app.schemas.planning import (
    PlanningResponse,
    PrecheckRepairAction,
    PrecheckSummary,
    PrecheckSummaryItem,
    ReservationConflictItem,
    ReservationCoverageDiagnostic,
)


def build_precheck_summary(
    *,
    previous: PlanningResponse,
    current: PlanningResponse,
    created_at: datetime,
) -> PrecheckSummary:
    previous_snapshot = _build_precheck_snapshot(previous)
    current_snapshot = _build_precheck_snapshot(current)
    changed_items: list[PrecheckSummaryItem] = []

    for key, title in (
        ("weather", "天气校验"),
        ("route", "路线校验"),
        ("reservation", "预约校验"),
        ("opening-hours", "营业时间校验"),
    ):
        before = previous_snapshot[key]
        after = current_snapshot[key]
        if before["status"] == after["status"] and before["summary"] == after["summary"]:
            continue

        actions = (
            _actions_for_key(key, after["days"], current, after.get("conflict_items", []))
            if after["status"] == "warning"
            else []
        )
        if key == "reservation":
            actions = _decorate_reservation_actions_with_conflicts(
                actions,
                after.get("conflict_items", []),
            )
        primary_action = actions[0] if actions else None

        changed_items.append(
            PrecheckSummaryItem(
                key=key,
                title=title,
                before_status=before["status"],
                after_status=after["status"],
                before_days=before["days"],
                after_days=after["days"],
                recommended_gap=primary_action.gap if primary_action else None,
                action_label=primary_action.label if primary_action else "",
                action_reason=primary_action.reason if primary_action else "",
                actions=actions,
                before_summary=before["summary"],
                after_summary=after["summary"],
                conflict_items=after.get("conflict_items", []),
            )
        )

    title = (
        f"出发前校验已刷新，{len(changed_items)} 项发生变化"
        if changed_items
        else "出发前校验已刷新，主要校验项无新增变化"
    )
    return PrecheckSummary(
        created_at=created_at,
        title=title,
        items=changed_items,
    )


def _build_precheck_snapshot(response: PlanningResponse) -> dict[str, dict[str, object]]:
    days = response.plan.days

    missing_weather_days = [day.day_number for day in days if day.weather is None]
    weather_risk_days = [
        day.day_number
        for day in days
        if day.weather is not None
        and _is_weather_risk(
            day.weather.day_weather,
            day.weather.night_weather,
            day.weather.advice,
        )
    ]
    if missing_weather_days:
        weather = {
            "status": "warning",
            "summary": f"第 {', '.join(str(day) for day in missing_weather_days)} 天缺少天气信息",
            "days": missing_weather_days,
        }
    elif weather_risk_days:
        weather = {
            "status": "warning",
            "summary": f"第 {', '.join(str(day) for day in weather_risk_days)} 天存在天气风险",
            "days": weather_risk_days,
        }
    else:
        weather = {"status": "ok", "summary": "每天天气信息齐全", "days": []}

    route_missing_days = [
        day.day_number
        for day in days
        if day.route_summary is None and not day.route_summaries and not day.route_segments
    ]
    if route_missing_days:
        route = {
            "status": "warning",
            "summary": f"第 {', '.join(str(day) for day in route_missing_days)} 天缺少路线摘要",
            "days": route_missing_days,
        }
    else:
        route = {"status": "ok", "summary": "每日都带有路线摘要", "days": []}

    reservation = _build_reservation_snapshot(response.diagnostics.reservation_coverage)

    opening_hours_missing = _collect_opening_hours_gaps(response)
    if opening_hours_missing:
        opening_hours = {
            "status": "warning",
            "summary": f"{len(opening_hours_missing)} 个地点缺少营业时间",
            "days": sorted({day for day, _ in opening_hours_missing}),
        }
    else:
        opening_hours = {"status": "ok", "summary": "主要地点都带有开放时间", "days": []}

    return {
        "weather": weather,
        "route": route,
        "reservation": reservation,
        "opening-hours": opening_hours,
    }


def _build_reservation_snapshot(
    coverage: list[ReservationCoverageDiagnostic],
) -> dict[str, object]:
    unresolved = [item for item in coverage if item.status == "unresolved"]
    auto_anchored = [item for item in coverage if item.auto_anchored_days]
    coordinated = [item for item in coverage if item.coordinated_days]
    if unresolved:
        return {
            "status": "warning",
            "summary": f"{len(unresolved)} 条预约仍未明确落地",
            "days": sorted(
                {
                    day
                    for item in unresolved
                    for day in (item.target_days or item.matched_days or item.auto_anchored_days)
                }
            ),
            "conflict_items": [
                conflict
                for item in unresolved
                for conflict in item.conflict_items
            ],
        }
    if auto_anchored:
        summary = f"{len(auto_anchored)} 条预约由系统保底注入"
        if coordinated:
            summary += f"，其中 {len(coordinated)} 条涉及多预约顺序协调"
        return {
            "status": "warning",
            "summary": summary,
            "days": sorted(
                {
                    day
                    for item in auto_anchored
                    for day in (item.auto_anchored_days or item.matched_days or item.target_days)
                }
            ),
            "conflict_items": [],
        }
    if coverage:
        return {"status": "ok", "summary": "预约都已明确落地", "days": [], "conflict_items": []}
    return {"status": "pending", "summary": "当前没有固定预约", "days": [], "conflict_items": []}


def _is_weather_risk(day_weather: str, night_weather: str, advice: str) -> bool:
    text = f"{day_weather} {night_weather} {advice}"
    return any(
        token in text
        for token in ("雨", "雪", "雷", "台风", "大风", "高温", "暴晒", "寒潮", "冰雹")
    )


def _collect_opening_hours_gaps(response: PlanningResponse) -> list[tuple[int, str]]:
    gaps: list[tuple[int, str]] = []
    for day in response.plan.days:
        candidates = [
            (
                day.stay.hotel_name,
                day.stay.poi.opening_hours if day.stay.poi else None,
                day.stay.poi.source if day.stay.poi else "",
            ),
            *[
                (
                    meal.venue_name,
                    meal.poi.opening_hours if meal.poi else None,
                    meal.poi.source if meal.poi else "",
                )
                for meal in day.meals
            ],
            *[
                (
                    activity.title,
                    activity.poi.opening_hours if activity.poi else None,
                    activity.poi.source if activity.poi else "",
                )
                for activity in day.activities
            ],
        ]
        for label, opening_hours, source in candidates:
            if not label or not source or source == "manual_placeholder":
                continue
            if opening_hours:
                continue
            gaps.append((day.day_number, label))
    return gaps


def _actions_for_key(
    key: str,
    days: list[int],
    response: PlanningResponse,
    conflict_items: list[ReservationConflictItem] | None = None,
) -> list[PrecheckRepairAction]:
    day_text = "、".join(str(day) for day in days) if days else "相关"
    reservation_conflict_text = _format_reservation_conflict_text(conflict_items or [])

    if key == "reservation":
        specific_actions = _build_reservation_conflict_actions(conflict_items or [])
        reason = (
            f"请优先处理第 {day_text} 天未完全落地的预约，明确覆盖固定时间窗，"
            "并避免与既有活动或交通安排冲突。"
        )
        if reservation_conflict_text:
            reason += f" 当前已识别冲突：{reservation_conflict_text}。"
        return [
            *specific_actions,
            PrecheckRepairAction(
                gap="reservation",
                label="处理预约",
                reason=reason,
                day_numbers=sorted(set(days)),
            )
        ]

    if key == "opening-hours":
        return [
            PrecheckRepairAction(
                gap="activity",
                label="替换活动",
                reason=(
                    f"请优先调整第 {day_text} 天可能存在营业时间风险的活动，"
                    "替换为营业状态更明确或时间更稳妥的选项。"
                ),
                day_numbers=sorted(set(days)),
            ),
            PrecheckRepairAction(
                gap="day-plan",
                label="调整游玩时段",
                reason=(
                    f"请重新梳理第 {day_text} 天的活动时段，尽量把依赖营业时间的点位放到更稳妥的时间窗，"
                    "避免到场后闭馆、排队过长或与用餐交通冲突。"
                ),
                day_numbers=sorted(set(days)),
            ),
        ]

    if key == "weather":
        if _days_have_existing_activities(response, days):
            return [
                PrecheckRepairAction(
                    gap="activity",
                    label="改室内活动",
                    reason=(
                        f"请优先调整第 {day_text} 天受天气影响的活动，尽量改为室内或更适合当前天气的安排，"
                        "同时减少暴晒、淋雨或大风暴露。"
                    ),
                    day_numbers=sorted(set(days)),
                ),
                PrecheckRepairAction(
                    gap="day-plan",
                    label="调整出发时段",
                    reason=(
                        f"请重新梳理第 {day_text} 天的出发和活动时段，尽量把易受天气影响的户外段落后移、前移，"
                        "或压缩在天气更平稳的时间窗内。"
                    ),
                    day_numbers=sorted(set(days)),
                ),
            ]
        return [
            PrecheckRepairAction(
                gap="day-plan",
                label="重排天气影响日",
                reason=(
                    f"请重新梳理第 {day_text} 天的整体安排，围绕最新天气重新组织活动、"
                    "出发时段和通勤方式。"
                ),
                day_numbers=sorted(set(days)),
            )
        ]

    if key == "route":
        return [
            PrecheckRepairAction(
                gap="day-plan",
                label="重排路线影响日",
                reason=(
                    f"请重新梳理第 {day_text} 天的路线衔接，补齐主要通勤段并减少跨区折返。"
                ),
                day_numbers=sorted(set(days)),
            ),
            PrecheckRepairAction(
                gap="day-plan",
                label="压缩跨区往返",
                reason=(
                    f"请优先压缩第 {day_text} 天的跨区往返，把相近区域的景点、餐饮和预约聚合在一起，"
                    "降低无效通勤和换乘次数。"
                ),
                day_numbers=sorted(set(days)),
            ),
        ]

    return []


def _format_reservation_conflict_text(conflict_items: list[ReservationConflictItem]) -> str:
    labels: list[str] = []
    for conflict in conflict_items[:3]:
        summary = conflict.summary
        if summary:
            labels.append(summary)
    return "；".join(labels)


def _build_reservation_conflict_actions(
    conflict_items: list[ReservationConflictItem],
) -> list[PrecheckRepairAction]:
    actions: list[PrecheckRepairAction] = []
    seen: set[tuple[int, str, str, str]] = set()

    for conflict in conflict_items[:3]:
        key = (
            conflict.day_number,
            conflict.kind,
            conflict.label,
            conflict.time_text,
        )
        if key in seen:
            continue
        seen.add(key)
        actions.append(
            PrecheckRepairAction(
                gap=_reservation_gap_for_conflict(conflict),
                label=_reservation_action_label_for_conflict(conflict),
                reason=_reservation_action_reason_for_conflict(conflict),
                day_numbers=[conflict.day_number],
            )
        )

    return actions


def _decorate_reservation_actions_with_conflicts(
    actions: list[PrecheckRepairAction],
    conflict_items: list[ReservationConflictItem],
) -> list[PrecheckRepairAction]:
    conflict_text = _format_reservation_conflict_text(conflict_items)
    if not conflict_text:
        return actions

    decorated: list[PrecheckRepairAction] = []
    for action in actions:
        if "当前已识别冲突" in action.reason:
            decorated.append(action)
            continue
        decorated.append(
            action.model_copy(
                update={"reason": f"当前已识别冲突：{conflict_text}。{action.reason}"},
                deep=True,
            )
        )
    return decorated


def _reservation_gap_for_conflict(
    conflict: ReservationConflictItem,
) -> str:
    if conflict.kind == "stay":
        return "stay"
    if conflict.kind == "activity":
        return "activity"
    if conflict.time_text == "早餐":
        return "breakfast"
    if conflict.time_text == "午餐":
        return "lunch"
    if conflict.time_text == "晚餐":
        return "dinner"
    if conflict.time_text == "加餐":
        return "snack"
    return "meal"


def _reservation_action_label_for_conflict(
    conflict: ReservationConflictItem,
) -> str:
    if conflict.kind == "stay":
        return "调整住宿安排"
    if conflict.kind == "activity":
        return "释放活动时段"
    if conflict.time_text:
        return f"调整{conflict.time_text}安排"
    return "处理预约冲突"


def _reservation_action_reason_for_conflict(
    conflict: ReservationConflictItem,
) -> str:
    conflict_prefix = "当前已识别冲突。"
    if conflict.summary:
        conflict_prefix = f"当前已识别冲突：{conflict.summary}。"
    if conflict.kind == "stay":
        return (
            f"请优先调整第 {conflict.day_number} 天的住宿安排“{conflict.label}”，"
            "确保固定住宿预约能够落地，并重新对齐当天动线。"
        )
    if conflict.kind == "activity":
        time_text = f"{conflict.time_text} 的" if conflict.time_text else ""
        return (
            f"请优先调整第 {conflict.day_number} 天{time_text}“{conflict.label}”，"
            "为固定预约释放时段，并尽量保留其他可复用安排。"
        )
    meal_text = conflict.time_text or "对应餐位"
    return (
        f"请优先调整第 {conflict.day_number} 天的{meal_text}安排“{conflict.label}”，"
        "为固定预约腾出餐位时间窗，并围绕预约位置重排同餐时段。"
    )


def _days_have_existing_activities(
    response: PlanningResponse,
    days: list[int],
) -> bool:
    target_days = set(days)
    return any(
        day.day_number in target_days and bool(day.activities) for day in response.plan.days
    )
