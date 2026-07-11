"""
Evaluation Scorer — Phase 5
============================
Computes aggregate scores from workflow results.
Used by the Supervisor to quantify performance per task / round.
"""

from __future__ import annotations

import statistics
from typing import Any


def score_workflow_result(
    *,
    test_pass_rate: float = 0.0,
    lint_score: float = 0.0,
    type_check_passed: bool = True,
    security_issues_count: int = 0,
    iterations_used: int = 1,
    max_iterations: int = 5,
    weights: dict[str, float] | None = None,
) -> float:
    """Compute a weighted aggregate score from workflow dimensions.

    Default weights (sum-to-1):
      test_pass_rate     : 0.30
      lint_score         : 0.15
      type_check_passed  : 0.10
      security           : 0.10  (0 issues = 1.0, penalised linearly)
      efficiency         : 0.10  (fewer iterations = higher)
      default boost      : 0.25  (baseline for completing)

    Args:
        test_pass_rate: Fraction of tests that passed (0.0-1.0).
        lint_score: Lint quality score (0.0-1.0).
        type_check_passed: Whether type checker succeeded.
        security_issues_count: Number of flagged security issues.
        iterations_used: How many feedback-loop iterations were consumed.
        max_iterations: The hard cap on iterations.
        weights: Optional custom weight dictionary.

    Returns:
        Aggregate score 0.0 – 1.0.
    """
    _defaults = {
        "test_pass_rate": 0.30,
        "lint_score": 0.15,
        "type_check": 0.10,
        "security": 0.10,
        "efficiency": 0.10,
        "base": 0.25,
    }
    w = {**_defaults, **(weights or {})}

    security_score = max(0.0, 1.0 - security_issues_count * 0.1)
    efficiency_score = max(0.0, 1.0 - (iterations_used - 1) / max(1, max_iterations - 1))

    composite = (
        w["test_pass_rate"] * test_pass_rate
        + w["lint_score"] * lint_score
        + w["type_check"] * (1.0 if type_check_passed else 0.0)
        + w["security"] * security_score
        + w["efficiency"] * efficiency_score
        + w["base"]
    )

    return round(min(1.0, max(0.0, composite)), 4)


def aggregate_round_results(
    scores: list[float],
) -> dict[str, float]:
    """Compute summary statistics for a round's scores.

    Returns dict with: min, max, mean, median, stdev, pass_rate (≥0.7).
    """
    if not scores:
        return {"min": 0, "max": 0, "mean": 0, "median": 0, "stdev": 0, "pass_rate": 0}

    return {
        "min": round(min(scores), 4),
        "max": round(max(scores), 4),
        "mean": round(statistics.mean(scores), 4),
        "median": round(statistics.median(scores), 4),
        "stdev": round(statistics.stdev(scores) if len(scores) >= 2 else 0.0, 4),
        "pass_rate": round(sum(1 for s in scores if s >= 0.7) / len(scores), 4),
    }


def compute_round_score(
    eval_results: list["EvalResult"] | list[dict[str, Any]],
    *,
    weights: dict[str, float] | None = None,
) -> tuple[float, float, float]:
    """Compute round statistics for a batch of eval results.

    Args:
        eval_results: List of EvalResult objects or dicts.
        weights: Optional custom weight dictionary.

    Returns:
        Tuple of (mean_score, median_score, pass_rate).
    """
    if not eval_results:
        return 0.0, 0.0, 0.0

    scores: list[float] = []
    passed_count = 0
    for r in eval_results:
        # Handle both EvalResult objects and dicts
        if hasattr(r, "overall_score"):  # EvalResult object
            score = r.overall_score
            passed = r.passed
        else:  # dict
            score = float(r.get("overall_score", 0))
            passed = bool(r.get("passed", False))

        scores.append(score)
        if passed:
            passed_count += 1

    mean_score = round(statistics.mean(scores), 4)
    median_score = round(statistics.median(scores), 4)
    pass_rate = round(passed_count / len(scores), 4)

    return mean_score, median_score, pass_rate


# ============================================================
# Phase 5 Test Compatibility Functions
# ============================================================


def score_result(
    eval_result: "EvalResult" | dict[str, Any],
    weights: dict[str, float] | None = None,
) -> float:
    """Score a single evaluation result using score_workflow_result."""
    if hasattr(eval_result, "overall_score"):  # EvalResult object
        return score_workflow_result(
            test_pass_rate=eval_result.test_pass_rate,
            lint_score=eval_result.lint_score,
            type_check_passed=eval_result.type_check_passed,
            security_issues_count=eval_result.security_issues_count,
            iterations_used=eval_result.iterations_taken,
            max_iterations=5,  # Default
            weights=weights,
        )
    else:  # dict
        return score_workflow_result(
            test_pass_rate=float(eval_result.get("test_pass_rate", 0)),
            lint_score=float(eval_result.get("lint_score", 0)),
            type_check_passed=bool(eval_result.get("type_check_passed", True)),
            security_issues_count=int(eval_result.get("security_issues_count", 0)),
            iterations_used=int(eval_result.get("iterations_taken", 1)),
            max_iterations=5,
            weights=weights,
        )


def score_batch(
    eval_results: list["EvalResult"] | list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> list[float]:
    """Score multiple evaluation results."""
    return [score_result(r, weights) for r in eval_results]


class CompositeScorer:
    """Composite scorer with configurable weights."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights

    def score(self, eval_result: "EvalResult" | dict[str, Any]) -> float:
        return score_result(eval_result, self.weights)

    def score_batch(
        self, eval_results: list["EvalResult"] | list[dict[str, Any]]
    ) -> list[float]:
        return [self.score(r) for r in eval_results]
