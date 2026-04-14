from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.schemas.planning import (
    ReplanRequest,
    TripCreateRequest,
    TripWorkspace,
    TripWorkspacePatchRequest,
)
from app.services.planner import TravelPlannerService
from app.services.trip_workspace_builders import (
    build_created_workspace,
    build_updated_workspace,
    normalize_day_numbers,
    normalize_reservations,
)
from app.services.trip_workspace_replan import merge_replanned_response, resolve_replan_targets
from app.services.trip_workspace_reservations import validate_reservations
from app.services.trip_workspace_runtime import TripWorkspaceRuntimeMixin
from app.services.trip_workspace_store import (
    TripWorkspaceStore,
    create_trip_workspace_store,
)
from app.services.trip_workspace_validation import validate_snapshot_matches_request

_REPLAN_REQUIRES_RESPONSE = (
    "\u5f53\u524d\u5de5\u4f5c\u533a\u8fd8\u662f\u8349\u7a3f\uff0c"
    "\u8bf7\u5148\u751f\u6210\u7ed3\u679c\u540e\u518d\u91cd\u65b0\u89c4\u5212\u3002"
)


class TripWorkspaceService(TripWorkspaceRuntimeMixin):
    def __init__(
        self,
        settings: Settings,
        planner_service: TravelPlannerService,
        store: TripWorkspaceStore | None = None,
    ) -> None:
        self.settings = settings
        self.planner_service = planner_service
        self.store = store or create_trip_workspace_store(settings)
        self._init_runtime_state()

    async def create_trip(self, payload: TripCreateRequest) -> TripWorkspace:
        manual_notes = payload.manual_notes or ""
        reservations = normalize_reservations(payload.reservations)
        validate_reservations(payload.request_brief, reservations)
        response = payload.response_snapshot
        if response is None and payload.generate_response:
            response = await self._generate_response(
                payload.request_brief,
                include_debug=payload.include_debug,
                manual_notes=manual_notes,
                reservations=reservations,
            )
        elif response is not None:
            validate_snapshot_matches_request(payload.request_brief, response)

        now = datetime.now(timezone.utc)
        workspace = build_created_workspace(
            now=now,
            request_brief=payload.request_brief,
            manual_notes=manual_notes,
            locked_day_numbers=normalize_day_numbers(
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
        reservations = normalize_reservations(
            payload.reservations if payload.reservations is not None else current.reservations
        )
        validate_reservations(request_brief, reservations)
        response_snapshot = current.response_snapshot
        if payload.generate_response:
            response_snapshot = await self._generate_response(
                request_brief,
                include_debug=payload.include_debug,
                manual_notes=manual_notes,
                reservations=reservations,
            )

        updated = build_updated_workspace(
            current=current,
            now=datetime.now(timezone.utc),
            request_brief=request_brief,
            manual_notes=manual_notes,
            locked_day_numbers=normalize_day_numbers(
                payload.locked_day_numbers
                if payload.locked_day_numbers is not None
                else current.locked_day_numbers,
                request_brief.days,
            ),
            reservations=reservations,
            response_snapshot=response_snapshot,
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
            raise ValueError(_REPLAN_REQUIRES_RESPONSE)

        validate_reservations(current.request_brief, current.reservations)
        target_days = resolve_replan_targets(
            request=current.request_brief,
            locked_day_numbers=current.locked_day_numbers,
            payload=payload,
            normalize_day_numbers=normalize_day_numbers,
        )
        fresh_response = await self._generate_response(
            current.request_brief,
            include_debug=payload.include_debug,
            manual_notes=current.manual_notes,
            reservations=current.reservations,
            replan_target_days=target_days,
            replan_reason=payload.reason,
        )
        merged_response = merge_replanned_response(
            current=current,
            fresh=fresh_response,
            target_days=target_days,
            reason=payload.reason,
            apply_budget=self.planner_service.coordinator.ai_client._apply_deterministic_budget,
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
