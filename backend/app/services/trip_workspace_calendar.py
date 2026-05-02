from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from app.schemas.planning import Activity, DayPlan, ReservationItem, TripWorkspace
from app.services.trip_workspace_reservations import reservation_trip_days


CalendarExportScope = Literal["full", "reservations", "itinerary"]


@dataclass(frozen=True)
class CalendarExportResult:
    filename: str
    content: str


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    stamp: datetime
    start_line: str
    end_line: str | None
    summary: str
    description: str = ""
    location: str = ""
    categories: str = ""
    status: str = "CONFIRMED"


def build_trip_workspace_calendar(
    workspace: TripWorkspace,
    *,
    scope: CalendarExportScope = "full",
) -> CalendarExportResult:
    normalized_scope = _normalize_scope(scope)
    calendar_name = (
        workspace.response_snapshot.plan.title.strip()
        if workspace.response_snapshot and workspace.response_snapshot.plan.title.strip()
        else f"{workspace.request_brief.destination} 行程工作区"
    )
    event_blocks = [_serialize_event(event) for event in _build_calendar_events(workspace, scope=normalized_scope)]
    content_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Trip Planning Agent//Smart Travel Planner//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape_ics_text(calendar_name)}",
        *event_blocks,
        "END:VCALENDAR",
        "",
    ]
    filename_base = _sanitize_filename(calendar_name) or "trip-workspace"
    filename_suffix = {
        "full": "",
        "reservations": "-reservations",
        "itinerary": "-itinerary",
    }[normalized_scope]
    return CalendarExportResult(
        filename=f"{filename_base}{filename_suffix}.ics",
        content="\r\n".join(content_lines),
    )


def _normalize_scope(scope: str) -> CalendarExportScope:
    normalized = (scope or "full").strip().lower()
    if normalized not in {"full", "reservations", "itinerary"}:
        raise ValueError(f"Unsupported calendar export scope: {scope}")
    return normalized  # type: ignore[return-value]


def _build_calendar_events(
    workspace: TripWorkspace,
    *,
    scope: CalendarExportScope,
) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    stamp = (
        workspace.updated_at.astimezone(UTC)
        if workspace.updated_at.tzinfo
        else workspace.updated_at.replace(tzinfo=UTC)
    )

    if scope in {"full", "reservations"}:
        for reservation in workspace.reservations:
            event = _build_reservation_event(workspace, reservation, stamp)
            if event is not None:
                events.append(event)

    if scope == "reservations" or workspace.response_snapshot is None:
        return events

    reserved_hotel_days = _hotel_reserved_days(workspace)
    for day in workspace.response_snapshot.plan.days:
        stay_event = _build_stay_event(workspace, day, reserved_hotel_days, stamp)
        if stay_event is not None:
            events.append(stay_event)
        for activity_index, activity in enumerate(day.activities):
            activity_event = _build_activity_event(workspace, day, activity, activity_index, stamp)
            if activity_event is not None:
                events.append(activity_event)

    return events


def _build_reservation_event(
    workspace: TripWorkspace,
    reservation: ReservationItem,
    stamp: datetime,
) -> CalendarEvent | None:
    start = reservation.start_at or reservation.end_at
    if start is None:
        return None

    start_line = _format_datetime_line("DTSTART", start)
    end_line = _format_datetime_line("DTEND", reservation.end_at) if reservation.end_at else None
    description_parts = [f"类型：{_reservation_type_label(reservation.type)}"]
    if reservation.notes.strip():
        description_parts.append(f"备注：{reservation.notes.strip()}")
    if reservation.source.strip():
        description_parts.append(f"来源：{reservation.source.strip()}")
    if reservation.confirmation_code.strip():
        description_parts.append(f"确认号：{reservation.confirmation_code.strip()}")

    return CalendarEvent(
        uid=f"{workspace.id}-reservation-{reservation.id}@trip-planning-agent",
        stamp=stamp,
        start_line=start_line,
        end_line=end_line,
        summary=f"{_reservation_type_label(reservation.type)}：{reservation.title.strip()}",
        description="\n".join(description_parts),
        location=reservation.location.strip(),
        categories=f"RESERVATION,{reservation.type.upper()}",
    )


