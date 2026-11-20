"""NewsFilterAgent / EnhancedFilterAgent with a scripted fake LLM."""

import json

import pytest

from src.agents.enhanced_filter_agent import EnhancedFilterAgent
from src.agents.news_filter_agent import NewsFilterAgent, normalise_judgement
from src.utils.markdown_parser import parse_articles_markdown

from .conftest import llm_message, tool_call

ARTICLES_MD = """# News Articles

---

## GPT-5 Released by OpenAI

**Source:** hackernews
**URL:** https://example.com/gpt5
**Published:** 2026-01-01 10:00
**Score:** 500

New LLM with better reasoning.

---

## New JavaScript Framework

**Source:** rss_x
**URL:** https://example.com/js
**Published:** 2026-01-01 11:00
**Score:** 3

Faster rendering.

---
"""


def verdicts(*items):
    return json.dumps(
        [
            {"id": i, "relevant": rel, "relevance_score": s, "reasoning": "r", "key_topics": t}
            for i, (rel, s, t) in enumerate(items)
        ]
    )


async def test_agent_filters_articles(fake_llm, tmp_path):
    src = tmp_path / "all.md"
    src.write_text(ARTICLES_MD, encoding="utf-8")
    out = tmp_path / "ctx" / "filtered.md"
    fake_llm.replies = [f"```json\n{verdicts((True, 10, ['LLMs']), (False, 1, []))}\n```"]

    agent = NewsFilterAgent(model="m")
    meta = await agent.execute(str(src), str(out))

    assert meta["stats"] == {"input": 2, "kept": 1, "errors": 0}
    assert len(fake_llm.calls) == 1, "both articles judged in a single batched call"
    kept = parse_articles_markdown(out.read_text(encoding="utf-8"))
    assert [k["title"] for k in kept] == ["GPT-5 Released by OpenAI"]
    assert kept[0]["source"] == "hackernews" and kept[0]["relevance_score"] == "10/10"
    assert kept[0]["key_topics"] == "LLMs"


async def test_threshold_applies_even_if_model_says_relevant(fake_llm):
    fake_llm.replies = [verdicts((True, 5, []), (True, 6, []))]
    agent = NewsFilterAgent(model="m", relevance_threshold=6)
    js = await agent.judge_articles([{"title": "a"}, {"title": "b"}])
    assert [agent.is_relevant(j) for j in js] == [False, True]


async def test_batches_and_preserves_order(fake_llm):
    fake_llm.replies = [verdicts((True, 9, []), (False, 1, [])), verdicts((True, 7, []))]
    agent = NewsFilterAgent(model="m", batch_size=2, max_concurrent=1)
    js = await agent.judge_articles([{"title": t} for t in "abc"])
    assert [j["relevance_score"] for j in js] == [9, 1, 7]
    assert len(fake_llm.calls) == 2


async def test_unparseable_reply_degrades_gracefully(fake_llm):
    fake_llm.replies = ["I cannot answer that."]
    js = await NewsFilterAgent(model="m").judge_articles([{"title": "a"}, {"title": "b"}])
    assert all(not j["relevant"] and "Failed to judge" in j["reasoning"] for j in js)


async def test_missing_ids_get_fallback(fake_llm):
    fake_llm.replies = [json.dumps([{"id": 1, "relevant": True, "relevance_score": 8}])]
    js = await NewsFilterAgent(model="m").judge_articles([{"title": "a"}, {"title": "b"}])
    assert js[0]["reasoning"] == "Missing from LLM reply" and js[1]["relevance_score"] == 8


async def test_single_judge_accepts_bare_object(fake_llm):
    fake_llm.replies = ['{"relevant": "yes", "relevance_score": "9.6", "key_topics": "a, b"}']
    j = await NewsFilterAgent(model="m")._judge_relevance({"title": "x"})
    assert j == {
        "relevant": True,
        "relevance_score": 10,
        "reasoning": "No reasoning given",
        "key_topics": ["a", "b"],
    }


@pytest.mark.parametrize(
    "raw, score",
    [
        ({"relevance_score": 42}, 10),
        ({"relevance_score": -3}, 0),
        ({"relevance_score": "x"}, 0),
        ("str", 0),
    ],
)
def test_normalise_clamps(raw, score):
    assert normalise_judgement(raw)["relevance_score"] == score


async def test_empty_input(fake_llm, tmp_path):
    src = tmp_path / "empty.md"
    src.write_text("# News Articles\n", encoding="utf-8")
    meta = await NewsFilterAgent(model="m").execute(str(src), str(tmp_path / "o.md"))
    assert meta["stats"] == {"input": 0, "kept": 0, "errors": 0} and not fake_llm.calls


async def test_tool_usage(fake_llm):
    agent = EnhancedFilterAgent(model="m")
    assert {t["function"]["name"] for t in agent.tools} == {"calculator", "web_search"}
    fake_llm.replies = [
        llm_message(tool_calls=[tool_call("c1", "calculator", '{"expression": "(95-80)/80*100"}')]),
        '{"relevant": true, "relevance_score": 8, "reasoning": "used calculator", "key_topics": ["ML"]}',
    ]
    j = await agent._judge_relevance({"title": "ML model improves accuracy from 80% to 95%"})
    assert j["relevance_score"] == 8 and j["tools_used"] == ["calculator"]
    tool_result = json.loads(fake_llm.calls[1]["messages"][-1]["content"])
    assert tool_result["result"] == 18.75


async def test_llm_errors_are_flagged_and_short(fake_llm, tmp_path):
    long_error = ValueError('provider said no\n{"error": {"code": 429, "details": "..."}}')
    fake_llm.replies = [long_error]
    src = tmp_path / "all.md"
    src.write_text(ARTICLES_MD, encoding="utf-8")
    meta = await NewsFilterAgent(model="m").execute(str(src), str(tmp_path / "o.md"))
    assert meta["stats"] == {"input": 2, "kept": 0, "errors": 2}
    j = await NewsFilterAgent(model="m").judge_articles([])  # no calls for empty input
    assert j == []


async def test_error_reasoning_is_one_line(fake_llm):
    fake_llm.replies = [ValueError("first line\nsecond line with JSON {...}")]
    (j,) = await NewsFilterAgent(model="m").judge_articles([{"title": "a"}])
    assert j["error"] is True and j["reasoning"] == "Failed to judge: ValueError: first line"
