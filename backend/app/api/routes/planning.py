from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response

from app.config import get_settings
from app.schemas.planning import (
    IntegrationStatus,
    PlanningJob,
    PlanningJobSummary,
    PlanningResponse,
    PlanningTelemetry,
    PrecheckRefreshRequest,
    ReplanRequest,
    TripCreateRequest,
    TripPlanningRequest,
    TripSummary,
    TripWorkspace,
    TripWorkspacePatchRequest,
)
from app.services.planner import TravelPlannerService
from app.services.planning_job_store import create_planning_job_store
from app.services.planning_jobs import PlanningJobService
from app.services.trip_workspace import TripWorkspaceService

router = APIRouter(tags=["planning"])


@lru_cache
def get_planner_service() -> TravelPlannerService:
    return TravelPlannerService(get_settings())


@lru_cache
def get_trip_workspace_service() -> TripWorkspaceService:
    return TripWorkspaceService(get_settings(), get_planner_service())


@lru_cache
def get_planning_job_service() -> PlanningJobService:
    return PlanningJobService(
        get_planner_service(),
        get_trip_workspace_service(),
        store=create_planning_job_store(get_settings()),
    )


@router.get("/plans/integrations/status", response_model=IntegrationStatus)
async def get_integration_status(
    refresh: bool = Query(default=False),
) -> IntegrationStatus:
    try:
        return await get_planner_service().diagnose_integrations(refresh=refresh)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTEGRATION_STATUS_ERROR",
                "message": "Failed to load integration status.",
            },
        ) from exc


@router.get("/plans/telemetry", response_model=PlanningTelemetry)
async def get_planning_telemetry() -> PlanningTelemetry:
    try:
        return await get_planner_service().get_telemetry()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PLANNING_TELEMETRY_ERROR",
                "message": "Failed to load planning telemetry.",
            },
        ) from exc


@router.post("/plans/generate", response_model=PlanningResponse)
async def generate_plan(
    payload: TripPlanningRequest,
    debug: bool = Query(default=False),
) -> PlanningResponse:
    try:
        return await get_planner_service().generate(
            payload,
            generated_at=datetime.now(timezone.utc),
            include_debug=debug,
        )
    except Exception as exc:
        raise_generation_error(exc)


@router.post("/jobs/plans/generate", response_model=PlanningJob, status_code=202)
async def start_generate_plan_job(
    payload: TripPlanningRequest,
    debug: bool = Query(default=False),
) -> PlanningJob:
    try:
        return await get_planning_job_service().start_generate_plan_job(
            payload,
            include_debug=debug,
        )
    except Exception as exc:
        raise_generation_error(exc)


@router.post("/trips", response_model=TripWorkspace)
async def create_trip(
    payload: TripCreateRequest,
) -> TripWorkspace:
    try:
        return await get_trip_workspace_service().create_trip(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TRIP_CREATE_VALIDATION_ERROR",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "TRIP_CREATE_ERROR",
                "message": "Failed to create trip workspace.",
            },
        ) from exc


@router.get("/trips", response_model=list[TripSummary])
async def list_recent_trips(
    limit: int = Query(default=10, ge=1, le=50),
) -> list[TripSummary]:
    try:
        return await get_trip_workspace_service().list_recent_trips(limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "TRIP_LIST_ERROR",
                "message": "Failed to load recent trip workspaces.",
            },
        ) from exc


@router.get("/trips/{trip_id}", response_model=TripWorkspace)
async def get_trip(
    trip_id: str,
) -> TripWorkspace:
    try:
        return await get_trip_workspace_service().get_trip(trip_id)
    except KeyError as exc:
        raise_trip_not_found_error(exc)


@router.get("/trips/share/{share_token}", response_model=TripWorkspace)
async def get_trip_by_share_token(
    share_token: str,
) -> TripWorkspace:
    try:
        return await get_trip_workspace_service().get_trip_by_share_token(share_token)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "TRIP_SHARE_NOT_FOUND",
                "message": "Shared trip workspace not found.",
            },
        ) from exc


