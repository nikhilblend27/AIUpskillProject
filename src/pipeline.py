"""Milestone 3 pipeline: fetch -> filter.

python src/pipeline.py      # or: python -m src.pipeline
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.agents.news_filter_agent import NewsFilterAgent  # noqa: E402
from src.main import build_orchestrator  # noqa: E402
from src.utils.console import setup_console  # noqa: E402


async def run_pipeline() -> dict:
    print("📰 Step 1: fetching articles...")
    articles = await build_orchestrator().fetch_all()
    print(f"   ✅ {len(articles)} articles -> {config.ALL_ARTICLES_FILE}")

    print("🤖 Step 2: filtering with NewsFilterAgent...")
    result = await NewsFilterAgent().execute(
        str(config.ALL_ARTICLES_FILE), str(config.FILTERED_FILE)
    )
    stats = result["stats"]
    print(f"   ✅ kept {stats['kept']}/{stats['input']} -> {config.FILTERED_FILE}")
    return result


if __name__ == "__main__":
    setup_console()
    asyncio.run(run_pipeline())
