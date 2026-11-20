"""Factory + Strategy pattern tests (M2)."""

import asyncio
import time

import pytest

from src.factories.fetcher_factory import FetcherFactory
from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.github_trending_fetcher import GitHubTrendingFetcher
from src.fetchers.hackernews_fetcher import HackerNewsFetcher
from src.fetchers.rss_fetcher import RSSFetcher
from src.strategies.rate_limit_strategy import (
    NoRateLimitStrategy,
    SemaphoreStrategy,
    TokenBucketStrategy,
)
from src.transformers.article_transformer import ArticleTransformer
from src.utils.rate_limiter import RateLimiter


@pytest.fixture
def t():
    return ArticleTransformer()


def test_factory_creates_known_types(t, tmp_storage):
    assert isinstance(FetcherFactory.create("hackernews", t, tmp_storage), HackerNewsFetcher)
    assert isinstance(FetcherFactory.create("github", t, tmp_storage), GitHubTrendingFetcher)
    rss = FetcherFactory.create("rss", t, tmp_storage, feed_url="https://a.com/rss", limit=3)
    assert isinstance(rss, RSSFetcher) and rss.limit == 3


def test_factory_errors(t, tmp_storage):
    with pytest.raises(ValueError, match="Unknown"):
        FetcherFactory.create("nope", t, tmp_storage)
    with pytest.raises(ValueError, match="feed_url"):
        FetcherFactory.create("rss", t, tmp_storage)
    with pytest.raises(TypeError):
        FetcherFactory.register("bad", dict)


def test_factory_register_new_source_without_editing_factory(t, tmp_storage, monkeypatch):
    monkeypatch.setattr(FetcherFactory, "_fetchers", dict(FetcherFactory._fetchers))

    class DevToFetcher(BaseFetcher):
        async def fetch_articles(self):
            return []

        def get_source_name(self):
            return "devto"

    FetcherFactory.register("devto", DevToFetcher)
    assert "devto" in FetcherFactory.get_available_types()
    built = FetcherFactory.create_from_config(
        [{"type": "devto"}, {"type": "hackernews"}], t, tmp_storage
    )
    assert [f.get_source_name() for f in built] == ["devto", "hackernews"]


async def _run_tracked(strategy, n=6, work=0.05):
    in_flight = peak = 0

    async def task():
        nonlocal in_flight, peak
        async with strategy:
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(work)
            in_flight -= 1

    await asyncio.gather(*(task() for _ in range(n)))
    return peak


async def test_semaphore_strategy_caps_concurrency():
    assert await _run_tracked(SemaphoreStrategy(2)) == 2


async def test_rate_limiter_execute():
    limiter = RateLimiter(1)

    async def value():
        return 7

    assert await limiter.execute(value()) == 7


async def test_token_bucket_limits_rate():
    bucket = TokenBucketStrategy(rate=5, per=0.5)  # 10/s, burst of 5
    start = time.perf_counter()
    for _ in range(10):
        await bucket.acquire()
    elapsed = time.perf_counter() - start
    assert 0.4 <= elapsed < 1.0  # 5 burst instantly, next 5 at ~0.1s each


async def test_no_rate_limit_strategy():
    assert await _run_tracked(NoRateLimitStrategy(), n=4) == 4


@pytest.mark.parametrize("bad", [lambda: SemaphoreStrategy(0), lambda: TokenBucketStrategy(0, 1)])
def test_strategy_validation(bad):
    with pytest.raises(ValueError):
        bad()
