from __future__ import annotations

import warnings

import pytest
from fastapi.testclient import TestClient

warnings.filterwarnings(
    "ignore",
    message=r"'asyncio\.iscoroutinefunction' is deprecated and slated for removal in Python 3\.16; use inspect\.iscoroutinefunction\(\) instead",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"'asyncio\.WindowsProactorEventLoopPolicy' is deprecated and slated for removal in Python 3\.16",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"'asyncio\.set_event_loop_policy' is deprecated and slated for removal in Python 3\.16",
    category=DeprecationWarning,
)

from app.api.routes import planning as planning_routes
from app.main import create_app
from app.schemas.planning import (
    PlanningJob,
    PlanningJobSummary,
    PrecheckRefreshRequest,
    ReplanRequest,
    TripSummary,
    TripWorkspace,
    TripWorkspaceVersionListResponse,
    TripWorkspaceVersion,
    TripWorkspaceVersionCreateRequest,
    TripWorkspaceVersionSummary,
    TripWorkspacePatchRequest,
)
from app.services.trip_workspace_calendar import CalendarExportResult


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _workspace_payload(**updates):
    payload = {
        "id": "trip-123",
        "share_token": "share-123",
        "share_enabled": True,
        "status": "ready",
        "version": 2,
        "created_at": "2026-04-15T00:00:00Z",
        "updated_at": "2026-04-15T01:00:00Z",
        "request_brief": {
            "destination": "上海",
            "start_date": "2026-05-01",
            "days": 2,
            "interests": [],
            "must_visit": [],
            "pace": "balanced",
            "budget_level": "comfort",
            "transport_preferences": [],
            "hotel_style": "市中心舒适型",
            "dining_preferences": [],
            "travelers": {"adults": 2, "children": 0, "seniors": 0},
        },
        "manual_notes": "",
        "version_origin_kind": "updated",
        "restored_from_version": None,
        "version_label": "",
        "is_starred": False,
        "is_archived": False,
        "locked_day_numbers": [],
        "reservations": [],
        "timeline": [],
        "response_snapshot": None,
    }
    payload.update(updates)
    return payload


