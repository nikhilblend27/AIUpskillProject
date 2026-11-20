"""Hacker News top stories (M1, refactored in M2).

API: https://github.com/HackerNews/API — one request for the ID list, then
one request per story, fetched concurrently under the rate limiter.
"""

from __future__ import annotations

import asyncio
import logging

from src.fetchers.base_fetcher import BaseFetcher
from src.models.article import Article
from src.storage.base_storage import ArticleStorage
from src.strategies.rate_limit_strategy import RateLimitStrategy
from src.transformers.article_transformer import ArticleTransformer

logger = logging.getLogger(__name__)


class HackerNewsFetcher(BaseFetcher):
    BASE_URL = "https://hacker-news.firebaseio.com/v0"

    def __init__(
        self,
        transformer: ArticleTransformer,
        storage: ArticleStorage,
        rate_limiter: RateLimitStrategy | None = None,
        limit: int = 30,
    ):
        super().__init__(transformer, storage, rate_limiter)
        self.limit = limit

    def get_source_name(self) -> str:
        return "hackernews"

    async def fetch_articles(self) -> list[Article]:
        async with self._session() as session:
            ids = await self._get_json(session, f"{self.BASE_URL}/topstories.json")
            if not isinstance(ids, list):
                return []
            # Over-fetch a little: some items are jobs/dead/text-only.
            wanted = ids[: int(self.limit * 1.3) + 1]
            raw = await asyncio.gather(
                *(self._get_json(session, f"{self.BASE_URL}/item/{i}.json") for i in wanted)
            )
        articles = self.transformer.transform_hackernews(raw)[: self.limit]
        logger.info("hackernews: %d articles", len(articles))
        return articles
