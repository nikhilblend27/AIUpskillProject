"""Turn raw source payloads into Article objects (M2: Single Responsibility).

Fetchers only do I/O; this class only shapes data. That split lets us
unit-test parsing without touching the network.
"""

from __future__ import annotations

import calendar
import html
import logging
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from src.models.article import Article

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
SUMMARY_MAX_CHARS = 300


def clean_text(text: str | None, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    """Strip HTML tags/entities and collapse whitespace into one line."""
    if not text:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", text))
    text = " ".join(text.split())
    return text if len(text) <= max_chars else text[: max_chars - 3].rstrip() + "..."


class ArticleTransformer:
    """Source-specific raw data -> List[Article]."""

    def transform_hackernews(self, raw_items: Iterable[dict[str, Any] | None]) -> list[Article]:
        articles = []
        for item in raw_items:
            if not item or item.get("type", "story") != "story":
                continue
            if item.get("dead") or item.get("deleted"):
                continue
            title = item.get("title")
            # Ask HN / text posts have no external URL — link to the HN thread.
            url = item.get("url") or (
                f"https://news.ycombinator.com/item?id={item['id']}" if item.get("id") else None
            )
            if not title or not url:
                continue
            articles.append(
                Article(
                    title=title,
                    url=url,
                    published_at=datetime.fromtimestamp(item.get("time", 0), tz=UTC),
                    source="hackernews",
                    summary=clean_text(item.get("text")),
                    score=int(item.get("score") or 0),
                )
            )
        return articles

    def transform_rss(self, entries: Iterable[Any], source: str = "rss") -> list[Article]:
        articles = []
        for entry in entries:
            try:
                title, url = entry.get("title"), entry.get("link")
                if not title or not url:
                    continue
                articles.append(
                    Article(
                        title=clean_text(title, 500),
                        url=url,
                        published_at=self._parse_entry_date(entry),
                        source=source,
                        summary=clean_text(entry.get("summary") or entry.get("description")),
                    )
                )
            except (ValueError, TypeError) as exc:
                logger.warning("Skipping malformed RSS entry: %s", exc)
        return articles

    def _parse_entry_date(self, entry: Any) -> datetime:
        for key in ("published_parsed", "updated_parsed"):
            parsed = entry.get(key)
            if parsed:
                return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
        for key in ("published", "updated"):
            if entry.get(key):
                return self._parse_date(entry[key])
        return datetime.now(UTC)

    def _parse_date(self, date_str: str) -> datetime:
        """Parse RFC-822 or ISO-8601 dates; fall back to now."""
        try:
            return parsedate_to_datetime(date_str)
        except (TypeError, ValueError):
            pass
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
