"""Talk to the hello-world MCP server (M4, Evening 16).

python -m src.mcp_servers.simple_client
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.mcp_servers.client import mcp_session  # noqa: E402
from src.utils.console import setup_console  # noqa: E402


async def main() -> None:
    async with mcp_session("src.mcp_servers.hello_server") as session:
        tools = await session.list_tools()
        print("🔧 Tools:", [t.name for t in tools.tools])
        hello = await session.call_tool("say_hello", {"name": "Blend"})
        print("👉", hello.content[0].text)
        now = await session.call_tool("get_time", {})
        print("🕒", now.content[0].text)


if __name__ == "__main__":
    setup_console()
    asyncio.run(main())
