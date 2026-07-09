"""
Tests for the Verification Module (Phase 2).

Tests the composable verification steps and the VerificationRunner.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from verification.runner import VerificationRunner
from verification.steps import (
    BanditSecurityStep,
    MypyTypeCheckStep,
    PytestStep,
    RuffLintStep,
    StepResult,
    SyntaxCheckStep,
    default_steps,
)

# ============================================================
# Step Tests
# ============================================================


class TestSyntaxCheckStep:
    """Tests for the SyntaxCheckStep."""

    def test_valid_python_passes(self) -> None:
        step = SyntaxCheckStep()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "good.py"
            p.write_text("x = 1\nprint(x)\n", encoding="utf-8")
            result = step.run(Path(tmp))
        assert result.passed
        assert result.name == "syntax_check"

    def test_invalid_python_fails(self) -> None:
        step = SyntaxCheckStep()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.py"
            p.write_text("def f(\n", encoding="utf-8")
            result = step.run(Path(tmp))
        assert not result.passed

    def test_no_files_passes(self) -> None:
        step = SyntaxCheckStep()
        with tempfile.TemporaryDirectory() as tmp:
            result = step.run(Path(tmp))
        assert result.passed


class TestRuffLintStep:
    """Tests for the RuffLintStep."""

    def test_clean_code_passes(self) -> None:
        step = RuffLintStep()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "clean.py"
            p.write_text("x = 1\n", encoding="utf-8")
            result = step.run(Path(tmp))
        assert result.passed
        assert result.name == "ruff_lint"

    def test_no_files_passes(self) -> None:
        step = RuffLintStep()
        with tempfile.TemporaryDirectory() as tmp:
            result = step.run(Path(tmp))
        assert result.passed


class TestMypyStep:
    """Tests for the MypyTypeCheckStep."""

    def test_no_files_passes(self) -> None:
        step = MypyTypeCheckStep()
        with tempfile.TemporaryDirectory() as tmp:
            result = step.run(Path(tmp))
        assert result.passed
        assert result.name == "mypy_type_check"


class TestPytestStep:
    """Tests for the PytestStep."""

    def test_no_tests_passes(self) -> None:
        step = PytestStep()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "main.py"
            p.write_text("x = 1\n", encoding="utf-8")
            result = step.run(Path(tmp))
        assert result.passed
        assert result.name == "pytest"

    def test_parse_test_results(self) -> None:
        stdout = (
            "tests/test_foo.py::test_one PASSED\n"
            "tests/test_foo.py::test_two FAILED\n"
            "tests/test_bar.py::test_three PASSED\n"
        )
        tests = PytestStep._parse_test_results(stdout)
        assert len(tests) == 3
        assert tests[0]["passed"] is True
        assert tests[1]["passed"] is False
        assert tests[2]["name"] == "tests/test_bar.py::test_three"

    def test_extract_coverage_none(self) -> None:
        assert PytestStep._extract_coverage("no coverage output") is None

    def test_extract_coverage_value(self) -> None:
        stdout = "TOTAL    100    10    90%"
        result = PytestStep._extract_coverage(stdout)
        assert result == 90.0


class TestBanditStep:
    """Tests for the BanditSecurityStep."""

    def test_no_files_passes(self) -> None:
        step = BanditSecurityStep()
        with tempfile.TemporaryDirectory() as tmp:
            result = step.run(Path(tmp))
        assert result.passed
        assert result.name == "bandit_security"


class TestDefaultSteps:
    """Tests for the default step pipeline."""

    def test_returns_five_steps(self) -> None:
        steps = default_steps()
        assert len(steps) == 5

    def test_all_have_name(self) -> None:
        for step in default_steps():
            assert step.name


# ============================================================
# Runner Tests
# ============================================================


class TestVerificationRunner:
    """Tests for the VerificationRunner."""

    def test_runner_with_clean_code(self) -> None:
        """Runner produces a report with clean code."""
        runner = VerificationRunner(
            steps=[SyntaxCheckStep()]  # Only syntax check for speed
        )
        report = runner.verify(
            task_id="t1",
            workflow_id="w1",
            iteration=1,
            files=[("main.py", "x = 1\nprint(x)\n")],
        )
        assert report.task_id == "t1"
        assert report.workflow_id == "w1"
        assert report.iteration == 1
        assert report.execution_passed  # Syntax step maps to execution_passed

    def test_runner_with_bad_syntax(self) -> None:
        """Runner catches syntax errors."""
        runner = VerificationRunner(
            steps=[SyntaxCheckStep()]
        )
        report = runner.verify(
            task_id="t2",
            workflow_id="w2",
            iteration=1,
            files=[("bad.py", "def f(\n")],
        )
        assert not report.execution_passed

    def test_runner_coverage_delta(self) -> None:
        """Runner computes coverage delta when prior_coverage is set."""
        # Mock the PytestStep to return coverage
        mock_result = StepResult(
            name="pytest",
            passed=True,
            output="",
            details={"tests": [], "coverage_percent": 85.0},
        )
        runner = VerificationRunner(
            steps=[],
            prior_coverage=70.0,
        )
        # Directly test _build_report
        report = runner._build_report(
            task_id="t3",
            workflow_id="w3",
            iteration=2,
            results={"pytest": mock_result},
        )
        assert report.coverage_percent == 85.0
        assert report.coverage_delta == 15.0

    def test_runner_no_steps(self) -> None:
        """Runner with no steps produces a clean report."""
        runner = VerificationRunner(steps=[])
        report = runner.verify(
            task_id="t4",
            workflow_id="w4",
            iteration=1,
            files=[("main.py", "x = 1\n")],
        )
        assert report.all_clean

    def test_runner_creates_nested_dirs(self) -> None:
        """Runner correctly creates nested directories from file paths."""
        runner = VerificationRunner(steps=[SyntaxCheckStep()])
        report = runner.verify(
            task_id="t5",
            workflow_id="w5",
            iteration=1,
            files=[
                ("src/utils/helpers.py", "def helper(): pass\n"),
                ("src/main.py", "from utils.helpers import helper\n"),
            ],
        )
        # Should not crash on nested paths
        assert report.task_id == "t5"
