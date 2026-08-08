"""
EvalResult Contract — Phase 5
=============================
Structured record representing the outcome of a single evaluation task
run through the Zyren pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalIssue:
    """A single issue found during evaluation."""
    source: str = ""           # e.g., "pytest", "mypy", "ruff", "bandit"
    severity: str = "warning"  # "info", "warning", "error", "critical"
    message: str = ""          # Human-readable description


@dataclass
class EvalResult:
    """Outcome from running one golden task through the full pipeline.

    Attributes:
        workflow_id: ID of the workflow instance that was evaluated.
        task_id: ID of the golden / SWE-bench task.
        passed: Whether the evaluation passed overall threshold.
        overall_score: Aggregate weighted score (0.0-1.0).
        test_pass_rate: Fraction of correctness tests passed.
        lint_score: Lint analysis score (1.0 = clean).
        type_check_passed: Whether type checking passed.
        security_issues_count: Number of security vulnerabilities detected.
        iterations_taken: How many orchestration iterations were needed.
        total_cost_usd: Total LLM cost for this workflow run.
        issues: List of issue messages from agents or evaluators.
        metadata: Arbitrary additional data (SWE-bench info, etc.).
    """

    workflow_id: str = ""
    task_id: str = ""
    passed: bool = False
    overall_score: float = 0.0
    test_pass_rate: float = 0.0
    lint_score: float = 1.0
    type_check_passed: bool = True
    security_issues_count: int = 0
    iterations_taken: int = 1
    total_cost_usd: float = 0.0
    issues: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result to a plain dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "passed": self.passed,
            "overall_score": self.overall_score,
            "test_pass_rate": self.test_pass_rate,
            "lint_score": self.lint_score,
            "type_check_passed": self.type_check_passed,
            "security_issues_count": self.security_issues_count,
            "iterations_taken": self.iterations_taken,
            "total_cost_usd": self.total_cost_usd,
            "issues": self.issues,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalResult:
        """Reconstruct an EvalResult from a dictionary."""
        return cls(
            workflow_id=data.get("workflow_id", ""),
            task_id=data.get("task_id", ""),
            passed=data.get("passed", False),
            overall_score=data.get("overall_score", 0.0),
            test_pass_rate=data.get("test_pass_rate", 0.0),
            lint_score=data.get("lint_score", 1.0),
            type_check_passed=data.get("type_check_passed", True),
            security_issues_count=data.get("security_issues_count", 0),
            iterations_taken=data.get("iterations_taken", 1),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            issues=data.get("issues", []),
            metadata=data.get("metadata", {}),
        )