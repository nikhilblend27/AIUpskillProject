"""Optional capability interfaces (M2: Interface Segregation).

BaseFetcher stays minimal. Sources that need more opt into these mixins
instead of forcing every fetcher to implement auth or pagination.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.article import Article


class AuthenticatedFetcher(ABC):
    """For sources that accept credentials."""

    @abstractmethod
    def get_auth_headers(self) -> dict[str, str]:
        """HTTP headers to send; empty dict means anonymous access."""


class PaginatedFetcher(ABC):
    """For sources that return results page by page."""

    @abstractmethod
    async def fetch_page(self, page: int) -> list[Article]: ...

    @abstractmethod
    def has_more_pages(self, page: int, last_page: list[Article]) -> bool: ...
