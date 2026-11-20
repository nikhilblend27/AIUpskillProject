"""Shared pytest fixtures.

Default test run is fully offline: no network, no LLM tokens. Tests that hit
real services are marked `network` / `llm` and excluded by default
(see pyproject.toml). Run them with:  pytest -m network   or   pytest -m llm
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

# Agents require a model name even when the LLM is stubbed.
os.environ.setdefault("LITELLM_MODEL", "test/fake-model")


@pytest.fixture
def sample_article_kwargs() -> dict:
    return {
        "title": "Sample article for tests",
        "url": "https://example.com/sample",
        "published_at": datetime(2026, 1, 1, 12, 0, 0),
        "source": "test",
    }


@pytest.fixture
def make_article():
    from src.models.article import Article

    def _make(i: int = 0, **overrides: Any) -> Article:
        data = {
            "title": f"Article {i}",
            "url": f"https://example.com/{i}",
            "published_at": datetime(2026, 1, 1, 12, i % 60, tzinfo=UTC),
            "source": "test",
            "summary": f"Summary {i}",
            "score": i,
        }
        data.update(overrides)
        return Article(**data)

    return _make


@pytest.fixture
def tmp_storage(tmp_path):
    from src.storage.markdown_storage import MarkdownStorage

    return MarkdownStorage(tmp_path / "articles")


def llm_message(content: str | None = None, tool_calls: list | None = None):
    """Shape-compatible stand-in for a LiteLLM ModelResponse."""
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    msg.model_dump = lambda **_: {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments},
            }
            for c in (tool_calls or [])
        ]
        or None,
    }
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def tool_call(call_id: str, name: str, arguments: str):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace litellm.acompletion with a scripted queue of responses.

    Usage: fake_llm.replies = ["text", llm_message(...), Exception(...)]
    Strings become plain text replies; exceptions are raised.
    """
    import litellm

    state = SimpleNamespace(replies=[], calls=[])

    async def _acompletion(**kwargs):
        # Snapshot: the agent keeps appending to the same messages list.
        state.calls.append({**kwargs, "messages": list(kwargs.get("messages", []))})
        if not state.replies:
            raise AssertionError("fake_llm ran out of scripted replies")
        reply = state.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return llm_message(reply) if isinstance(reply, str) else reply

    monkeypatch.setattr(litellm, "acompletion", _acompletion)
    return state
