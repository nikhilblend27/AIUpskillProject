"""NewsFilterAgent + function calling (M3, Evening 13).

Each article is judged with the calculator and web_search tools available.
The model decides whether to call them; `_call_llm_with_tools` runs the loop.
Judged one article per call (tool loops don't batch well), so prefer the
plain NewsFilterAgent for big runs.
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.news_filter_agent import (
    SYSTEM_PROMPT,
    NewsFilterAgent,
    _fallback,
    normalise_judgement,
    short_error,
)
from src.tools.calculator import CALCULATOR_SCHEMA, calculator
from src.tools.web_search import WEB_SEARCH_SCHEMA, web_search
from src.utils.llm_json import extract_json

logger = logging.getLogger(__name__)

TOOL_PROMPT = """Judge whether this article is relevant to AI/ML.

Title: {title}
Summary: {summary}

You may call tools if they genuinely help:
- calculator: for any arithmetic (e.g. percentage changes mentioned in the summary)
- web_search: to look up an unfamiliar product or term

When finished, reply with ONLY this JSON:
{{"relevant": true|false, "relevance_score": 0-10, "reasoning": "<mention any tool you used>", \
"key_topics": ["topic"]}}"""


class EnhancedFilterAgent(NewsFilterAgent):
    def __init__(self, model: str | None = None, **kwargs: Any):
        super().__init__(model=model, tools=[CALCULATOR_SCHEMA, WEB_SEARCH_SCHEMA], **kwargs)
        self.register_tool_function("calculator", calculator)
        self.register_tool_function("web_search", web_search)

    async def judge_articles(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [await self._judge_relevance(a) for a in articles]

    async def _judge_relevance(self, article: dict[str, Any]) -> dict[str, Any]:
        prompt = TOOL_PROMPT.format(
            title=article.get("title", ""), summary=(article.get("summary") or "n/a")[:600]
        )
        try:
            reply = await self._call_llm_with_tools(prompt, SYSTEM_PROMPT)
            judgement = normalise_judgement(extract_json(reply))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Enhanced judge failed: %s", short_error(exc))
            return _fallback(f"Failed to judge: {short_error(exc)}")
        judgement["tools_used"] = [t["tool"] for t in getattr(self, "tool_trace", [])]
        return judgement
