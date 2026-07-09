"""
Grounded Critic Agent — Interpreter of Verification Signals
=============================================================

Consumes a VerificationReport + CodePatch, interprets the factual signals
against a rubric, and produces a ReviewDecision (PASS or BLOCK).

Uses a DIFFERENT model family than the Coder (per README line 231)
to reduce shared blind spots and sycophancy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import (
    CodePatch,
    ReviewDecision,
    ReviewIssue,
    Severity,
    Verdict,
    VerificationReport,
)

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient

# ============================================================
# System Prompt
# ============================================================

CRITIC_SYSTEM_PROMPT = """\
You are the Grounded Critic — a rigorous code reviewer. Your job is to
interpret FACTUAL verification signals (test results, type errors, lint
violations) and decide whether code should PASS or be BLOCKED.

Rules:
1. You make decisions based on EVIDENCE, not gut feeling.
2. If all verification signals are clean (tests pass, types check, lint clean),
   and the code correctly addresses the task, verdict is PASS.
3. If ANY signal is failing, verdict is BLOCK with specific issues.
4. For each issue, cite the EXACT source (pytest, mypy, ruff) and error.
5. Provide actionable, specific feedback — not vague suggestions.
6. Respond ONLY with the structured JSON output.

Escalation tone by iteration:
- Iteration 1: Constructive and encouraging
- Iteration 2: Direct and firm
- Iteration 3+: Hard block with exhaustive detail
"""


class CriticAgent(BaseAgent):
    """Grounded Critic — interprets verification signals and decides PASS/BLOCK.

    Uses the 'critic' model (different family than Coder) to reduce
    shared blind spots.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model: str = "critic",
        agent_id: str = "critic-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="critic", llm_client=llm_client)
        self.model = model

    def run(  # type: ignore[override]
        self,
        patch: CodePatch,
        report: VerificationReport,
    ) -> ReviewDecision:
        """Review a code patch using verification signals.

        Args:
            patch: The code that was verified.
            report: Factual verification results from the Tester.

        Returns:
            A ReviewDecision — PASS or BLOCK with feedback.
        """
        self.logger.info(
            "Reviewing: task=%s, iteration=%d, all_clean=%s",
            patch.task_id,
            patch.iteration,
            report.all_clean,
        )

        # Fast path: if all signals are clean, we can do a quick pass
        # but still ask the LLM to verify the code addresses the task
        if report.all_clean:
            return self._review_with_llm(patch, report)

        # If signals are failing, always use the LLM for detailed analysis
        return self._review_with_llm(patch, report)

    def _review_with_llm(
        self,
        patch: CodePatch,
        report: VerificationReport,
    ) -> ReviewDecision:
        """Use the critic model to review code with verification context."""
        user_prompt = self._build_prompt(patch, report)

        messages = [
            {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        result = self.llm_client.complete_structured(
            model=self.model,
            messages=messages,
            response_model=_CriticResponse,
        )

        # Convert to ReviewDecision contract
        issues = [
            ReviewIssue(
                description=i.description,
                severity=Severity(i.severity),
                suggestion=i.suggestion,
                source=i.source,
            )
            for i in result.issues
        ]

        decision = ReviewDecision(
            task_id=patch.task_id,
            workflow_id=patch.workflow_id,
            iteration=patch.iteration,
            verdict=Verdict(result.verdict),
            justification=result.justification,
            issues=issues,
            feedback_for_coder=result.feedback_for_coder,
        )

        self.logger.info(
            "Review complete: verdict=%s, issues=%d, task=%s",
            decision.verdict.value,
            len(decision.issues),
            patch.task_id,
        )
        return decision

    def _build_prompt(
        self,
        patch: CodePatch,
        report: VerificationReport,
    ) -> str:
        """Build the review prompt with all verification context."""
        # Build code section
        code_parts = []
        for f in patch.files:
            code_parts.append(f"### {f.path}\n```\n{f.content}\n```")
        code_section = "\n\n".join(code_parts)

        # Build verification section
        verification_parts = [
            f"- **Tests passed:** {report.tests_passed}",
            f"- **Type check passed:** {report.type_check_passed}",
            f"- **Lint passed:** {report.lint_passed}",
            f"- **Execution passed:** {report.execution_passed}",
        ]

        if not report.tests_passed:
            for tr in report.test_results:
                verification_parts.append(f"  - Test `{tr.name}`: {'✅' if tr.passed else '❌'}")
                if tr.output:
                    verification_parts.append(f"    Output: {tr.output[:500]}")

        if not report.type_check_passed and report.type_check_output:
            tc_out = report.type_check_output[:1000]
            verification_parts.append(
                f"- **Type check output:**\n```\n{tc_out}\n```"
            )

        if not report.lint_passed and report.lint_output:
            lint_out = report.lint_output[:1000]
            verification_parts.append(
                f"- **Lint output:**\n```\n{lint_out}\n```"
            )

        if not report.execution_passed and report.execution_output:
            exec_out = report.execution_output[:1000]
            verification_parts.append(
                f"- **Execution output:**\n```\n{exec_out}\n```"
            )

        verification_section = "\n".join(verification_parts)

        return (
            f"## Code Under Review (Iteration {patch.iteration})\n\n"
            f"{code_section}\n\n"
            f"## Coder's Explanation\n{patch.explanation or 'None provided.'}\n\n"
            f"## Verification Signals (Facts)\n{verification_section}\n\n"
            f"## Your Task\n"
            f"Review the code and verification signals. Decide PASS or BLOCK."
        )


# ============================================================
# Internal response model (not an inter-agent contract)
# ============================================================

from pydantic import BaseModel, Field  # noqa: E402


class _CriticIssueResponse(BaseModel):
    """A single issue in the Critic's response."""

    description: str = Field(description="What the issue is.")
    severity: str = Field(description="low, medium, high, or critical.")
    suggestion: str = Field(default="", description="Suggested fix.")
    source: str = Field(default="", description="Source tool (pytest, mypy, ruff).")


class _CriticResponse(BaseModel):
    """Structured response from the Critic LLM call."""

    verdict: str = Field(description="PASS or BLOCK.")
    justification: str = Field(description="Why this verdict was chosen.")
    issues: list[_CriticIssueResponse] = Field(
        default_factory=list,
        description="List of issues found.",
    )
    feedback_for_coder: str = Field(
        default="",
        description="Structured feedback for the Coder.",
    )
