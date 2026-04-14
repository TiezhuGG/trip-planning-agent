from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import Settings
from app.schemas.planning import IntegrationStatus


def read_cached_diagnose_status(
    *,
    force_refresh: bool,
    cache_ttl_seconds: float,
    cached_status: IntegrationStatus | None,
    cached_at: float,
    now: float,
) -> IntegrationStatus | None:
    if (
        not force_refresh
        and cache_ttl_seconds > 0
        and cached_status is not None
        and (now - cached_at) <= cache_ttl_seconds
    ):
        return cached_status.model_copy(deep=True)
    return None


async def build_diagnose_status(
    *,
    settings: Settings,
    has_client: bool,
    force_refresh: bool,
    ensure_tool_catalog_fn: Callable[[bool], Awaitable[list[dict[str, Any]]]],
    resolve_tool_name_fn: Callable[[str, bool], str | None],
    format_connection_error_fn: Callable[[Exception], str],
    tool_circuit_warning_messages_fn: Callable[[], Awaitable[list[str]]],
) -> IntegrationStatus:
    warnings: list[str] = []
    available_tools: list[str] = []
    resolved_tools: dict[str, str] = {}
    missing_tools: list[str] = []
    mcp_connected = False

    if has_client:
        try:
            catalog = await asyncio.wait_for(
                ensure_tool_catalog_fn(force_refresh),
                timeout=settings.amap_mcp_timeout_seconds + 2,
            )
            available_tools = [item.get("name", "") for item in catalog if item.get("name")]
            mcp_connected = True
            resolved_tools = {
                purpose: resolve_tool_name_fn(purpose, False) or ""
                for purpose in ("poi_search", "route_plan", "weather")
            }
            resolved_tools = {key: value for key, value in resolved_tools.items() if value}
            missing_tools = [
                purpose
                for purpose in ("poi_search", "route_plan", "weather")
                if purpose not in resolved_tools
            ]
            if missing_tools:
                warnings.append(
                    f"MCP 已连接，但仍缺少工具映射: {', '.join(missing_tools)}。"
                )
        except Exception as exc:
            warnings.append(format_connection_error_fn(exc))
    else:
        warnings.append("未配置 MCP 启动命令，规划请求会直接失败。")

    if settings.amap_api_key and not settings.amap_security_js_code:
        warnings.append(
            "已配置高德 JS Key，但未配置安全密钥；如果控制台开启了安全校验，前端地图会加载失败。"
        )
    warnings.extend(await tool_circuit_warning_messages_fn())
    warnings = list(dict.fromkeys(item for item in warnings if item))

    return IntegrationStatus(
        mcp_enabled=settings.has_mcp,
        mcp_connected=mcp_connected,
        mcp_command=settings.amap_mcp_command,
        available_tools=available_tools,
        resolved_tools=resolved_tools,
        missing_tools=missing_tools,
        map_rendering_enabled=settings.has_map_rendering,
        map_js_key_configured=bool(settings.amap_api_key),
        security_js_code_configured=bool(settings.amap_security_js_code),
        warnings=warnings,
    )
