"""Storage abstraction (M2: Dependency Inversion).

High-level code (fetchers, orchestrator) depends on `ArticleStorage`, never
on a concrete storage class. Swapping Markdown for JSON is a one-line change
in the composition root (src/main.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.models.article import Article


class ArticleStorage(ABC):
    """Persist a batch of articles and return where they went."""

    @abstractmethod
    def save(self, articles: list[Article], filename: str | None = None) -> Path: ...
