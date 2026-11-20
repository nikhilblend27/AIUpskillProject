"""Central paths and settings, so scripts work from any working directory."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

ARTICLES_DIR = DATA_DIR / "articles"
CONTEXT_DIR = DATA_DIR / "context"
OUTPUT_DIR = DATA_DIR / "output"
EVALUATION_DIR = DATA_DIR / "evaluation"

ALL_ARTICLES_FILE = ARTICLES_DIR / "all_articles.md"
FILTERED_FILE = CONTEXT_DIR / "filtered_articles.md"
SUMMARY_FILE = CONTEXT_DIR / "summary.md"
NEWSLETTER_FILE = OUTPUT_DIR / "newsletter.md"
GOLDEN_DATASET_FILE = EVALUATION_DIR / "golden_dataset.json"
EVALUATION_REPORT_FILE = EVALUATION_DIR / "evaluation_report.md"


def db_path() -> Path:
    return Path(os.getenv("NEWS_DB_PATH", DATA_DIR / "news_agent.db"))


# Sources used by the default pipeline. Edit here (or pass your own list to
# FetcherFactory.create_from_config) — no fetcher code needs to change.
DEFAULT_SOURCES: list[dict] = [
    {"type": "hackernews", "limit": 30},
    {"type": "rss", "feed_url": "https://www.theverge.com/rss/index.xml", "limit": 20},
    {"type": "github", "limit": 15},
]
