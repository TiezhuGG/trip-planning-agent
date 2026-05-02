from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.planning import (
    Activity,
    DayPOI,
    DayPlan,
    DayStayInfo,
    MealRecommendation,
    PlanningResponse,
    POIRecommendation,
    ReservationConflictItem,
    ReservationCoverageDiagnostic,
    ReservationItem,
    TripPlanningRequest,
)


def validate_reservations(
    request: TripPlanningRequest,
    reservations: list[ReservationItem],
) -> None:
    trip_start = request.start_date
    trip_end = request.start_date + timedelta(days=request.days - 1)
    for reservation in reservations:
        start_at = normalize_datetime(reservation.start_at)
        end_at = normalize_datetime(reservation.end_at)
        if start_at is not None and end_at is not None and end_at < start_at:
            raise ValueError(f"预约“{reservation.title}”的结束时间不能早于开始时间。")

        dated_values = [value for value in (start_at, end_at) if value is not None]
        if not dated_values:
            continue

        if all(value.date() < trip_start for value in dated_values):
            raise ValueError(f"预约“{reservation.title}”不在本次行程日期范围内。")
        if all(value.date() > trip_end for value in dated_values):
            raise ValueError(f"预约“{reservation.title}”不在本次行程日期范围内。")

    validate_reservation_time_conflicts(reservations)


def build_effective_request(
    request: TripPlanningRequest,
    *,
    manual_notes: str = "",
    reservations: list[ReservationItem] | None = None,
    replan_target_days: set[int] | None = None,
    replan_reason: str | None = None,
) -> TripPlanningRequest:
    effective_reservations = filter_reservations_for_target_days(
        request=request,
        reservations=reservations or [],
        target_days=replan_target_days,
    )

    note_sections: list[str] = []
    base_notes = (request.notes or "").strip()
    if base_notes:
        note_sections.append(base_notes)

    workspace_notes = manual_notes.strip()
    if workspace_notes:
        note_sections.append(
            "Workspace notes that must be considered:\n"
            f"{workspace_notes}"
        )

    reservation_notes = build_reservation_notes(request, effective_reservations)
    if reservation_notes:
        note_sections.append(reservation_notes)

    replan_notes = build_replan_notes(
        target_days=replan_target_days,
        reason=replan_reason,
    )
    if replan_notes:
        note_sections.append(replan_notes)

    effective_notes = "\n\n".join(note_sections).strip()
    if effective_notes == (request.notes or "").strip():
        return request
    return request.model_copy(update={"notes": effective_notes or None}, deep=True)


def audit_generated_reservations(
    request: TripPlanningRequest,
    reservations: list[ReservationItem],
    response: PlanningResponse,
) -> list[str]:
    warnings: list[str] = []
    for item in build_reservation_coverage_diagnostics(
        request=request,
        reservations=reservations,
        response=response,
    ):
        if item.status != "unresolved":
            continue
        if item.target_days:
            day_text = ", ".join(f"day {day}" for day in item.target_days)
            warnings.append(
                f"Reservation audit: “{item.title}” is not explicitly reflected in {day_text}; verify manually or replan the affected day."
            )
        else:
            warnings.append(
                f"Reservation audit: “{item.title}” is not explicitly reflected in the generated itinerary; verify manually."
            )
    return warnings


def apply_reservation_fallback_anchors(
    request: TripPlanningRequest,
    reservations: list[ReservationItem],
    response: PlanningResponse,
) -> tuple[PlanningResponse, list[str], dict[str, list[int]]]:
    if not reservations:
        return response, [], {}

    updated_days: list[DayPlan] = []
    warnings: list[str] = []
    auto_anchored_days: dict[str, set[int]] = {}
    changed = False

    for day in response.plan.days:
        target_reservations = sorted(
            [
                item
                for item in reservations
                if day.day_number in reservation_trip_days(request, item)
            ],
            key=_reservation_coordination_sort_key,
        )
        if not target_reservations:
            updated_days.append(day)
            continue

        updated_day = day.model_copy(deep=True)
        day_changed = False
        anchored_reservations: list[ReservationItem] = []
        for reservation in target_reservations:
            if reservation_matches_day_content(reservation, updated_day):
                continue
            updated_day, anchored = _anchor_reservation_to_day(
                request=request,
                reservation=reservation,
                day=updated_day,
            )
            if not anchored:
                continue
            day_changed = True
            changed = True
            anchored_reservations.append(reservation)
            auto_anchored_days.setdefault(
                _reservation_diagnostic_key(reservation),
                set(),
            ).add(day.day_number)
            warnings.append(
                f"Reservation fallback: “{reservation.title}” was auto-anchored into day {day.day_number}."
            )

        if day_changed:
            updated_day = _apply_daily_anchor_coordination(
                day=updated_day,
                anchored_reservations=anchored_reservations,
            )
            updated_day = updated_day.model_copy(
                update={
                    "fallbacks": sorted(set(_build_day_fallbacks(updated_day, anchored_reservations)))
                },
                deep=True,
            )
        updated_days.append(updated_day)

    if not changed:
        return response, [], {}

    updated_plan = response.plan.model_copy(update={"days": updated_days}, deep=True)
    return (
        response.model_copy(update={"plan": updated_plan}, deep=True),
        list(dict.fromkeys(warnings)),
        {
            key: sorted(days)
            for key, days in auto_anchored_days.items()
        },
    )


