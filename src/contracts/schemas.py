"""
Type-Safe Inter-Agent Contracts
================================

Pydantic v2 strict-mode schemas for every agent boundary in the minimal
feedback loop. Validate BEFORE committing to the event log.

Schemas:
    - TaskAssignment:      Orchestrator → Coder
    - CodePatch:           Coder → Tester
    - VerificationReport:  Tester → Critic (facts only)
    - ReviewDecision:      Critic → Orchestrator/Coder
    - WorkflowState:       State projection (current workflow status)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ============================================================
# Enums
# ============================================================


class Verdict(StrEnum):
    """Review outcome from the Grounded Critic."""

    PASS = "PASS"
    BLOCK = "BLOCK"


class Severity(StrEnum):
    """Issue severity in review feedback."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkflowStatus(StrEnum):
    """Lifecycle status of a workflow."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"


# ============================================================
# Base Contract
# ============================================================


class BaseContract(BaseModel):
    """Base class for all inter-agent contracts."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="UTC timestamp when this contract was created.",
    )


# ============================================================
# TaskAssignment — Orchestrator → Coder
# ============================================================


class TaskAssignment(BaseContract):
    """Task assignment from the Orchestrator to the Coder agent.

    Contains the task description, constraints, and iteration context
    so the Coder knows whether this is a first attempt or a retry
    with feedback.
    """

    task_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:12],
        description="Unique identifier for this task.",
    )
    workflow_id: str = Field(
        description="Parent workflow identifier.",
    )
    description: str = Field(
        min_length=1,
        description="Natural-language description of the coding task.",
    )
    language: str = Field(
        default="python",
        description="Target programming language.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Additional constraints or requirements.",
    )
    iteration: int = Field(
        default=1,
        ge=1,
        description="Current iteration number (1 = first attempt).",
    )
    prior_feedback: str | None = Field(
        default=None,
        description="Structured feedback from the Critic on prior iteration.",
    )


# ============================================================
# CodePatch — Coder → Tester
# ============================================================


class FileContent(BaseContract):
    """A single file with its content."""

    path: str = Field(
        min_length=1,
        description="Relative file path (e.g., 'utils.py').",
    )
    content: str = Field(
        description="Full file content.",
    )


class CodePatch(BaseContract):
    """Code patch produced by the Coder agent.

    Contains one or more files constituting the solution attempt.
    """

    task_id: str = Field(description="Task this patch addresses.")
    workflow_id: str = Field(description="Parent workflow identifier.")
    iteration: int = Field(ge=1, description="Iteration number.")
    files: list[FileContent] = Field(
        min_length=1,
        description="Files in this patch (at least one).",
    )
    explanation: str = Field(
        default="",
        description="Coder's explanation of the approach.",
    )

    @model_validator(mode="after")
    def _validate_unique_paths(self) -> CodePatch:
        """Ensure no duplicate file paths in the patch."""
        paths = [f.path for f in self.files]
        if len(paths) != len(set(paths)):
            msg = "Duplicate file paths in patch."
            raise ValueError(msg)
        return self


# ============================================================
# VerificationReport — Tester → Critic (facts only)
# ============================================================


class TestResult(BaseContract):
    """Result of a single test execution."""

    name: str = Field(description="Test name or identifier.")
    passed: bool = Field(description="Whether the test passed.")
    output: str = Field(default="", description="Test output or error message.")


class VerificationReport(BaseContract):
    """Verification report from the Tester agent.

    Contains ONLY measured facts — no opinions, no suggestions.
    The Grounded Critic interprets these signals.
    """

    task_id: str = Field(description="Task that was verified.")
    workflow_id: str = Field(description="Parent workflow identifier.")
    iteration: int = Field(ge=1, description="Iteration number.")

    # --- External Signals (facts only) ---
    tests_passed: bool = Field(description="Whether ALL tests passed.")
    test_results: list[TestResult] = Field(
        default_factory=list,
        description="Individual test results.",
    )
    type_check_passed: bool = Field(description="Whether type checking passed.")
    type_check_output: str = Field(
        default="",
        description="Raw mypy output.",
    )
    lint_passed: bool = Field(description="Whether linting passed.")
    lint_output: str = Field(
        default="",
        description="Raw ruff output.",
    )
    execution_passed: bool = Field(
        default=True,
        description="Whether the code executed without runtime errors.",
    )
    execution_output: str = Field(
        default="",
        description="Raw stdout/stderr from execution.",
    )

    @property
    def all_clean(self) -> bool:
        """True if every verification signal is clean."""
        return (
            self.tests_passed
            and self.type_check_passed
            and self.lint_passed
            and self.execution_passed
        )


# ============================================================
# ReviewDecision — Critic → Orchestrator / Coder
# ============================================================


class ReviewIssue(BaseContract):
    """A single issue identified by the Grounded Critic."""

    description: str = Field(
        min_length=1,
        description="What the issue is.",
    )
    severity: Severity = Field(description="Issue severity.")
    suggestion: str = Field(
        default="",
        description="Suggested fix or approach.",
    )
    source: str = Field(
        default="",
        description="Source of the signal (e.g., 'pytest', 'mypy', 'ruff').",
    )


class ReviewDecision(BaseContract):
    """Review decision from the Grounded Critic.

    PASS:  All checks clean AND rubric satisfied → proceed to merge.
    BLOCK: Issues found → return structured feedback to the Coder.
    """

    task_id: str = Field(description="Task that was reviewed.")
    workflow_id: str = Field(description="Parent workflow identifier.")
    iteration: int = Field(ge=1, description="Iteration number.")
    verdict: Verdict = Field(description="PASS or BLOCK.")
    justification: str = Field(
        min_length=1,
        description="Why this verdict was chosen.",
    )
    issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="List of issues (empty if PASS).",
    )
    feedback_for_coder: str = Field(
        default="",
        description="Structured feedback for the Coder's next iteration.",
    )

    @model_validator(mode="after")
    def _validate_block_has_issues(self) -> ReviewDecision:
        """A BLOCK verdict must have at least one issue or feedback."""
        if self.verdict == Verdict.BLOCK and not self.issues and not self.feedback_for_coder:
            msg = "BLOCK verdict must include issues or feedback_for_coder."
            raise ValueError(msg)
        return self


# ============================================================
# WorkflowState — State Projection
# ============================================================


class WorkflowState(BaseModel):
    """Projected current state of a workflow.

    Built by folding all events for a workflow_id.
    Not frozen because projections are mutable during construction.
    """

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(description="Workflow identifier.")
    status: WorkflowStatus = Field(
        default=WorkflowStatus.PENDING,
        description="Current lifecycle status.",
    )
    task_description: str = Field(
        default="",
        description="Original task description.",
    )
    current_iteration: int = Field(
        default=0,
        description="Current iteration count.",
    )
    max_iterations: int = Field(
        default=3,
        description="Maximum allowed iterations.",
    )
    patches: list[dict[str, Any]] = Field(
        default_factory=list,
        description="History of code patches (serialized).",
    )
    reviews: list[dict[str, Any]] = Field(
        default_factory=list,
        description="History of review decisions (serialized).",
    )
    final_verdict: Verdict | None = Field(
        default=None,
        description="Final review verdict (if workflow is done).",
    )
    error: str | None = Field(
        default=None,
        description="Error message if workflow failed.",
    )
