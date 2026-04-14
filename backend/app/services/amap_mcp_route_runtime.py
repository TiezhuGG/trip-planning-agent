from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from app.schemas.planning import GeoPoint, POIRecommendation, RouteStep, RouteSummary, ToolCallRecord
from app.services.amap_mcp_route_support import (
    estimate_fallback_transport_cost,
    extract_transport_cost_cny,
    fallback_route,
    format_distance_text,
    format_duration_text,
    haversine_km,
    parse_cny_amount,
    polyline_distance_km,
)
from app.services.amap_mcp_route_webservice import (
    plan_route_via_web_service,
    plan_transit_via_web_service,
    resolve_route_location,
    route_address_candidates,
)
from app.services.mcp_stdio_client import MCPProtocolError

ResolveRouteToolName = Callable[[str, bool | None], str | None]
BuildRouteArguments = Callable[[POIRecommendation, POIRecommendation], dict[str, Any]]
HasCoordinates = Callable[[POIRecommendation], bool]
DeduplicateQueries = Callable[[list[str]], list[str]]
NormalizeCityName = Callable[[str | None], str]
CacheRouteLocation = Callable[[str, str], None]
IsRateLimitText = Callable[[str], bool]
IsRateLimitError = Callable[[Exception], bool]
RetryDelaySeconds = Callable[[int], float]
RouteAddress = Callable[[POIRecommendation], str]
CallToolForPurpose = Callable[[str, dict[str, Any], list[ToolCallRecord], str | None], Awaitable[Any]]
PlanRouteViaWebService = Callable[
    [str, POIRecommendation, POIRecommendation, list[POIRecommendation], list[ToolCallRecord]],
    Awaitable[dict[str, Any]],
]
BuildRouteToolAttempts = Callable[
    [str, POIRecommendation, POIRecommendation],
    list[tuple[str, dict[str, Any]]],
]
CallRouteToolWithRetry = Callable[[str, dict[str, Any], list[ToolCallRecord]], Awaitable[Any]]
CallRouteWebserviceWithRetry = Callable[
    [str, POIRecommendation, POIRecommendation, list[POIRecommendation], list[ToolCallRecord]],
    Awaitable[dict[str, Any]],
]
NormalizeRoute = Callable[
    [Any, int, POIRecommendation, POIRecommendation, list[POIRecommendation], str],
    RouteSummary,
]
RouteModeCandidates = Callable[[str], list[str]]
AdaptiveRetryBudget = Callable[[str, int], Awaitable[int]]
RecordAdaptiveRetryResult = Callable[[str, bool], Awaitable[None]]
ResolveRouteLocation = Callable[[POIRecommendation], Awaitable[str]]
NormalizeCityName = Callable[[str | None], str]
SummarizeToolPayload = Callable[[Any], str]