def build_reservation_notes(
    request: TripPlanningRequest,
    reservations: list[ReservationItem],
) -> str:
    if not reservations:
        return ""

    lines = [
        "Fixed reservations and anchors that must be respected when generating the itinerary:",
    ]
    for item in reservations:
        parts = [f"type={item.type}", f"title={item.title.strip()}"]
        trip_days = reservation_trip_days(request, item)
        if trip_days:
            parts.append("trip_days=" + ",".join(f"day{day}" for day in trip_days))
        time_range = format_reservation_range(item)
        if time_range:
            parts.append(f"time={time_range}")
        if item.location.strip():
            parts.append(f"location={item.location.strip()}")
        if item.source.strip():
            parts.append(f"source={item.source.strip()}")
        if item.confirmation_code.strip():
            parts.append(f"confirmation={item.confirmation_code.strip()}")
        if item.notes.strip():
            parts.append(f"notes={item.notes.strip()}")
        lines.append(f"- {'; '.join(parts)}")

    schedule_rules = build_reservation_schedule_rules(request, reservations)
    if schedule_rules:
        lines.append("")
        lines.append("Reservation scheduling directives:")
        lines.extend(schedule_rules)

    lines.append(
        "Scheduling rules: on the listed trip_days, keep the reservation time window available, "
        "place nearby meals/activities around the anchor, and avoid long cross-city detours that would cause conflicts."
    )
    return "\n".join(lines)


def _anchor_reservation_to_day(
    *,
    request: TripPlanningRequest,
    reservation: ReservationItem,
    day: DayPlan,
) -> tuple[DayPlan, bool]:
    if reservation.type == "hotel":
        return _anchor_hotel_reservation(request, reservation, day), True
    if reservation.type == "restaurant":
        return _anchor_restaurant_reservation(request, reservation, day), True
    if reservation.type in {"flight", "train", "ticket", "other"}:
        return _anchor_activity_reservation(request, reservation, day), True
    return day, False


def _anchor_hotel_reservation(
    request: TripPlanningRequest,
    reservation: ReservationItem,
    day: DayPlan,
) -> DayPlan:
    hotel_name = reservation.title.strip() or day.stay.hotel_name or "已预订酒店"
    area = reservation.location.strip() or day.stay.area or day.hotel_area
    placeholder_poi = _reservation_placeholder_poi(request, reservation, fallback_name=hotel_name)
    stay = DayStayInfo(
        area=area,
        hotel_name=hotel_name,
        reason="已按固定酒店预约锁定住宿",
        room_nightly_cost_cny=day.stay.room_nightly_cost_cny,
        poi=placeholder_poi,
    )
    return day.model_copy(
        update={
            "hotel_area": area,
            "stay": stay,
            "map_pois": _merge_placeholder_day_poi(
                day.map_pois,
                DayPOI(kind="stay", label=hotel_name, poi=placeholder_poi),
            ),
        },
        deep=True,
    )


def _anchor_restaurant_reservation(
    request: TripPlanningRequest,
    reservation: ReservationItem,
    day: DayPlan,
) -> DayPlan:
    meal_type = _infer_reservation_meal_type(reservation)
    venue_name = reservation.title.strip() or reservation.location.strip() or "已预约餐厅"
    placeholder_poi = _reservation_placeholder_poi(request, reservation, fallback_name=venue_name)
    anchored_meal = MealRecommendation(
        meal_type=meal_type,
        venue_name=venue_name,
        cuisine="",
        suggestion="已按固定餐厅预约锁定该餐位",
        estimated_cost="",
        estimated_cost_cny=0,
        poi=placeholder_poi,
    )
    meals = [item.model_copy(deep=True) for item in day.meals if item.meal_type != meal_type]
    meals.append(anchored_meal)
    meals = _sort_meals(meals)
    return day.model_copy(
        update={
            "meals": meals,
            "map_pois": _merge_placeholder_day_poi(
                day.map_pois,
                DayPOI(kind="meal", label=meal_type, poi=placeholder_poi),
            ),
        },
        deep=True,
    )


