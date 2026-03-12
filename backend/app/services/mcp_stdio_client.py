import asyncio
import json
import os
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
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.timeout_seconds = timeout_seconds
        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._request_id = 0
        self._write_lock = asyncio.Lock()
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None

    async def connect(self) -> None:
        if self._process is not None:
            return

        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self.env},
        )

        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "trip-planning-agent", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized", {})

    async def list_tools(self) -> dict[str, Any]:
        await self.connect()
        return await self._request("tools/list", {})

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await self.connect()
        return await self._request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

    async def close(self) -> None:
        if self._process is None:
            return

        if self._process.stdin:
            self._process.stdin.close()

        if self._reader_task:
            self._reader_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()

        await self._process.wait()
        self._process = None

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        await self._send(payload)

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        await self._send(payload)

        try:
            response = await asyncio.wait_for(future, timeout=self.timeout_seconds)
        finally:
            self._pending.pop(request_id, None)

        if "error" in response:
            raise MCPProtocolError(str(response["error"]))

        return response.get("result", {})

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise MCPProtocolError("MCP process is not connected.")

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        message = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body
        async with self._write_lock:
            self._process.stdin.write(message)
            await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        reader = self._process.stdout

        try:
            while True:
                headers = {}
                while True:
                    line = await reader.readline()
                    if not line:
                        return
                    if line in {b"\r\n", b"\n"}:
                        break
                    decoded = line.decode("utf-8").strip()
                    if ":" in decoded:
                        key, value = decoded.split(":", 1)
                        headers[key.strip().lower()] = value.strip()

                content_length = int(headers.get("content-length", "0"))
                if content_length <= 0:
                    continue

                body = await reader.readexactly(content_length)
                message = json.loads(body.decode("utf-8"))
                if "id" in message and message["id"] in self._pending:
                    self._pending[message["id"]].set_result(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(exc)

    async def _drain_stderr(self) -> None:
        if self._process is None or self._process.stderr is None:
            return

        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    return
        except asyncio.CancelledError:
            raise

