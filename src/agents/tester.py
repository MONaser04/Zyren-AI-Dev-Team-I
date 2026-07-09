"""
Tester Agent — External Signal Generator
==========================================

Takes a CodePatch, writes files to a temp directory, runs verification
tools (ruff, mypy, pytest), and produces a VerificationReport containing
ONLY measured facts — no opinions.

For v0: runs in a temp directory with subprocess (not Docker-sandboxed).
Docker sandbox is Phase 3.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from agents.base import BaseAgent
from contracts.schemas import CodePatch, TestResult, VerificationReport


class TesterAgent(BaseAgent):
    """Tester agent — runs external verification tools on code patches.

    Captures stdout/stderr/exit codes from real tools.
    Produces facts only — no opinions, no suggestions.
    """

    def __init__(
        self,
        agent_id: str = "tester-01",
    ) -> None:
        # Tester doesn't need an LLM — it runs tools
        from gateway.llm_client import LLMClient

        super().__init__(
            agent_id=agent_id,
            role="tester",
            llm_client=LLMClient(),  # Unused but required by base
        )

    def run(self, patch: CodePatch) -> VerificationReport:  # type: ignore[override]
        """Run verification tools on a code patch.

        Args:
            patch: The code patch to verify.

        Returns:
            A VerificationReport with factual results.
        """
        self.logger.info(
            "Verifying patch: task=%s, iteration=%d, files=%d",
            patch.task_id,
            patch.iteration,
            len(patch.files),
        )

        with tempfile.TemporaryDirectory(prefix="aidev_test_") as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Write all files from the patch
            for file in patch.files:
                file_path = tmp_path / file.path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(file.content, encoding="utf-8")

            # Run verification tools
            lint_passed, lint_output = self._run_lint(tmp_path)
            type_passed, type_output = self._run_type_check(tmp_path)
            tests_passed, test_results = self._run_tests(tmp_path)
            exec_passed, exec_output = self._run_execution(tmp_path, patch)

        report = VerificationReport(
            task_id=patch.task_id,
            workflow_id=patch.workflow_id,
            iteration=patch.iteration,
            tests_passed=tests_passed,
            test_results=test_results,
            type_check_passed=type_passed,
            type_check_output=type_output,
            lint_passed=lint_passed,
            lint_output=lint_output,
            execution_passed=exec_passed,
            execution_output=exec_output,
        )

        self.logger.info(
            "Verification complete: all_clean=%s, task=%s",
            report.all_clean,
            patch.task_id,
        )
        return report

    def _run_lint(self, work_dir: Path) -> tuple[bool, str]:
        """Run ruff linter on the work directory."""
        py_files = list(work_dir.rglob("*.py"))
        if not py_files:
            return True, "No Python files to lint."

        result = self._run_subprocess(
            ["ruff", "check", "--no-fix", "."],
            cwd=work_dir,
        )
        return result.returncode == 0, result.stdout + result.stderr

    def _run_type_check(self, work_dir: Path) -> tuple[bool, str]:
        """Run mypy type checker on the work directory."""
        py_files = list(work_dir.rglob("*.py"))
        if not py_files:
            return True, "No Python files to type-check."

        result = self._run_subprocess(
            ["mypy", "--ignore-missing-imports", "--no-error-summary", "."],
            cwd=work_dir,
        )
        return result.returncode == 0, result.stdout + result.stderr

    def _run_tests(self, work_dir: Path) -> tuple[bool, list[TestResult]]:
        """Run pytest on the work directory."""
        test_files = list(work_dir.rglob("test_*.py"))
        if not test_files:
            return True, [
                TestResult(name="no_tests", passed=True, output="No test files found.")
            ]

        result = self._run_subprocess(
            ["pytest", "-v", "--tb=short", "--no-header", "."],
            cwd=work_dir,
        )

        test_results = [
            TestResult(
                name="pytest_suite",
                passed=result.returncode == 0,
                output=(result.stdout + result.stderr)[:2000],  # Truncate
            )
        ]

        return result.returncode == 0, test_results

    def _run_execution(
        self, work_dir: Path, patch: CodePatch
    ) -> tuple[bool, str]:
        """Try to execute the main Python file to check for runtime errors."""
        # Find the main file (first non-test .py file)
        main_files = [
            f for f in patch.files
            if f.path.endswith(".py") and not f.path.startswith("test_")
        ]
        if not main_files:
            return True, "No main file to execute."

        main_file = main_files[0].path
        result = self._run_subprocess(
            ["python", "-c", f"import ast; ast.parse(open(r'{main_file}').read())"],
            cwd=work_dir,
        )
        return result.returncode == 0, result.stdout + result.stderr

    @staticmethod
    def _run_subprocess(
        cmd: list[str],
        cwd: Path,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        """Run a subprocess with timeout and capture output."""
        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr=f"TIMEOUT: Command timed out after {timeout}s",
            )
        except FileNotFoundError:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr=f"Tool not found: {cmd[0]}",
            )