def _anchor_activity_reservation(
    request: TripPlanningRequest,
    reservation: ReservationItem,
    day: DayPlan,
) -> DayPlan:
    title = reservation.title.strip() or reservation.location.strip() or "固定预约"
    location_name = reservation.location.strip() or title
    start_time, end_time = _reservation_activity_time_range(reservation)
    placeholder_poi = _reservation_placeholder_poi(request, reservation, fallback_name=location_name)
    activity = Activity(
        start_time=start_time,
        end_time=end_time,
        title=title,
        category="transport" if reservation.type in {"flight", "train"} else "reservation",
        description=_build_reservation_activity_description(reservation),
        location_name=location_name,
        transport_from_previous="请围绕固定预约预留到达时间",
        expected_cost=None,
        ticket_cost_cny=0,
        booking_tip=_build_reservation_booking_tip(reservation),
        poi=placeholder_poi,
    )
    activities = [item.model_copy(deep=True) for item in day.activities]
    activities.append(activity)
    activities.sort(key=lambda item: (item.start_time, item.end_time, item.title))
    transport_tips = list(day.transport_tips)
    transport_hint = _build_transport_anchor_tip(reservation)
    if transport_hint and transport_hint not in transport_tips:
        transport_tips.append(transport_hint)
    return day.model_copy(
        update={
            "activities": activities,
            "transport_tips": transport_tips,
            "map_pois": _merge_placeholder_day_poi(
                day.map_pois,
                DayPOI(kind="activity", label=title, poi=placeholder_poi),
            ),
        },
        deep=True,
    )


def _apply_daily_anchor_coordination(
    *,
    day: DayPlan,
    anchored_reservations: list[ReservationItem],
) -> DayPlan:
    if len(anchored_reservations) < 2:
        return day

    ordered = sorted(anchored_reservations, key=_reservation_coordination_sort_key)
    anchor_text = " -> ".join(
        item
        for item in (_format_daily_anchor_summary(item) for item in ordered)
        if item
    )
    if not anchor_text:
        return day

    coordination_tip = (
        f"固定预约顺序：{anchor_text}；请预留预约之间的通勤与候场缓冲，"
        "将可调整活动压缩到剩余空档。"
    )
    transport_tips = list(day.transport_tips)
    if coordination_tip not in transport_tips:
        transport_tips.append(coordination_tip)
    return day.model_copy(update={"transport_tips": transport_tips}, deep=True)


def _build_day_fallbacks(
    day: DayPlan,
    anchored_reservations: list[ReservationItem],
) -> list[str]:
    fallbacks = [*day.fallbacks, "reservation_anchor_injected"]
    if len(anchored_reservations) >= 2:
        fallbacks.append("reservation_multi_anchor_coordinated")
    return fallbacks


def _reservation_placeholder_poi(
    request: TripPlanningRequest,
    reservation: ReservationItem,
    *,
    fallback_name: str,
) -> POIRecommendation:
    address = reservation.location.strip() or f"{request.destination}{fallback_name}"
    return POIRecommendation(
        name=fallback_name,
        address=address,
        district=request.destination,
        source="manual_placeholder",
    )


def _merge_placeholder_day_poi(items: list[DayPOI], new_item: DayPOI) -> list[DayPOI]:
    merged = [item.model_copy(deep=True) for item in items]
    key = (
        new_item.kind,
        normalize_search_text(new_item.label),
        normalize_search_text(new_item.poi.name),
    )
    for item in merged:
        item_key = (
            item.kind,
            normalize_search_text(item.label),
            normalize_search_text(item.poi.name),
        )
        if item_key == key:
            return merged
    merged.append(new_item)
    return merged


def _infer_reservation_meal_type(reservation: ReservationItem) -> str:
    text = f"{reservation.title} {reservation.notes}".lower()
    hour = _reservation_hour(reservation)
    if any(token in text for token in ("早餐", "早饭", "早茶", "breakfast")):
        return "breakfast"
    if any(token in text for token in ("午餐", "中餐", "lunch", "brunch")):
        return "lunch"
    if any(token in text for token in ("晚餐", "晚饭", "dinner", "supper")):
        return "dinner"
    if any(token in text for token in ("加餐", "下午茶", "夜宵", "snack")):
        return "snack"
    if 5 <= hour < 11:
        return "breakfast"
    if 11 <= hour < 16:
        return "lunch"
    if 17 <= hour < 23:
        return "dinner"
    return "snack"


def _reservation_activity_time_range(reservation: ReservationItem) -> tuple[str, str]:
    start = normalize_datetime(reservation.start_at)
    end = normalize_datetime(reservation.end_at)
    if start is None and end is None:
        return "09:00", "10:00"
    effective_start = start or end
    effective_end = end or start
    assert effective_start is not None
    assert effective_end is not None
    return effective_start.strftime("%H:%M"), effective_end.strftime("%H:%M")


def _build_reservation_activity_description(reservation: ReservationItem) -> str:
    type_label = {
        "flight": "航班预约",
        "train": "车次预约",
        "ticket": "门票预约",
        "other": "固定预约",
    }.get(reservation.type, "固定预约")
    extras = [type_label]
    if reservation.location.strip():
        extras.append(f"地点：{reservation.location.strip()}")
    if reservation.notes.strip():
        extras.append(f"备注：{reservation.notes.strip()}")
    return "；".join(extras)


def _build_reservation_booking_tip(reservation: ReservationItem) -> str:
    parts: list[str] = ["固定预约锚点，请预留对应时间窗"]
    if reservation.confirmation_code.strip():
        parts.append(f"确认号：{reservation.confirmation_code.strip()}")
    if reservation.source.strip():
        parts.append(f"来源：{reservation.source.strip()}")
    return "；".join(parts)