def _build_stay_event(
    workspace: TripWorkspace,
    day: DayPlan,
    reserved_hotel_days: set[int],
    stamp: datetime,
) -> CalendarEvent | None:
    if day.day_number in reserved_hotel_days:
        return None
    hotel_name = (day.stay.hotel_name or "").strip()
    if not hotel_name:
        return None

    day_date = _parse_iso_date(day.date)
    if day_date is None:
        return None

    description_parts = []
    if day.stay.area:
        description_parts.append(f"区域：{day.stay.area}")
    if day.stay.reason:
        description_parts.append(f"说明：{day.stay.reason}")
    if day.stay.poi and day.stay.poi.address:
        description_parts.append(f"地址：{day.stay.poi.address}")

    return CalendarEvent(
        uid=f"{workspace.id}-stay-day{day.day_number}@trip-planning-agent",
        stamp=stamp,
        start_line=f"DTSTART;VALUE=DATE:{day_date.strftime('%Y%m%d')}",
        end_line=f"DTEND;VALUE=DATE:{(day_date + timedelta(days=1)).strftime('%Y%m%d')}",
        summary=f"住宿：{hotel_name}",
        description="\n".join(description_parts),
        location=(
            day.stay.poi.address
            if day.stay.poi and day.stay.poi.address
            else day.stay.area or day.hotel_area
        ),
        categories="ITINERARY,STAY",
    )


def _build_activity_event(
    workspace: TripWorkspace,
    day: DayPlan,
    activity: Activity,
    activity_index: int,
    stamp: datetime,
) -> CalendarEvent | None:
    start_at = _combine_day_and_clock(day.date, activity.start_time)
    end_at = _combine_day_and_clock(day.date, activity.end_time)
    if start_at is None:
        return None

    description_parts = [activity.description.strip()] if activity.description.strip() else []
    if activity.booking_tip:
        description_parts.append(f"预约提示：{activity.booking_tip}")
    if activity.expected_cost:
        description_parts.append(f"费用：{activity.expected_cost}")

    location_parts = []
    if activity.poi and activity.poi.name:
        location_parts.append(activity.poi.name)
    if activity.poi and activity.poi.address:
        location_parts.append(activity.poi.address)
    elif activity.location_name:
        location_parts.append(activity.location_name)

    return CalendarEvent(
        uid=f"{workspace.id}-activity-day{day.day_number}-{activity_index}@trip-planning-agent",
        stamp=stamp,
        start_line=_format_datetime_line("DTSTART", start_at),
        end_line=_format_datetime_line("DTEND", end_at) if end_at is not None else None,
        summary=f"行程活动：{activity.title}",
        description="\n".join(description_parts),
        location=" · ".join(item for item in location_parts if item),
        categories="ITINERARY,ACTIVITY",
    )


def _hotel_reserved_days(workspace: TripWorkspace) -> set[int]:
    return {
        day
        for reservation in workspace.reservations
        if reservation.type == "hotel"
        for day in reservation_trip_days(workspace.request_brief, reservation)
    }


def _serialize_event(event: CalendarEvent) -> str:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{_escape_ics_text(event.uid)}",
        f"DTSTAMP:{event.stamp.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        event.start_line,
    ]
    if event.end_line:
        lines.append(event.end_line)
    lines.append(f"SUMMARY:{_escape_ics_text(event.summary)}")
    if event.description:
        lines.append(f"DESCRIPTION:{_escape_ics_text(event.description)}")
    if event.location:
        lines.append(f"LOCATION:{_escape_ics_text(event.location)}")
    if event.categories:
        lines.append(f"CATEGORIES:{event.categories}")
    lines.append(f"STATUS:{event.status}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines)


def _format_datetime_line(field_name: str, value: datetime) -> str:
    if value.tzinfo is not None:
        normalized = value.astimezone(UTC)
        return f"{field_name}:{normalized.strftime('%Y%m%dT%H%M%SZ')}"
    return f"{field_name}:{value.strftime('%Y%m%dT%H%M%S')}"


def _combine_day_and_clock(day_value: str, clock_value: str) -> datetime | None:
    day_date = _parse_iso_date(day_value)
    parsed_time = _parse_clock(clock_value)
    if day_date is None or parsed_time is None:
        return None
    return datetime.combine(day_date, parsed_time)


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def _parse_clock(value: str) -> time | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    for pattern in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(normalized, pattern).time()
        except ValueError:
            continue
    return None


def _escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\n", "\\n")
        .replace(";", r"\;")
        .replace(",", r"\,")
    )


def _sanitize_filename(value: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]+', "-", value).strip()
    sanitized = re.sub(r"\s+", "-", sanitized)
    return sanitized[:80]


def _reservation_type_label(value: str) -> str:
    return {
        "flight": "航班",
        "train": "火车",
        "hotel": "酒店",
        "restaurant": "餐厅",
        "ticket": "门票",
        "other": "预约",
    }.get(value, value)
