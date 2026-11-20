"""Milestone 4: full multi-agent pipeline, with persistence through MCP.

Fetch -> [MCP save] -> Filter -> [MCP save scores] -> Summarize (+MCP search) -> Write

python src/complete_pipeline.py      # or: python -m src.complete_pipeline
python src/complete_pipeline.py --skip-fetch   # reuse data/articles/all_articles.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.agents.news_filter_agent import NewsFilterAgent  # noqa: E402
from src.agents.summarizer_agent import SummarizerAgent  # noqa: E402
from src.agents.writer_agent import WriterAgent  # noqa: E402
from src.main import build_orchestrator  # noqa: E402
from src.skills.search_skill import SearchSkill  # noqa: E402
from src.utils.console import setup_console  # noqa: E402
from src.utils.markdown_parser import parse_articles_markdown  # noqa: E402


def _db_rows(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Markdown-parsed article dicts -> save_articles payload."""
    rows = []
    for a in articles:
        if not a.get("url"):
            continue
        row = {
            "title": a["title"],
            "url": a["url"],
            "source": a.get("source") or "unknown",
            "published_at": a.get("published") or "unknown",
            "summary": a.get("summary", ""),
            "score": int(str(a.get("score") or 0).split("/")[0] or 0),
        }
        # Don't overwrite a stored score with the 0 we use when the LLM failed.
        if "relevance_score" in a and not a.get("error"):
            row["relevance_score"] = int(a["relevance_score"])
            row["key_topics"] = a.get("key_topics", [])
        rows.append(row)
    return rows


async def run_complete_pipeline(skip_fetch: bool = False) -> dict[str, Any]:
    start = time.perf_counter()
    print("=" * 64 + "\n  AI News Pipeline — Fetch → Filter → Summarize → Write\n" + "=" * 64)

    if skip_fetch and config.ALL_ARTICLES_FILE.exists():
        print(f"\n📰 1. Reusing {config.ALL_ARTICLES_FILE.name}")
    else:
        print("\n📰 1. Fetching articles...")
        orchestrator = build_orchestrator()
        fetched = await orchestrator.fetch_all()
        for source, n in orchestrator.last_stats.items():
            print(f"      {source:<22} {n:>3}")
        print(f"   ✅ {len(fetched)} unique articles")
        if not fetched:
            raise SystemExit("No articles fetched — check your network connection.")

    articles = parse_articles_markdown(config.ALL_ARTICLES_FILE.read_text(encoding="utf-8"))

    async with SearchSkill() as skill:
        print("\n💾 2. Saving to database via MCP (save_articles)...")
        saved = await skill.save_articles(_db_rows(articles))
        print(f"   ✅ {saved['saved']} upserted — {saved['total_in_db']} articles in DB")

        print("\n🤖 3. NewsFilterAgent...")
        filter_agent = NewsFilterAgent()
        await filter_agent.execute(str(config.ALL_ARTICLES_FILE), str(config.FILTERED_FILE))
        result = filter_agent.last_result
        kept, total = result["total_output"], result["total_input"]
        print(f"   ✅ kept {kept}/{total} (threshold {filter_agent.relevance_threshold})")
        if result["stats"]["errors"]:
            print(
                f"   ⚠️  {result['stats']['errors']} articles could not be judged (LLM errors / "
                "quota) and were left out — re-run later with --skip-fetch"
            )
        await skill.save_articles(_db_rows(result["all_judgements"]))
        print("   💾 relevance scores stored in DB")

        print("\n📝 4. SummarizerAgent (with SearchSkill context)...")
        summarizer = SummarizerAgent(search_skill=skill)
        summary = await summarizer.execute(str(config.FILTERED_FILE), str(config.SUMMARY_FILE))
        print(f"   ✅ {summary['stats'].get('topics', 0)} topics -> {config.SUMMARY_FILE.name}")

    print("\n✍️  5. WriterAgent...")
    writer = WriterAgent()
    await writer.execute(str(config.SUMMARY_FILE), str(config.NEWSLETTER_FILE))
    llm_calls = filter_agent.llm_calls + summarizer.llm_calls + writer.llm_calls

    elapsed = time.perf_counter() - start
    print("\n" + "=" * 64)
    print(f"🎉 Done in {elapsed:.0f}s — {llm_calls} LLM calls")
    print(f"   Newsletter: {config.NEWSLETTER_FILE}")
    print("=" * 64)
    return {"fetched": total, "kept": kept, "llm_calls": llm_calls, "seconds": elapsed}


if __name__ == "__main__":
    setup_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-fetch", action="store_true", help="reuse the last fetch")
    asyncio.run(run_complete_pipeline(skip_fetch=parser.parse_args().skip_fetch))