def _build_transport_anchor_tip(reservation: ReservationItem) -> str:
    time_range = format_reservation_range(reservation)
    if reservation.type == "flight":
        return f"已锁定航班：{reservation.title.strip()} {time_range}".strip()
    if reservation.type == "train":
        return f"已锁定车次：{reservation.title.strip()} {time_range}".strip()
    if reservation.type == "ticket":
        return f"已锁定门票：{reservation.title.strip()} {time_range}".strip()
    if reservation.type == "other":
        return f"已锁定预约：{reservation.title.strip()} {time_range}".strip()
    return ""


def _reservation_hour(reservation: ReservationItem) -> int:
    value = normalize_datetime(reservation.start_at or reservation.end_at)
    if value is None:
        return -1
    return value.hour


def _reservation_primary_slot(reservation: ReservationItem) -> str:
    value = normalize_datetime(reservation.start_at or reservation.end_at)
    if value is None:
        return "unspecified"
    return _reservation_slot_label(value)


def _reservation_slot_label(value: datetime) -> str:
    normalized = normalize_datetime(value)
    assert normalized is not None
    hour = normalized.hour
    if 5 <= hour < 10:
        return "morning"
    if 10 <= hour < 14:
        return "lunch"
    if 14 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "dinner"
    return "night"


def _sort_meals(meals: list[MealRecommendation]) -> list[MealRecommendation]:
    order = {
        "breakfast": 0,
        "lunch": 1,
        "dinner": 2,
        "snack": 3,
    }
    return sorted(meals, key=lambda item: (order.get(item.meal_type, 99), item.venue_name))


def build_replan_notes(*, target_days: set[int] | None, reason: str | None) -> str:
    if not target_days and not (reason or "").strip():
        return ""

    lines = ["Partial replanning instructions:"]
    if target_days:
        ordered_days = ", ".join(str(day) for day in sorted(target_days))
        lines.append(f"- regenerate_days={ordered_days}")
    if (reason or "").strip():
        lines.append(f"- reason={reason.strip()}")
    return "\n".join(lines)


def reservation_trip_days(
    request: TripPlanningRequest,
    reservation: ReservationItem,
) -> list[int]:
    trip_start = request.start_date
    trip_end = request.start_date + timedelta(days=request.days - 1)
    start_at = normalize_datetime(reservation.start_at)
    end_at = normalize_datetime(reservation.end_at)
    if start_at is None and end_at is None:
        return []

    start_date = (start_at or end_at).date()
    end_date = (end_at or start_at).date()
    effective_start = max(start_date, trip_start)
    effective_end = min(end_date, trip_end)
    if effective_end < effective_start:
        return []

    return [
        (effective_start + timedelta(days=offset) - trip_start).days + 1
        for offset in range((effective_end - effective_start).days + 1)
    ]


def filter_reservations_for_target_days(
    *,
    request: TripPlanningRequest,
    reservations: list[ReservationItem],
    target_days: set[int] | None,
) -> list[ReservationItem]:
    if not target_days:
        return reservations

    filtered: list[ReservationItem] = []
    for reservation in reservations:
        trip_days = set(reservation_trip_days(request, reservation))
        if not trip_days or trip_days.intersection(target_days):
            filtered.append(reservation)
    return filtered


def build_reservation_schedule_rules(
    request: TripPlanningRequest,
    reservations: list[ReservationItem],
) -> list[str]:
    rules: list[str] = []
    for reservation in reservations:
        trip_days = reservation_trip_days(request, reservation)
        day_text = ",".join(f"day{day}" for day in trip_days) if trip_days else "unspecified"
        time_range = format_reservation_range(reservation)

        if reservation.type == "hotel":
            parts = [
                f"stay_anchor_days={day_text}",
                f"title={reservation.title.strip()}",
            ]
            if reservation.location.strip():
                parts.append(f"location={reservation.location.strip()}")
            if reservation.start_at is not None:
                parts.append(f"check_in={format_reservation_time(reservation.start_at)}")
                parts.append(f"check_in_slot={_reservation_slot_label(reservation.start_at)}")
            if reservation.end_at is not None:
                parts.append(f"check_out={format_reservation_time(reservation.end_at)}")
                parts.append(f"check_out_slot={_reservation_slot_label(reservation.end_at)}")
            parts.append("requirement=keep_stay_aligned_with_reserved_hotel")
            rules.append(f"- {'; '.join(parts)}")
            continue

        parts = [
            f"anchor_days={day_text}",
            f"type={reservation.type}",
            f"title={reservation.title.strip()}",
        ]
        if time_range:
            parts.append(f"time_window={time_range}")
            parts.append(f"anchor_slot={_reservation_primary_slot(reservation)}")
        if reservation.location.strip():
            parts.append(f"location={reservation.location.strip()}")
        if reservation.type == "restaurant":
            parts.append(f"meal_slot={_infer_reservation_meal_type(reservation)}")
            parts.append("requirement=place_the_reserved_restaurant_into_that_meal_slot")
        elif reservation.type in {"flight", "train"}:
            parts.append("requirement=block_the_transport_slot_and_keep_transfer_buffer")
        elif reservation.type == "ticket":
            parts.append("requirement=place_the_ticketed_activity_into_that_time_window")
        parts.append("requirement=keep_time_window_clear_and_place_anchor_explicitly")
        rules.append(f"- {'; '.join(parts)}")
    rules.extend(_build_daily_reservation_coordination_rules(request, reservations))
    return rules


