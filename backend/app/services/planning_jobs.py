from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from app.config import Settings
from app.schemas.planning import (
    PlanningJob,
    PlanningJobSummary,
    PrecheckRefreshRequest,
    ReplanRequest,
    TripPlanningRequest,
    TripWorkspacePatchRequest,
)
from app.services.planning_job_store import PlanningJobStore, create_planning_job_store
from app.services.planner import TravelPlannerService
from app.services.trip_workspace import TripWorkspaceService


JobRunner = Callable[[], Awaitable[dict[str, object]]]


class PlanningJobService:
    def __init__(
        self,
        planner_service: TravelPlannerService,
        trip_workspace_service: TripWorkspaceService,
        *,
        settings: Settings | None = None,
        store: PlanningJobStore | None = None,
        max_jobs: int = 100,
    ) -> None:
        self.planner_service = planner_service
        self.trip_workspace_service = trip_workspace_service
        self.max_jobs = max(10, int(max_jobs))
        self.store = store or (create_planning_job_store(settings) if settings is not None else None)
        self._jobs: dict[str, PlanningJob] = {}
        self._lock = asyncio.Lock()
        self._restore_jobs()

    async def start_generate_plan_job(
        self,
        payload: TripPlanningRequest,
        *,
        include_debug: bool,
    ) -> PlanningJob:
        return await self._start_job(
            kind="generate_plan",
            progress_message="Planning job queued.",
            running_message="Planning in progress.",
            runner=lambda: self._run_generate_plan(payload, include_debug=include_debug),
        )

    async def start_update_trip_job(
        self,
        trip_id: str,
        payload: TripWorkspacePatchRequest,
    ) -> PlanningJob:
        await self.trip_workspace_service.get_trip(trip_id)
        return await self._start_job(
            kind="update_trip",
            trip_id=trip_id,
            progress_message="Workspace refresh job queued.",
            running_message="Workspace refresh in progress.",
            runner=lambda: self._run_update_trip(trip_id, payload),
        )

    async def start_replan_trip_job(
        self,
        trip_id: str,
        payload: ReplanRequest,
    ) -> PlanningJob:
        await self.trip_workspace_service.get_trip(trip_id)
        return await self._start_job(
            kind="replan_trip",
            trip_id=trip_id,
            progress_message="Replan job queued.",
            running_message="Replan in progress.",
            runner=lambda: self._run_replan_trip(trip_id, payload),
        )

    async def start_precheck_trip_job(
        self,
        trip_id: str,
        payload: PrecheckRefreshRequest,
    ) -> PlanningJob:
        await self.trip_workspace_service.get_trip(trip_id)
        return await self._start_job(
            kind="precheck_trip",
            trip_id=trip_id,
            progress_message="Precheck job queued.",
            running_message="Precheck in progress.",
            runner=lambda: self._run_precheck_trip(trip_id, payload),
        )

    async def get_job(self, job_id: str) -> PlanningJob:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"job {job_id} not found")
            return job.model_copy(deep=True)

    async def list_jobs(
        self,
        *,
        limit: int = 10,
        trip_id: str | None = None,
    ) -> list[PlanningJobSummary]:
        normalized_limit = max(1, min(int(limit), 50))
        async with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda item: item.updated_at,
                reverse=True,
            )
            if trip_id:
                jobs = [item for item in jobs if item.trip_id == trip_id]
            return [
                self._to_job_summary(item)
                for item in jobs[:normalized_limit]
            ]

    async def _start_job(
        self,
        *,
        kind: PlanningJob["kind"],
        progress_message: str,
        running_message: str,
        runner: JobRunner,
        trip_id: str | None = None,
    ) -> PlanningJob:
        now = datetime.now(timezone.utc)
        job = PlanningJob(
            id=uuid.uuid4().hex,
            kind=kind,
            status="queued",
            created_at=now,
            updated_at=now,
            trip_id=trip_id,
            progress_message=progress_message,
        )
        async with self._lock:
            self._jobs[job.id] = job
            self._save_job_locked(job)
            self._trim_jobs_locked()
        asyncio.create_task(self._execute_job(job.id, runner, running_message=running_message))
        return job.model_copy(deep=True)

    async def _execute_job(
        self,
        job_id: str,
        runner: JobRunner,
        *,
        running_message: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        await self._update_job(
            job_id,
            status="running",
            started_at=now,
            updated_at=now,
            progress_message=running_message,
        )
        try:
            result = await runner()
        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            await self._update_job(
                job_id,
                status="failed",
                completed_at=completed_at,
                updated_at=completed_at,
                error_code=exc.__class__.__name__.upper(),
                error_message=str(exc) or "Job failed",
                progress_message="Job failed.",
            )
            return

        completed_at = datetime.now(timezone.utc)
        await self._update_job(
            job_id,
            status="succeeded",
            completed_at=completed_at,
            updated_at=completed_at,
            progress_message=str(result.get("progress_message") or "Job completed."),
            planning_response=result.get("planning_response"),
            trip_workspace=result.get("trip_workspace"),
            error_code="",
            error_message="",
        )

    async def _run_generate_plan(
        self,
        payload: TripPlanningRequest,
        *,
        include_debug: bool,
    ) -> dict[str, object]:
        response = await self.planner_service.generate(
            payload,
            generated_at=datetime.now(timezone.utc),
            include_debug=include_debug,
        )
        return {
            "progress_message": "Planning completed.",
            "planning_response": response,
        }

    async def _run_update_trip(
        self,
        trip_id: str,
        payload: TripWorkspacePatchRequest,
    ) -> dict[str, object]:
        workspace = await self.trip_workspace_service.update_trip(trip_id, payload)
        return {
            "progress_message": "Workspace refresh completed.",
            "trip_workspace": workspace,
        }

    async def _run_replan_trip(
        self,
        trip_id: str,
        payload: ReplanRequest,
    ) -> dict[str, object]:
        workspace = await self.trip_workspace_service.replan_trip(trip_id, payload)
        return {
            "progress_message": "Replan completed.",
            "trip_workspace": workspace,
        }

    async def _run_precheck_trip(
        self,
        trip_id: str,
        payload: PrecheckRefreshRequest,
    ) -> dict[str, object]:
        workspace = await self.trip_workspace_service.refresh_precheck(trip_id, payload)
        return {
            "progress_message": "Precheck completed.",
            "trip_workspace": workspace,
        }

    async def _update_job(self, job_id: str, **updates: object) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            updated_job = job.model_copy(update=updates, deep=True)
            self._jobs[job_id] = updated_job
            self._save_job_locked(updated_job)

    def _trim_jobs_locked(self) -> None:
        if len(self._jobs) <= self.max_jobs:
            return
        ordered = sorted(self._jobs.values(), key=lambda item: item.updated_at)
        for item in ordered[: len(self._jobs) - self.max_jobs]:
            self._jobs.pop(item.id, None)
            if self.store is not None:
                self.store.delete(item.id)

    def _to_job_summary(self, job: PlanningJob) -> PlanningJobSummary:
        return PlanningJobSummary.model_validate(
            job.model_dump(
                exclude={
                    "planning_response",
                    "trip_workspace",
                }
            )
        )

    def _restore_jobs(self) -> None:
        if self.store is None:
            return
        restored_jobs = self.store.list_recent(limit=self.max_jobs)
        if not restored_jobs:
            return

        now = datetime.now(timezone.utc)
        recovered_jobs: dict[str, PlanningJob] = {}
        for job in restored_jobs:
            recovered = job
            if job.status in {"queued", "running"}:
                recovered = job.model_copy(
                    update={
                        "status": "failed",
                        "updated_at": now,
                        "completed_at": now,
                        "error_code": "INTERRUPTED",
                        "error_message": "Service restarted before the job completed.",
                        "progress_message": "Job interrupted by service restart.",
                    },
                    deep=True,
                )
                self.store.save(recovered)
            recovered_jobs[recovered.id] = recovered
        self._jobs = recovered_jobs

    def _save_job_locked(self, job: PlanningJob) -> None:
        if self.store is None:
            return
        self.store.save(job)
