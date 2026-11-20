"""Fetcher tests with the HTTP layer stubbed out (fast, offline).

Real-network smoke tests are at the bottom, marked `network`.
"""

import asyncio
import time

import pytest

from src.fetchers.github_trending_fetcher import GitHubTrendingFetcher
from src.fetchers.hackernews_fetcher import HackerNewsFetcher
from src.fetchers.rss_fetcher import RSSFetcher
from src.strategies.rate_limit_strategy import SemaphoreStrategy
from src.transformers.article_transformer import ArticleTransformer

RSS_XML = """<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>First</title><link>https://r/1</link><description>One</description>
<pubDate>Tue, 10 Jun 2025 04:00:00 GMT</pubDate></item>
<item><title>Second</title><link>https://r/2</link></item>
</channel></rss>"""


@pytest.fixture
def deps(tmp_storage):
    return ArticleTransformer(), tmp_storage


async def test_hackernews_fetch_concurrent_and_limited(deps, monkeypatch):
    fetcher = HackerNewsFetcher(*deps, rate_limiter=SemaphoreStrategy(50), limit=5)
    in_flight = peak = 0

    async def fake_get_json(session, url, **kw):
        nonlocal in_flight, peak
        if url.endswith("topstories.json"):
            return list(range(100))
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        i = int(url.rsplit("/", 1)[1].split(".")[0])
        return {"id": i, "type": "story", "title": f"S{i}", "url": f"https://s/{i}", "time": 0}

    monkeypatch.setattr(fetcher, "_get_json", fake_get_json)
    start = time.perf_counter()
    articles = await fetcher.fetch_articles()
    assert [a.title for a in articles] == [f"S{i}" for i in range(5)]
    assert peak > 1, "story fetches should run concurrently"
    assert time.perf_counter() - start < 0.5


async def test_hackernews_handles_api_failure(deps, monkeypatch):
    fetcher = HackerNewsFetcher(*deps)

    async def fail(session, url, **kw):
        return None

    monkeypatch.setattr(fetcher, "_get_json", fail)
    assert await fetcher.fetch_articles() == []


async def test_rss_fetcher_parses_feed(deps, monkeypatch):
    fetcher = RSSFetcher("https://www.example.com/feed.xml", *deps)

    async def fake_text(session, url):
        return RSS_XML

    monkeypatch.setattr(fetcher, "_get_text", fake_text)
    articles = await fetcher.fetch_articles()
    assert fetcher.get_source_name() == "rss_example_com"
    assert [a.url for a in articles] == ["https://r/1", "https://r/2"]
    assert articles[0].published_at.year == 2025


async def test_rss_fetcher_garbage_feed(deps, monkeypatch):
    fetcher = RSSFetcher("https://x.org/rss", *deps)

    async def fake_text(session, url):
        return "<<<not xml"

    monkeypatch.setattr(fetcher, "_get_text", fake_text)
    assert await fetcher.fetch_articles() == []


def test_rss_requires_url(deps):
    with pytest.raises(ValueError):
        RSSFetcher("", *deps)


async def test_github_fetcher_parses_and_sends_auth(deps, monkeypatch):
    fetcher = GitHubTrendingFetcher(*deps, token="secret", limit=1)
    assert fetcher.get_auth_headers()["Authorization"] == "Bearer secret"
    seen = {}

    async def fake_json(session, url, **kw):
        seen.update(kw["params"])
        return {
            "items": [
                {
                    "full_name": "a/b",
                    "html_url": "https://github.com/a/b",
                    "description": "LLM lib",
                    "stargazers_count": 42,
                    "language": "Python",
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {"full_name": "c/d", "html_url": "https://github.com/c/d"},
            ]
        }

    monkeypatch.setattr(fetcher, "_get_json", fake_json)
    articles = await fetcher.fetch_articles()
    assert seen["sort"] == "stars" and seen["q"].startswith("created:>")
    assert len(articles) == 1 and articles[0].score == 42
    assert "Stars: 42" in articles[0].summary


async def test_fetch_and_save_writes_file_and_swallows_errors(deps, monkeypatch, make_article):
    fetcher = HackerNewsFetcher(*deps)

    async def ok():
        return [make_article(1)]

    monkeypatch.setattr(fetcher, "fetch_articles", ok)
    assert len(await fetcher.fetch_and_save()) == 1
    assert (deps[1].base_path / "hackernews_articles.md").exists()

    async def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(fetcher, "fetch_articles", boom)
    assert await fetcher.fetch_and_save() == []


# --- live smoke tests (pytest -m network) ------------------------------------
@pytest.mark.network
async def test_live_hackernews(deps):
    articles = await HackerNewsFetcher(*deps, limit=3).fetch_articles()
    assert 0 < len(articles) <= 3


@pytest.mark.network
async def test_live_github(deps):
    assert await GitHubTrendingFetcher(*deps, limit=3).fetch_articles()