def _build_daily_reservation_coordination_rules(
    request: TripPlanningRequest,
    reservations: list[ReservationItem],
) -> list[str]:
    reservations_by_day: dict[int, list[ReservationItem]] = {}
    for reservation in reservations:
        for day_number in reservation_trip_days(request, reservation):
            reservations_by_day.setdefault(day_number, []).append(reservation)

    rules: list[str] = []
    for day_number in sorted(reservations_by_day):
        day_reservations = reservations_by_day[day_number]
        if len(day_reservations) < 2:
            continue

        ordered = sorted(day_reservations, key=_reservation_coordination_sort_key)
        anchor_windows = [
            _format_coordination_anchor_window(item)
            for item in ordered
            if _format_coordination_anchor_window(item)
        ]
        if len(anchor_windows) < 2:
            continue

        requirement_parts = [
            "sequence_the_day_around_all_anchor_windows",
            "preserve_transfer_buffers_between_anchor_windows",
            "compress_flexible_activities_into_the_remaining_gaps",
        ]
        if any(item.type == "restaurant" for item in ordered):
            requirement_parts.append("avoid_scheduling_other_meals_inside_reserved_time_windows")
        if any(item.type == "hotel" for item in ordered):
            requirement_parts.append("align_departure_and_return_with_the_reserved_hotel_anchor")

        rules.append(
            "- "
            + "; ".join(
                [
                    f"day_anchor_plan=day{day_number}",
                    f"anchor_count={len(anchor_windows)}",
                    f"anchors={' | '.join(anchor_windows)}",
                    f"requirements={','.join(requirement_parts)}",
                ]
            )
        )

    return rules


def _reservation_coordination_sort_key(reservation: ReservationItem) -> tuple[datetime, datetime, str, str]:
    primary = normalize_datetime(reservation.start_at or reservation.end_at)
    fallback = normalize_datetime(reservation.end_at or reservation.start_at)
    max_value = datetime.max.replace(tzinfo=timezone.utc)
    return (
        primary or max_value,
        fallback or max_value,
        reservation.type,
        reservation.title.strip(),
    )


def _format_coordination_anchor_window(reservation: ReservationItem) -> str:
    title = reservation.title.strip() or reservation.location.strip()
    if not title:
        return ""

    slot = _reservation_primary_slot(reservation)
    time_range = format_reservation_range(reservation)
    if time_range:
        return f"{reservation.type}:{title}@{slot}[{time_range}]"
    return f"{reservation.type}:{title}@{slot}"


def _format_daily_anchor_summary(reservation: ReservationItem) -> str:
    title = reservation.title.strip() or reservation.location.strip()
    if not title:
        return ""

    start = normalize_datetime(reservation.start_at or reservation.end_at)
    if start is not None:
        return f"{start.strftime('%H:%M')} {title}"
    return title


def validate_reservation_time_conflicts(
    reservations: list[ReservationItem],
) -> None:
    checkable_types = {"flight", "train", "restaurant", "ticket", "other"}
    windows: list[tuple[ReservationItem, datetime, datetime]] = []
    for reservation in reservations:
        if reservation.type not in checkable_types:
            continue
        start_at = normalize_datetime(reservation.start_at)
        end_at = normalize_datetime(reservation.end_at)
        if start_at is None:
            continue
        effective_end = end_at or start_at
        windows.append((reservation, start_at, effective_end))

    windows.sort(key=lambda item: item[1])
    for index, (current, _, current_end) in enumerate(windows):
        for other, other_start, _ in windows[index + 1 :]:
            if other_start > current_end:
                break
            raise ValueError(
                f"预约“{current.title}”与“{other.title}”存在时间重叠，请先调整后再保存。"
            )


def reservation_is_reflected_in_plan(
    request: TripPlanningRequest,
    reservation: ReservationItem,
    response: PlanningResponse,
) -> bool:
    target_days = set(reservation_trip_days(request, reservation))
    candidate_days = [
        day
        for day in response.plan.days
        if not target_days or day.day_number in target_days
    ]
    if not candidate_days:
        return False

    for day in candidate_days:
        if reservation_matches_day_content(reservation, day):
            return True
    return False


