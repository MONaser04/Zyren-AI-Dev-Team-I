"""
Feedback Analyser — Phase 5
============================
Analyses evaluation results to extract patterns, root causes, and
actionable recommendations for the tuner and supervisor.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from optim.feedback_store import FeedbackStore
from src.contracts.eval_result import EvalResult

logger = logging.getLogger(__name__)


# ── Analysis Result ────────────────────────────────────────────────────────────


def analyse_round(
    eval_results: list[EvalResult],
    feedback_store: FeedbackStore | None = None,
) -> dict[str, Any]:
    """Analyse a batch of evaluation results and produce a structured report.

    Returns a dict with:
      - summary        : aggregate statistics
      - weaknesses     : top failing dimensions
      - error_patterns : recurring errors from feedback store
      - recommendations: suggested actions for next round
    """
    if not eval_results:
        return {
            "summary": {"total": 0, "passed": 0, "failed": 0, "mean_score": 0.0},
            "weaknesses": [],
            "error_patterns": [],
            "recommendations": [],
        }

    total = len(eval_results)
    passed = sum(1 for r in eval_results if r.passed)
    failed = total - passed
    scores = [r.overall_score for r in eval_results]

    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "mean_score": round(sum(scores) / total, 4),
        "total_cost_usd": round(sum(r.total_cost_usd for r in eval_results), 6),
        "mean_iterations": round(sum(r.iterations_taken for r in eval_results) / total, 2),
    }

    # ── Weaknesses: which dimensions drag scores down ──────────────────────────
    weaknesses: list[dict[str, Any]] = []
    low_test_counter = sum(1 for r in eval_results if r.test_pass_rate < 0.7)
    low_lint_counter = sum(1 for r in eval_results if r.lint_score < 0.7)
    type_failures = sum(1 for r in eval_results if not r.type_check_passed)
    security_flags = sum(r.security_issues_count for r in eval_results)

    if low_test_counter > total * 0.3:
        weaknesses.append(
            {
                "dimension": "test_pass_rate",
                "affected_count": low_test_counter,
                "severity": "high",
                "suggestion": "Focus prompt tuning on coder and tester agents.",
            }
        )
    if low_lint_counter > total * 0.3:
        weaknesses.append(
            {
                "dimension": "lint_score",
                "affected_count": low_lint_counter,
                "severity": "medium",
                "suggestion": "Add explicit linting instructions to coder prompt.",
            }
        )
    if type_failures > 0:
        weaknesses.append(
            {
                "dimension": "type_check",
                "affected_count": type_failures,
                "severity": "medium",
                "suggestion": "Instruct coder to add type annotations; verify with mypy.",
            }
        )
    if security_flags > 0:
        weaknesses.append(
            {
                "dimension": "security",
                "affected_count": security_flags,
                "severity": "high" if security_flags > total else "medium",
                "suggestion": "Enable security agent in workflow; add security constraints.",
            }
        )

    # ── Error Patterns ─────────────────────────────────────────────────────────
    error_patterns: list[dict[str, Any]] = []
    if feedback_store:
        error_patterns = feedback_store.get_error_patterns(min_count=2)

    # ── Recommendations ────────────────────────────────────────────────────────
    recommendations: list[str] = []

    if summary["mean_score"] < 0.5:
        recommendations.append(
            "Overall score is low — consider full prompt overhaul for all agents."
        )
    if summary["mean_iterations"] > 3:
        recommendations.append(
            "High iteration count suggests inefficient feedback loop — tune critic prompt."
        )
    if summary["total_cost_usd"] > 2.0:
        recommendations.append(
            "Cost per round is high — review model routing; downgrade simple tasks to 'fast' tier."
        )

    for w in weaknesses:
        if w.get("suggestion"):
            recommendations.append(w["suggestion"])

    if not weaknesses and summary["mean_score"] >= 0.85:
        recommendations.append(
            "Performance is strong across all dimensions. Minor tuning for edge cases only."
        )

    return {
        "summary": summary,
        "weaknesses": weaknesses,
        "error_patterns": error_patterns,
        "recommendations": list(dict.fromkeys(recommendations)),  # deduplicate
    }


def extract_issue_frequencies(
    eval_results: list[EvalResult],
) -> dict[str, int]:
    """Count how often each issue message appears across results."""
    counter: Counter[str] = Counter()
    for r in eval_results:
        for issue in r.issues:
            counter[issue] += 1
    return dict(counter.most_common(20))


def compute_improvement_delta(
    previous_scores: list[float],
    current_scores: list[float],
) -> float:
    """Compute mean score improvement from previous to current round.

    Returns:
        Delta (current_mean - previous_mean). Positive = improvement.
    """
    prev_mean = sum(previous_scores) / len(previous_scores) if previous_scores else 0.0
    curr_mean = sum(current_scores) / len(current_scores) if current_scores else 0.0
    return round(curr_mean - prev_mean, 4)