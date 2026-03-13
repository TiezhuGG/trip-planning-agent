from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any


class MCPProtocolError(RuntimeError):
    pass


class MCPStdioClient:
    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 20,
        inherit_proxy_env: bool = False,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.timeout_seconds = timeout_seconds
        self.inherit_proxy_env = inherit_proxy_env
        self.resolved_command = command
        self.stderr_tail: list[str] = []

    async def connect(self) -> None:
        self.resolved_command = self._resolve_command()
        if not self.resolved_command:
            raise MCPProtocolError("MCP command is empty.")

        self._load_sdk()

    async def list_tools(self) -> dict[str, Any]:
        await self.connect()
        return await self._run_with_session(self._list_tools_once)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await self.connect()
        return await self._run_with_session(
            lambda session: self._call_tool_once(session, tool_name, arguments)
        )

    async def close(self) -> None:
        return

    def get_debug_snapshot(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "resolved_command": self.resolved_command,
            "args": self.args,
            "stderr_tail": self.stderr_tail[-5:],
        }

    async def _run_with_session(self, operation):
        ClientSession, StdioServerParameters, stdio_client = self._load_sdk()

        if self._is_windows_selector_policy():
            raise MCPProtocolError(
                "当前后端运行在 WindowsSelectorEventLoopPolicy 下，无法使用 stdio MCP 子进程。"
                "这通常是因为使用了 uvicorn --reload。"
                "请改用不带 --reload 的启动方式，或改造成独立的 HTTP/SSE MCP 服务。"
            )

        server_params = StdioServerParameters(
            command=self.resolved_command,
            args=self.args,
            env=self._build_process_env(),
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await operation(session)
        except Exception as exc:
            raise MCPProtocolError(f"MCP SDK 调用失败: {self._format_exception(exc)}") from exc

    async def _list_tools_once(self, session) -> dict[str, Any]:
        response = await session.list_tools()
        tools = getattr(response, "tools", [])
        return {"tools": [self._serialize(tool) for tool in tools]}

    async def _call_tool_once(
        self,
        session,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        response = await session.call_tool(tool_name, arguments)
        return self._serialize(response)

    def _serialize(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._serialize(item) for key, item in value.items()}

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(mode="json")

        dict_method = getattr(value, "dict", None)
        if callable(dict_method):
            return dict_method()

        if hasattr(value, "__dict__"):
            return {
                str(key): self._serialize(item)
                for key, item in vars(value).items()
                if not str(key).startswith("_")
            }

        return str(value)

    def _load_sdk(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as exc:
            raise MCPProtocolError(
                '未安装官方 MCP Python SDK，请在 backend 目录执行: .\\venv\\Scripts\\python.exe -m pip install "mcp>=1,<2"'
            ) from exc

        return ClientSession, StdioServerParameters, stdio_client

    def _is_windows_selector_policy(self) -> bool:
        if os.name != "nt":
            return False

        policy = asyncio.get_event_loop_policy()
        selector_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if selector_cls is None:
            return False
        return isinstance(policy, selector_cls)

    def _resolve_command(self) -> str:
        command = self.command.strip()
        if not command:
            return ""

        command_path = Path(command)
        if command_path.is_absolute() and command_path.exists():
            return str(command_path)

        if command_path.parent != Path(".") and command_path.exists():
            return str(command_path.resolve())

        resolved = shutil.which(command)
        if resolved:
            return resolved

        backend_dir = Path(__file__).resolve().parents[2]
        repo_dir = backend_dir.parent
        executable_name = command_path.name

        if os.name == "nt" and not command_path.suffix:
            executable_name = f"{executable_name}.exe"
            candidates = [
                backend_dir / "venv" / "Scripts" / executable_name,
                backend_dir / ".venv" / "Scripts" / executable_name,
                repo_dir / "backend" / "venv" / "Scripts" / executable_name,
                repo_dir / "backend" / ".venv" / "Scripts" / executable_name,
            ]
        else:
            candidates = [
                backend_dir / "venv" / "bin" / executable_name,
                backend_dir / ".venv" / "bin" / executable_name,
                repo_dir / "backend" / "venv" / "bin" / executable_name,
                repo_dir / "backend" / ".venv" / "bin" / executable_name,
            ]

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        return command

    def _build_process_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if not self.inherit_proxy_env:
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            ):
                env.pop(key, None)
            no_proxy_hosts = ["127.0.0.1", "localhost", "restapi.amap.com", "api-inference.modelscope.cn"]
            env["NO_PROXY"] = ",".join(no_proxy_hosts)
            env["no_proxy"] = env["NO_PROXY"]

        env.update(self.env)
        return env

    def _format_exception(self, exc: Exception) -> str:
        if hasattr(exc, "exceptions") and isinstance(getattr(exc, "exceptions"), tuple):
            children = [
                self._format_exception(child)
                for child in getattr(exc, "exceptions")
                if isinstance(child, Exception)
            ]
            child_text = " | ".join(children)
            return f"{exc.__class__.__name__}: {exc}" + (f" -> {child_text}" if child_text else "")

        base = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, Exception) and cause is not exc:
            return f"{base} -> {self._format_exception(cause)}"
        return base