def build_reservation_coverage_diagnostics(
    *,
    request: TripPlanningRequest,
    reservations: list[ReservationItem],
    response: PlanningResponse,
    auto_anchored_days: dict[str, list[int]] | None = None,
) -> list[ReservationCoverageDiagnostic]:
    coverage: list[ReservationCoverageDiagnostic] = []
    anchored_map = auto_anchored_days or {}
    coordination_by_day = {
        day.day_number: _extract_day_coordination_tip(day)
        for day in response.plan.days
    }

    for reservation in reservations:
        target_days = reservation_trip_days(request, reservation)
        target_day_set = set(target_days)
        matched_days = [
            day.day_number
            for day in response.plan.days
            if (not target_day_set or day.day_number in target_day_set)
            and reservation_matches_day_content(reservation, day)
        ]
        matched_days = list(dict.fromkeys(matched_days))
        anchored_days = [
            day for day in anchored_map.get(_reservation_diagnostic_key(reservation), [])
            if not matched_days or day in matched_days
        ]
        coordinated_days, coordination_tip = _resolve_reservation_coordination(
            matched_days=matched_days,
            coordination_by_day=coordination_by_day,
        )

        if matched_days:
            detail = f"Covered on day {', '.join(str(day) for day in matched_days)}."
            if anchored_days:
                detail = (
                    f"Covered on day {', '.join(str(day) for day in matched_days)} "
                    f"with runtime fallback anchoring on day {', '.join(str(day) for day in anchored_days)}."
                )
            coverage.append(
                ReservationCoverageDiagnostic(
                    reservation_id=reservation.id,
                    title=reservation.title,
                    status="covered",
                    target_days=target_days,
                    matched_days=matched_days,
                    auto_anchored_days=anchored_days,
                    coordinated_days=coordinated_days,
                    coordination_tip=coordination_tip,
                    reason_code="runtime_fallback" if anchored_days else "generated_match",
                    reason_summary=_build_reservation_reason_summary(
                        matched_days=matched_days,
                        anchored_days=anchored_days,
                        coordinated_days=coordinated_days,
                    ),
                    detail=detail,
                )
            )
            continue

        if reservation.start_at is None and reservation.end_at is None:
            coverage.append(
                ReservationCoverageDiagnostic(
                    reservation_id=reservation.id,
                    title=reservation.title,
                    status="pending",
                    target_days=target_days,
                    matched_days=[],
                    auto_anchored_days=[],
                    coordinated_days=[],
                    coordination_tip="",
                    reason_code="missing_time_window",
                    reason_summary="预约缺少明确时间窗，当前无法自动核验它应该落在哪一天或哪个时段。",
                    detail="Missing time window; cannot verify placement automatically.",
                )
            )
            continue

        if target_days:
            detail = f"Expected on day {', '.join(str(day) for day in target_days)}, but no explicit match was found."
        else:
            detail = "No explicit match was found in the generated itinerary."
        unresolved_reason = _build_unresolved_reservation_reason_summary(
            reservation=reservation,
            response=response,
            target_days=target_days,
        )
        coverage.append(
            ReservationCoverageDiagnostic(
                reservation_id=reservation.id,
                title=reservation.title,
                status="unresolved",
                target_days=target_days,
                matched_days=[],
                auto_anchored_days=[],
                coordinated_days=[],
                coordination_tip="",
                reason_code="day_conflict" if unresolved_reason["has_conflict"] else "no_explicit_match",
                reason_summary=unresolved_reason["summary"],
                conflict_items=unresolved_reason["conflict_items"],
                detail=detail,
            )
        )

    return coverage


def _extract_day_coordination_tip(day: DayPlan) -> str:
    return next(
        (tip for tip in day.transport_tips if tip.startswith("固定预约顺序：")),
        "",
    )


def _resolve_reservation_coordination(
    *,
    matched_days: list[int],
    coordination_by_day: dict[int, str],
) -> tuple[list[int], str]:
    coordinated_days = [
        day for day in matched_days
        if coordination_by_day.get(day)
    ]
    if not coordinated_days:
        return [], ""

    if len(coordinated_days) == 1:
        return coordinated_days, coordination_by_day[coordinated_days[0]]

    return (
        coordinated_days,
        "；".join(
            f"第 {day} 天：{coordination_by_day[day]}"
            for day in coordinated_days
            if coordination_by_day.get(day)
        ),
    )


def _build_reservation_reason_summary(
    *,
    matched_days: list[int],
    anchored_days: list[int],
    coordinated_days: list[int],
) -> str:
    if anchored_days:
        if coordinated_days:
            return (
                f"系统已在第 {', '.join(str(day) for day in matched_days)} 天按预约信息保底注入，"
                "并对同日多预约顺序做了协调。"
            )
        return (
            f"系统已在第 {', '.join(str(day) for day in matched_days)} 天按预约信息保底注入，"
            "避免固定时间窗完全丢失。"
        )
    return (
        f"行程已在第 {', '.join(str(day) for day in matched_days)} 天明确体现该预约锚点。"
    )


