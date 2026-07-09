"""
Verification Steps — Composable External Signal Generators
============================================================

Each step runs a single external tool (ruff, mypy, pytest, bandit, etc.)
in a work directory and returns a typed StepResult.

Steps are composable — the VerificationRunner chains them in order.
Each step captures stdout/stderr/exit codes: **facts only, no opinions.**
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path


# ============================================================
# Step Result
# ============================================================


@dataclass(frozen=True)
class StepResult:
    """Result from a single verification step."""

    name: str
    passed: bool
    output: str
    exit_code: int = 0
    details: dict[str, object] = field(default_factory=dict)


# ============================================================
# Step Protocol
# ============================================================


@runtime_checkable
class VerificationStep(Protocol):
    """Protocol for composable verification steps."""

    @property
    def name(self) -> str: ...

    def run(self, work_dir: Path) -> StepResult: ...


# ============================================================
# Helper: Subprocess Runner
# ============================================================


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


# ============================================================
# Concrete Steps
# ============================================================


class SyntaxCheckStep:
    """Check Python syntax via ast.parse — catches SyntaxError."""

    @property
    def name(self) -> str:
        return "syntax_check"

    def run(self, work_dir: Path) -> StepResult:
        py_files = list(work_dir.rglob("*.py"))
        if not py_files:
            return StepResult(
                name=self.name, passed=True, output="No Python files."
            )

        errors: list[str] = []
        for f in py_files:
            result = _run_subprocess(
                ["python", "-c", f"import ast; ast.parse(open(r'{f}').read())"],
                cwd=work_dir,
            )
            if result.returncode != 0:
                errors.append(f"{f.name}: {result.stderr.strip()}")

        passed = len(errors) == 0
        output = "\n".join(errors) if errors else "All files parse OK."
        return StepResult(
            name=self.name,
            passed=passed,
            output=output,
            exit_code=0 if passed else 1,
        )


class RuffLintStep:
    """Run ruff linter on the work directory."""

    @property
    def name(self) -> str:
        return "ruff_lint"

    def run(self, work_dir: Path) -> StepResult:
        py_files = list(work_dir.rglob("*.py"))
        if not py_files:
            return StepResult(
                name=self.name, passed=True, output="No Python files to lint."
            )

        result = _run_subprocess(
            ["ruff", "check", "--no-fix", "."],
            cwd=work_dir,
        )
        output = (result.stdout + result.stderr).strip()
        return StepResult(
            name=self.name,
            passed=result.returncode == 0,
            output=output,
            exit_code=result.returncode,
        )


class MypyTypeCheckStep:
    """Run mypy type checker on the work directory."""

    @property
    def name(self) -> str:
        return "mypy_type_check"

    def run(self, work_dir: Path) -> StepResult:
        py_files = list(work_dir.rglob("*.py"))
        if not py_files:
            return StepResult(
                name=self.name,
                passed=True,
                output="No Python files to type-check.",
            )

        result = _run_subprocess(
            ["mypy", "--ignore-missing-imports", "--no-error-summary", "."],
            cwd=work_dir,
        )
        output = (result.stdout + result.stderr).strip()
        return StepResult(
            name=self.name,
            passed=result.returncode == 0,
            output=output,
            exit_code=result.returncode,
        )


class PytestStep:
    """Run pytest and parse individual test results."""

    @property
    def name(self) -> str:
        return "pytest"

    def run(self, work_dir: Path) -> StepResult:
        test_files = list(work_dir.rglob("test_*.py"))
        if not test_files:
            return StepResult(
                name=self.name,
                passed=True,
                output="No test files found.",
                details={"tests": [], "coverage_percent": None},
            )

        # Run pytest with verbose output and coverage if available
        cmd = ["pytest", "-v", "--tb=short", "--no-header", "."]
        result = _run_subprocess(cmd, cwd=work_dir, timeout=60)
        output = (result.stdout + result.stderr).strip()

        # Parse individual test results from verbose output
        tests = self._parse_test_results(result.stdout)

        # Try to extract coverage if pytest-cov was used
        coverage = self._extract_coverage(result.stdout)

        return StepResult(
            name=self.name,
            passed=result.returncode == 0,
            output=output[:3000],  # Truncate
            exit_code=result.returncode,
            details={
                "tests": tests,
                "coverage_percent": coverage,
            },
        )

    @staticmethod
    def _parse_test_results(stdout: str) -> list[dict[str, object]]:
        """Parse pytest verbose output into individual test results."""
        tests: list[dict[str, object]] = []
        for line in stdout.splitlines():
            # Match lines like: "tests/test_foo.py::test_bar PASSED"
            match = re.match(
                r"^(.+?::.+?)\s+(PASSED|FAILED|ERROR|SKIPPED)",
                line.strip(),
            )
            if match:
                tests.append({
                    "name": match.group(1),
                    "passed": match.group(2) == "PASSED",
                    "status": match.group(2),
                })
        return tests

    @staticmethod
    def _extract_coverage(stdout: str) -> float | None:
        """Extract coverage percentage from pytest-cov output."""
        # Match lines like: "TOTAL    100    10    90%"
        match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", stdout)
        if match:
            return float(match.group(1))
        return None


class BanditSecurityStep:
    """Run bandit security scanner on Python code."""

    @property
    def name(self) -> str:
        return "bandit_security"

    def run(self, work_dir: Path) -> StepResult:
        py_files = list(work_dir.rglob("*.py"))
        # Exclude test files from security scanning
        py_files = [f for f in py_files if not f.name.startswith("test_")]
        if not py_files:
            return StepResult(
                name=self.name,
                passed=True,
                output="No non-test Python files to scan.",
            )

        # Run bandit with JSON output for structured results
        result = _run_subprocess(
            [
                "bandit",
                "-r",
                ".",
                "--exclude",
                "test_*",
                "-f",
                "json",
                "-q",
            ],
            cwd=work_dir,
        )

        # Parse JSON output if possible
        issues: list[dict[str, str]] = []
        if result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                for issue in data.get("results", []):
                    issues.append({
                        "severity": issue.get("issue_severity", "UNKNOWN"),
                        "confidence": issue.get(
                            "issue_confidence", "UNKNOWN"
                        ),
                        "text": issue.get("issue_text", ""),
                        "file": issue.get("filename", ""),
                        "line": str(issue.get("line_number", 0)),
                    })
            except (json.JSONDecodeError, KeyError):
                pass

        # bandit exit code 0 = no issues, 1 = issues found
        # If bandit is not installed, treat as passed (graceful degradation)
        if "Tool not found" in result.stderr:
            return StepResult(
                name=self.name,
                passed=True,
                output="bandit not installed — skipping security scan.",
            )

        output = (
            f"{len(issues)} security issue(s) found."
            if issues
            else "No security issues found."
        )

        return StepResult(
            name=self.name,
            passed=result.returncode == 0,
            output=output,
            exit_code=result.returncode,
            details={"issues": issues},
        )


# ============================================================
# Default Step Pipeline
# ============================================================


def default_steps() -> list[VerificationStep]:
    """Return the default verification pipeline."""
    return [
        SyntaxCheckStep(),
        RuffLintStep(),
        MypyTypeCheckStep(),
        PytestStep(),
        BanditSecurityStep(),
    ]