class _FakeTripWorkspaceService:
    def __init__(
        self,
        result: CalendarExportResult | None = None,
        workspace: TripWorkspace | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.workspace = workspace
        self.error = error
        self.export_scopes: list[str] = []
        self.versions: list[TripWorkspaceVersionSummary] = []
        self.version_snapshot: TripWorkspaceVersion | None = None

    async def export_trip_calendar(self, trip_id: str, *, scope: str = "full") -> CalendarExportResult:
        assert trip_id
        self.export_scopes.append(scope)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result

    async def refresh_precheck(self, trip_id: str, payload: PrecheckRefreshRequest) -> TripWorkspace:
        assert trip_id
        assert isinstance(payload, PrecheckRefreshRequest)
        if self.error is not None:
            raise self.error
        assert self.workspace is not None
        return self.workspace

    async def revoke_share_link(self, trip_id: str) -> TripWorkspace:
        assert trip_id
        if self.error is not None:
            raise self.error
        assert self.workspace is not None
        return self.workspace

    async def regenerate_share_link(self, trip_id: str) -> TripWorkspace:
        assert trip_id
        if self.error is not None:
            raise self.error
        assert self.workspace is not None
        return self.workspace

    async def list_recent_trips(self, limit: int = 10) -> list[TripSummary]:
        assert limit >= 1
        if self.error is not None:
            raise self.error
        return [
            TripSummary(
                id="trip-123",
                share_token="share-123",
                share_enabled=True,
                status="ready",
                version=2,
                destination="上海",
                start_date="2026-05-01",
                days=2,
                updated_at="2026-04-15T01:00:00Z",
                created_at="2026-04-15T00:00:00Z",
                reservations_count=1,
                locked_day_count=1,
                has_result=True,
                title="上海 2 天行程",
            )
        ]

    async def list_trip_versions(
        self,
        trip_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> TripWorkspaceVersionListResponse:
        assert trip_id
        assert limit >= 1
        assert offset >= 0
        if self.error is not None:
            raise self.error
        items = self.versions[offset : offset + limit]
        return TripWorkspaceVersionListResponse(
            items=items,
            total=len(self.versions),
            has_more=offset + len(items) < len(self.versions),
        )

    async def get_trip_version(self, trip_id: str, version: int) -> TripWorkspaceVersion:
        assert trip_id
        assert version >= 1
        if self.error is not None:
            raise self.error
        assert self.version_snapshot is not None
        return self.version_snapshot

    async def restore_trip_version(self, trip_id: str, version: int) -> TripWorkspace:
        assert trip_id
        assert version >= 1
        if self.error is not None:
            raise self.error
        assert self.workspace is not None
        return self.workspace

    async def create_trip_version_snapshot(
        self,
        trip_id: str,
        payload: TripWorkspaceVersionCreateRequest,
    ) -> TripWorkspace:
        assert trip_id
        assert isinstance(payload, TripWorkspaceVersionCreateRequest)
        if self.error is not None:
            raise self.error
        assert self.workspace is not None
        return self.workspace

    async def delete_trip_version(self, trip_id: str, version: int) -> None:
        assert trip_id
        assert version >= 1
        if self.error is not None:
            raise self.error
        return None

    async def update_trip_version_label(
        self,
        trip_id: str,
        version: int,
        version_label: str,
    ) -> TripWorkspace:
        assert trip_id
        assert version >= 1
        assert isinstance(version_label, str)
        if self.error is not None:
            raise self.error
        assert self.workspace is not None
        return self.workspace

    async def update_trip_version_meta(
        self,
        trip_id: str,
        version: int,
        *,
        version_label: str,
        is_starred: bool | None,
        is_archived: bool | None,
    ) -> TripWorkspace:
        assert trip_id
        assert version >= 1
        assert isinstance(version_label, str)
        _ = is_starred
        _ = is_archived
        if self.error is not None:
            raise self.error
        assert self.workspace is not None
        return self.workspace


class _FakePlanningJobService:
    def __init__(
        self,
        job: PlanningJob | None = None,
        error: Exception | None = None,
        jobs: list[PlanningJobSummary] | None = None,
    ) -> None:
        self.job = job
        self.error = error
        self.jobs = jobs or []

    async def start_generate_plan_job(self, payload, *, include_debug: bool) -> PlanningJob:
        assert payload is not None
        _ = include_debug
        if self.error is not None:
            raise self.error
        assert self.job is not None
        return self.job

    async def start_update_trip_job(
        self,
        trip_id: str,
        payload: TripWorkspacePatchRequest,
    ) -> PlanningJob:
        assert trip_id
        assert isinstance(payload, TripWorkspacePatchRequest)
        if self.error is not None:
            raise self.error
        assert self.job is not None
        return self.job

    async def start_replan_trip_job(self, trip_id: str, payload: ReplanRequest) -> PlanningJob:
        assert trip_id
        assert isinstance(payload, ReplanRequest)
        if self.error is not None:
            raise self.error
        assert self.job is not None
        return self.job

    async def start_precheck_trip_job(
        self,
        trip_id: str,
        payload: PrecheckRefreshRequest,
    ) -> PlanningJob:
        assert trip_id
        assert isinstance(payload, PrecheckRefreshRequest)
        if self.error is not None:
            raise self.error
        assert self.job is not None
        return self.job

    async def get_job(self, job_id: str) -> PlanningJob:
        assert job_id
        if self.error is not None:
            raise self.error
        assert self.job is not None
        return self.job

    async def list_jobs(
        self,
        *,
        limit: int = 10,
        trip_id: str | None = None,
    ) -> list[PlanningJobSummary]:
        assert limit >= 1
        _ = trip_id
        if self.error is not None:
            raise self.error
        return self.jobs[:limit]


def _make_client(
    monkeypatch,
    workspace_service: _FakeTripWorkspaceService,
    job_service: _FakePlanningJobService | None = None,
) -> TestClient:
    monkeypatch.setattr(planning_routes, "get_trip_workspace_service", lambda: workspace_service)
    monkeypatch.setattr(
        planning_routes,
        "get_planning_job_service",
        lambda: job_service or _FakePlanningJobService(),
    )
    return TestClient(create_app())


def test_export_trip_calendar_route_returns_ics_attachment(monkeypatch) -> None:
    workspace_service = _FakeTripWorkspaceService(
        result=CalendarExportResult(
            filename="trip workspace.ics",
            content="BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
        )
    )
    client = _make_client(
        monkeypatch,
        workspace_service,
    )

    response = client.get("/api/v1/trips/trip-123/export/ics")

    assert response.status_code == 200
    assert response.text.startswith("BEGIN:VCALENDAR")
    assert response.headers["content-type"].startswith("text/calendar")
    assert 'attachment; filename="trip workspace.ics"' in response.headers["content-disposition"]
    assert "filename*=UTF-8''trip%20workspace.ics" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    assert workspace_service.export_scopes == ["full"]


def test_export_trip_calendar_route_forwards_scope(monkeypatch) -> None:
    workspace_service = _FakeTripWorkspaceService(
        result=CalendarExportResult(
            filename="trip workspace-reservations.ics",
            content="BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n",
        )
    )
    client = _make_client(monkeypatch, workspace_service)

    response = client.get("/api/v1/trips/trip-123/export/ics?scope=reservations")

    assert response.status_code == 200
    assert workspace_service.export_scopes == ["reservations"]


def test_list_recent_trips_route_returns_summaries(monkeypatch) -> None:
    client = _make_client(monkeypatch, _FakeTripWorkspaceService())

    response = client.get("/api/v1/trips?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "trip-123"
    assert payload[0]["title"] == "上海 2 天行程"


def test_list_recent_trips_route_returns_500_for_unexpected_error(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(error=RuntimeError("boom")),
    )

    response = client.get("/api/v1/trips")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "TRIP_LIST_ERROR"


def test_start_generate_plan_job_route_returns_accepted_job(monkeypatch) -> None:
    job = PlanningJob.model_validate(
        {
            "id": "job-123",
            "kind": "generate_plan",
            "status": "queued",
            "created_at": "2026-04-27T00:00:00Z",
            "updated_at": "2026-04-27T00:00:00Z",
            "progress_message": "queued",
        }
    )
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(),
        _FakePlanningJobService(job=job),
    )

    response = client.post(
        "/api/v1/jobs/plans/generate",
        json={
            "destination": "上海",
            "start_date": "2026-05-01",
            "days": 2,
            "interests": [],
            "must_visit": [],
            "pace": "balanced",
            "budget_level": "comfort",
            "transport_preferences": [],
            "hotel_style": "市中心舒适型",
            "dining_preferences": [],
            "travelers": {"adults": 2, "children": 0, "seniors": 0},
            "notes": None,
            "origin": None,
        },
    )

    assert response.status_code == 202
    assert response.json()["id"] == "job-123"
    assert response.json()["kind"] == "generate_plan"


def test_start_replan_trip_job_route_returns_accepted_job(monkeypatch) -> None:
    job = PlanningJob.model_validate(
        {
            "id": "job-234",
            "kind": "replan_trip",
            "status": "queued",
            "created_at": "2026-04-27T00:00:00Z",
            "updated_at": "2026-04-27T00:00:00Z",
            "trip_id": "trip-123",
            "progress_message": "queued",
        }
    )
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(),
        _FakePlanningJobService(job=job),
    )

    response = client.post(
        "/api/v1/jobs/trips/trip-123/replan",
        json={
            "scope": "trip",
            "day_numbers": [],
            "preserve_locked_days": True,
            "repair_mode": "replace",
            "repair_gap": None,
            "reason": None,
            "include_debug": False,
        },
    )

    assert response.status_code == 202
    assert response.json()["kind"] == "replan_trip"


def test_start_update_trip_job_route_returns_accepted_job(monkeypatch) -> None:
    job = PlanningJob.model_validate(
        {
            "id": "job-222",
            "kind": "update_trip",
            "status": "queued",
            "created_at": "2026-04-27T00:00:00Z",
            "updated_at": "2026-04-27T00:00:00Z",
            "trip_id": "trip-123",
            "progress_message": "queued",
        }
    )
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(),
        _FakePlanningJobService(job=job),
    )

    response = client.post(
        "/api/v1/jobs/trips/trip-123/update",
        json={
            "manual_notes": "refresh this trip",
            "locked_day_numbers": [1],
            "reservations": [],
            "generate_response": True,
            "include_debug": False,
        },
    )

    assert response.status_code == 202
    assert response.json()["kind"] == "update_trip"
    assert response.json()["trip_id"] == "trip-123"