def _build_unresolved_reservation_reason_summary(
    *,
    reservation: ReservationItem,
    response: PlanningResponse,
    target_days: list[int],
) -> dict[str, object]:
    candidate_days = [
        day
        for day in response.plan.days
        if not target_days or day.day_number in set(target_days)
    ]
    conflict_items = [
        item
        for day in candidate_days
        for item in _build_day_conflict_items(reservation, day)
    ]
    if conflict_items:
        joined = "；".join(item.summary for item in conflict_items[:2] if item.summary)
        return {
            "has_conflict": True,
            "summary": (
                "目标日期内未找到与该预约匹配的明确行程内容，且当前日程存在明显冲突："
                f"{joined}。建议优先重排对应日期并围绕固定时间窗补齐锚点。"
            ),
            "conflict_items": conflict_items,
        }

    if target_days:
        return {
            "has_conflict": False,
            "summary": (
                "目标日期内未找到与该预约匹配的明确行程内容，"
                "建议优先重排对应日期并围绕固定时间窗补齐锚点。"
            ),
            "conflict_items": [],
        }

    return {
        "has_conflict": False,
        "summary": "生成结果中未找到与该预约匹配的明确行程内容，建议手动核验或重新规划。",
        "conflict_items": [],
    }


def _build_day_conflict_items(
    reservation: ReservationItem,
    day: DayPlan,
) -> list[ReservationConflictItem]:
    conflicts: list[ReservationConflictItem] = []

    if reservation.type == "hotel":
        conflicts.extend(_collect_hotel_conflicts(reservation, day))
    elif reservation.type == "restaurant":
        conflicts.extend(_collect_restaurant_conflicts(reservation, day))

    conflicts.extend(_collect_activity_time_conflicts(reservation, day))
    return conflicts[:3]


def _collect_hotel_conflicts(
    reservation: ReservationItem,
    day: DayPlan,
) -> list[ReservationConflictItem]:
    conflicts: list[ReservationConflictItem] = []
    reserved_title = normalize_search_text(reservation.title)
    reserved_location = normalize_search_text(reservation.location)
    hotel_name = normalize_search_text(day.stay.hotel_name)
    hotel_area = normalize_search_text(day.hotel_area or day.stay.area)

    if hotel_name and reserved_title and reserved_title not in hotel_name and hotel_name not in reserved_title:
        conflicts.append(
            ReservationConflictItem(
                day_number=day.day_number,
                kind="stay",
                label=day.stay.hotel_name,
                summary=f"第 {day.day_number} 天住宿已安排在“{day.stay.hotel_name}”",
            )
        )
    elif hotel_area and reserved_location and reserved_location not in hotel_area and hotel_area not in reserved_location:
        label = day.hotel_area or day.stay.area
        if label:
            conflicts.append(
                ReservationConflictItem(
                    day_number=day.day_number,
                    kind="stay",
                    label=label,
                    summary=f"第 {day.day_number} 天住宿区域已安排在“{label}”",
                )
            )
    return conflicts


def _collect_restaurant_conflicts(
    reservation: ReservationItem,
    day: DayPlan,
) -> list[ReservationConflictItem]:
    conflicts: list[ReservationConflictItem] = []
    meal_type = _infer_reservation_meal_type(reservation)
    reserved_title = normalize_search_text(reservation.title)
    reserved_location = normalize_search_text(reservation.location)
    existing = next((meal for meal in day.meals if meal.meal_type == meal_type), None)
    if existing is None:
        return conflicts

    venue_text = normalize_search_text(existing.venue_name)
    if reserved_title and reserved_title in venue_text:
        return conflicts
    if reserved_location and reserved_location in venue_text:
        return conflicts

    conflicts.append(
        ReservationConflictItem(
            day_number=day.day_number,
            kind="meal",
            label=existing.venue_name,
            time_text=_meal_type_label_zh(meal_type),
            summary=f"第 {day.day_number} 天{_meal_type_label_zh(meal_type)}档已安排“{existing.venue_name}”",
        )
    )
    return conflicts


def _collect_activity_time_conflicts(
    reservation: ReservationItem,
    day: DayPlan,
) -> list[ReservationConflictItem]:
    window = _reservation_time_window_on_day(reservation, day)
    if window is None:
        return []

    overlapping = [
        activity
        for activity in day.activities
        if _activity_overlaps_window(activity, day, window)
        and not _activity_matches_reservation(activity, reservation)
    ]
    if not overlapping:
        return []

    conflicts: list[ReservationConflictItem] = []
    for activity in overlapping[:2]:
        conflicts.append(
            ReservationConflictItem(
                day_number=day.day_number,
                kind="activity",
                label=activity.title,
                time_text=_format_activity_time_text(activity),
                summary=f"第 {day.day_number} 天已有活动占用预约时段：{_format_activity_conflict_label(activity)}",
            )
        )
    return conflicts


def _reservation_time_window_on_day(
    reservation: ReservationItem,
    day: DayPlan,
) -> tuple[datetime, datetime] | None:
    start_at = normalize_datetime(reservation.start_at)
    end_at = normalize_datetime(reservation.end_at)
    if start_at is None and end_at is None:
        return None

    effective_start = start_at or end_at
    effective_end = end_at or start_at
    if effective_start is None or effective_end is None:
        return None

    day_start = datetime.fromisoformat(day.date).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    clipped_start = max(effective_start, day_start)
    clipped_end = min(effective_end, day_end)
    if clipped_end < clipped_start:
        return None
    return clipped_start, clipped_end


