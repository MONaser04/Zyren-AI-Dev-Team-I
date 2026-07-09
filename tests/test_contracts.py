"""
Tests — Type-Safe Inter-Agent Contracts
=========================================

Validates that all Pydantic schemas:
- Accept valid data
- Reject invalid data (missing fields, wrong types)
- Cross-field validators work correctly
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.schemas import (
    CodePatch,
    FileContent,
    ReviewDecision,
    ReviewIssue,
    Severity,
    TaskAssignment,
    Verdict,
    VerificationReport,
    WorkflowState,
    WorkflowStatus,
)


class TestTaskAssignment:
    """Test the TaskAssignment contract."""

    def test_valid_task(self) -> None:
        task = TaskAssignment(
            workflow_id="wf-001",
            description="Fix the off-by-one error in paginate()",
        )
        assert task.workflow_id == "wf-001"
        assert task.language == "python"
        assert task.iteration == 1
        assert task.prior_feedback is None
        assert task.task_id  # Auto-generated
        assert task.created_at is not None

    def test_task_with_feedback(self) -> None:
        task = TaskAssignment(
            workflow_id="wf-001",
            description="Fix pagination",
            iteration=2,
            prior_feedback="The slice end should be start + size, not start + size - 1",
        )
        assert task.iteration == 2
        assert task.prior_feedback is not None

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskAssignment(workflow_id="wf-001", description="")

    def test_negative_iteration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskAssignment(workflow_id="wf-001", description="Fix bug", iteration=0)


class TestCodePatch:
    """Test the CodePatch contract."""

    def test_valid_patch(self) -> None:
        patch = CodePatch(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            files=[FileContent(path="utils.py", content="def foo(): pass")],
            explanation="Simple fix",
        )
        assert len(patch.files) == 1
        assert patch.files[0].path == "utils.py"

    def test_empty_files_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodePatch(
                task_id="t-001",
                workflow_id="wf-001",
                iteration=1,
                files=[],
            )

    def test_duplicate_paths_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CodePatch(
                task_id="t-001",
                workflow_id="wf-001",
                iteration=1,
                files=[
                    FileContent(path="a.py", content="x"),
                    FileContent(path="a.py", content="y"),
                ],
            )

    def test_multiple_files(self) -> None:
        patch = CodePatch(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            files=[
                FileContent(path="main.py", content="print('hello')"),
                FileContent(path="test_main.py", content="def test_hello(): pass"),
            ],
        )
        assert len(patch.files) == 2


class TestVerificationReport:
    """Test the VerificationReport contract."""

    def test_all_clean(self) -> None:
        report = VerificationReport(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            tests_passed=True,
            type_check_passed=True,
            lint_passed=True,
        )
        assert report.all_clean is True

    def test_not_clean(self) -> None:
        report = VerificationReport(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            tests_passed=False,
            type_check_passed=True,
            lint_passed=True,
        )
        assert report.all_clean is False

    def test_with_test_results(self) -> None:
        from contracts.schemas import TestResult

        report = VerificationReport(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            tests_passed=False,
            test_results=[
                TestResult(name="test_add", passed=True, output=""),
                TestResult(name="test_sub", passed=False, output="AssertionError"),
            ],
            type_check_passed=True,
            lint_passed=True,
        )
        assert len(report.test_results) == 2
        assert not report.all_clean


class TestReviewDecision:
    """Test the ReviewDecision contract."""

    def test_pass_verdict(self) -> None:
        decision = ReviewDecision(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            verdict=Verdict.PASS,
            justification="All checks passed and code is correct.",
        )
        assert decision.verdict == Verdict.PASS

    def test_block_with_issues(self) -> None:
        decision = ReviewDecision(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            verdict=Verdict.BLOCK,
            justification="Tests are failing.",
            issues=[
                ReviewIssue(
                    description="test_paginate fails with AssertionError",
                    severity=Severity.HIGH,
                    suggestion="Fix the slice boundary",
                    source="pytest",
                ),
            ],
            feedback_for_coder="The slice should be items[start:start+size]",
        )
        assert decision.verdict == Verdict.BLOCK
        assert len(decision.issues) == 1

    def test_block_without_issues_or_feedback_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReviewDecision(
                task_id="t-001",
                workflow_id="wf-001",
                iteration=1,
                verdict=Verdict.BLOCK,
                justification="Something is wrong.",
                issues=[],
                feedback_for_coder="",
            )


class TestWorkflowState:
    """Test the WorkflowState projection model."""

    def test_default_state(self) -> None:
        state = WorkflowState(workflow_id="wf-001")
        assert state.status == WorkflowStatus.PENDING
        assert state.current_iteration == 0
        assert state.final_verdict is None

    def test_completed_state(self) -> None:
        state = WorkflowState(
            workflow_id="wf-001",
            status=WorkflowStatus.PASSED,
            current_iteration=2,
            final_verdict=Verdict.PASS,
        )
        assert state.status == WorkflowStatus.PASSED
