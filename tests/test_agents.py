"""
Tests — Role Agents
=====================

Validates:
- TesterAgent produces correct VerificationReport from known-good/bad code
- Agent output types are correct
"""

from __future__ import annotations

from agents.tester import TesterAgent as RealTesterAgent
from contracts.schemas import CodePatch, FileContent, VerificationReport


class TestTesterAgent:
    """Test the Tester agent with real subprocess calls."""

    def test_good_code_passes_lint(self) -> None:
        """Code that is syntactically correct should pass basic checks."""
        tester = RealTesterAgent()
        patch = CodePatch(
            task_id="t-001",
            workflow_id="wf-001",
            iteration=1,
            files=[
                FileContent(
                    path="hello.py",
                    content=(
                        "def greet(name: str) -> str:\n"
                        '    """Greet someone."""\n'
                        '    return f"Hello, {name}!"\n'
                    ),
                ),
            ],
        )
        report: VerificationReport = tester.run(patch=patch)

        assert isinstance(report, VerificationReport)
        assert report.task_id == "t-001"
        assert report.iteration == 1
        # Execution (AST parse) should pass for valid Python
        assert report.execution_passed is True

    def test_bad_syntax_fails_execution(self) -> None:
        """Code with syntax errors should fail execution check."""
        tester = RealTesterAgent()
        patch = CodePatch(
            task_id="t-002",
            workflow_id="wf-001",
            iteration=1,
            files=[
                FileContent(
                    path="broken.py",
                    content="def broken(\n    # missing closing paren and colon\n",
                ),
            ],
        )
        report: VerificationReport = tester.run(patch=patch)

        assert isinstance(report, VerificationReport)
        assert report.execution_passed is False

    def test_report_has_all_fields(self) -> None:
        """Verification report must have all required fields."""
        tester = RealTesterAgent()
        patch = CodePatch(
            task_id="t-003",
            workflow_id="wf-001",
            iteration=1,
            files=[
                FileContent(path="simple.py", content="x = 1\n"),
            ],
        )
        report = tester.run(patch=patch)

        # All required fields must be present
        assert report.task_id == "t-003"
        assert report.workflow_id == "wf-001"
        assert report.iteration == 1
        assert isinstance(report.tests_passed, bool)
        assert isinstance(report.type_check_passed, bool)
        assert isinstance(report.lint_passed, bool)
        assert isinstance(report.execution_passed, bool)
