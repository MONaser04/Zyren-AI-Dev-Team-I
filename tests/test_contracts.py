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
    EscalationLevel,
    FileContent,
    RebuttalJudgment,
    RebuttalOutcome,
    RebuttalRequest,
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


# ============================================================
# Phase 2 — New Contract Tests
# ============================================================


class TestEscalationLevel:
    """Test the EscalationLevel enum."""

    def test_all_levels(self) -> None:
        levels = list(EscalationLevel)
        assert len(levels) == 4
        assert EscalationLevel.SOFT in levels
        assert EscalationLevel.ESCALATE in levels

    def test_review_with_escalation(self) -> None:
        decision = ReviewDecision(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=3,
            verdict=Verdict.PASS,
            justification="All signals clean after 3 iterations.",
            escalation_level=EscalationLevel.HARD_BLOCK,
        )
        assert decision.escalation_level == EscalationLevel.HARD_BLOCK


class TestRebuttalRequest:
    """Test the RebuttalRequest contract."""

    def test_valid_rebuttal(self) -> None:
        rebuttal = RebuttalRequest(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            justification="The failing test asserts wrong behavior per the spec.",
            disputed_issues=["Test test_foo expects 42 but spec says 43"],
        )
        assert rebuttal.original_verdict == Verdict.BLOCK
        assert len(rebuttal.disputed_issues) == 1

    def test_short_justification_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RebuttalRequest(
                task_id="t-001",
                workflow_id="wf-001",
                iteration=1,
                justification="no",  # Too short (min_length=10)
            )


class TestRebuttalJudgment:
    """Test the RebuttalJudgment contract."""

    def test_accepted(self) -> None:
        judgment = RebuttalJudgment(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            outcome=RebuttalOutcome.ACCEPTED,
            reasoning="The coder correctly identified a false positive.",
        )
        assert judgment.outcome == RebuttalOutcome.ACCEPTED

    def test_rejected(self) -> None:
        judgment = RebuttalJudgment(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            outcome=RebuttalOutcome.REJECTED,
            reasoning="The issues are legitimate.",
        )
        assert judgment.outcome == RebuttalOutcome.REJECTED


class TestVerificationReportPhase2:
    """Test Phase 2 enhancements to VerificationReport."""

    def test_security_fields(self) -> None:
        report = VerificationReport(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            tests_passed=True,
            type_check_passed=True,
            lint_passed=True,
            security_passed=False,
            security_output="2 security issues found.",
        )
        assert not report.security_passed
        assert not report.all_clean  # security_passed is now part of all_clean

    def test_coverage_fields(self) -> None:
        report = VerificationReport(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=2,
            tests_passed=True,
            type_check_passed=True,
            lint_passed=True,
            coverage_percent=85.0,
            coverage_delta=15.0,
        )
        assert report.coverage_percent == 85.0
        assert report.coverage_delta == 15.0
        assert report.all_clean

    def test_all_clean_includes_security(self) -> None:
        report = VerificationReport(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            tests_passed=True,
            type_check_passed=True,
            lint_passed=True,
            execution_passed=True,
            security_passed=True,
        )
        assert report.all_clean


class TestWorkflowStatePhase2:
    """Test Phase 2 WorkflowState enhancements."""

    def test_rebuttal_fields_default(self) -> None:
        state = WorkflowState(workflow_id="wf-001")
        assert state.rebuttals == []
        assert state.rebuttal_judgments == []

    def test_with_rebuttals(self) -> None:
        state = WorkflowState(
            workflow_id="wf-001",
            rebuttals=[{"justification": "test"}],
            rebuttal_judgments=[{"outcome": "rejected"}],
        )
        assert len(state.rebuttals) == 1
        assert len(state.rebuttal_judgments) == 1