def _activity_overlaps_window(
    activity: Activity,
    day: DayPlan,
    window: tuple[datetime, datetime],
) -> bool:
    activity_window = _activity_time_window(activity, day)
    if activity_window is None:
        return False
    activity_start, activity_end = activity_window
    reservation_start, reservation_end = window
    return activity_start <= reservation_end and reservation_start <= activity_end


def _activity_time_window(
    activity: Activity,
    day: DayPlan,
) -> tuple[datetime, datetime] | None:
    try:
        day_start = datetime.fromisoformat(day.date)
        start_at = datetime.strptime(activity.start_time, "%H:%M")
        end_at = datetime.strptime(activity.end_time, "%H:%M")
    except ValueError:
        return None

    start = day_start.replace(hour=start_at.hour, minute=start_at.minute, tzinfo=timezone.utc)
    end = day_start.replace(hour=end_at.hour, minute=end_at.minute, tzinfo=timezone.utc)
    if end < start:
        end = end + timedelta(days=1)
    return start, end


def _activity_matches_reservation(
    activity: Activity,
    reservation: ReservationItem,
) -> bool:
    haystack = " ".join(
        [
            activity.title,
            activity.location_name,
            activity.description,
            activity.poi.name if activity.poi else "",
            activity.poi.address if activity.poi else "",
        ]
    )
    normalized_haystack = normalize_search_text(haystack)
    title = normalize_search_text(reservation.title)
    location = normalize_search_text(reservation.location)
    if title and title in normalized_haystack:
        return True
    if location and location in normalized_haystack:
        return True
    return False


def _format_activity_conflict_label(activity: Activity) -> str:
    time_text = "-".join(part for part in (activity.start_time, activity.end_time) if part)
    if time_text:
        return f"{time_text}“{activity.title}”"
    return f"“{activity.title}”"


def _format_activity_time_text(activity: Activity) -> str:
    return "-".join(part for part in (activity.start_time, activity.end_time) if part)


def _meal_type_label_zh(meal_type: str) -> str:
    labels = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "加餐",
    }
    return labels.get(meal_type, meal_type)


def reservation_matches_day_content(reservation: ReservationItem, day: Any) -> bool:
    normalized_title = normalize_search_text(reservation.title)
    normalized_location = normalize_search_text(reservation.location)
    keyword_pool = reservation_search_tokens(reservation)

    if reservation.type == "hotel":
        haystacks = [
            day.stay.hotel_name,
            day.stay.area,
            day.hotel_area,
            day.overview,
        ]
    elif reservation.type == "restaurant":
        haystacks = [
            day.overview,
            *[meal.venue_name for meal in day.meals],
            *[(meal.poi.name if meal.poi else "") for meal in day.meals],
            *[(meal.poi.address if meal.poi else "") for meal in day.meals],
        ]
    else:
        haystacks = [
            day.theme,
            day.overview,
            *day.transport_tips,
            *[activity.title for activity in day.activities],
            *[activity.location_name for activity in day.activities],
            *[activity.description for activity in day.activities],
            *[(activity.poi.name if activity.poi else "") for activity in day.activities],
            *[(activity.poi.address if activity.poi else "") for activity in day.activities],
        ]

    normalized_haystack = " ".join(
        item for item in (normalize_search_text(value) for value in haystacks) if item
    )
    if not normalized_haystack:
        return False
    if normalized_title and normalized_title in normalized_haystack:
        return True
    if normalized_location and normalized_location in normalized_haystack:
        return True

    hits = [token for token in keyword_pool if token in normalized_haystack]
    if len(hits) >= 2:
        return True
    return any(len(token) >= 4 and token in normalized_haystack for token in keyword_pool)


def _reservation_diagnostic_key(reservation: ReservationItem) -> str:
    return "|".join(
        [
            reservation.id.strip(),
            reservation.type,
            reservation.title.strip(),
            format_reservation_time(reservation.start_at),
            format_reservation_time(reservation.end_at),
            reservation.location.strip(),
        ]
    )


def reservation_search_tokens(reservation: ReservationItem) -> list[str]:
    tokens: list[str] = []
    for raw in (reservation.title, reservation.location):
        for item in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", raw or ""):
            normalized = normalize_search_text(item)
            if len(normalized) >= 2:
                tokens.append(normalized)
    return list(dict.fromkeys(tokens))


def normalize_search_text(value: str | None) -> str:
    if not value:
        return ""
    return "".join(
        ch.lower()
        for ch in value
        if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff")
    )


def format_reservation_range(reservation: ReservationItem) -> str:
    if reservation.start_at is None and reservation.end_at is None:
        return ""
    if reservation.start_at is not None and reservation.end_at is not None:
        return (
            f"{format_reservation_time(reservation.start_at)}"
            f" -> {format_reservation_time(reservation.end_at)}"
        )
    value = reservation.start_at if reservation.start_at is not None else reservation.end_at
    return format_reservation_time(value)


def format_reservation_time(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M")


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
