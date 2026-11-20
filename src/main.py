"""Fetch-only entry point (M1/M2). Composition root: all wiring happens here.

python src/main.py          # or: python -m src.main
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.factories.fetcher_factory import FetcherFactory  # noqa: E402
from src.orchestrator import FetchOrchestrator  # noqa: E402
from src.storage.markdown_storage import MarkdownStorage  # noqa: E402
from src.transformers.article_transformer import ArticleTransformer  # noqa: E402
from src.utils.console import setup_console  # noqa: E402


def build_orchestrator(sources: list[dict] | None = None) -> FetchOrchestrator:
    """Wire concrete classes together. Swap MarkdownStorage for JSONStorage here only."""
    transformer = ArticleTransformer()
    storage = MarkdownStorage(config.ARTICLES_DIR)
    fetchers = FetcherFactory.create_from_config(
        sources or config.DEFAULT_SOURCES, transformer, storage
    )
    return FetchOrchestrator(fetchers, storage)


async def main() -> None:
    orchestrator = build_orchestrator()
    print(f"📰 Fetching from: {', '.join(f.get_source_name() for f in orchestrator.fetchers)}")
    start = time.perf_counter()
    articles = await orchestrator.fetch_all()
    for source, count in orchestrator.last_stats.items():
        print(f"   {source:<22} {count:>3} articles")
    print(f"✅ {len(articles)} unique articles in {time.perf_counter() - start:.1f}s")
    print(f"   Saved to {config.ALL_ARTICLES_FILE}")


if __name__ == "__main__":
    setup_console()
    asyncio.run(main())
