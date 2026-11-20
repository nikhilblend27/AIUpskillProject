"""NewsFilterAgent — keep only AI/ML-relevant articles (M3).

Design notes
------------
* Articles are judged in batches (default 10 per LLM call). Free-tier
  providers allow only a handful of requests per minute, and batching also
  cuts cost ~10x. `_judge_relevance(article)` is still available for one-off
  use and for the evaluator.
* Every judgement is normalised (types coerced, score clamped 0-10). If the
  LLM output can't be parsed the article is marked "not relevant" with the
  error as reasoning — one bad reply never crashes the pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from src.agents.base_agent import BaseAgent
from src.utils.llm_json import extract_json
from src.utils.markdown_parser import parse_articles_markdown

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert AI/ML news analyst curating a daily digest for \
software engineers who work with AI.

RELEVANT (score 6-10): machine learning, deep learning, LLMs and foundation models, \
AI agents, neural networks, computer vision, NLP, speech, generative AI (image/video/audio), \
AI research papers, AI infrastructure (GPUs/TPUs for training or inference, ML tooling), \
AI products and applications, AI policy, ethics, safety and regulation, notable AI company news.

NOT RELEVANT (score 0-5): general programming, web/mobile development, DevOps, databases, \
security, hardware, gadgets or business news with no meaningful AI angle. A product that \
merely mentions "AI" in passing scores 3-5.

Scoring: 9-10 core AI development or major release; 7-8 clear AI application or research; \
6 AI is a substantial but secondary theme; 0-5 not about AI.
Judge only from the title and summary given. Be consistent and concise."""

BATCH_PROMPT = """Judge each article below. Return ONLY a JSON array with exactly one object \
per article, in the same order, each with this shape:
{{"id": <article id>, "relevant": true|false, "relevance_score": 0-10, \
"reasoning": "<one short sentence>", "key_topics": ["<1-3 short topic labels>"]}}

Examples:
- "GPT-5 released with better reasoning" -> {{"relevant": true, "relevance_score": 10, \
"reasoning": "Major LLM release", "key_topics": ["LLMs"]}}
- "New JavaScript framework hits 1.0" -> {{"relevant": false, "relevance_score": 1, \
"reasoning": "Web development, not AI", "key_topics": ["Web Development"]}}

Articles:
{articles}"""


def short_error(exc: BaseException) -> str:
    """One-line error text — provider errors often embed a whole JSON body."""
    first = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {first[:160]}".rstrip(": ")


def _fallback(reason: str) -> dict[str, Any]:
    """Judgement used when the LLM gave no usable answer.

    `error=True` lets callers (pipeline stats, evaluator) tell "the model said
    no" apart from "we never got an answer".
    """
    return {
        "relevant": False,
        "relevance_score": 0,
        "reasoning": reason,
        "key_topics": [],
        "error": True,
    }


def normalise_judgement(raw: Any) -> dict[str, Any]:
    """Coerce an LLM judgement into a predictable shape."""
    if not isinstance(raw, dict):
        return _fallback("Malformed judgement")
    try:
        score = int(round(float(raw.get("relevance_score", 0))))
    except (TypeError, ValueError):
        score = 0
    relevant = raw.get("relevant", False)
    if isinstance(relevant, str):
        relevant = relevant.strip().lower() in {"true", "yes", "1"}
    topics = raw.get("key_topics") or []
    if isinstance(topics, str):
        topics = [t.strip() for t in topics.split(",")]
    return {
        "relevant": bool(relevant),
        "relevance_score": max(0, min(10, score)),
        "reasoning": str(raw.get("reasoning") or "").strip() or "No reasoning given",
        "key_topics": [str(t).strip() for t in topics if str(t).strip()][:5],
    }


