"""SummarizerAgent — filtered articles -> per-topic digest summaries (M4).

1. Group articles by shared key topics (greedy; leftovers are folded into
   "Other AI News" so we make at most `max_topics` LLM calls).
2. Optionally ask the SearchSkill (Database MCP server) for earlier coverage
   of each topic and give it to the LLM as context ("continuing story" vs new).
3. Write summary.md, keeping each article's title + URL so the WriterAgent
   can link to sources.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

from src.agents.base_agent import BaseAgent
from src.skills.search_skill import SearchSkill
from src.utils.markdown_parser import parse_articles_markdown, parse_topics

logger = logging.getLogger(__name__)

OTHER_TOPIC = "Other AI News"

SYSTEM_PROMPT = (
    "You are a precise technical editor. Summarise AI/ML news for busy engineers. "
    "Never invent facts that are not in the provided article titles and notes."
)

TOPIC_PROMPT = """Topic: {topic}

Today's articles:
{articles}
{related}
Write the digest entry for this topic:
- First, 2-3 sentences on the main theme and why it matters.
- Then 3-5 bullet points ("- ") with the key developments, naming the article each comes from.
Plain markdown only, no heading."""


class SummarizerAgent(BaseAgent):
    def __init__(
        self,
        model: str | None = None,
        search_skill: SearchSkill | None = None,
        max_topics: int = 6,
        max_concurrent: int = 2,
        **kwargs: Any,
    ):
        super().__init__(model=model, **kwargs)
        self.search_skill = search_skill
        self.max_topics = max(1, max_topics)
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent))

    async def _load_context(self, input_path: str) -> dict[str, Any]:
        articles = parse_articles_markdown(Path(input_path).read_text(encoding="utf-8"))
        for a in articles:
            a["topics"] = parse_topics(a.get("key_topics"))
            try:
                a["relevance_score"] = int(str(a.get("relevance_score", "0")).split("/")[0])
            except ValueError:
                a["relevance_score"] = 0
        return {"articles": articles}

    def group_by_topic(self, articles: list[dict[str, Any]]) -> OrderedDict[str, list]:
        """Greedy grouping over *all* key topics, capped at max_topics.

        Repeatedly pick the topic shared by the most still-ungrouped articles
        (case-insensitive), so "LLMs" catches every article tagged with it
        even when it isn't the first tag. Topics with a single article are
        folded into OTHER_TOPIC.
        """
        display: dict[str, str] = {}
        for a in articles:
            for t in a["topics"]:
                display.setdefault(t.lower(), t)

        groups: OrderedDict[str, list] = OrderedDict()
        remaining = list(articles)
        while remaining and len(groups) < self.max_topics - 1:
            counts = Counter(t.lower() for a in remaining for t in {x for x in a["topics"]})
            if not counts:
                break
            best, n = max(counts.items(), key=lambda kv: (kv[1], -len(kv[0])))
            if n < 2:
                break
            members = [a for a in remaining if best in {t.lower() for t in a["topics"]}]
            groups[display[best]] = members
            remaining = [a for a in remaining if a not in members]
        if remaining:
            groups[OTHER_TOPIC] = remaining
        return groups

    async def _process(self, context: dict[str, Any]) -> dict[str, Any]:
        articles = context["articles"]
        if not articles:
            return {"topics": OrderedDict(), "summaries": {}, "total_articles": 0, "stats": {}}

        groups = self.group_by_topic(articles)
        topics = list(groups)
        summaries = await asyncio.gather(*(self._summarize_topic(t, groups[t]) for t in topics))
        return {
            "topics": groups,
            "summaries": dict(zip(topics, summaries, strict=False)),
            "total_articles": len(articles),
            "stats": {"articles": len(articles), "topics": len(topics)},
        }

    async def _related_context(self, topic: str, articles: list[dict[str, Any]]) -> str:
        if not self.search_skill or topic == OTHER_TOPIC:
            return ""
        today = {a.get("url") for a in articles}
        hits = await self.search_skill.search(topic, limit=8)
        earlier = [h for h in hits.get("articles", []) if h.get("url") not in today][:5]
        if not earlier:
            return ""
        lines = "\n".join(f"- {h['title']} ({h.get('source', '')})" for h in earlier)
        return f"\nEarlier coverage in our database (for context only):\n{lines}\n"

    async def _summarize_topic(self, topic: str, articles: list[dict[str, Any]]) -> str:
        listing = "\n".join(
            f"- {a['title']} — {a.get('reasoning', '')} {a.get('summary', '')[:200]}".rstrip()
            for a in articles
        )
        related = await self._related_context(topic, articles)
        prompt = TOPIC_PROMPT.format(topic=topic, articles=listing, related=related)
        async with self._semaphore:
            try:
                return (await self._call_llm(prompt, SYSTEM_PROMPT)).strip()
            except Exception as exc:  # noqa: BLE001 — fall back to a plain list
                logger.warning("Summary for %s failed: %s", topic, exc)
                return "\n".join(f"- {a['title']}" for a in articles)

    async def _save_result(self, result: dict[str, Any], output_path: str) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        parts = [
            "# AI/ML Daily Digest — Summary\n\n",
            f"**Total Articles:** {result['total_articles']}  \n",
            f"**Topics:** {len(result['summaries'])}\n\n---\n\n",
        ]
        for topic, summary in result["summaries"].items():
            items = result["topics"][topic]
            parts.append(f"## {topic} ({len(items)} articles)\n\n{summary}\n\n**Sources:**\n\n")
            parts.extend(f"- [{a['title']}]({a.get('url', '')})\n" for a in items)
            parts.append("\n---\n\n")
        if not result["summaries"]:
            parts.append("_No relevant articles today._\n")
        path.write_text("".join(parts), encoding="utf-8")
