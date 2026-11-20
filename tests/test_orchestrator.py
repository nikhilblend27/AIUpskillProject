"""Orchestrator tests with mock fetchers/storage — no HTTP, no disk (M2 DIP)."""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from src.fetchers.base_fetcher import BaseFetcher
from src.orchestrator import FetchOrchestrator
from src.storage.base_storage import ArticleStorage


class FakeFetcher(BaseFetcher):
    def __init__(self, name, articles=None, error=None, delay=0.0):
        super().__init__(transformer=None, storage=MagicMock(spec=ArticleStorage))
        self._name, self._articles, self._error, self._delay = name, articles or [], error, delay

    def get_source_name(self):
        return self._name

    async def fetch_articles(self):
        await asyncio.sleep(self._delay)
        if self._error:
            raise self._error
        return self._articles


async def test_orchestrator_with_mocks(make_article):
    storage = MagicMock(spec=ArticleStorage)
    orch = FetchOrchestrator([FakeFetcher("a", [make_article(1)])], storage)
    articles = await orch.fetch_all()
    assert len(articles) == 1
    storage.save.assert_called_once_with(articles, "all_articles.md")


async def test_multiple_fetchers_run_concurrently_and_dedupe(make_article):
    shared = make_article(1)
    fetchers = [
        FakeFetcher("a", [shared, make_article(2)], delay=0.2),
        FakeFetcher("b", [shared, make_article(3)], delay=0.2),
        FakeFetcher("c", [make_article(4)], delay=0.2),
    ]
    orch = FetchOrchestrator(fetchers, MagicMock(spec=ArticleStorage))
    start = time.perf_counter()
    articles = await orch.fetch_all()
    assert time.perf_counter() - start < 0.5, "sources should be fetched concurrently"
    assert sorted(a.url for a in articles) == [make_article(i).url for i in (1, 2, 3, 4)]
    assert orch.last_stats == {"a": 2, "b": 2, "c": 1}


async def test_one_failing_source_does_not_break_the_run(make_article):
    orch = FetchOrchestrator(
        [FakeFetcher("bad", error=RuntimeError("boom")), FakeFetcher("ok", [make_article(1)])],
        MagicMock(spec=ArticleStorage),
    )
    assert len(await orch.fetch_all()) == 1
    assert orch.last_stats["bad"] == 0


async def test_nothing_fetched_writes_nothing():
    storage = MagicMock(spec=ArticleStorage)
    assert await FetchOrchestrator([FakeFetcher("a")], storage).fetch_all() == []
    storage.save.assert_not_called()


def test_requires_fetchers():
    with pytest.raises(ValueError):
        FetchOrchestrator([], MagicMock(spec=ArticleStorage))