def test_start_trip_precheck_job_route_returns_accepted_job(monkeypatch) -> None:
    job = PlanningJob.model_validate(
        {
            "id": "job-345",
            "kind": "precheck_trip",
            "status": "queued",
            "created_at": "2026-04-27T00:00:00Z",
            "updated_at": "2026-04-27T00:00:00Z",
            "trip_id": "trip-123",
            "progress_message": "queued",
        }
    )
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(),
        _FakePlanningJobService(job=job),
    )

    response = client.post("/api/v1/jobs/trips/trip-123/precheck", json={})

    assert response.status_code == 202
    assert response.json()["kind"] == "precheck_trip"


def test_get_planning_job_route_returns_job(monkeypatch) -> None:
    job = PlanningJob.model_validate(
        {
            "id": "job-123",
            "kind": "precheck_trip",
            "status": "running",
            "created_at": "2026-04-27T00:00:00Z",
            "updated_at": "2026-04-27T00:01:00Z",
            "trip_id": "trip-123",
            "progress_message": "running",
        }
    )
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(),
        _FakePlanningJobService(job=job),
    )

    response = client.get("/api/v1/jobs/job-123")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["trip_id"] == "trip-123"


def test_list_planning_jobs_route_returns_recent_jobs(monkeypatch) -> None:
    jobs = [
        PlanningJobSummary.model_validate(
            {
                "id": "job-789",
                "kind": "precheck_trip",
                "status": "succeeded",
                "created_at": "2026-04-27T00:00:00Z",
                "updated_at": "2026-04-27T00:02:00Z",
                "trip_id": "trip-123",
                "progress_message": "done",
            }
        )
    ]
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(),
        _FakePlanningJobService(jobs=jobs),
    )

    response = client.get("/api/v1/jobs?limit=5&trip_id=trip-123")

    assert response.status_code == 200
    assert response.json()[0]["id"] == "job-789"
    assert response.json()[0]["trip_id"] == "trip-123"


