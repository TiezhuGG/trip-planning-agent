from __future__ import annotations

from typing import Any

from app.services.mcp_stdio_client import MCPProtocolError
from app.utils.json_extract import extract_json_payload


def format_connection_error(
    *,
    exc: Exception,
    client,
    command: str,
) -> str:
    detail = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
    if client is None:
        return f"MCP 连接失败: {detail}"

    snapshot = client.get_debug_snapshot()
    resolved_command = snapshot.get("resolved_command") or snapshot.get("command") or command
    stderr_tail = snapshot.get("stderr_tail") or []
    stderr_text = f"；stderr: {' | '.join(stderr_tail)}" if stderr_tail else ""
    return f"MCP 连接失败: {detail}；命令: {resolved_command}{stderr_text}"


def unwrap_tool_result(result: Any) -> Any:
    if isinstance(result, dict) and "content" in result:
        content = result["content"]
        if isinstance(content, list):
            texts: list[str] = []
            structured: list[Any] = []
            for item in content:
                if isinstance(item, dict):
                    if "json" in item:
                        structured.append(item["json"])
                    if item.get("type") == "text" and "text" in item:
                        texts.append(item["text"])
            if structured:
                return structured[0] if len(structured) == 1 else structured
            if texts:
                extracted = extract_json_payload("\n".join(texts))
                return extracted if extracted is not None else {"text": "\n".join(texts)}
        return content
    return result


def raise_on_tool_error(payload: Any, tool_name: str) -> None:
    if not isinstance(payload, dict):
        return
    error = payload.get("error")
    if error:
        raise MCPProtocolError(f"{tool_name} 返回错误: {error}")
    if payload.get("isError"):
        raise MCPProtocolError(f"{tool_name} 调用被标记为 isError")


def summarize_tool_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("pois", "results", "forecasts", "casts", "return"):
            value = payload.get(key)
            if isinstance(value, list):
                return f"(返回 {len(value)} 项)"
        keys = ", ".join(list(payload.keys())[:4])
        return f"(keys: {keys})" if keys else ""
    if isinstance(payload, list):
        return f"(返回 {len(payload)} 项)"
    return ""
