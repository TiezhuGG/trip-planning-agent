from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import uuid

from app.schemas.planning import PlanningJob, PrecheckRefreshRequest, ReplanRequest, TripWorkspacePatchRequest
from app.services.planning_jobs import PlanningJobService


class _FakePlannerService:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response if response is not None else {"plan": "ok"}
        self.error = error

    async def generate(self, payload, *, generated_at, include_debug: bool):
        assert payload is not None
        assert generated_at is not None
        _ = include_debug
        if self.error is not None:
            raise self.error
        return self.response


class _FakeTripWorkspaceService:
    def __init__(self, workspace=None, *, delay_event: asyncio.Event | None = None) -> None:
        self.workspace = workspace if workspace is not None else {"id": "trip-123", "status": "ready"}
        self.delay_event = delay_event

    async def get_trip(self, trip_id: str):
        assert trip_id
        return {"id": trip_id}

    async def update_trip(self, trip_id: str, payload: TripWorkspacePatchRequest):
        assert trip_id
        assert isinstance(payload, TripWorkspacePatchRequest)
        if self.delay_event is not None:
            await self.delay_event.wait()
        return self.workspace

    async def replan_trip(self, trip_id: str, payload: ReplanRequest):
        assert trip_id
        assert isinstance(payload, ReplanRequest)
        if self.delay_event is not None:
            await self.delay_event.wait()
        return self.workspace

    async def refresh_precheck(self, trip_id: str, payload: PrecheckRefreshRequest):
        assert trip_id
        assert isinstance(payload, PrecheckRefreshRequest)
        if self.delay_event is not None:
            await self.delay_event.wait()
        return self.workspace


class _FakePlanningJobStore:
    def __init__(self, jobs=None) -> None:
        self.jobs = {
            job.id: job
            for job in (jobs or [])
        }

    def get_by_id(self, job_id: str):
        return self.jobs.get(job_id)

    def list_recent(self, limit: int = 10, trip_id: str | None = None):
        items = list(self.jobs.values())
        if trip_id:
            items = [item for item in items if item.trip_id == trip_id]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[:limit]

    def save(self, job) -> None:
        self.jobs[job.id] = job

    def delete(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)


async def _wait_for_terminal_job(service: PlanningJobService, job_id: str):
    for _ in range(100):
        job = await service.get_job(job_id)
        if job.status in {"succeeded", "failed"}:
            return job
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish in time")


def test_update_trip_job_completes_with_workspace_payload() -> None:
    async def run() -> None:
        workspace = {"id": "trip-123", "status": "ready", "version": 3}
        service = PlanningJobService(
            _FakePlannerService(),
            _FakeTripWorkspaceService(workspace=workspace),
            store=_FakePlanningJobStore(),
        )

        job = await service.start_update_trip_job(
            "trip-123",
            TripWorkspacePatchRequest(generate_response=True),
        )
        completed_job = await _wait_for_terminal_job(service, job.id)

        assert completed_job.status == "succeeded"
        assert completed_job.trip_id == "trip-123"
        assert completed_job.progress_message == "Workspace refresh completed."
        assert completed_job.trip_workspace == workspace

    asyncio.run(run())


def test_generate_plan_job_records_failure_details() -> None:
    async def run() -> None:
        service = PlanningJobService(
            _FakePlannerService(error=RuntimeError("boom")),
            _FakeTripWorkspaceService(),
            store=_FakePlanningJobStore(),
        )

        job = await service.start_generate_plan_job(
            {"destination": "Shanghai"},
            include_debug=False,
        )
        completed_job = await _wait_for_terminal_job(service, job.id)

        assert completed_job.status == "failed"
        assert completed_job.error_code == "RUNTIMEERROR"
        assert completed_job.error_message == "boom"
        assert completed_job.progress_message == "Job failed."

    asyncio.run(run())


