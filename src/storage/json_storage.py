"""JSON storage — a second ArticleStorage implementation that proves DIP works."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.models.article import Article
from src.storage.base_storage import ArticleStorage


class JSONStorage(ArticleStorage):
    def __init__(self, base_path: str | Path = "data/articles"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, articles: list[Article], filename: str | None = None) -> Path:
        filename = filename or f"articles_{datetime.now():%Y%m%d_%H%M%S}.json"
        path = self.base_path / Path(filename).with_suffix(".json").name
        payload = {"total": len(articles), "articles": [a.to_dict() for a in articles]}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
