"""Markdown storage (M1, refactored onto ArticleStorage in M2)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.models.article import Article
from src.storage.base_storage import ArticleStorage


class MarkdownStorage(ArticleStorage):
    """Write articles as one human-readable markdown file per batch."""

    def __init__(self, base_path: str | Path = "data/articles"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, articles: list[Article], filename: str | None = None) -> Path:
        filename = filename or f"articles_{datetime.now():%Y%m%d_%H%M%S}.md"
        path = self.base_path / filename
        sources = sorted({a.source for a in articles})

        parts = [
            "# News Articles\n\n",
            f"**Generated:** {datetime.now():%Y-%m-%d %H:%M}  \n",
            f"**Total Articles:** {len(articles)}  \n",
            f"**Sources:** {', '.join(sources) or 'none'}\n\n",
            "---\n\n",
        ]
        for article in articles:
            parts.append(self._format_article(article))
            parts.append("\n---\n\n")

        path.write_text("".join(parts), encoding="utf-8")
        return path

    def _format_article(self, article: Article) -> str:
        return article.to_markdown()