@router.patch("/trips/{trip_id}", response_model=TripWorkspace)
async def update_trip(
    trip_id: str,
    payload: TripWorkspacePatchRequest,
) -> TripWorkspace:
    try:
        return await get_trip_workspace_service().update_trip(trip_id, payload)
    except KeyError as exc:
        raise_trip_not_found_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TRIP_UPDATE_VALIDATION_ERROR",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise_generation_error(exc)


@router.post("/jobs/trips/{trip_id}/update", response_model=PlanningJob, status_code=202)
async def start_update_trip_job(
    trip_id: str,
    payload: TripWorkspacePatchRequest,
) -> PlanningJob:
    try:
        return await get_planning_job_service().start_update_trip_job(trip_id, payload)
    except KeyError as exc:
        raise_trip_not_found_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TRIP_UPDATE_VALIDATION_ERROR",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise_generation_error(exc)


@router.post("/trips/{trip_id}/replan", response_model=TripWorkspace)
async def replan_trip(
    trip_id: str,
    payload: ReplanRequest,
) -> TripWorkspace:
    try:
        return await get_trip_workspace_service().replan_trip(trip_id, payload)
    except KeyError as exc:
        raise_trip_not_found_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TRIP_REPLAN_VALIDATION_ERROR",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise_generation_error(exc)


@router.post("/jobs/trips/{trip_id}/replan", response_model=PlanningJob, status_code=202)
async def start_replan_trip_job(
    trip_id: str,
    payload: ReplanRequest,
) -> PlanningJob:
    try:
        return await get_planning_job_service().start_replan_trip_job(trip_id, payload)
    except KeyError as exc:
        raise_trip_not_found_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TRIP_REPLAN_VALIDATION_ERROR",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise_generation_error(exc)


@router.post("/trips/{trip_id}/precheck", response_model=TripWorkspace)
async def refresh_trip_precheck(
    trip_id: str,
    payload: PrecheckRefreshRequest,
) -> TripWorkspace:
    try:
        return await get_trip_workspace_service().refresh_precheck(trip_id, payload)
    except KeyError as exc:
        raise_trip_not_found_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TRIP_PRECHECK_VALIDATION_ERROR",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise_generation_error(exc)


@router.post("/jobs/trips/{trip_id}/precheck", response_model=PlanningJob, status_code=202)
async def start_trip_precheck_job(
    trip_id: str,
    payload: PrecheckRefreshRequest,
) -> PlanningJob:
    try:
        return await get_planning_job_service().start_precheck_trip_job(trip_id, payload)
    except KeyError as exc:
        raise_trip_not_found_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TRIP_PRECHECK_VALIDATION_ERROR",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise_generation_error(exc)


@router.get("/jobs", response_model=list[PlanningJobSummary])
async def list_planning_jobs(
    limit: int = Query(default=10, ge=1, le=50),
    trip_id: str | None = Query(default=None),
) -> list[PlanningJobSummary]:
    try:
        return await get_planning_job_service().list_jobs(limit=limit, trip_id=trip_id)
    except Exception as exc:
        raise_generation_error(exc)


@router.get("/jobs/{job_id}", response_model=PlanningJob)
async def get_planning_job(
    job_id: str,
) -> PlanningJob:
    try:
        return await get_planning_job_service().get_job(job_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": "Planning job not found.",
            },
        ) from exc
    except Exception as exc:
        raise_generation_error(exc)


@router.post("/trips/{trip_id}/share/revoke", response_model=TripWorkspace)
async def revoke_trip_share(
    trip_id: str,
) -> TripWorkspace:
    try:
        return await get_trip_workspace_service().revoke_share_link(trip_id)
    except KeyError as exc:
        raise_trip_not_found_error(exc)


