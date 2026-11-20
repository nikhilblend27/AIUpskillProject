"""Create fetchers by name (M2: Factory pattern).

New sources call `FetcherFactory.register(...)` — the factory itself never
needs editing, so it stays Open/Closed too.
"""

from __future__ import annotations

from typing import Any

from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.github_trending_fetcher import GitHubTrendingFetcher
from src.fetchers.hackernews_fetcher import HackerNewsFetcher
from src.fetchers.rss_fetcher import RSSFetcher
from src.storage.base_storage import ArticleStorage
from src.transformers.article_transformer import ArticleTransformer


class FetcherFactory:
    _fetchers: dict[str, type[BaseFetcher]] = {
        "hackernews": HackerNewsFetcher,
        "rss": RSSFetcher,
        "github": GitHubTrendingFetcher,
    }

    @classmethod
    def create(
        cls,
        source_type: str,
        transformer: ArticleTransformer,
        storage: ArticleStorage,
        **kwargs: Any,
    ) -> BaseFetcher:
        """Build a fetcher; extra kwargs (feed_url, limit, rate_limiter...) pass through."""
        try:
            fetcher_class = cls._fetchers[source_type]
        except KeyError:
            raise ValueError(
                f"Unknown fetcher type {source_type!r}. Available: {cls.get_available_types()}"
            ) from None
        if fetcher_class is RSSFetcher or issubclass(fetcher_class, RSSFetcher):
            feed_url = kwargs.pop("feed_url", None)
            if not feed_url:
                raise ValueError("RSS fetcher requires feed_url")
            return fetcher_class(feed_url, transformer, storage, **kwargs)
        return fetcher_class(transformer, storage, **kwargs)

    @classmethod
    def create_from_config(
        cls,
        config: list[dict[str, Any]],
        transformer: ArticleTransformer,
        storage: ArticleStorage,
    ) -> list[BaseFetcher]:
        """[{'type': 'rss', 'feed_url': ...}, {'type': 'hackernews'}] -> fetchers."""
        return [
            cls.create(
                item["type"], transformer, storage, **{k: v for k, v in item.items() if k != "type"}
            )
            for item in config
        ]

    @classmethod
    def register(cls, name: str, fetcher_class: type[BaseFetcher]) -> None:
        if not (isinstance(fetcher_class, type) and issubclass(fetcher_class, BaseFetcher)):
            raise TypeError("fetcher_class must subclass BaseFetcher")
        cls._fetchers[name] = fetcher_class

    @classmethod
    def get_available_types(cls) -> list[str]:
        return sorted(cls._fetchers)
