"""Reusable MCP stdio client helper.

Launches a server module as a subprocess (`python -m <module>`) and yields
an initialised `ClientSession`.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from src.config import PROJECT_ROOT


def server_params(module: str, env: dict[str, str] | None = None) -> StdioServerParameters:
    merged = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT), "PYTHONIOENCODING": "utf-8"}
    merged.update(env or {})
    # PYTHONPATH makes `-m src....` resolvable from any working directory.
    return StdioServerParameters(command=sys.executable, args=["-m", module], env=merged)


@asynccontextmanager
async def mcp_session(
    module: str, env: dict[str, str] | None = None
) -> AsyncIterator[ClientSession]:
    async with stdio_client(server_params(module, env)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_json_tool(session: ClientSession, name: str, arguments: dict[str, Any]) -> Any:
    """Call a tool whose result is a single JSON text block; raise on tool errors."""
    result = await session.call_tool(name, arguments)
    text = result.content[0].text if result.content else ""
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool {name} failed: {text}")
    return json.loads(text)
