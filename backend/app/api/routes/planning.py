from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.schemas.planning import IntegrationStatus, PlanningResponse, TripPlanningRequest
from app.services.planner import TravelPlannerService

router = APIRouter(tags=["planning"])


@lru_cache
def get_planner_service() -> TravelPlannerService:
    return TravelPlannerService(get_settings())


@router.get("/plans/integrations/status", response_model=IntegrationStatus)
async def get_integration_status() -> IntegrationStatus:
    try:
        return await get_planner_service().diagnose_integrations()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTEGRATION_STATUS_ERROR",
                "message": "集成状态检查失败，请稍后重试。",
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
        "目的地仅支持中文城市名",
        "仅支持中文城市名",
    )

    if any(marker.lower() in message for marker in validation_markers):
        return "VALIDATION_ERROR", "请求参数不合法，请检查目的地和出行信息。", 422
    if "destination" in message and "城市名" in raw_message:
        return "VALIDATION_ERROR", "请求参数不合法，请检查目的地和出行信息。", 422
    if "429" in message or "ratelimit" in message or "setlimitexceeded" in message:
        return "LLM_RATE_LIMIT", "大模型服务当前限流，系统暂时无法完成本次规划，请稍后重试。", 503
    if "mcpprotocolerror" in message:
        return "MCP_PROTOCOL_ERROR", "地图服务连接异常，暂时无法生成稳定行程。", 503
    if "timeout" in message or "connect" in message or "network" in message:
        return "NETWORK_ERROR", "当前网络或外部服务连接异常，请稍后重试。", 503
    return "INTERNAL_ERROR", "生成旅行计划失败，请稍后重试。", 500
