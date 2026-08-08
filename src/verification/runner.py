"""
Verification Runner — Composable Pipeline Orchestrator
========================================================

Writes CodePatch files to a temp directory, runs a pipeline of
VerificationStep instances, and returns a structured VerificationReport.

This is the bridge between the agent world (contracts) and the
tool world (subprocess calls). The runner owns the temp directory
lifecycle and collects results into the shared contract.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from contracts.schemas import TestResult, VerificationReport
from verification.steps import (
    StepResult,
    VerificationStep,
    default_steps,
)

logger = logging.getLogger(__name__)


class VerificationRunner:
    """Orchestrates a pipeline of verification steps.

    Usage:
        runner = VerificationRunner()
        report = runner.verify(patch)
    """

    def __init__(
        self,
        steps: list[VerificationStep] | None = None,
        prior_coverage: float | None = None,
    ) -> None:
        """Initialize with optional custom step pipeline.

        Args:
            steps: Custom steps (defaults to the standard pipeline).
            prior_coverage: Coverage from the prior iteration (for delta).
        """
        self.steps = steps if steps is not None else default_steps()
        self.prior_coverage = prior_coverage

    def verify(
        self,
        *,
        task_id: str,
        workflow_id: str,
        iteration: int,
        files: list[tuple[str, str]],
    ) -> VerificationReport:
        """Run the full verification pipeline.

        Args:
            task_id: Task identifier.
            workflow_id: Workflow identifier.
            iteration: Current iteration number.
            files: List of (path, content) tuples to verify.

        Returns:
            A VerificationReport with all step results.
        """
        logger.info(
            "Starting verification: task=%s, iteration=%d, files=%d, steps=%d",
            task_id,
            iteration,
            len(files),
            len(self.steps),
        )

        with tempfile.TemporaryDirectory(prefix="zyren-ai-dev-team_verify_") as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Write all files
            for path, content in files:
                file_path = tmp_path / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

            # Run all steps
            results: dict[str, StepResult] = {}
            for step in self.steps:
                result = step.run(tmp_path)
                results[step.name] = result
                logger.debug(
                    "Step %s: passed=%s",
                    step.name,
                    result.passed,
                )

        # Build the VerificationReport from step results
        return self._build_report(
            task_id=task_id,
            workflow_id=workflow_id,
            iteration=iteration,
            results=results,
        )

    def _build_report(
        self,
        *,
        task_id: str,
        workflow_id: str,
        iteration: int,
        results: dict[str, StepResult],
    ) -> VerificationReport:
        """Convert step results into a VerificationReport."""
        # Extract step results with safe defaults
        syntax = results.get("syntax_check")
        lint = results.get("ruff_lint")
        type_check = results.get("mypy_type_check")
        pytest_result = results.get("pytest")
        security = results.get("bandit_security")

        # Build test results
        test_results: list[TestResult] = []
        tests_passed = True
        if pytest_result:
            tests_passed = pytest_result.passed
            parsed_tests = pytest_result.details.get("tests", [])
            if isinstance(parsed_tests, list):
                for t in parsed_tests:
                    if isinstance(t, dict):
                        test_results.append(
                            TestResult(
                                name=str(t.get("name", "unknown")),
                                passed=bool(t.get("passed", False)),
                                output=str(t.get("status", "")),
                            )
                        )
            if not test_results:
                test_results = [
                    TestResult(
                        name="pytest_suite",
                        passed=pytest_result.passed,
                        output=pytest_result.output[:2000],
                    )
                ]

        # Extract coverage
        coverage_percent: float | None = None
        if pytest_result and pytest_result.details.get("coverage_percent") is not None:
            raw = pytest_result.details["coverage_percent"]
            coverage_percent = float(raw) if isinstance(raw, (int, float)) else None

        # Compute coverage delta
        coverage_delta: float | None = None
        if coverage_percent is not None and self.prior_coverage is not None:
            coverage_delta = coverage_percent - self.prior_coverage

        return VerificationReport(
            task_id=task_id,
            workflow_id=workflow_id,
            iteration=iteration,
            tests_passed=tests_passed,
            test_results=test_results,
            type_check_passed=type_check.passed if type_check else True,
            type_check_output=type_check.output if type_check else "",
            lint_passed=lint.passed if lint else True,
            lint_output=lint.output if lint else "",
            execution_passed=syntax.passed if syntax else True,
            execution_output=syntax.output if syntax else "",
            security_passed=security.passed if security else True,
            security_output=security.output if security else "",
            coverage_percent=coverage_percent,
            coverage_delta=coverage_delta,
        )
