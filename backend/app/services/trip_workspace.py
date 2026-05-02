from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.schemas.planning import (
    PrecheckRefreshRequest,
    ReplanRequest,
    TripSummary,
    TripCreateRequest,
    TripWorkspace,
    TripWorkspacePatchRequest,
)
from app.services.planner import TravelPlannerService
from app.services.trip_workspace_builders import (
    append_timeline_event,
    build_timeline_event,
    build_created_workspace,
    build_updated_workspace,
    generate_share_token,
    normalize_day_numbers,
    normalize_reservations,
    resolve_workspace_status,
)
from app.services.trip_workspace_calendar import build_trip_workspace_calendar
from app.services.trip_workspace_precheck import build_precheck_summary
from app.services.trip_workspace_replan import build_replan_summary, merge_replanned_response, resolve_replan_targets
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
_PRECHECK_REQUIRES_RESPONSE = (
    "\u5f53\u524d\u5de5\u4f5c\u533a\u8fd8\u6ca1\u6709\u53ef\u7528\u884c\u7a0b\uff0c"
    "\u8bf7\u5148\u751f\u6210\u7ed3\u679c\u540e\u518d\u5237\u65b0\u51fa\u53d1\u524d\u6821\u9a8c\u3002"
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

    async def list_recent_trips(self, limit: int = 10) -> list[TripSummary]:
        async with self._lock:
            workspaces = self.store.list_recent(limit=max(1, int(limit)))
        return [self._build_trip_summary(item) for item in workspaces]

    async def get_trip_by_share_token(self, share_token: str) -> TripWorkspace:
        async with self._lock:
            workspace = self.store.get_by_share_token(share_token)
            if workspace is None or not workspace.share_enabled:
                raise KeyError(f"share token {share_token} not found")
            return workspace.model_copy(deep=True)

    async def export_trip_calendar(self, trip_id: str, *, scope: str = "full"):
        workspace = await self._read_trip(trip_id)
        if workspace is None:
            raise KeyError(f"trip {trip_id} not found")
        return build_trip_workspace_calendar(workspace, scope=scope)

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
        updated = self._append_workspace_event(
            updated,
            kind="generated" if payload.generate_response else "updated",
            title="已重新生成工作区结果" if payload.generate_response else "已更新工作区",
            summary=self._build_update_summary(
                workspace=updated,
                generated=payload.generate_response,
            ),
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
            payload=payload,
            apply_budget=self.planner_service.coordinator.ai_client._apply_deterministic_budget,
        )
        replan_summary = build_replan_summary(
            current=current,
            merged=merged_response,
            target_days=target_days,
            payload=payload,
        )
        now = datetime.now(timezone.utc)
        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "updated_at": now,
                "status": resolve_workspace_status(
                    merged_response,
                    last_precheck_summary=current.last_precheck_summary,
                ),
                "last_replan_summary": replan_summary,
                "response_snapshot": merged_response,
            },
            deep=True,
        )
        updated = self._append_workspace_event(
            updated,
            kind="replanned",
            title="已完成局部重规划" if payload.scope == "day" else "已完成整程重规划",
            summary=replan_summary.title,
            target_days=sorted(target_days),
        )
        await self._save_trip(updated)
        return updated.model_copy(deep=True)

    async def refresh_precheck(
        self,
        trip_id: str,
        payload: PrecheckRefreshRequest,
    ) -> TripWorkspace:
        current = await self._read_trip(trip_id)
        if current is None:
            raise KeyError(f"trip {trip_id} not found")
        if current.response_snapshot is None:
            raise ValueError(_PRECHECK_REQUIRES_RESPONSE)

        validate_reservations(current.request_brief, current.reservations)
        refreshed_response = await self._generate_response(
            current.request_brief,
            include_debug=payload.include_debug,
            manual_notes=current.manual_notes,
            reservations=current.reservations,
        )
        now = datetime.now(timezone.utc)
        precheck_summary = build_precheck_summary(
            previous=current.response_snapshot,
            current=refreshed_response,
            created_at=now,
        )
        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "updated_at": now,
                "status": resolve_workspace_status(
                    refreshed_response,
                    last_precheck_summary=precheck_summary,
                ),
                "last_precheck_summary": precheck_summary,
                "response_snapshot": refreshed_response,
            },
            deep=True,
        )
        updated = self._append_workspace_event(
            updated,
            kind="prechecked",
            title="已刷新出发前预检",
            summary=precheck_summary.title,
            target_days=self._extract_precheck_target_days(precheck_summary),
        )
        await self._save_trip(updated)
        return updated.model_copy(deep=True)

    async def revoke_share_link(self, trip_id: str) -> TripWorkspace:
        current = await self._read_trip(trip_id)
        if current is None:
            raise KeyError(f"trip {trip_id} not found")

        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "updated_at": datetime.now(timezone.utc),
                "share_enabled": False,
            },
            deep=True,
        )
        updated = self._append_workspace_event(
            updated,
            kind="share_revoked",
            title="已撤销分享链接",
            summary="旧分享链接将不再可访问，你仍可在工作区内继续编辑。",
        )
        await self._save_trip(updated)
        return updated.model_copy(deep=True)

    async def regenerate_share_link(self, trip_id: str) -> TripWorkspace:
        current = await self._read_trip(trip_id)
        if current is None:
            raise KeyError(f"trip {trip_id} not found")

        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "updated_at": datetime.now(timezone.utc),
                "share_enabled": True,
                "share_token": generate_share_token(),
            },
            deep=True,
        )
        updated = self._append_workspace_event(
            updated,
            kind="share_regenerated",
            title="已生成新的分享链接",
            summary="新的分享链接已生效，旧链接将不可继续访问。",
        )
        await self._save_trip(updated)
        return updated.model_copy(deep=True)

    def _append_workspace_event(
        self,
        workspace: TripWorkspace,
        *,
        kind: str,
        title: str,
        summary: str = "",
        target_days: list[int] | None = None,
    ) -> TripWorkspace:
        event = build_timeline_event(
            now=workspace.updated_at,
            version=workspace.version,
            kind=kind,  # type: ignore[arg-type]
            title=title,
            summary=summary,
            target_days=target_days,
        )
        return workspace.model_copy(
            update={"timeline": append_timeline_event(workspace.timeline, event)},
            deep=True,
        )

    def _build_update_summary(
        self,
        *,
        workspace: TripWorkspace,
        generated: bool,
    ) -> str:
        if generated and workspace.response_snapshot is not None:
            return (
                f"{workspace.request_brief.destination} {workspace.request_brief.days} 天行程快照已刷新，"
                f"当前共有 {len(workspace.reservations)} 条预约锚点。"
            )
        return (
            f"已同步备注、锁定日和预约信息；当前共有 {len(workspace.locked_day_numbers)} 个锁定日，"
            f"{len(workspace.reservations)} 条预约。"
        )

    def _extract_precheck_target_days(self, precheck_summary) -> list[int]:
        return sorted(
            {
                day
                for item in precheck_summary.items
                for day in (item.after_days or item.before_days)
            }
        )

    def _build_trip_summary(self, workspace: TripWorkspace) -> TripSummary:
        title = ""
        if workspace.response_snapshot is not None:
            title = workspace.response_snapshot.plan.title
        if not title:
            title = f"{workspace.request_brief.destination} {workspace.request_brief.days} 天行程"
        return TripSummary(
            id=workspace.id,
            share_token=workspace.share_token,
            share_enabled=workspace.share_enabled,
            status=workspace.status,
            version=workspace.version,
            destination=workspace.request_brief.destination,
            start_date=workspace.request_brief.start_date,
            days=workspace.request_brief.days,
            updated_at=workspace.updated_at,
            created_at=workspace.created_at,
            reservations_count=len(workspace.reservations),
            locked_day_count=len(workspace.locked_day_numbers),
            has_result=workspace.response_snapshot is not None,
            title=title,
        )
