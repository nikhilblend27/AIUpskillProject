"""Run many fetchers concurrently (M1, dependency-injected in M2)."""

from __future__ import annotations

import asyncio
import logging
import time

from src.fetchers.base_fetcher import BaseFetcher
from src.models.article import Article
from src.storage.base_storage import ArticleStorage

logger = logging.getLogger(__name__)


class FetchOrchestrator:
    """Depends only on abstractions (BaseFetcher, ArticleStorage) — DIP."""

    def __init__(
        self,
        fetchers: list[BaseFetcher],
        storage: ArticleStorage,
        combined_filename: str | None = "all_articles.md",
    ):
        if not fetchers:
            raise ValueError("FetchOrchestrator needs at least one fetcher")
        self.fetchers = fetchers
        self.storage = storage
        self.combined_filename = combined_filename
        self.last_stats: dict[str, int] = {}

    async def fetch_all(self) -> list[Article]:
        """Fetch every source at once, de-duplicate by URL, save the combined file."""
        start = time.perf_counter()
        results = await asyncio.gather(
            *(f.fetch_and_save() for f in self.fetchers), return_exceptions=True
        )

        seen: set[str] = set()
        articles: list[Article] = []
        self.last_stats = {}
        for fetcher, result in zip(self.fetchers, results, strict=False):
            name = fetcher.get_source_name()
            if isinstance(result, BaseException):
                logger.error("%s failed: %s", name, result)
                self.last_stats[name] = 0
                continue
            self.last_stats[name] = len(result)
            for article in result:
                if article.url not in seen:
                    seen.add(article.url)
                    articles.append(article)

        if self.combined_filename and articles:
            self.storage.save(articles, self.combined_filename)
        logger.info(
            "Fetched %d unique articles from %d sources in %.2fs",
            len(articles),
            len(self.fetchers),
            time.perf_counter() - start,
        )
        return articles