def build_route_tool_attempts(
    *,
    mode: str,
    origin: POIRecommendation,
    destination: POIRecommendation,
    has_coordinates: HasCoordinates,
    resolve_route_tool_name: ResolveRouteToolName,
    build_route_coordinate_arguments: BuildRouteArguments,
    build_route_arguments: BuildRouteArguments,
) -> list[tuple[str, dict[str, Any]]]:
    attempts: list[tuple[str, dict[str, Any]]] = []
    if has_coordinates(origin) and has_coordinates(destination):
        coordinate_tool = resolve_route_tool_name(mode, True)
        if coordinate_tool:
            attempts.append((coordinate_tool, build_route_coordinate_arguments(origin, destination)))

    if not attempts:
        address_tool = resolve_route_tool_name(mode, False)
        if address_tool:
            attempts.append((address_tool, build_route_arguments(origin, destination)))

    deduped: list[tuple[str, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for tool_name, arguments in attempts:
        key = (tool_name, str(arguments))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((tool_name, arguments))
    return deduped
async def call_route_tool_with_retry(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    trace: list[ToolCallRecord],
    route_retry_attempts: int,
    adaptive_retry_budget: AdaptiveRetryBudget,
    call_tool_for_purpose: CallToolForPurpose,
    record_adaptive_retry_result: RecordAdaptiveRetryResult,
    is_rate_limit_error: IsRateLimitError,
    retry_delay_seconds: RetryDelaySeconds,
) -> Any:
    retry_budget = await adaptive_retry_budget("route_tool", route_retry_attempts)
    last_exc: Exception | None = None
    for attempt in range(retry_budget):
        try:
            result = await call_tool_for_purpose(
                "route_plan",
                arguments,
                trace,
                tool_name,
            )
            await record_adaptive_retry_result("route_tool", True)
            return result
        except Exception as exc:
            last_exc = exc
            if attempt >= retry_budget - 1 or not is_rate_limit_error(exc):
                await record_adaptive_retry_result("route_tool", False)
                raise
            await asyncio.sleep(retry_delay_seconds(attempt))
    if last_exc is not None:
        await record_adaptive_retry_result("route_tool", False)
        raise last_exc
    raise MCPProtocolError(f"路线工具调用失败: {tool_name}")


async def call_route_webservice_with_retry(
    *,
    mode: str,
    origin: POIRecommendation,
    destination: POIRecommendation,
    waypoints: list[POIRecommendation],
    trace: list[ToolCallRecord],
    route_retry_attempts: int,
    adaptive_retry_budget: AdaptiveRetryBudget,
    plan_route_via_web_service: PlanRouteViaWebService,
    record_adaptive_retry_result: RecordAdaptiveRetryResult,
    is_rate_limit_error: IsRateLimitError,
    retry_delay_seconds: RetryDelaySeconds,
) -> dict[str, Any]:
    channel = f"route_webservice::{mode}"
    retry_budget = await adaptive_retry_budget(channel, route_retry_attempts)
    last_exc: Exception | None = None
    for attempt in range(retry_budget):
        try:
            result = await plan_route_via_web_service(mode, origin, destination, waypoints, trace)
            await record_adaptive_retry_result(channel, True)
            return result
        except Exception as exc:
            last_exc = exc
            if attempt >= retry_budget - 1 or not is_rate_limit_error(exc):
                await record_adaptive_retry_result(channel, False)
                raise
            await asyncio.sleep(retry_delay_seconds(attempt))
    if last_exc is not None:
        await record_adaptive_retry_result(channel, False)
        raise last_exc
    raise MCPProtocolError(f"高德路线 Web Service 调用失败: {mode}")


async def plan_route(
    *,
    day_number: int,
    origin: POIRecommendation,
    destination: POIRecommendation,
    waypoints: list[POIRecommendation],
    mode: str,
    has_client: bool,
    trace: list[ToolCallRecord],
    route_mode_candidates_fn: RouteModeCandidates,
    build_route_tool_attempts_fn: BuildRouteToolAttempts,
    call_route_tool_with_retry_fn: CallRouteToolWithRetry,
    call_route_webservice_with_retry_fn: CallRouteWebserviceWithRetry,
    normalize_route_fn: NormalizeRoute,
) -> RouteSummary:
    if not has_client:
        raise MCPProtocolError("未配置高德 MCP 客户端，无法执行路线规划。")

    errors: list[str] = []
    for candidate_mode in route_mode_candidates_fn(mode):
        for tool_name, arguments in build_route_tool_attempts_fn(
            candidate_mode,
            origin,
            destination,
        ):
            try:
                raw = await call_route_tool_with_retry_fn(tool_name, arguments, trace)
                return normalize_route_fn(
                    raw,
                    day_number,
                    origin,
                    destination,
                    waypoints,
                    candidate_mode,
                )
            except Exception as exc:
                errors.append(f"{candidate_mode}/{tool_name}: {exc}")

        if candidate_mode in {"transit", "driving", "walking"}:
            try:
                raw = await call_route_webservice_with_retry_fn(
                    candidate_mode,
                    origin,
                    destination,
                    waypoints,
                    trace,
                )
                return normalize_route_fn(
                    raw,
                    day_number,
                    origin,
                    destination,
                    waypoints,
                    candidate_mode,
                )
            except Exception as exc:
                errors.append(f"{candidate_mode}_webservice: {exc}")

    raise MCPProtocolError(f"第 {day_number} 天路线规划失败: {'；'.join(errors[:4])}")