def test_get_planning_job_route_returns_404_when_missing(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(),
        _FakePlanningJobService(error=KeyError("job missing")),
    )

    response = client.get("/api/v1/jobs/missing")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "JOB_NOT_FOUND"


def test_export_trip_calendar_route_returns_404_for_missing_trip(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(error=KeyError("trip missing not found")),
    )

    response = client.get("/api/v1/trips/missing/export/ics")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TRIP_NOT_FOUND"


def test_export_trip_calendar_route_returns_422_for_validation_error(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(error=ValueError("invalid calendar payload")),
    )

    response = client.get("/api/v1/trips/trip-123/export/ics")

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "TRIP_EXPORT_VALIDATION_ERROR",
        "message": "invalid calendar payload",
    }


def test_export_trip_calendar_route_returns_500_for_unexpected_error(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(error=RuntimeError("boom")),
    )

    response = client.get("/api/v1/trips/trip-123/export/ics")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "TRIP_EXPORT_ERROR"


def test_refresh_trip_precheck_route_returns_workspace(monkeypatch) -> None:
    workspace = TripWorkspace.model_validate(_workspace_payload())
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(workspace=workspace),
    )

    response = client.post("/api/v1/trips/trip-123/precheck", json={})

    assert response.status_code == 200
    assert response.json()["id"] == "trip-123"
    assert response.json()["version"] == 2


def test_refresh_trip_precheck_route_returns_404_for_missing_trip(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(error=KeyError("trip missing not found")),
    )

    response = client.post("/api/v1/trips/missing/precheck", json={})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TRIP_NOT_FOUND"


