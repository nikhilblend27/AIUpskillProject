"""RSS/Atom feeds (M1, refactored in M2).

Downloads with aiohttp (async, rate-limited), parses with feedparser in a
worker thread because feedparser is synchronous.
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

import feedparser

from src.fetchers.base_fetcher import BaseFetcher
from src.models.article import Article
from src.storage.base_storage import ArticleStorage
from src.strategies.rate_limit_strategy import RateLimitStrategy
from src.transformers.article_transformer import ArticleTransformer

logger = logging.getLogger(__name__)

DEFAULT_FEED_URL = "https://www.theverge.com/rss/index.xml"


class RSSFetcher(BaseFetcher):
    def __init__(
        self,
        feed_url: str,
        transformer: ArticleTransformer,
        storage: ArticleStorage,
        rate_limiter: RateLimitStrategy | None = None,
        limit: int = 30,
        name: str | None = None,
    ):
        super().__init__(transformer, storage, rate_limiter)
        if not feed_url:
            raise ValueError("RSSFetcher requires a feed_url")
        self.feed_url = feed_url
        self.limit = limit
        host = urlparse(feed_url).netloc.removeprefix("www.") or "feed"
        self._name = name or "rss_" + re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_")

    def get_source_name(self) -> str:
        return self._name

    async def fetch_articles(self) -> list[Article]:
        async with self._session() as session:
            body = await self._get_text(session, self.feed_url)
        if not body:
            return []
        feed = await asyncio.to_thread(feedparser.parse, body)
        if feed.bozo and not feed.entries:
            logger.warning("%s: unparseable feed (%s)", self._name, feed.get("bozo_exception"))
            return []
        articles = self.transformer.transform_rss(feed.entries, source=self._name)[: self.limit]
        logger.info("%s: %d articles", self._name, len(articles))
        return articles
