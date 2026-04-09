from __future__ import annotations

import asyncio
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.schemas.planning import (
    PlanningResponse,
    ReplanRequest,
    ReservationItem,
    TripCreateRequest,
    TripPlanningRequest,
    TripWorkspace,
    TripWorkspacePatchRequest,
)
from app.services.planner import TravelPlannerService
from app.services.trip_workspace_store import (
    TripWorkspaceStore,
    create_trip_workspace_store,
)


class TripWorkspaceService:
    def __init__(
        self,
        settings: Settings,
        planner_service: TravelPlannerService,
        store: TripWorkspaceStore | None = None,
    ) -> None:
        self.settings = settings
        self.planner_service = planner_service
        self.store = store or create_trip_workspace_store(settings)
        self._lock = asyncio.Lock()

    async def create_trip(self, payload: TripCreateRequest) -> TripWorkspace:
        manual_notes = payload.manual_notes or ""
        reservations = self._normalize_reservations(payload.reservations)
        self._validate_reservations(payload.request_brief, reservations)
        response = payload.response_snapshot
        if response is None and payload.generate_response:
            response = await self._generate_response(
                payload.request_brief,
                include_debug=payload.include_debug,
                manual_notes=manual_notes,
                reservations=reservations,
            )
        elif response is not None:
            self._validate_snapshot_matches_request(payload.request_brief, response)

        now = datetime.now(timezone.utc)
        workspace = TripWorkspace(
            id=uuid.uuid4().hex,
            share_token=secrets.token_urlsafe(9),
            status="ready" if response is not None else "draft",
            version=1,
            created_at=now,
            updated_at=now,
            request_brief=payload.request_brief,
            manual_notes=manual_notes,
            locked_day_numbers=self._normalize_day_numbers(
                payload.locked_day_numbers,
                payload.request_brief.days,
            ),
            reservations=reservations,
            response_snapshot=response,
        )
        await self._save_trip(workspace)
        return workspace.model_copy(deep=True)

    async def get_trip(self, trip_id: str) -> TripWorkspace:
        workspace = await self._read_trip(trip_id)
        if workspace is None:
            raise KeyError(f"trip {trip_id} not found")
        return workspace

    async def get_trip_by_share_token(self, share_token: str) -> TripWorkspace:
        async with self._lock:
            workspace = self.store.get_by_share_token(share_token)
            if workspace is None:
                raise KeyError(f"share token {share_token} not found")
            return workspace.model_copy(deep=True)

    async def update_trip(
        self,
        trip_id: str,
        payload: TripWorkspacePatchRequest,
    ) -> TripWorkspace:
        current = await self._read_trip(trip_id)
        if current is None:
            raise KeyError(f"trip {trip_id} not found")

        request_brief = payload.request_brief or current.request_brief
        manual_notes = payload.manual_notes if payload.manual_notes is not None else current.manual_notes
        reservations = self._normalize_reservations(
            payload.reservations if payload.reservations is not None else current.reservations
        )
        self._validate_reservations(request_brief, reservations)
        response_snapshot = current.response_snapshot
        if payload.generate_response:
            response_snapshot = await self._generate_response(
                request_brief,
                include_debug=payload.include_debug,
                manual_notes=manual_notes,
                reservations=reservations,
            )

        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "updated_at": datetime.now(timezone.utc),
                "status": "ready" if response_snapshot is not None else "draft",
                "request_brief": request_brief,
                "manual_notes": manual_notes,
                "locked_day_numbers": self._normalize_day_numbers(
                    payload.locked_day_numbers
                    if payload.locked_day_numbers is not None
                    else current.locked_day_numbers,
                    request_brief.days,
                ),
                "reservations": reservations,
                "response_snapshot": response_snapshot,
            },
            deep=True,
        )
        await self._save_trip(updated)
        return updated.model_copy(deep=True)

    async def replan_trip(
        self,
        trip_id: str,
        payload: ReplanRequest,
    ) -> TripWorkspace:
        current = await self._read_trip(trip_id)
        if current is None:
            raise KeyError(f"trip {trip_id} not found")
        if current.response_snapshot is None:
            raise ValueError("当前工作区还是草稿，需先生成结果后才能重规划。")

        self._validate_reservations(current.request_brief, current.reservations)
        target_days = self._resolve_replan_targets(
            request=current.request_brief,
            locked_day_numbers=current.locked_day_numbers,
            payload=payload,
        )
        fresh_response = await self._generate_response(
            current.request_brief,
            include_debug=payload.include_debug,
            manual_notes=current.manual_notes,
            reservations=current.reservations,
            replan_target_days=target_days,
            replan_reason=payload.reason,
        )
        merged_response = self._merge_response_for_replan(
            current=current,
            fresh=fresh_response,
            payload=payload,
            target_days=target_days,
        )
        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "updated_at": datetime.now(timezone.utc),
                "response_snapshot": merged_response,
            },
            deep=True,
        )
        await self._save_trip(updated)
        return updated.model_copy(deep=True)

    async def _generate_response(
        self,
        request: TripPlanningRequest,
        *,
        include_debug: bool,
        manual_notes: str = "",
        reservations: list[ReservationItem] | None = None,
        replan_target_days: set[int] | None = None,
        replan_reason: str | None = None,
    ) -> PlanningResponse:
        effective_request = self._build_effective_request(
            request,
            manual_notes=manual_notes,
            reservations=reservations,
            replan_target_days=replan_target_days,
            replan_reason=replan_reason,
        )
        response = await self.planner_service.generate(
            effective_request,
            generated_at=datetime.now(timezone.utc),
            include_debug=include_debug,
        )
        audit_warnings = self._audit_generated_reservations(
            request,
            reservations or [],
            response,
        )
        if not audit_warnings:
            return response

        merged_meta = response.meta.model_copy(
            update={
                "warnings": list(dict.fromkeys([*response.meta.warnings, *audit_warnings])),
            },
            deep=True,
        )
        merged_diagnostics = response.diagnostics.model_copy(
            update={
                "warnings": list(dict.fromkeys([*response.diagnostics.warnings, *audit_warnings])),
            },
            deep=True,
        )
        return response.model_copy(
            update={
                "meta": merged_meta,
                "diagnostics": merged_diagnostics,
            },
            deep=True,
        )

    def _merge_response_for_replan(
        self,
        *,
        current: TripWorkspace,
        fresh: PlanningResponse,
        payload: ReplanRequest,
        target_days: set[int] | None = None,
    ) -> PlanningResponse:
        request = current.request_brief
        if current.response_snapshot is None:
            raise ValueError("当前工作区没有可用于重规划的已生成结果。")

        target_days = target_days or self._resolve_replan_targets(
            request=request,
            locked_day_numbers=current.locked_day_numbers,
            payload=payload,
        )
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
        merged_plan = self.planner_service.coordinator.ai_client._apply_deterministic_budget(
            request,
            merged_plan,
        )
        warning = self._build_replan_warning(target_days, payload.reason)
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

    def _resolve_replan_targets(
        self,
        *,
        request: TripPlanningRequest,
        locked_day_numbers: list[int],
        payload: ReplanRequest,
    ) -> set[int]:
        valid_days = set(range(1, request.days + 1))
        explicit_days = self._normalize_day_numbers(payload.day_numbers, request.days)
        if payload.scope == "trip":
            target_days = (
                valid_days.difference(locked_day_numbers)
                if payload.preserve_locked_days
                else valid_days
            )
        else:
            if not explicit_days:
                raise ValueError("按天重规划时必须指定 day_numbers。")
            invalid_days = set(explicit_days).difference(valid_days)
            if invalid_days:
                raise ValueError(f"存在超出行程范围的日期: {sorted(invalid_days)}")
            target_days = set(explicit_days)
        if not target_days:
            raise ValueError("当前没有可重规划的日期。")
        return target_days

    def _build_replan_warning(self, target_days: set[int], reason: str | None) -> str:
        ordered = "、".join(f"第 {day} 天" for day in sorted(target_days))
        if reason:
            return f"已按请求重新生成 {ordered}，原因: {reason}。"
        return f"已按请求重新生成 {ordered}。"

    def _validate_snapshot_matches_request(
        self,
        request: TripPlanningRequest,
        response: PlanningResponse,
    ) -> None:
        request_payload = request.model_dump(mode="json")
        response_payload = response.request_echo.model_dump(mode="json")
        if request_payload != response_payload:
            raise ValueError("response_snapshot.request_echo 与 request_brief 不一致。")

    async def _read_trip(self, trip_id: str) -> TripWorkspace | None:
        async with self._lock:
            workspace = self.store.get_by_id(trip_id)
            if workspace is None:
                return None
            return workspace.model_copy(deep=True)

    async def _save_trip(self, workspace: TripWorkspace) -> None:
        async with self._lock:
            self.store.save(workspace.model_copy(deep=True))

    def _normalize_day_numbers(self, day_numbers: list[int], max_days: int) -> list[int]:
        return sorted(
            {
                int(day)
                for day in day_numbers
                if isinstance(day, int) and 1 <= int(day) <= max_days
            }
        )

    def _normalize_reservations(self, reservations):
        normalized = []
        for item in reservations or []:
            reservation = item.model_copy(deep=True) if hasattr(item, "model_copy") else item
            if not reservation.id:
                reservation = reservation.model_copy(update={"id": uuid.uuid4().hex}, deep=True)
            normalized.append(reservation)
        return normalized

    def _validate_reservations(
        self,
        request: TripPlanningRequest,
        reservations: list[ReservationItem],
    ) -> None:
        trip_start = request.start_date
        trip_end = request.start_date + timedelta(days=request.days - 1)
        for reservation in reservations:
            start_at = self._normalize_datetime(reservation.start_at)
            end_at = self._normalize_datetime(reservation.end_at)
            if start_at is not None and end_at is not None and end_at < start_at:
                raise ValueError(
                    f"预约“{reservation.title}”的结束时间不能早于开始时间。"
                )

            dated_values = [value for value in (start_at, end_at) if value is not None]
            if not dated_values:
                continue

            if all(value.date() < trip_start for value in dated_values):
                raise ValueError(f"预约“{reservation.title}”不在本次行程日期范围内。")
            if all(value.date() > trip_end for value in dated_values):
                raise ValueError(f"预约“{reservation.title}”不在本次行程日期范围内。")

        self._validate_reservation_time_conflicts(reservations)

    def _build_effective_request(
        self,
        request: TripPlanningRequest,
        *,
        manual_notes: str = "",
        reservations: list[ReservationItem] | None = None,
        replan_target_days: set[int] | None = None,
        replan_reason: str | None = None,
    ) -> TripPlanningRequest:
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

        reservation_notes = self._build_reservation_notes(request, reservations or [])
        if reservation_notes:
            note_sections.append(reservation_notes)

        replan_notes = self._build_replan_notes(
            target_days=replan_target_days,
            reason=replan_reason,
        )
        if replan_notes:
            note_sections.append(replan_notes)

        effective_notes = "\n\n".join(note_sections).strip()
        if effective_notes == (request.notes or "").strip():
            return request
        return request.model_copy(update={"notes": effective_notes or None}, deep=True)

    def _build_reservation_notes(
        self,
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
            trip_days = self._reservation_trip_days(request, item)
            if trip_days:
                parts.append(
                    "trip_days="
                    + ",".join(f"day{day}" for day in trip_days)
                )
            time_range = self._format_reservation_range(item)
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

        lines.append(
            "Scheduling rules: on the listed trip_days, keep the reservation time window available, "
            "place nearby meals/activities around the anchor, and avoid long cross-city detours that would cause conflicts."
        )
        return "\n".join(lines)

    def _build_replan_notes(self, *, target_days: set[int] | None, reason: str | None) -> str:
        if not target_days and not (reason or "").strip():
            return ""

        lines = ["Partial replanning instructions:"]
        if target_days:
            ordered_days = ", ".join(str(day) for day in sorted(target_days))
            lines.append(f"- regenerate_days={ordered_days}")
        if (reason or "").strip():
            lines.append(f"- reason={reason.strip()}")
        return "\n".join(lines)

    def _reservation_trip_days(
        self,
        request: TripPlanningRequest,
        reservation: ReservationItem,
    ) -> list[int]:
        trip_start = request.start_date
        trip_end = request.start_date + timedelta(days=request.days - 1)
        start_at = self._normalize_datetime(reservation.start_at)
        end_at = self._normalize_datetime(reservation.end_at)
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

    def _validate_reservation_time_conflicts(
        self,
        reservations: list[ReservationItem],
    ) -> None:
        checkable_types = {"flight", "train", "restaurant", "ticket", "other"}
        windows: list[tuple[ReservationItem, datetime, datetime]] = []
        for reservation in reservations:
            if reservation.type not in checkable_types:
                continue
            start_at = self._normalize_datetime(reservation.start_at)
            end_at = self._normalize_datetime(reservation.end_at)
            if start_at is None:
                continue
            effective_end = end_at or start_at
            windows.append((reservation, start_at, effective_end))

        windows.sort(key=lambda item: item[1])
        for index, (current, current_start, current_end) in enumerate(windows):
            for other, other_start, other_end in windows[index + 1 :]:
                if other_start > current_end:
                    break
                raise ValueError(
                    f"预约“{current.title}”与“{other.title}”存在时间重叠，请先调整后再保存。"
                )

    def _audit_generated_reservations(
        self,
        request: TripPlanningRequest,
        reservations: list[ReservationItem],
        response: PlanningResponse,
    ) -> list[str]:
        warnings: list[str] = []
        for reservation in reservations:
            if self._reservation_is_reflected_in_plan(request, reservation, response):
                continue
            target_days = self._reservation_trip_days(request, reservation)
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

    def _reservation_is_reflected_in_plan(
        self,
        request: TripPlanningRequest,
        reservation: ReservationItem,
        response: PlanningResponse,
    ) -> bool:
        target_days = set(self._reservation_trip_days(request, reservation))
        candidate_days = [
            day
            for day in response.plan.days
            if not target_days or day.day_number in target_days
        ]
        if not candidate_days:
            return False

        for day in candidate_days:
            if self._reservation_matches_day_content(reservation, day):
                return True
        return False

    def _reservation_matches_day_content(self, reservation: ReservationItem, day) -> bool:
        normalized_title = self._normalize_search_text(reservation.title)
        normalized_location = self._normalize_search_text(reservation.location)
        keyword_pool = self._reservation_search_tokens(reservation)

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
            item for item in (self._normalize_search_text(value) for value in haystacks) if item
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

    def _reservation_search_tokens(self, reservation: ReservationItem) -> list[str]:
        tokens: list[str] = []
        for raw in (reservation.title, reservation.location):
            for item in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", raw or ""):
                normalized = self._normalize_search_text(item)
                if len(normalized) >= 2:
                    tokens.append(normalized)
        return list(dict.fromkeys(tokens))

    def _normalize_search_text(self, value: str | None) -> str:
        if not value:
            return ""
        return "".join(
            ch.lower()
            for ch in value
            if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff")
        )

    def _format_reservation_range(self, reservation: ReservationItem) -> str:
        if reservation.start_at is None and reservation.end_at is None:
            return ""
        if reservation.start_at is not None and reservation.end_at is not None:
            return (
                f"{self._format_reservation_time(reservation.start_at)}"
                f" -> {self._format_reservation_time(reservation.end_at)}"
            )
        value = reservation.start_at if reservation.start_at is not None else reservation.end_at
        return self._format_reservation_time(value)

    def _format_reservation_time(self, value: datetime | None) -> str:
        if value is None:
            return ""
        return value.strftime("%Y-%m-%d %H:%M")

    def _normalize_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