@router.post("/trips/{trip_id}/share/regenerate", response_model=TripWorkspace)
async def regenerate_trip_share(
    trip_id: str,
) -> TripWorkspace:
    try:
        return await get_trip_workspace_service().regenerate_share_link(trip_id)
    except KeyError as exc:
        raise_trip_not_found_error(exc)


@router.get("/trips/{trip_id}/export/ics")
async def export_trip_calendar(
    trip_id: str,
    scope: Literal["full", "reservations", "itinerary"] = "full",
) -> Response:
    try:
        result = await get_trip_workspace_service().export_trip_calendar(trip_id, scope=scope)
        return Response(
            content=result.content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{result.filename}"; '
                    f"filename*=UTF-8''{quote(result.filename)}"
                ),
                "Cache-Control": "no-store",
            },
        )
    except KeyError as exc:
        raise_trip_not_found_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "TRIP_EXPORT_VALIDATION_ERROR",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "TRIP_EXPORT_ERROR",
                "message": "Failed to export calendar.",
            },
        ) from exc


def raise_trip_not_found_error(exc: KeyError) -> None:
    raise HTTPException(
        status_code=404,
        detail={
            "code": "TRIP_NOT_FOUND",
            "message": "Trip workspace not found.",
        },
    ) from exc


def raise_generation_error(exc: Exception) -> None:
    code, message, status_code = _classify_generation_error(exc)
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    ) from exc


def _classify_generation_error(exc: Exception) -> tuple[str, str, int]:
    raw_message = f"{exc.__class__.__name__}: {exc}"
    message = raw_message.lower()
    validation_markers = (
        "validationerror",
        "tripplanningrequest",
        "field required",
        "only supports chinese city names",
        "destination",
        "目的地仅支持中文城市名",
        "中文城市名",
    )

    if any(marker in message for marker in validation_markers):
        return "VALIDATION_ERROR", "Request validation failed.", 422
    if "429" in message or "ratelimit" in message or "setlimitexceeded" in message:
        return "LLM_RATE_LIMIT", "Planner service is rate limited.", 503

    mcp_related_markers = (
        "mcpprotocolerror",
        "missing tools",
        "web service key",
        "amap_maps_api_key",
        "工具映射不完整",
        "工具映射异常",
        "缺少工具映射",
    )
    if any(marker in message for marker in mcp_related_markers):
        return _classify_mcp_error(message)
    if "timeout" in message or "connect" in message or "network" in message:
        return "NETWORK_ERROR", "Network or upstream service error.", 503
    return "INTERNAL_ERROR", "Plan generation failed.", 500


def _classify_mcp_error(message: str) -> tuple[str, str, int]:
    startup_markers = (
        "mcp command is empty",
        "filenotfounderror",
        "notimplementederror",
        "windows selector",
    )
    mapping_markers = (
        "missing tools",
        "tool mapping",
        "工具映射不完整",
        "工具映射异常",
        "缺少工具映射",
    )
    key_markers = (
        "web service key",
        "amap_maps_api_key",
    )
    timeout_markers = (
        "timeout",
        "timed out",
        "connect",
        "connection",
        "network",
    )
    rate_limit_markers = (
        "cuqps_has_exceeded_the_limit",
        "rate limit",
        "too many requests",
        "429",
    )

    if any(marker in message for marker in startup_markers):
        return "MCP_STARTUP_ERROR", "Map service startup failed.", 503
    if any(marker in message for marker in mapping_markers):
        return "MCP_TOOL_MAPPING_ERROR", "Map service tool mapping is incomplete.", 503
    if any(marker in message for marker in key_markers):
        return "AMAP_KEY_MISSING", "Map service key is missing.", 503
    if any(marker in message for marker in rate_limit_markers):
        return "MCP_RATE_LIMIT", "Map service is rate limited.", 503
    if any(marker in message for marker in timeout_markers):
        return "MCP_TIMEOUT", "Map service request timed out.", 503
    return "MCP_PROTOCOL_ERROR", "Map service communication failed.", 503
