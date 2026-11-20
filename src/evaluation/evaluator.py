"""Evaluate NewsFilterAgent on the hand-labelled golden dataset (M5).

Reports accuracy, precision, recall, F1, the confusion matrix and the mean
absolute error of the 0-10 relevance score.

    python src/evaluation/evaluator.py     # or: python -m src.evaluation.evaluator
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import config  # noqa: E402
from src.agents.news_filter_agent import NewsFilterAgent  # noqa: E402
from src.utils.console import setup_console  # noqa: E402


def calculate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Binary classification metrics; 'positive' = relevant.

    Cases where the LLM gave no answer (`error=True`) are excluded and counted
    separately — scoring them as "not relevant" would silently deflate recall.
    """
    errors = sum(1 for r in results if r.get("error"))
    results = [r for r in results if not r.get("error")]
    tp = sum(1 for r in results if r["expected"] and r["predicted"])
    fp = sum(1 for r in results if not r["expected"] and r["predicted"])
    fn = sum(1 for r in results if r["expected"] and not r["predicted"])
    tn = sum(1 for r in results if not r["expected"] and not r["predicted"])
    total = len(results)

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    scored = [r for r in results if r.get("expected_score") is not None]
    mae = (
        sum(abs(r["score"] - r["expected_score"]) for r in scored) / len(scored) if scored else None
    )
    return {
        "accuracy": (tp + tn) / total if total else 0.0,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "score_mae": mae,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "correct": tp + tn,
        "total": total,
        "errors": errors,
    }


class FilterEvaluator:
    def __init__(
        self,
        golden_dataset_path: str | Path = config.GOLDEN_DATASET_FILE,
        agent: NewsFilterAgent | None = None,
    ):
        self.golden_dataset_path = Path(golden_dataset_path)
        self.dataset = json.loads(self.golden_dataset_path.read_text(encoding="utf-8"))
        threshold = int(self.dataset.get("relevance_threshold", 6))
        self.agent = agent or NewsFilterAgent(relevance_threshold=threshold)

    async def evaluate(self) -> dict[str, Any]:
        cases = self.dataset["test_cases"]
        judgements = await self.agent.judge_articles(
            [{"title": c["title"], "summary": c.get("summary", "")} for c in cases]
        )
        results = []
        for case, j in zip(cases, judgements, strict=False):
            predicted = self.agent.is_relevant(j)
            results.append(
                {
                    "test_case_id": case["id"],
                    "title": case["title"],
                    "expected": bool(case["expected_relevant"]),
                    "predicted": predicted,
                    "correct": predicted == bool(case["expected_relevant"]),
                    "score": j["relevance_score"],
                    "expected_score": case.get("expected_score"),
                    "reasoning": j["reasoning"],
                    "label_reason": case.get("reason", ""),
                    "error": bool(j.get("error")),
                }
            )
        return {
            "results": results,
            "metrics": calculate_metrics(results),
            "test_cases": len(cases),
            "model": self.agent.model,
            "threshold": self.agent.relevance_threshold,
            "llm_calls": self.agent.llm_calls,
        }

    async def save_report(self, evaluation: dict[str, Any], output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        m, c = evaluation["metrics"], evaluation["metrics"]["confusion"]
        mae = f"{m['score_mae']:.2f}" if m["score_mae"] is not None else "n/a"
        lines = [
            "# NewsFilterAgent — Evaluation Report\n",
            f"- **Date:** {datetime.now():%Y-%m-%d %H:%M}",
            f"- **Model:** `{evaluation['model']}`",
            f"- **Dataset:** `{self.golden_dataset_path.name}` "
            f"(v{self.dataset.get('version', '?')}, {evaluation['test_cases']} cases)",
            f"- **Relevance threshold:** {evaluation['threshold']}/10\n",
        ]
        if m["errors"]:
            lines.append(
                f"> ⚠️ **Incomplete run:** {m['errors']} of {evaluation['test_cases']} cases got no "
                "answer from the LLM (provider error or quota) and are excluded from the metrics "
                "below. Re-run the evaluator for a complete result.\n"
            )
        lines += [
            "## Metrics\n",
            "| Metric | Value |",
            "|---|---|",
            f"| Accuracy | {m['accuracy']:.1%} ({m['correct']}/{m['total']}) |",
            f"| Precision | {m['precision']:.1%} |",
            f"| Recall | {m['recall']:.1%} |",
            f"| F1 score | {m['f1_score']:.3f} |",
            f"| Score MAE (0-10) | {mae} |\n",
            "## Confusion matrix\n",
            "| | Predicted relevant | Predicted not relevant |",
            "|---|---|---|",
            f"| **Actually relevant** | {c['tp']} (TP) | {c['fn']} (FN) |",
            f"| **Actually not relevant** | {c['fp']} (FP) | {c['tn']} (TN) |\n",
            "## Per-case results\n",
            "| # | Result | Title | Expected | Predicted (score) | Model reasoning |",
            "|---|---|---|---|---|---|",
        ]
        for r in evaluation["results"]:
            mark = "⚠️ no answer" if r.get("error") else ("✅" if r["correct"] else "❌")
            lines.append(
                f"| {r['test_case_id']} | {mark} | {r['title']} | "
                f"{'Relevant' if r['expected'] else 'Not'} ({r['expected_score']}) | "
                f"{'Relevant' if r['predicted'] else 'Not'} ({r['score']}) | "
                f"{r['reasoning'].replace('|', '/')} |"
            )
        failures = [r for r in evaluation["results"] if not r["correct"] and not r.get("error")]
        lines.append("\n## Failure analysis\n")
        if failures:
            for r in failures:
                kind = "False positive" if r["predicted"] else "False negative"
                lines.append(
                    f"- **#{r['test_case_id']} {kind}:** {r['title']} — label says "
                    f"\"{r['label_reason']}\"; model said \"{r['reasoning']}\"."
                )
        else:
            lines.append("No misclassifications on this dataset.")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


async def run_evaluation() -> dict[str, Any]:
    evaluator = FilterEvaluator()
    evaluation = await evaluator.evaluate()
    m = evaluation["metrics"]
    print(f"📊 Evaluated {m['total']}/{evaluation['test_cases']} cases with {evaluation['model']}")
    print(f"   Accuracy  {m['accuracy']:.1%}")
    print(f"   Precision {m['precision']:.1%}")
    print(f"   Recall    {m['recall']:.1%}")
    print(f"   F1        {m['f1_score']:.3f}")
    if m["errors"]:
        print(
            f"⚠️  {m['errors']} cases got no LLM answer and were excluded — "
            "the report is marked incomplete. Re-run when your provider/quota allows."
        )
    path = await evaluator.save_report(evaluation, config.EVALUATION_REPORT_FILE)
    print(f"💾 Report: {path}")
    return evaluation


if __name__ == "__main__":
    setup_console()
    asyncio.run(run_evaluation())
