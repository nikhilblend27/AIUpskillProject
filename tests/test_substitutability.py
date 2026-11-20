"""Liskov Substitution: every fetcher honours the same contract (M2).

Network is stubbed at the HTTP-helper level so this runs offline, but each
fetcher's own parsing code still runs.
"""

import pytest

from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.github_trending_fetcher import GitHubTrendingFetcher
from src.fetchers.hackernews_fetcher import HackerNewsFetcher
from src.fetchers.rss_fetcher import RSSFetcher
from src.models.article import Article
from src.transformers.article_transformer import ArticleTransformer

from .test_fetchers import RSS_XML


async def _fake_json(session, url, **kw):
    if "topstories" in url:
        return [1]
    if "item/" in url:
        return {"id": 1, "type": "story", "title": "HN", "url": "https://hn/1", "time": 0}
    return {"items": [{"full_name": "a/b", "html_url": "https://github.com/a/b"}]}


async def _fake_text(session, url):
    return RSS_XML


async def _down(*args, **kwargs):
    return None


def all_fetchers(storage):
    t = ArticleTransformer()
    return [
        HackerNewsFetcher(t, storage),
        RSSFetcher("https://feed.example.com/rss", t, storage),
        GitHubTrendingFetcher(t, storage),
    ]


@pytest.fixture
def fetchers(tmp_storage):
    return all_fetchers(tmp_storage)


async def test_all_fetchers_substitutable(fetchers, monkeypatch):
    for fetcher in fetchers:
        monkeypatch.setattr(fetcher, "_get_json", _fake_json)
        monkeypatch.setattr(fetcher, "_get_text", _fake_text)
        assert isinstance(fetcher, BaseFetcher)
        articles = await fetcher.fetch_articles()
        assert isinstance(articles, list) and articles
        assert all(isinstance(a, Article) for a in articles)
        name = fetcher.get_source_name()
        assert isinstance(name, str) and name and " " not in name


async def test_all_fetchers_return_empty_list_when_source_down(fetchers, monkeypatch):
    """Postcondition holds under failure too: [] — never None, never an exception."""
    for fetcher in fetchers:
        monkeypatch.setattr(fetcher, "_get_json", _down)
        monkeypatch.setattr(fetcher, "_get_text", _down)
        assert await fetcher.fetch_articles() == []


async def test_polymorphic_usage(fetchers, monkeypatch):
    async def process(fetcher: BaseFetcher) -> int:
        return len(await fetcher.fetch_and_save())

    for fetcher in fetchers:
        monkeypatch.setattr(fetcher, "_get_json", _fake_json)
        monkeypatch.setattr(fetcher, "_get_text", _fake_text)
        assert await process(fetcher) >= 1


def test_base_fetcher_is_minimal():
    """Interface Segregation: only what every source needs is abstract."""
    assert BaseFetcher.__abstractmethods__ == {"fetch_articles", "get_source_name"}
