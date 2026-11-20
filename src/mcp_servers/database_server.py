"""Database MCP server (M4) — exposes the SQLite article store as MCP tools.

Tools
  save_articles    upsert one or more articles (also stores relevance scores)
  search_articles  keyword search over title / summary / topics
  get_article      fetch one article by id or url
  query_articles   list articles, optionally by source / min relevance
  get_sources      article counts per source

DB file: $NEWS_DB_PATH, default data/news_agent.db.
Run standalone: python -m src.mcp_servers.database_server  (speaks MCP on stdio)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import TextContent, Tool  # noqa: E402

from src.config import db_path  # noqa: E402
from src.storage.db_manager import DatabaseManager  # noqa: E402

# stdout is the protocol channel — logs must go to stderr.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger("database_server")

server = Server("news-database")
_db: DatabaseManager | None = None

MAX_LIMIT = 200

_ARTICLE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "url": {"type": "string"},
        "source": {"type": "string"},
        "published_at": {"type": "string", "description": "ISO-8601 timestamp"},
        "summary": {"type": "string"},
        "score": {"type": "integer"},
        "relevance_score": {"type": "integer", "minimum": 0, "maximum": 10},
        "key_topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "url", "source", "published_at"],
}

TOOLS = [
    Tool(
        name="save_articles",
        description="Save (upsert by URL) one or more articles into the news database.",
        inputSchema={
            "type": "object",
            "properties": {"articles": {"type": "array", "items": _ARTICLE_SCHEMA}},
            "required": ["articles"],
        },
    ),
    Tool(
        name="search_articles",
        description="Search saved articles by keyword in title, summary or topics.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword or phrase"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_article",
        description="Get a single saved article by numeric id or by url.",
        inputSchema={
            "type": "object",
            "properties": {"id": {"type": "integer"}, "url": {"type": "string"}},
        },
    ),
    Tool(
        name="query_articles",
        description="List recent articles, optionally filtered by source or minimum relevance.",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "min_relevance": {"type": "integer", "minimum": 0, "maximum": 10},
                "limit": {"type": "integer", "default": 50},
            },
        },
    ),
    Tool(
        name="get_sources",
        description="List sources in the database with article counts.",
        inputSchema={"type": "object", "properties": {}},
    ),
]


async def get_db() -> DatabaseManager:
    global _db
    if _db is None:
        _db = DatabaseManager(db_path())
        await _db.initialize()
    return _db


def _limit(arguments: dict[str, Any], default: int) -> int:
    try:
        return max(1, min(int(arguments.get("limit", default)), MAX_LIMIT))
    except (TypeError, ValueError):
        return default


async def handle_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Pure dispatch — unit-testable without the MCP transport."""
    db = await get_db()
    if name == "save_articles":
        articles = arguments.get("articles") or []
        if not isinstance(articles, list):
            raise ValueError("'articles' must be a list")
        saved = await db.insert_articles(articles)
        return {"saved": saved, "total_in_db": await db.count()}
    if name == "search_articles":
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("'query' is required")
        rows = await db.search_articles(query, _limit(arguments, 20))
        return {"query": query, "total": len(rows), "articles": rows}
    if name == "get_article":
        article = await db.get_article(arguments.get("id"), arguments.get("url"))
        return {"found": article is not None, "article": article}
    if name == "query_articles":
        rows = await db.query_articles(
            source=arguments.get("source"),
            limit=_limit(arguments, 50),
            min_relevance=arguments.get("min_relevance"),
        )
        return {"total": len(rows), "articles": rows}
    if name == "get_sources":
        sources = await db.get_sources()
        return {"total": len(sources), "sources": sources}
    raise ValueError(f"Unknown tool: {name}")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # Exceptions raised here are returned to the client as isError=True results.
    result = await handle_tool(name, arguments or {})
    return [TextContent(type="text", text=json.dumps(result, default=str, ensure_ascii=False))]


async def main() -> None:
    await get_db()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
