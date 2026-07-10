"""
OptimReport Contract — Phase 5
===============================
Structured reporting data model for the full Supervisor optimisation session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TuningResult:
    """Result of prompt tuning for a single agent."""

    agent: str
    original_prompt: str
    variants: list[str]
    evaluations: list[dict[str, Any]]
    best_variant: str
    best_score: float
    best_variant_idx: int = 0
    baseline_score: float = 0.0
    improvement: float = 0.0
    tuning_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "original_prompt": self.original_prompt,
            "variants": self.variants,
            "evaluations": self.evaluations,
            "best_variant": self.best_variant,
            "best_score": self.best_score,
            "best_variant_idx": self.best_variant_idx,
            "baseline_score": self.baseline_score,
            "improvement": self.improvement,
            "tuning_cost_usd": self.tuning_cost_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TuningResult:
        return cls(
            agent=data.get("agent", ""),
            original_prompt=data.get("original_prompt", ""),
            variants=data.get("variants", []),
            evaluations=data.get("evaluations", []),
            best_variant=data.get("best_variant", ""),
            best_score=data.get("best_score", 0.0),
            best_variant_idx=data.get("best_variant_idx", 0),
            baseline_score=data.get("baseline_score", 0.0),
            improvement=data.get("improvement", 0.0),
            tuning_cost_usd=data.get("tuning_cost_usd", 0.0),
        )


@dataclass
class RoundReport:
    """One round of evaluation -> analysis -> tuning -> convergence check."""

    round_num: int = 0
    started_at: str = ""
    finished_at: str = ""

    # Evaluation results for this round
    eval_results: list[dict[str, Any]] = field(default_factory=list)

    # Aggregates
    mean_score: float = 0.0
    median_score: float = 0.0
    total_cost_usd: float = 0.0

    # Tuning outputs
    tuning_results: list[dict[str, Any]] = field(default_factory=list)

    # Model routing changes
    model_changes: list[dict[str, Any]] = field(default_factory=list)

    # Convergence flag
    converged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_num": self.round_num,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "eval_results": self.eval_results,
            "mean_score": self.mean_score,
            "median_score": self.median_score,
            "total_cost_usd": self.total_cost_usd,
            "tuning_results": self.tuning_results,
            "model_changes": self.model_changes,
            "converged": self.converged,
        }


@dataclass
class OptimReport:
    """Full optimisation session report."""

    supervisor_id: str = ""
    status: str = "running"  # running | completed | converged | budget_exceeded | error
    started_at: str = ""
    finished_at: str | None = None

    rounds: list[RoundReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def best_score(self) -> float:
        """Return the highest mean score across all rounds."""
        return max((r.mean_score for r in self.rounds), default=0.0)

    @property
    def best_round(self) -> int:
        """Return the round number with the highest mean score."""
        if not self.rounds:
            return 0
        best = max(self.rounds, key=lambda r: r.mean_score)
        return best.round_num

    @property
    def total_cost_usd(self) -> float:
        """Sum of all round costs."""
        return round(sum(r.total_cost_usd for r in self.rounds), 6)

    @property
    def total_evaluations(self) -> int:
        """Total number of individual evaluations across rounds."""
        return sum(len(r.eval_results) for r in self.rounds)

    @property
    def total_tunings(self) -> int:
        """Total number of prompt tunings performed."""
        return sum(len(r.tuning_results) for r in self.rounds)

    def add_round(self, round_report: RoundReport) -> None:
        """Append a new round report to the session."""
        self.rounds.append(round_report)

    def finalize(self, status: str) -> None:
        """Mark the report as finished."""
        self.status = status
        self.finished_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Full serialization of the session report."""
        return {
            "supervisor_id": self.supervisor_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "best_score": self.best_score,
            "best_round": self.best_round,
            "total_cost_usd": self.total_cost_usd,
            "total_evaluations": self.total_evaluations,
            "total_tunings": self.total_tunings,
            "rounds": [r.to_dict() for r in self.rounds],
            "errors": self.errors,
        }