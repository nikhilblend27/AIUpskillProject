"""Evaluator metrics + report generation (fake agent — no LLM)."""

import json

import pytest

from src import config
from src.agents.news_filter_agent import NewsFilterAgent
from src.evaluation.evaluator import FilterEvaluator, calculate_metrics


def r(expected, predicted, score=5, expected_score=5):
    return {
        "expected": expected,
        "predicted": predicted,
        "score": score,
        "expected_score": expected_score,
    }


def test_metrics_known_values():
    # TP=2, FN=1, FP=1, TN=1
    m = calculate_metrics(
        [r(True, True), r(True, True), r(True, False), r(False, True), r(False, False)]
    )
    assert m["confusion"] == {"tp": 2, "fp": 1, "fn": 1, "tn": 1}
    assert m["accuracy"] == pytest.approx(0.6)
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["f1_score"] == pytest.approx(2 / 3)


def test_metrics_edge_cases():
    m = calculate_metrics([r(False, False, score=3, expected_score=1)])
    assert m["precision"] == m["recall"] == m["f1_score"] == 0.0
    assert m["accuracy"] == 1.0 and m["score_mae"] == 2
    assert calculate_metrics([])["accuracy"] == 0.0


def test_golden_dataset_is_well_formed():
    data = json.loads(config.GOLDEN_DATASET_FILE.read_text(encoding="utf-8"))
    cases = data["test_cases"]
    assert len(cases) >= 10 and len({c["id"] for c in cases}) == len(cases)
    assert {True, False} <= {c["expected_relevant"] for c in cases}
    for c in cases:
        assert c["title"] and isinstance(c["expected_relevant"], bool)
        assert (c["expected_score"] >= 6) == c["expected_relevant"], c["id"]


class OracleAgent(NewsFilterAgent):
    """Answers from the labels, except it gets case #2 wrong."""

    def __init__(self, cases):
        super().__init__(model="fake")
        self.cases = {c["title"]: c for c in cases}

    async def judge_articles(self, articles):
        out = []
        for a in articles:
            c = self.cases[a["title"]]
            relevant = c["expected_relevant"] if c["id"] != 2 else True
            out.append(
                {
                    "relevant": relevant,
                    "relevance_score": 9 if relevant else 1,
                    "reasoning": "oracle",
                    "key_topics": [],
                }
            )
        return out


async def test_evaluate_and_report(tmp_path):
    cases = json.loads(config.GOLDEN_DATASET_FILE.read_text(encoding="utf-8"))["test_cases"]
    evaluator = FilterEvaluator(agent=OracleAgent(cases))
    evaluation = await evaluator.evaluate()
    m = evaluation["metrics"]
    assert m["total"] == len(cases) and m["correct"] == len(cases) - 1
    assert m["confusion"]["fp"] == 1 and m["recall"] == 1.0

    path = await evaluator.save_report(evaluation, tmp_path / "report.md")
    text = path.read_text(encoding="utf-8")
    assert "| Accuracy |" in text and "False positive" in text and "#2" in text


def test_errored_cases_are_excluded_from_metrics():
    results = [r(True, True), {**r(True, False), "error": True}]
    m = calculate_metrics(results)
    assert m["total"] == 1 and m["errors"] == 1 and m["recall"] == 1.0


async def test_incomplete_run_is_flagged_in_report(tmp_path):
    cases = json.loads(config.GOLDEN_DATASET_FILE.read_text(encoding="utf-8"))["test_cases"]

    class HalfBroken(OracleAgent):
        async def judge_articles(self, articles):
            out = await super().judge_articles(articles)
            for j in out[10:]:
                j.update(relevant=False, relevance_score=0, error=True, reasoning="Failed")
            return out

    evaluator = FilterEvaluator(agent=HalfBroken(cases))
    evaluation = await evaluator.evaluate()
    assert evaluation["metrics"]["errors"] == len(cases) - 10
    assert evaluation["metrics"]["total"] == 10
    text = (await evaluator.save_report(evaluation, tmp_path / "r.md")).read_text("utf-8")
    assert "Incomplete run" in text and "⚠️ no answer" in text
