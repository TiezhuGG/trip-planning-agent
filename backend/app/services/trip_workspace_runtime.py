from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.schemas.planning import (
    PlanningResponse,
    ReservationItem,
    TripPlanningRequest,
    TripWorkspace,
)
from app.services.trip_workspace_reservations import (
    audit_generated_reservations,
    build_effective_request,
)


class TripWorkspaceRuntimeMixin:
    def _init_runtime_state(self) -> None:
        self._lock = asyncio.Lock()

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
        effective_request = build_effective_request(
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
        return self._merge_reservation_audit_warnings(
            request=request,
            reservations=reservations or [],
            response=response,
        )

    def _merge_reservation_audit_warnings(
        self,
        *,
        request: TripPlanningRequest,
        reservations: list[ReservationItem],
        response: PlanningResponse,
    ) -> PlanningResponse:
        audit_warnings = audit_generated_reservations(
            request,
            reservations,
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

    async def _read_trip(self, trip_id: str) -> TripWorkspace | None:
        async with self._lock:
            workspace = self.store.get_by_id(trip_id)
            if workspace is None:
                return None
            return workspace.model_copy(deep=True)

    async def _save_trip(self, workspace: TripWorkspace) -> None:
        async with self._lock:
            self.store.save(workspace.model_copy(deep=True))
