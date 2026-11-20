"""SQLite persistence for articles (Milestone 4).

Uses the standard-library `sqlite3` driver and runs each query in a worker
thread via `asyncio.to_thread`, so callers stay async without needing the
extra `aiosqlite` dependency.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = "data/news_agent.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    url             TEXT UNIQUE NOT NULL,
    source          TEXT NOT NULL,
    published_at    TEXT NOT NULL,
    summary         TEXT DEFAULT '',
    score           INTEGER DEFAULT 0,
    relevance_score INTEGER,
    key_topics      TEXT DEFAULT '',
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_relevance ON articles(relevance_score);
"""

# Upsert: new rows are inserted; existing URLs get refreshed, but a NULL
# relevance_score / empty key_topics never overwrites an earlier judgement.
_UPSERT = """
INSERT INTO articles (title, url, source, published_at, summary, score, relevance_score, key_topics)
VALUES (:title, :url, :source, :published_at, :summary, :score, :relevance_score, :key_topics)
ON CONFLICT(url) DO UPDATE SET
    title           = excluded.title,
    summary         = CASE WHEN excluded.summary != '' THEN excluded.summary ELSE articles.summary END,
    score           = MAX(articles.score, excluded.score),
    relevance_score = COALESCE(excluded.relevance_score, articles.relevance_score),
    key_topics      = CASE WHEN excluded.key_topics != '' THEN excluded.key_topics ELSE articles.key_topics END,
    updated_at      = CURRENT_TIMESTAMP
"""


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class DatabaseManager:
    """Async-friendly wrapper around a SQLite file."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or os.getenv("NEWS_DB_PATH", DEFAULT_DB_PATH))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # -- internals -------------------------------------------------------
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open, commit (or roll back) and always close — Windows keeps files locked otherwise."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _run(self, fn, *args):
        return asyncio.to_thread(fn, *args)

    @staticmethod
    def _normalise(article: dict[str, Any]) -> dict[str, Any]:
        for field in ("title", "url", "source", "published_at"):
            if not article.get(field):
                raise ValueError(f"article is missing required field {field!r}")
        topics = article.get("key_topics") or ""
        if isinstance(topics, (list, tuple)):
            topics = ", ".join(str(t) for t in topics)
        relevance = article.get("relevance_score")
        return {
            "title": str(article["title"]),
            "url": str(article["url"]),
            "source": str(article["source"]),
            "published_at": str(article["published_at"]),
            "summary": str(article.get("summary") or ""),
            "score": int(article.get("score") or 0),
            "relevance_score": None if relevance in (None, "") else int(relevance),
            "key_topics": topics,
        }

    # -- public API ------------------------------------------------------
    async def initialize(self) -> None:
        def _init():
            with self._connect() as conn:
                conn.executescript(_SCHEMA)

        await self._run(_init)

    async def insert_article(self, article: dict[str, Any]) -> None:
        await self.insert_articles([article])

    async def insert_articles(self, articles: list[dict[str, Any]]) -> int:
        """Upsert many articles in one transaction. Returns rows written."""
        rows = [self._normalise(a) for a in articles]

        def _insert():
            with self._connect() as conn:
                conn.executemany(_UPSERT, rows)
            return len(rows)

        return await self._run(_insert)

    async def query_articles(
        self,
        source: str | None = None,
        limit: int = 50,
        min_relevance: int | None = None,
    ) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM articles WHERE 1=1", []
        if source:
            sql += " AND source = ?"
            params.append(source)
        if min_relevance is not None:
            sql += " AND relevance_score >= ?"
            params.append(min_relevance)
        sql += " ORDER BY published_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        return await self._fetch(sql, params)

    async def search_articles(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Case-insensitive keyword search over title, summary and topics."""
        pattern = f"%{_escape_like(query.strip())}%"
        sql = (
            "SELECT * FROM articles WHERE title LIKE ? ESCAPE '\\' "
            "OR summary LIKE ? ESCAPE '\\' OR key_topics LIKE ? ESCAPE '\\' "
            "ORDER BY COALESCE(relevance_score, -1) DESC, published_at DESC LIMIT ?"
        )
        return await self._fetch(sql, [pattern, pattern, pattern, max(1, int(limit))])

    async def get_article(
        self, article_id: int | None = None, url: str | None = None
    ) -> dict[str, Any] | None:
        if article_id is None and not url:
            raise ValueError("Provide article_id or url")
        if article_id is not None:
            rows = await self._fetch("SELECT * FROM articles WHERE id = ?", [int(article_id)])
        else:
            rows = await self._fetch("SELECT * FROM articles WHERE url = ?", [url])
        return rows[0] if rows else None

    async def get_sources(self) -> list[dict[str, Any]]:
        return await self._fetch(
            "SELECT source, COUNT(*) AS count FROM articles GROUP BY source ORDER BY count DESC",
            [],
        )

    async def count(self) -> int:
        rows = await self._fetch("SELECT COUNT(*) AS n FROM articles", [])
        return int(rows[0]["n"])

    async def _fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        def _query():
            with self._connect() as conn:
                return [dict(row) for row in conn.execute(sql, params).fetchall()]

        return await self._run(_query)
