"""DatabaseManager, the MCP tool handlers, and a real MCP stdio round-trip."""

import pytest

from src.mcp_servers import database_server
from src.skills.search_skill import SearchSkill
from src.storage.db_manager import DatabaseManager


def row(i, **kw):
    base = {
        "title": f"Title {i}",
        "url": f"https://x/{i}",
        "source": "hn",
        "published_at": f"2026-01-0{i}T00:00:00",
    }
    return {**base, **kw}


@pytest.fixture
async def db(tmp_path):
    manager = DatabaseManager(tmp_path / "test.db")
    await manager.initialize()
    return manager


async def test_insert_query_and_upsert(db):
    await db.insert_articles([row(1, score=5), row(2, source="rss")])
    assert await db.count() == 2
    await db.insert_article(row(1, relevance_score=9, key_topics=["LLMs"], summary=""))
    a1 = await db.get_article(url="https://x/1")
    assert a1["relevance_score"] == 9 and a1["key_topics"] == "LLMs" and a1["score"] == 5
    await db.insert_article(row(1))  # later save without a score must not erase it
    assert (await db.get_article(url="https://x/1"))["relevance_score"] == 9
    assert await db.count() == 2
    assert [a["url"] for a in await db.query_articles(source="rss")] == ["https://x/2"]
    assert [a["url"] for a in await db.query_articles(min_relevance=8)] == ["https://x/1"]


async def test_search_is_case_insensitive_and_escapes_wildcards(db):
    await db.insert_articles(
        [row(1, title="New LLM agents"), row(2, title="100% pure"), row(3, key_topics="Robotics")]
    )
    assert [a["url"] for a in await db.search_articles("llm")] == ["https://x/1"]
    assert [a["url"] for a in await db.search_articles("%")] == ["https://x/2"]
    assert [a["url"] for a in await db.search_articles("robot")] == ["https://x/3"]


async def test_sources_and_validation(db):
    await db.insert_articles([row(1), row(2), row(3, source="rss")])
    assert await db.get_sources() == [{"source": "hn", "count": 2}, {"source": "rss", "count": 1}]
    with pytest.raises(ValueError):
        await db.insert_article({"title": "no url"})
    with pytest.raises(ValueError):
        await db.get_article()


async def test_mcp_tool_handlers(tmp_path, monkeypatch):
    monkeypatch.setattr(database_server, "_db", None)
    monkeypatch.setenv("NEWS_DB_PATH", str(tmp_path / "h.db"))
    handle = database_server.handle_tool

    assert (await handle("save_articles", {"articles": [row(1), row(2)]}))["saved"] == 2
    assert (await handle("search_articles", {"query": "Title 2"}))["total"] == 1
    got = await handle("get_article", {"url": "https://x/1"})
    assert got["found"] and got["article"]["title"] == "Title 1"
    assert (await handle("query_articles", {"limit": 1}))["total"] == 1
    assert (await handle("get_sources", {}))["sources"] == [{"source": "hn", "count": 2}]
    with pytest.raises(ValueError):
        await handle("search_articles", {"query": " "})
    with pytest.raises(ValueError):
        await handle("drop_tables", {})


async def test_search_skill_over_real_mcp_stdio(tmp_path):
    """Spawns the real server subprocess and talks MCP to it."""
    async with SearchSkill(env={"NEWS_DB_PATH": str(tmp_path / "mcp.db")}) as skill:
        tools = await skill.list_tools()
        assert {"save_articles", "search_articles", "get_article"} <= set(tools)
        await skill.save_articles([row(1, title="Agents everywhere")])
        hits = await skill.search("agents")
        assert hits["success"] and hits["total"] == 1
        assert (await skill.get_article(url="https://x/1"))["title"] == "Agents everywhere"
        assert (await skill.get_sources())["total"] == 1
        with pytest.raises(RuntimeError, match="failed"):
            await skill.save_articles([{"title": "missing fields"}])
