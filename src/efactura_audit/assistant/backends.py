"""Where the assistant's tool calls run.

- LocalBackend: calls the tool functions in-process (fastest; the default inside the app).
- MCPBackend: starts the MCP server as a subprocess and calls the same tools over stdio, exactly
  as an external MCP client would.
Both return the same JSON, so answers are identical and traceable either way.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from contextlib import AsyncExitStack
from typing import Any

from .tools import AuditTools


class LocalBackend:
    transport = "local"

    def __init__(self, tools: AuditTools):
        self.tools = tools

    def tool_specs(self) -> list[dict]:
        return [{"name": s.name, "description": s.description, "parameters": s.json_schema()} for s in self.tools.specs()]

    def call(self, name: str, arguments: dict) -> Any:
        return self.tools.call(name, arguments)

    def close(self) -> None:
        pass


class MCPBackend:
    transport = "mcp"

    def __init__(self, workspace: str, lang: str = "ro", startup_timeout: float = 30.0):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._stack = AsyncExitStack()
        env = {**os.environ, "EFACTURA_LANG": lang}
        params = StdioServerParameters(command=sys.executable, args=["-m", "efactura_audit.mcp_server", str(workspace)], env=env)

        async def start():
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
            return session, listed.tools

        self._session, tools = self._run(start(), startup_timeout)
        self._specs = [{"name": t.name, "description": (t.description or "").split("\n\nArgs:")[0],
                        "parameters": _simplify_schema(t.inputSchema)} for t in tools]

    def _run(self, coro, timeout: float = 60.0):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def tool_specs(self) -> list[dict]:
        return self._specs

    def call(self, name: str, arguments: dict) -> Any:
        args = {k: v for k, v in (arguments or {}).items() if v is not None and v != ""}
        result = self._run(self._session.call_tool(name, args))
        if getattr(result, "structuredContent", None):
            sc = result.structuredContent
            return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
        texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
        joined = "\n".join(texts)
        try:
            return json.loads(joined)
        except json.JSONDecodeError:
            return {"error": joined} if result.isError else {"text": joined}

    def close(self) -> None:
        try:
            self._run(self._stack.aclose(), 10)
        except Exception:  # noqa: BLE001
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)


def _simplify_schema(schema: dict) -> dict:
    """Turn pydantic's anyOf/null schemas into plain types for small local models."""
    props = {}
    for name, p in (schema.get("properties") or {}).items():
        q = dict(p)
        if "anyOf" in q:
            types = [a for a in q.pop("anyOf") if a.get("type") != "null"]
            if types:
                q.update(types[0])
        if "enum" in q and "type" not in q:
            q["type"] = "string"
        q.pop("title", None)
        q.pop("default", None)
        props[name] = q
    return {"type": "object", "properties": props, "required": schema.get("required", [])}
