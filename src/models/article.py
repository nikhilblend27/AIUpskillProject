"""Article data model (Milestone 1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class Article:
    """A single news item, independent of the source it came from."""

    title: str
    url: str
    published_at: datetime
    source: str
    summary: str = ""
    score: int = 0

    def __post_init__(self) -> None:
        if not self.title or not self.title.strip():
            raise ValueError("Article must have a title")
        if not self.url or not self.url.strip():
            raise ValueError("Article must have a URL")
        self.title = " ".join(self.title.split())
        self.url = self.url.strip()

    def to_markdown(self) -> str:
        """Render as a markdown section (parsed back by src.utils.markdown_parser)."""
        return (
            f"## {self.title}\n\n"
            f"**Source:** {self.source}  \n"
            f"**URL:** {self.url}  \n"
            f"**Published:** {self.published_at.strftime('%Y-%m-%d %H:%M')}  \n"
            f"**Score:** {self.score}\n\n"
            f"{self.summary}\n"
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON/DB-friendly dict (datetime -> ISO string)."""
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat()
        return data


if __name__ == "__main__":
    print(Article("Test Article", "https://example.com", datetime.now(), "test").to_markdown())
