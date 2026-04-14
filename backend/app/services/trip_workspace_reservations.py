from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.planning import PlanningResponse, ReservationItem, TripPlanningRequest


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
    for reservation in reservations:
        if reservation_is_reflected_in_plan(request, reservation, response):
            continue
        target_days = reservation_trip_days(request, reservation)
        if target_days:
            day_text = ", ".join(f"day {day}" for day in target_days)
            warnings.append(
                f"Reservation audit: “{reservation.title}” is not explicitly reflected in {day_text}; verify manually or replan the affected day."
            )
        else:
            warnings.append(
                f"Reservation audit: “{reservation.title}” is not explicitly reflected in the generated itinerary; verify manually."
            )
    return warnings


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
            if reservation.end_at is not None:
                parts.append(f"check_out={format_reservation_time(reservation.end_at)}")
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
        if reservation.location.strip():
            parts.append(f"location={reservation.location.strip()}")
        parts.append("requirement=keep_time_window_clear_and_place_anchor_explicitly")
        rules.append(f"- {'; '.join(parts)}")
    return rules


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
