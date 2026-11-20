"""SummarizerAgent + WriterAgent with a fake LLM and a fake SearchSkill."""

from src.agents.summarizer_agent import OTHER_TOPIC, SummarizerAgent
from src.agents.writer_agent import WriterAgent


def article(title, topics, url=None):
    return {"title": title, "url": url or f"https://x/{title}", "topics": topics, "reasoning": "r"}


def test_grouping_uses_all_topics_and_folds_singletons():
    agent = SummarizerAgent(model="m", max_topics=4)
    groups = agent.group_by_topic(
        [
            article("a", ["AI Models", "LLMs"]),
            article("b", ["LLMs"]),
            article("c", ["llms", "Agents"]),
            article("d", ["Robotics"]),
            article("e", ["Robotics", "Vision"]),
            article("f", ["Unique"]),
            article("g", []),
        ]
    )
    assert {k: [a["title"] for a in v] for k, v in groups.items()} == {
        "LLMs": ["a", "b", "c"],
        "Robotics": ["d", "e"],
        OTHER_TOPIC: ["f", "g"],
    }


def test_grouping_respects_max_topics():
    agent = SummarizerAgent(model="m", max_topics=2)
    arts = [article(f"{t}{i}", [t]) for t in "xyz" for i in range(2)]
    assert list(agent.group_by_topic(arts)) == ["x", OTHER_TOPIC]


class FakeSkill:
    def __init__(self):
        self.queries = []

    async def search(self, query, limit=10):
        self.queries.append(query)
        return {
            "articles": [
                {"title": "Old LLM story", "url": "https://old", "source": "hn"},
                {"title": "today dup", "url": "https://x/a"},
            ]
        }


FILTERED_MD = """# Filtered

---

## a

**URL:** https://x/a
**Relevance Score:** 9/10
**Key Topics:** LLMs

body a

---

## b

**URL:** https://x/b
**Relevance Score:** 7/10
**Key Topics:** LLMs, Agents

body b

---
"""


async def test_summarizer_end_to_end_uses_search_skill(fake_llm, tmp_path):
    src, out = tmp_path / "f.md", tmp_path / "s.md"
    src.write_text(FILTERED_MD, encoding="utf-8")
    fake_llm.replies = ["LLM theme.\n- point one"]
    skill = FakeSkill()

    meta = await SummarizerAgent(model="m", search_skill=skill).execute(str(src), str(out))

    assert meta["stats"] == {"articles": 2, "topics": 1}
    assert skill.queries == ["LLMs"]
    prompt = fake_llm.calls[0]["messages"][-1]["content"]
    assert "Old LLM story" in prompt and "today dup" not in prompt
    text = out.read_text(encoding="utf-8")
    assert "## LLMs (2 articles)" in text and "- [a](https://x/a)" in text


async def test_summarizer_falls_back_to_titles_on_llm_failure(fake_llm, tmp_path):
    src, out = tmp_path / "f.md", tmp_path / "s.md"
    src.write_text(FILTERED_MD, encoding="utf-8")
    fake_llm.replies = [ValueError("boom")]
    await SummarizerAgent(model="m").execute(str(src), str(out))
    assert "- a\n- b" in out.read_text(encoding="utf-8")


async def test_writer_creates_newsletter(fake_llm, tmp_path):
    src, out = tmp_path / "s.md", tmp_path / "out" / "n.md"
    src.write_text("# Summary\n\n## LLMs (1 articles)\n\n- [a](https://x/a)\n", encoding="utf-8")
    fake_llm.replies = ["# Model Title To Strip\nIntro.\n\n## LLMs\n- [a](https://x/a)"]
    await WriterAgent(model="m").execute(str(src), str(out))
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# AI/ML Daily Newsletter — ")
    assert "Model Title To Strip" not in text and "[a](https://x/a)" in text


async def test_writer_skips_llm_when_nothing_relevant(fake_llm, tmp_path):
    src, out = tmp_path / "s.md", tmp_path / "n.md"
    src.write_text("# Summary\n\n_No relevant articles today._\n", encoding="utf-8")
    await WriterAgent(model="m").execute(str(src), str(out))
    assert "Quiet day" in out.read_text(encoding="utf-8") and not fake_llm.calls
