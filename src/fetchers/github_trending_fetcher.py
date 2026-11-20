"""GitHub "trending" repositories (M2 — added without editing existing classes).

GitHub has no official trending API and scraping its HTML breaks often, so
this uses the public Search API: repos created in the last N days, sorted by
stars. It works anonymously (10 searches/min); set GITHUB_TOKEN for more.

It also opts into `AuthenticatedFetcher` to show Interface Segregation:
only sources that need auth carry auth methods.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.interfaces import AuthenticatedFetcher
from src.models.article import Article
from src.storage.base_storage import ArticleStorage
from src.strategies.rate_limit_strategy import RateLimitStrategy
from src.transformers.article_transformer import ArticleTransformer, clean_text

logger = logging.getLogger(__name__)


class GitHubTrendingFetcher(BaseFetcher, AuthenticatedFetcher):
    SEARCH_URL = "https://api.github.com/search/repositories"

    def __init__(
        self,
        transformer: ArticleTransformer,
        storage: ArticleStorage,
        rate_limiter: RateLimitStrategy | None = None,
        limit: int = 20,
        days: int = 7,
        token: str | None = None,
    ):
        super().__init__(transformer, storage, rate_limiter)
        self.limit = limit
        self.days = days
        self.token = token or os.getenv("GITHUB_TOKEN")

    def get_source_name(self) -> str:
        return "github_trending"

    def get_auth_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def fetch_articles(self) -> list[Article]:
        since = (datetime.now(UTC) - timedelta(days=self.days)).strftime("%Y-%m-%d")
        params = {
            "q": f"created:>{since}",
            "sort": "stars",
            "order": "desc",
            "per_page": str(min(self.limit, 100)),
        }
        async with self._session(self.get_auth_headers()) as session:
            data = await self._get_json(session, self.SEARCH_URL, params=params)
        if not isinstance(data, dict):
            return []
        articles = self.parse_repos(data.get("items", []))[: self.limit]
        logger.info("github_trending: %d articles", len(articles))
        return articles

    def parse_repos(self, items: list[dict[str, Any]]) -> list[Article]:
        articles = []
        for repo in items:
            if not repo.get("full_name") or not repo.get("html_url"):
                continue
            stars = int(repo.get("stargazers_count") or 0)
            language = repo.get("language") or "n/a"
            description = clean_text(repo.get("description")) or "No description."
            created = repo.get("created_at") or datetime.now(UTC).isoformat()
            articles.append(
                Article(
                    title=repo["full_name"],
                    url=repo["html_url"],
                    published_at=datetime.fromisoformat(created.replace("Z", "+00:00")),
                    source=self.get_source_name(),
                    summary=f"{description} (Language: {language}, Stars: {stars})",
                    score=stars,
                )
            )
        return articles
