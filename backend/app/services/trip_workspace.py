from __future__ import annotations

import asyncio
import json
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.schemas.planning import (
    PlanningResponse,
    ReplanRequest,
    TripCreateRequest,
    TripPlanningRequest,
    TripWorkspace,
    TripWorkspacePatchRequest,
)
from app.services.planner import TravelPlannerService


class TripWorkspaceService:
    def __init__(
        self,
        settings: Settings,
        planner_service: TravelPlannerService,
    ) -> None:
        self.settings = settings
        self.planner_service = planner_service
        self._store_path = self._resolve_store_path(settings.planner_trip_store_path)
        self._lock = asyncio.Lock()

    async def create_trip(self, payload: TripCreateRequest) -> TripWorkspace:
        response = payload.response_snapshot
        if response is None and payload.generate_response:
            response = await self._generate_response(
                payload.request_brief,
                include_debug=payload.include_debug,
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
            manual_notes=payload.manual_notes or "",
            locked_day_numbers=self._normalize_day_numbers(
                payload.locked_day_numbers,
                payload.request_brief.days,
            ),
            response_snapshot=response,
        )
        await self._write_trip(workspace)
        return workspace.model_copy(deep=True)

    async def get_trip(self, trip_id: str) -> TripWorkspace:
        workspace = await self._read_trip(trip_id)
        if workspace is None:
            raise KeyError(f"trip {trip_id} not found")
        return workspace

    async def get_trip_by_share_token(self, share_token: str) -> TripWorkspace:
        async with self._lock:
            store = self._load_store_unlocked()
            for workspace in store.values():
                if workspace.share_token == share_token:
                    return workspace.model_copy(deep=True)
        raise KeyError(f"share token {share_token} not found")

    async def update_trip(
        self,
        trip_id: str,
        payload: TripWorkspacePatchRequest,
    ) -> TripWorkspace:
        current = await self._read_trip(trip_id)
        if current is None:
            raise KeyError(f"trip {trip_id} not found")

        request_brief = payload.request_brief or current.request_brief
        response_snapshot = current.response_snapshot
        if payload.request_brief is not None and payload.generate_response:
            response_snapshot = await self._generate_response(
                request_brief,
                include_debug=payload.include_debug,
            )
        elif payload.generate_response and payload.request_brief is None:
            response_snapshot = await self._generate_response(
                request_brief,
                include_debug=payload.include_debug,
            )

        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "updated_at": datetime.now(timezone.utc),
                "status": "ready" if response_snapshot is not None else "draft",
                "request_brief": request_brief,
                "manual_notes": payload.manual_notes if payload.manual_notes is not None else current.manual_notes,
                "locked_day_numbers": self._normalize_day_numbers(
                    payload.locked_day_numbers
                    if payload.locked_day_numbers is not None
                    else current.locked_day_numbers,
                    request_brief.days,
                ),
                "response_snapshot": response_snapshot,
            },
            deep=True,
        )
        await self._write_trip(updated)
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

        fresh_response = await self._generate_response(
            current.request_brief,
            include_debug=payload.include_debug,
        )
        merged_response = self._merge_response_for_replan(
            current=current,
            fresh=fresh_response,
            payload=payload,
        )
        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "updated_at": datetime.now(timezone.utc),
                "response_snapshot": merged_response,
            },
            deep=True,
        )
        await self._write_trip(updated)
        return updated.model_copy(deep=True)

    async def _generate_response(
        self,
        request: TripPlanningRequest,
        *,
        include_debug: bool,
    ) -> PlanningResponse:
        return await self.planner_service.generate(
            request,
            generated_at=datetime.now(timezone.utc),
            include_debug=include_debug,
        )

    def _merge_response_for_replan(
        self,
        *,
        current: TripWorkspace,
        fresh: PlanningResponse,
        payload: ReplanRequest,
    ) -> PlanningResponse:
        request = current.request_brief
        if current.response_snapshot is None:
            raise ValueError("当前工作区没有可用于重规划的已生成结果。")
        target_days = self._resolve_replan_targets(
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
            if payload.preserve_locked_days:
                target_days = valid_days.difference(locked_day_numbers)
            else:
                target_days = valid_days
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
            store = self._load_store_unlocked()
            workspace = store.get(trip_id)
            if workspace is None:
                return None
            return workspace.model_copy(deep=True)

    async def _write_trip(self, workspace: TripWorkspace) -> None:
        async with self._lock:
            store = self._load_store_unlocked()
            store[workspace.id] = workspace.model_copy(deep=True)
            self._save_store_unlocked(store)

    def _load_store_unlocked(self) -> dict[str, TripWorkspace]:
        if not self._store_path.exists():
            return {}
        payload = json.loads(self._store_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        store: dict[str, TripWorkspace] = {}
        for trip_id, item in payload.items():
            store[str(trip_id)] = TripWorkspace.model_validate(item)
        return store

    def _save_store_unlocked(self, store: dict[str, TripWorkspace]) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            trip_id: workspace.model_dump(mode="json")
            for trip_id, workspace in store.items()
        }
        self._store_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _resolve_store_path(self, configured_path: str) -> Path:
        path = Path(configured_path)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[2] / path

    def _normalize_day_numbers(self, day_numbers: list[int], max_days: int) -> list[int]:
        normalized = sorted(
            {
                int(day)
                for day in day_numbers
                if isinstance(day, int) and 1 <= int(day) <= max_days
            }
        )
        return normalized