class NewsFilterAgent(BaseAgent):
    def __init__(
        self,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        relevance_threshold: int = 6,
        batch_size: int = 10,
        max_concurrent: int = 2,
        **kwargs: Any,
    ):
        super().__init__(model=model, tools=tools, **kwargs)
        self.relevance_threshold = relevance_threshold
        self.batch_size = max(1, batch_size)
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent))

    def is_relevant(self, judgement: dict[str, Any]) -> bool:
        return (
            bool(judgement["relevant"]) and judgement["relevance_score"] >= self.relevance_threshold
        )

    # -- Template Method steps ---------------------------------------------
    async def _load_context(self, input_path: str) -> dict[str, Any]:
        content = Path(input_path).read_text(encoding="utf-8")
        articles = parse_articles_markdown(content)
        logger.info("Loaded %d articles from %s", len(articles), input_path)
        return {"articles": articles}

    async def _process(self, context: dict[str, Any]) -> dict[str, Any]:
        articles: list[dict[str, Any]] = context["articles"]
        judgements = await self.judge_articles(articles)

        judged = [{**a, **j} for a, j in zip(articles, judgements, strict=False)]
        kept = sorted(
            (a for a in judged if self.is_relevant(a)),
            key=lambda a: a["relevance_score"],
            reverse=True,
        )
        errors = sum(1 for j in judged if j.get("error"))
        if errors:
            logger.warning("%d/%d articles could not be judged (LLM errors)", errors, len(judged))
        return {
            "filtered_articles": kept,
            "all_judgements": judged,
            "total_input": len(articles),
            "total_output": len(kept),
            "stats": {"input": len(articles), "kept": len(kept), "errors": errors},
        }

    async def _save_result(self, result: dict[str, Any], output_path: str) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        total_in, total_out = result["total_input"], result["total_output"]
        rate = (total_out / total_in * 100) if total_in else 0.0

        parts = [
            "# Filtered AI/ML Articles\n\n",
            f"**Total Input:** {total_in}  \n",
            f"**Total Output:** {total_out}  \n",
            f"**Keep Rate:** {rate:.1f}%  \n",
            f"**Threshold:** {self.relevance_threshold}/10\n\n---\n\n",
        ]
        for a in result["filtered_articles"]:
            parts.append(
                f"## {a['title']}\n\n"
                f"**Source:** {a.get('source', 'unknown')}  \n"
                f"**URL:** {a.get('url', '')}  \n"
                f"**Published:** {a.get('published', '')}  \n"
                f"**Score:** {a.get('score', 0)}  \n"
                f"**Relevance Score:** {a['relevance_score']}/10  \n"
                f"**Reasoning:** {a['reasoning']}  \n"
                f"**Key Topics:** {', '.join(a['key_topics'])}\n\n"
                f"{a.get('summary', '')}\n\n---\n\n"
            )
        path.write_text("".join(parts), encoding="utf-8")
        logger.info("Saved %d/%d articles to %s", total_out, total_in, path)

    # -- judging -----------------------------------------------------------
    async def judge_articles(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Judge all articles (batched, limited concurrency). Order is preserved."""
        batches = [
            articles[i : i + self.batch_size] for i in range(0, len(articles), self.batch_size)
        ]
        results = await asyncio.gather(*(self._judge_batch(b) for b in batches))
        return [j for batch in results for j in batch]

    async def _judge_relevance(self, article: dict[str, Any]) -> dict[str, Any]:
        """Judge a single article."""
        return (await self._judge_batch([article]))[0]

    async def _judge_batch(self, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        listing = "\n\n".join(
            f"[id={i}] Title: {a.get('title', '')}\nSummary: {(a.get('summary') or 'n/a')[:400]}"
            for i, a in enumerate(batch)
        )
        async with self._semaphore:
            try:
                reply = await self._call_llm(BATCH_PROMPT.format(articles=listing), SYSTEM_PROMPT)
                data = extract_json(reply)
            except Exception as exc:  # noqa: BLE001 — degrade, don't crash
                logger.warning("Batch of %d failed: %s", len(batch), exc)
                return [_fallback(f"Failed to judge: {short_error(exc)}") for _ in batch]

        if isinstance(data, dict):  # single object for a batch of one
            data = [data]
        by_id: dict[int, Any] = {}
        for pos, item in enumerate(data if isinstance(data, list) else []):
            key = item.get("id", pos) if isinstance(item, dict) else pos
            try:
                by_id[int(key)] = item
            except (TypeError, ValueError):
                by_id[pos] = item
        return [
            normalise_judgement(by_id[i]) if i in by_id else _fallback("Missing from LLM reply")
            for i in range(len(batch))
        ]
