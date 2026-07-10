"""
Orchestrator Convergence Integration — Phase 5
===============================================
Integrates the ConvergenceDetector into the orchestration loop.
Provides per-workflow convergence tracking.
"""

from __future__ import annotations

from typing import Any

from optim.convergence import ConvergenceConfig, ConvergenceDetector, ConvergenceResult
from src.contracts.eval_result import EvalResult


class OrchestratorConvergence:
    """Manages convergence detection for a single workflow run."""

    def __init__(self, config: ConvergenceConfig | None = None) -> None:
        self.detector = ConvergenceDetector(config)

    # ------------------------------------------------------------------
    # Check after each iteration
    # ------------------------------------------------------------------
    def check(self, eval_result: EvalResult) -> ConvergenceResult:
        """Record evaluation result and check convergence."""
        return self.detector.record(eval_result)

    # ------------------------------------------------------------------
    # Reset for new workflow
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset detector for new workflow."""
        self.detector.reset()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        """Get convergence status."""
        return self.detector.status()


def create_convergence_manager(
    min_samples: int = 3,
    window_size: int = 3,
    improvement_threshold: float = 0.02,
    patience: int = 2,
    min_score: float = 0.7,
) -> OrchestratorConvergence:
    """Factory for orchestrator convergence with sensible defaults."""
    config = ConvergenceConfig(
        min_samples=min_samples,
        window_size=window_size,
        improvement_threshold=improvement_threshold,
        patience=patience,
        min_score=min_score,
    )
    return OrchestratorConvergence(config)