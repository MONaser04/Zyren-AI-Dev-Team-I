"""
Optimisation Convergence Detection — Phase 5
=============================================
Determines when the optimisation loop should stop because scores
have plateaued (further rounds unlikely to yield meaningful gains).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.contracts.eval_result import EvalResult

logger = logging.getLogger(__name__)


@dataclass
class ConvergenceConfig:
    """Configuration for convergence detection."""

    min_samples: int = 3          # Minimum rounds before checking
    window_size: int = 3          # Rolling window for trend calculation
    improvement_threshold: float = 0.02  # Min improvement ratio to continue
    patience: int = 2             # Rounds with no improvement before stopping
    min_score: float = 0.7        # Minimum acceptable score (don't stop below this)
    max_rounds: int = 10          # Absolute maximum rounds (hard cap)


@dataclass
class ConvergenceResult:
    """Output of a convergence check."""

    converged: bool
    improvement: float            # Delta between this round and previous
    patience_counter: int         # How many rounds with no improvement
    trend: str                    # "improving", "stable", "declining"
    recommendation: str           # Human-readable recommendation


def check_convergence(
    eval_results: list[EvalResult],
    config: ConvergenceConfig,
    *,
    previous_best_score: float = 0.0,
    patience_counter: int = 0,
    current_round: int = 1,
) -> ConvergenceResult:
    """Check whether optimisation should stop based on score trends.

    Args:
        eval_results: Results from the current round.
        config: Convergence thresholds.
        previous_best_score: Best mean score from all prior rounds.
        patience_counter: Current count of rounds with no improvement.
        current_round: The current round number (1-indexed).

    Returns:
        ConvergenceResult with converged flag and reasoning.
    """
    if not eval_results:
        return ConvergenceResult(
            converged=False,
            improvement=0.0,
            patience_counter=patience_counter,
            trend="unknown",
            recommendation="No results to evaluate.",
        )

    # Hard cap
    if current_round >= config.max_rounds:
        return ConvergenceResult(
            converged=True,
            improvement=0.0,
            patience_counter=patience_counter,
            trend="stable",
            recommendation=f"Reached maximum rounds ({config.max_rounds}). Stopping.",
        )

    scores = [r.overall_score for r in eval_results]
    current_mean = sum(scores) / len(scores)
    improvement = round(current_mean - previous_best_score, 4)

    # Not enough data yet
    if current_round < config.min_samples:
        return ConvergenceResult(
            converged=False,
            improvement=improvement,
            patience_counter=0,
            trend="collecting" if current_round < config.min_samples else "evaluating",
            recommendation=f"Need at least {config.min_samples} rounds before convergence check.",
        )

    # Determine trend
    if improvement > config.improvement_threshold:
        trend = "improving"
        new_patience = 0  # Reset patience on improvement
    elif improvement < -config.improvement_threshold:
        trend = "declining"
        new_patience = patience_counter + 1
    else:
        trend = "stable"
        new_patience = patience_counter + 1

    # Convergence decision
    if new_patience >= config.patience and current_mean >= config.min_score:
        return ConvergenceResult(
            converged=True,
            improvement=improvement,
            patience_counter=new_patience,
            trend=trend,
            recommendation=(
                f"Converged after {current_round} rounds: "
                f"mean score {current_mean:.3f} with {new_patience} rounds "
                f"of no significant improvement (threshold={config.improvement_threshold})."
            ),
        )

    if current_mean < config.min_score:
        # Don't stop if below minimum threshold even if plateaued
        return ConvergenceResult(
            converged=False,
            improvement=improvement,
            patience_counter=new_patience,
            trend=trend,
            recommendation=(
                f"Plateau detected but mean score ({current_mean:.3f}) is below "
                f"minimum threshold ({config.min_score}). Continue optimising."
            ),
        )

    return ConvergenceResult(
        converged=False,
        improvement=improvement,
        patience_counter=new_patience,
        trend=trend,
        recommendation=(
            f"Still optimising: improvement={improvement:.4f}, "
            f"patience={new_patience}/{config.patience}, "
            f"mean_score={current_mean:.3f}."
        ),
    )


def should_continue(
    eval_results: list[EvalResult],
    config: ConvergenceConfig,
    **kwargs: Any,
) -> tuple[bool, ConvergenceResult]:
    """Convenience: returns (should_continue, result)."""
    result = check_convergence(eval_results, config, **kwargs)
    return (not result.converged), result