def test_refresh_trip_precheck_route_returns_422_for_validation_error(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(error=ValueError("precheck unavailable")),
    )

    response = client.post("/api/v1/trips/trip-123/precheck", json={})

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "TRIP_PRECHECK_VALIDATION_ERROR",
        "message": "precheck unavailable",
    }


def test_revoke_trip_share_route_returns_workspace(monkeypatch) -> None:
    workspace = TripWorkspace.model_validate(
        _workspace_payload(share_enabled=False, version=3)
    )
    client = _make_client(monkeypatch, _FakeTripWorkspaceService(workspace=workspace))

    response = client.post("/api/v1/trips/trip-123/share/revoke")

    assert response.status_code == 200
    assert response.json()["share_enabled"] is False
    assert response.json()["version"] == 3


def test_regenerate_trip_share_route_returns_workspace(monkeypatch) -> None:
    workspace = TripWorkspace.model_validate(
        _workspace_payload(share_token="share-456", version=4)
    )
    client = _make_client(monkeypatch, _FakeTripWorkspaceService(workspace=workspace))

    response = client.post("/api/v1/trips/trip-123/share/regenerate")

    assert response.status_code == 200
    assert response.json()["share_enabled"] is True
    assert response.json()["share_token"] == "share-456"


def test_list_trip_versions_route_returns_versions(monkeypatch) -> None:
    workspace_service = _FakeTripWorkspaceService()
    workspace_service.versions = [
        TripWorkspaceVersionSummary(
            trip_id="trip-123",
            version=3,
            status="ready",
            updated_at="2026-04-15T02:00:00Z",
            created_at="2026-04-15T00:00:00Z",
            has_result=True,
            title="v3",
            version_label="收藏版",
            is_starred=True,
            is_archived=False,
            is_current=True,
            version_origin_kind="restored",
            restored_from_version=1,
        ),
        TripWorkspaceVersionSummary(
            trip_id="trip-123",
            version=2,
            status="ready",
            updated_at="2026-04-15T01:00:00Z",
            created_at="2026-04-15T00:00:00Z",
            has_result=True,
            title="v2",
            version_label="",
            is_starred=False,
            is_archived=False,
            is_current=False,
            version_origin_kind="updated",
            restored_from_version=None,
        ),
    ]
    client = _make_client(monkeypatch, workspace_service)

    response = client.get("/api/v1/trips/trip-123/versions?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["has_more"] is False
    assert len(payload["items"]) == 2
    assert payload["items"][0]["version"] == 3
    assert payload["items"][0]["is_current"] is True
    assert payload["items"][0]["version_origin_kind"] == "restored"
    assert payload["items"][0]["version_label"] == "收藏版"
    assert payload["items"][0]["is_starred"] is True
    assert payload["items"][0]["restored_from_version"] == 1


def test_list_trip_versions_route_supports_offset(monkeypatch) -> None:
    workspace_service = _FakeTripWorkspaceService()
    workspace_service.versions = [
        TripWorkspaceVersionSummary(
            trip_id="trip-123",
            version=4,
            status="ready",
            updated_at="2026-04-15T03:00:00Z",
            created_at="2026-04-15T00:00:00Z",
            has_result=True,
            title="v4",
            version_label="",
            is_starred=False,
            is_archived=False,
            is_current=True,
            version_origin_kind="updated",
            restored_from_version=None,
        ),
        TripWorkspaceVersionSummary(
            trip_id="trip-123",
            version=3,
            status="ready",
            updated_at="2026-04-15T02:00:00Z",
            created_at="2026-04-15T00:00:00Z",
            has_result=True,
            title="v3",
            version_label="",
            is_starred=False,
            is_archived=False,
            is_current=False,
            version_origin_kind="updated",
            restored_from_version=None,
        ),
        TripWorkspaceVersionSummary(
            trip_id="trip-123",
            version=2,
            status="ready",
            updated_at="2026-04-15T01:00:00Z",
            created_at="2026-04-15T00:00:00Z",
            has_result=True,
            title="v2",
            version_label="",
            is_starred=False,
            is_archived=False,
            is_current=False,
            version_origin_kind="updated",
            restored_from_version=None,
        ),
    ]
    client = _make_client(monkeypatch, workspace_service)

    response = client.get("/api/v1/trips/trip-123/versions?limit=1&offset=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["has_more"] is True
    assert len(payload["items"]) == 1
    assert payload["items"][0]["version"] == 3


def test_get_trip_version_route_returns_snapshot(monkeypatch) -> None:
    workspace_service = _FakeTripWorkspaceService()
    workspace_service.version_snapshot = TripWorkspaceVersion(
        trip_id="trip-123",
        version=2,
        captured_at="2026-04-15T01:00:00Z",
        is_current=False,
        workspace=TripWorkspace.model_validate(
            _workspace_payload(version=2, restored_from_version=1)
        ),
    )
    client = _make_client(monkeypatch, workspace_service)

    response = client.get("/api/v1/trips/trip-123/versions/2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trip_id"] == "trip-123"
    assert payload["version"] == 2
    assert payload["workspace"]["id"] == "trip-123"
    assert payload["workspace"]["version_origin_kind"] == "updated"
    assert payload["workspace"]["restored_from_version"] == 1


def test_restore_trip_version_route_returns_restored_workspace(monkeypatch) -> None:
    workspace = TripWorkspace.model_validate(
        _workspace_payload(version=4, restored_from_version=2)
    )
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(workspace=workspace),
    )

    response = client.post("/api/v1/trips/trip-123/versions/2/restore")

    assert response.status_code == 200
    assert response.json()["id"] == "trip-123"
    assert response.json()["version"] == 4
    assert response.json()["version_origin_kind"] == "updated"
    assert response.json()["restored_from_version"] == 2


def test_create_trip_version_snapshot_route_returns_workspace(monkeypatch) -> None:
    workspace = TripWorkspace.model_validate(
        _workspace_payload(version=5, version_label="手动快照", version_origin_kind="snapshot")
    )
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(workspace=workspace),
    )

    response = client.post(
        "/api/v1/trips/trip-123/versions",
        json={"version_label": "手动快照"},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 5
    assert response.json()["version_label"] == "手动快照"
    assert response.json()["version_origin_kind"] == "snapshot"


def test_delete_trip_version_route_returns_204(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(),
    )

    response = client.delete("/api/v1/trips/trip-123/versions/3")

    assert response.status_code == 204


def test_delete_trip_version_route_returns_422_for_validation_error(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(error=ValueError("仅支持删除手动保存的版本快照。")),
    )

    response = client.delete("/api/v1/trips/trip-123/versions/3")

    assert response.status_code == 422
    assert response.json()["detail"] == {
      "code": "TRIP_VERSION_DELETE_VALIDATION_ERROR",
      "message": "仅支持删除手动保存的版本快照。",
    }


def test_update_trip_version_label_route_returns_workspace(monkeypatch) -> None:
    workspace = TripWorkspace.model_validate(
        _workspace_payload(version=4, version_label="已标记版本", is_starred=True)
    )
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(workspace=workspace),
    )

    response = client.patch(
        "/api/v1/trips/trip-123/versions/4/label",
        json={"version_label": "已标记版本"},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 4
    assert response.json()["version_label"] == "已标记版本"


def test_update_trip_version_meta_route_returns_workspace(monkeypatch) -> None:
    workspace = TripWorkspace.model_validate(
        _workspace_payload(version=4, version_label="收藏版", is_starred=True, is_archived=True)
    )
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(workspace=workspace),
    )

    response = client.patch(
        "/api/v1/trips/trip-123/versions/4/meta",
        json={"version_label": "收藏版", "is_starred": True, "is_archived": True},
    )

    assert response.status_code == 200
    assert response.json()["version"] == 4
    assert response.json()["is_starred"] is True
    assert response.json()["is_archived"] is True


def test_get_trip_version_route_returns_404_when_missing(monkeypatch) -> None:
    client = _make_client(
        monkeypatch,
        _FakeTripWorkspaceService(error=KeyError("trip version missing")),
    )

    response = client.get("/api/v1/trips/trip-123/versions/99")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TRIP_VERSION_NOT_FOUND"
