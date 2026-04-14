from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from app.schemas.planning import ReservationItem, TripPlanningRequest, TripWorkspace


def normalize_day_numbers(day_numbers: list[int], max_days: int) -> list[int]:
    return sorted(
        {
            int(day)
            for day in day_numbers
            if isinstance(day, int) and 1 <= int(day) <= max_days
        }
    )


def normalize_reservations(
    reservations: list[ReservationItem] | None,
) -> list[ReservationItem]:
    normalized: list[ReservationItem] = []
    for item in reservations or []:
        reservation = item.model_copy(deep=True) if hasattr(item, "model_copy") else item
        if not reservation.id:
            reservation = reservation.model_copy(update={"id": uuid.uuid4().hex}, deep=True)
        normalized.append(reservation)
    return normalized


def build_created_workspace(
    *,
    now: datetime,
    request_brief: TripPlanningRequest,
    manual_notes: str,
    locked_day_numbers: list[int],
    reservations: list[ReservationItem],
    response_snapshot,
) -> TripWorkspace:
    return TripWorkspace(
        id=uuid.uuid4().hex,
        share_token=secrets.token_urlsafe(9),
        status="ready" if response_snapshot is not None else "draft",
        version=1,
        created_at=now,
        updated_at=now,
        request_brief=request_brief,
        manual_notes=manual_notes,
        locked_day_numbers=locked_day_numbers,
        reservations=reservations,
        response_snapshot=response_snapshot,
    )


def build_updated_workspace(
    *,
    current: TripWorkspace,
    now: datetime,
    request_brief: TripPlanningRequest,
    manual_notes: str,
    locked_day_numbers: list[int],
    reservations: list[ReservationItem],
    response_snapshot,
) -> TripWorkspace:
    return current.model_copy(
        update={
            "version": current.version + 1,
            "updated_at": now,
            "status": "ready" if response_snapshot is not None else "draft",
            "request_brief": request_brief,
            "manual_notes": manual_notes,
            "locked_day_numbers": locked_day_numbers,
            "reservations": reservations,
            "response_snapshot": response_snapshot,
        },
        deep=True,
    )