def test_replan_job_exposes_running_progress_message() -> None:
    async def run() -> None:
        delay_event = asyncio.Event()
        service = PlanningJobService(
            _FakePlannerService(),
            _FakeTripWorkspaceService(delay_event=delay_event),
            store=_FakePlanningJobStore(),
        )

        job = await service.start_replan_trip_job(
            "trip-123",
            ReplanRequest(scope="trip"),
        )
        await asyncio.sleep(0.01)
        running_job = await service.get_job(job.id)

        assert running_job.status == "running"
        assert running_job.progress_message == "Replan in progress."

        delay_event.set()
        completed_job = await _wait_for_terminal_job(service, job.id)
        assert completed_job.status == "succeeded"
        assert completed_job.progress_message == "Replan completed."

    asyncio.run(run())


def test_job_store_trims_oldest_jobs_when_limit_is_exceeded() -> None:
    async def run() -> None:
        service = PlanningJobService(
            _FakePlannerService(),
            _FakeTripWorkspaceService(),
            store=_FakePlanningJobStore(),
            max_jobs=10,
        )

        created_job_ids: list[str] = []
        for index in range(11):
            job = await service.start_precheck_trip_job(
                f"trip-{index}",
                PrecheckRefreshRequest(),
            )
            created_job_ids.append(job.id)

        for job_id in created_job_ids[1:]:
            await _wait_for_terminal_job(service, job_id)

        assert len(service._jobs) == 10
        assert created_job_ids[0] not in service._jobs
        assert created_job_ids[-1] in service._jobs

    asyncio.run(run())


def test_list_jobs_filters_by_trip_id_and_sorts_latest_first() -> None:
    async def run() -> None:
        delay_event = asyncio.Event()
        service = PlanningJobService(
            _FakePlannerService(),
            _FakeTripWorkspaceService(delay_event=delay_event),
            store=_FakePlanningJobStore(),
        )

        first_job = await service.start_replan_trip_job(
            "trip-a",
            ReplanRequest(scope="trip"),
        )
        second_job = await service.start_precheck_trip_job(
            "trip-b",
            PrecheckRefreshRequest(),
        )
        await asyncio.sleep(0.01)

        filtered_jobs = await service.list_jobs(limit=5, trip_id="trip-b")
        all_jobs = await service.list_jobs(limit=5)

        assert [job.id for job in filtered_jobs] == [second_job.id]
        assert [job.id for job in all_jobs[:2]] == [second_job.id, first_job.id]

        delay_event.set()

    asyncio.run(run())


def test_completed_job_is_persisted_to_store() -> None:
    async def run() -> None:
        store = _FakePlanningJobStore()
        service = PlanningJobService(
            _FakePlannerService(),
            _FakeTripWorkspaceService(),
            store=store,
        )

        job = await service.start_precheck_trip_job(
            "trip-123",
            PrecheckRefreshRequest(),
        )
        await _wait_for_terminal_job(service, job.id)

        persisted = store.get_by_id(job.id)
        assert persisted is not None
        assert persisted.status == "succeeded"
        assert persisted.progress_message == "Precheck completed."

    asyncio.run(run())


def test_restore_marks_inflight_jobs_as_interrupted() -> None:
    async def run() -> None:
        store = _FakePlanningJobStore(
            jobs=[
                PlanningJob(
                    id=uuid.uuid4().hex,
                    kind="precheck_trip",
                    status="running",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    started_at=datetime.now(timezone.utc),
                    trip_id="trip-123",
                    progress_message="Precheck in progress.",
                )
            ]
        )
        existing_job = next(iter(store.jobs.values()))

        service = PlanningJobService(
            _FakePlannerService(),
            _FakeTripWorkspaceService(),
            store=store,
        )

        restored_job = await service.get_job(existing_job.id)
        assert restored_job.status == "failed"
        assert restored_job.error_code == "INTERRUPTED"
        assert restored_job.error_message == "Service restarted before the job completed."
        assert restored_job.progress_message == "Job interrupted by service restart."

    asyncio.run(run())
