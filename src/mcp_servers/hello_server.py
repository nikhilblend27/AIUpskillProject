"""Hello-world MCP server (M4, Evening 16) — the smallest useful MCP server.

Run via the client:  python -m src.mcp_servers.simple_client
Note: an MCP stdio server must never print to stdout — that channel carries
the JSON-RPC protocol. Log to stderr instead.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("hello-server")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="say_hello",
            description="Greet someone by name",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Who to greet"}},
                "required": ["name"],
            },
        ),
        Tool(
            name="get_time",
            description="Current UTC time in ISO-8601",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "say_hello":
        return [TextContent(type="text", text=f"Hello, {arguments.get('name', 'world')}! 👋")]
    if name == "get_time":
        return [TextContent(type="text", text=datetime.now(UTC).isoformat())]
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
