"""SearchSkill — a higher-level capability built on the Database MCP server (M4).

Agents call `skill.search("LLM")` and never see MCP details. Use it as an
async context manager to keep one server process open for many calls:

    async with SearchSkill() as skill:
        await skill.save_articles([...])
        hits = await skill.search("agents")

Without `async with`, each call opens and closes its own connection.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession

from src.mcp_servers.client import call_json_tool, mcp_session

logger = logging.getLogger(__name__)

SERVER_MODULE = "src.mcp_servers.database_server"


class SearchSkill:
    def __init__(self, env: dict[str, str] | None = None):
        self.env = env
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> SearchSkill:
        self._stack = AsyncExitStack()
        self._session = await self._stack.enter_async_context(mcp_session(SERVER_MODULE, self.env))
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._stack:
            await self._stack.aclose()
        self._stack = self._session = None

    async def _call(self, tool: str, arguments: dict[str, Any]) -> Any:
        if self._session is not None:
            return await call_json_tool(self._session, tool, arguments)
        async with mcp_session(SERVER_MODULE, self.env) as session:
            return await call_json_tool(session, tool, arguments)

    async def list_tools(self) -> list[str]:
        if self._session is not None:
            return [t.name for t in (await self._session.list_tools()).tools]
        async with mcp_session(SERVER_MODULE, self.env) as session:
            return [t.name for t in (await session.list_tools()).tools]

    # -- skill API -----------------------------------------------------------
    async def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Never raises: failures come back as success=False so agents can carry on."""
        try:
            data = await self._call("search_articles", {"query": query, "limit": limit})
            return {"success": True, **data}
        except Exception as exc:  # noqa: BLE001
            logger.warning("SearchSkill.search(%r) failed: %s", query, exc)
            return {"success": False, "query": query, "error": str(exc), "total": 0, "articles": []}

    async def save_articles(self, articles: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._call("save_articles", {"articles": articles})

    async def get_article(self, article_id: int | None = None, url: str | None = None) -> Any:
        args: dict[str, Any] = {}
        if article_id is not None:
            args["id"] = article_id
        if url:
            args["url"] = url
        return (await self._call("get_article", args))["article"]

    async def query(self, **filters: Any) -> dict[str, Any]:
        return await self._call("query_articles", filters)

    async def get_sources(self) -> dict[str, Any]:
        return await self._call("get_sources", {})
