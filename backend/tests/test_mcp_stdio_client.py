import asyncio

import pytest

from app.services.mcp_stdio_client import MCPProtocolError, MCPStdioClient


def test_connect_reports_missing_command_clearly() -> None:
    client = MCPStdioClient(command="definitely-missing-mcp-command")

    with pytest.raises(MCPProtocolError) as exc_info:
        asyncio.run(client.connect())

    assert "MCP 启动命令不存在" in str(exc_info.value)
    assert "definitely-missing-mcp-command" in str(exc_info.value)
