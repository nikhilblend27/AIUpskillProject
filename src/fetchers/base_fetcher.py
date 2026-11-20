"""Abstract fetcher (M2: Open/Closed + Template Method).

A new source is a new subclass — nothing here or in the orchestrator changes.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import aiohttp

from src.models.article import Article
from src.storage.base_storage import ArticleStorage
from src.strategies.rate_limit_strategy import RateLimitStrategy, SemaphoreStrategy
from src.transformers.article_transformer import ArticleTransformer

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=20)
DEFAULT_HEADERS = {"User-Agent": "ai-upskill-news-pipeline/1.0 (+learning project)"}


class BaseFetcher(ABC):
    """Contract every source must honour.

    Liskov guarantees (checked in tests/test_substitutability.py):
      * fetch_articles() always returns list[Article] — never None, and
        network errors are logged and turned into an empty list.
      * get_source_name() returns a non-empty, filename-safe string.
    """

    def __init__(
        self,
        transformer: ArticleTransformer,
        storage: ArticleStorage,
        rate_limiter: RateLimitStrategy | None = None,
    ):
        self.transformer = transformer
        self.storage = storage
        self.rate_limiter = rate_limiter or SemaphoreStrategy(10)

    @abstractmethod
    async def fetch_articles(self) -> list[Article]:
        """Fetch from the source. The only step that varies by source."""

    @abstractmethod
    def get_source_name(self) -> str:
        """Short identifier, e.g. 'hackernews'."""

    # -- Template Method ---------------------------------------------------
    async def fetch_and_save(self) -> list[Article]:
        """Fetch (varies) -> save (shared). Failures yield an empty list."""
        try:
            articles = await self.fetch_articles()
        except Exception as exc:  # noqa: BLE001 — one bad source must not sink the run
            logger.error("%s fetch failed: %s", self.get_source_name(), exc)
            articles = []
        if articles:
            self.storage.save(articles, f"{self.get_source_name()}_articles.md")
        return articles

    # -- shared helpers ----------------------------------------------------
    def _session(self, headers: dict[str, str] | None = None) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            timeout=DEFAULT_TIMEOUT, headers={**DEFAULT_HEADERS, **(headers or {})}
        )

    async def _get_json(self, session: aiohttp.ClientSession, url: str, **kwargs) -> Any:
        """Rate-limited GET returning parsed JSON, or None on failure."""
        async with self.rate_limiter:
            try:
                async with session.get(url, **kwargs) as resp:
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                logger.warning("GET %s failed: %s", url, exc)
                return None

    async def _get_text(self, session: aiohttp.ClientSession, url: str) -> str | None:
        async with self.rate_limiter:
            try:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    return await resp.text()
            except (aiohttp.ClientError, TimeoutError) as exc:
                logger.warning("GET %s failed: %s", url, exc)
                return None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source={self.get_source_name()!r})"
