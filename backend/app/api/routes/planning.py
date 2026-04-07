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
    mcp_related_markers = (
        "mcpprotocolerror",
        "mcp 工具映射不完整",
        "missing tools",
        "高德 web service key",
        "amap_maps_api_key",
    )
    if any(marker in message for marker in mcp_related_markers):
        return _classify_mcp_error(message)
    if "timeout" in message or "connect" in message or "network" in message:
        return "NETWORK_ERROR", "当前网络或外部服务连接异常，请稍后重试。", 503
    return "INTERNAL_ERROR", "生成旅行计划失败，请稍后重试。", 500


def _classify_mcp_error(message: str) -> tuple[str, str, int]:
    startup_markers = (
        "mcp command is empty",
        "mcp 启动命令不存在",
        "系统找不到指定的文件",
        "filenotfounderror",
        "notimplementederror",
        "windows selector",
    )
    mapping_markers = (
        "工具映射不完整",
        "缺少工具映射",
        "missing tools",
    )
    key_markers = (
        "未配置高德 web service key",
        "缺少高德 web service key",
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
        return "MCP_STARTUP_ERROR", "地图服务进程启动失败，请检查 MCP 启动命令与运行环境。", 503
    if any(marker in message for marker in mapping_markers):
        return "MCP_TOOL_MAPPING_ERROR", "地图服务工具映射不完整，请检查 MCP 工具配置。", 503
    if any(marker in message for marker in key_markers):
        return "AMAP_KEY_MISSING", "地图服务密钥未正确配置，请检查 AMAP_MAPS_API_KEY。", 503
    if any(marker in message for marker in rate_limit_markers):
        return "MCP_RATE_LIMIT", "地图服务当前限流，暂时无法生成稳定行程。", 503
    if any(marker in message for marker in timeout_markers):
        return "MCP_TIMEOUT", "地图服务连接超时，请稍后重试。", 503
    return "MCP_PROTOCOL_ERROR", "地图服务连接异常，暂时无法生成稳定行程。", 503
