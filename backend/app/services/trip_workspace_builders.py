from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Literal

from app.schemas.planning import (
    PlanningResponse,
    PrecheckSummary,
    ReservationItem,
    TripPlanningRequest,
    TripWorkspace,
    WorkspaceTimelineEvent,
)


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
    status = resolve_workspace_status(response_snapshot)
    title = "已创建工作区并生成首版行程" if response_snapshot is not None else "已保存工作区草稿"
    summary = (
        f"{request_brief.destination} {request_brief.days} 天行程已生成，可继续补充预约、预检或重规划。"
        if response_snapshot is not None
        else f"{request_brief.destination} {request_brief.days} 天需求已保存为草稿。"
    )
    return TripWorkspace(
        id=uuid.uuid4().hex,
        share_token=generate_share_token(),
        share_enabled=True,
        status=status,
        version=1,
        created_at=now,
        updated_at=now,
        request_brief=request_brief,
        manual_notes=manual_notes,
        locked_day_numbers=locked_day_numbers,
        reservations=reservations,
        timeline=[
            build_timeline_event(
                now=now,
                version=1,
                kind="created",
                title=title,
                summary=summary,
            )
        ],
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
            "status": resolve_workspace_status(
                response_snapshot,
                last_precheck_summary=current.last_precheck_summary,
            ),
            "request_brief": request_brief,
            "manual_notes": manual_notes,
            "locked_day_numbers": locked_day_numbers,
            "reservations": reservations,
            "response_snapshot": response_snapshot,
        },
        deep=True,
    )


def generate_share_token() -> str:
    return secrets.token_urlsafe(9)


def build_timeline_event(
    *,
    now: datetime,
    version: int,
    kind: Literal[
        "created",
        "updated",
        "generated",
        "replanned",
        "prechecked",
        "share_revoked",
        "share_regenerated",
    ],
    title: str,
    summary: str = "",
    target_days: list[int] | None = None,
) -> WorkspaceTimelineEvent:
    return WorkspaceTimelineEvent(
        id=uuid.uuid4().hex,
        created_at=now,
        kind=kind,
        title=title,
        summary=summary,
        version=version,
        target_days=sorted(set(target_days or [])),
    )


def append_timeline_event(
    events: list[WorkspaceTimelineEvent],
    event: WorkspaceTimelineEvent,
) -> list[WorkspaceTimelineEvent]:
    return [event, *events][:50]


def resolve_workspace_status(
    response_snapshot: PlanningResponse | None,
    *,
    last_precheck_summary: PrecheckSummary | None = None,
) -> str:
    if response_snapshot is None:
        return "draft"

    coverage = response_snapshot.diagnostics.reservation_coverage
    if any(item.status != "covered" for item in coverage):
        return "action_required"

    if last_precheck_summary and any(item.after_status == "warning" for item in last_precheck_summary.items):
        return "action_required"

    return "ready"
