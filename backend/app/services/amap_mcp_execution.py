from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from app.schemas.planning import ToolCallRecord
from app.services.mcp_stdio_client import MCPProtocolError

CatalogLoader = Callable[[], Awaitable[list[dict[str, Any]]]]
CatalogGetter = Callable[[], list[dict[str, Any]]]
ToolNameResolver = Callable[[str], str | None]
CircuitKeyBuilder = Callable[[str, str], str]
BeforeToolCall = Callable[[str, str, str], Awaitable[None]]
AfterToolCallSuccess = Callable[[str, float], Awaitable[None]]
AfterToolCallFailure = Callable[[str, BaseException, float], Awaitable[None]]
UnwrapToolResult = Callable[[Any], Any]
RaiseOnToolError = Callable[[Any, str], None]
SummarizeToolPayload = Callable[[Any], str]


async def call_tool_for_purpose(
    *,
    client: Any,
    purpose: str,
    arguments: dict[str, Any],
    trace: list[ToolCallRecord],
    timeout_seconds: float,
    ensure_tool_catalog: CatalogLoader,
    get_tool_catalog: CatalogGetter,
    resolve_tool_name: ToolNameResolver,
    tool_circuit_key: CircuitKeyBuilder,
    before_tool_call: BeforeToolCall,
    after_tool_call_success: AfterToolCallSuccess,
    after_tool_call_failure: AfterToolCallFailure,
    unwrap_tool_result: UnwrapToolResult,
    raise_on_tool_error: RaiseOnToolError,
    summarize_tool_payload: SummarizeToolPayload,
    tool_name_override: str | None = None,
) -> Any:
    await asyncio.wait_for(
        ensure_tool_catalog(),
        timeout=timeout_seconds + 2,
    )
    tool_name = tool_name_override or resolve_tool_name(purpose)
    if not tool_name:
        available = [item.get("name", "") for item in get_tool_catalog() if item.get("name")]
        raise MCPProtocolError(
            f"未找到可用于 {purpose} 的 MCP 工具；当前可用工具: {', '.join(available) if available else '无'}"
        )

    circuit_key = tool_circuit_key(purpose, tool_name)
    started_at = time.monotonic()
    call_attempted = False
    try:
        await before_tool_call(circuit_key, purpose, tool_name)
        call_attempted = True
        result = await asyncio.wait_for(
            client.call_tool(tool_name, arguments),
            timeout=timeout_seconds + 2,
        )
        normalized = unwrap_tool_result(result)
        raise_on_tool_error(normalized, tool_name)
        await after_tool_call_success(
            circuit_key,
            elapsed_seconds=max(0.0, time.monotonic() - started_at),
        )
        trace.append(
            ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments,
                success=True,
                summary=f"工具调用成功 ({purpose}) {summarize_tool_payload(normalized)}",
            )
        )
        return normalized
    except MCPProtocolError as exc:
        if call_attempted:
            await after_tool_call_failure(
                circuit_key,
                exc,
                elapsed_seconds=max(0.0, time.monotonic() - started_at),
            )
        trace.append(
            ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments,
                success=False,
                summary=f"工具调用失败 ({purpose}): {exc}",
            )
        )
        raise
    except Exception as exc:
        if call_attempted:
            await after_tool_call_failure(
                circuit_key,
                exc,
                elapsed_seconds=max(0.0, time.monotonic() - started_at),
            )
        trace.append(
            ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments,
                success=False,
                summary=f"工具调用异常 ({purpose}): {exc}",
            )
        )
        raise
    except asyncio.CancelledError as exc:
        if call_attempted:
            await after_tool_call_failure(
                circuit_key,
                exc,
                elapsed_seconds=max(0.0, time.monotonic() - started_at),
            )
        raise
