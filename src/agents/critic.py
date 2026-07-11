"""
Grounded Critic Agent — Interpreter of Verification Signals
=============================================================

Consumes a VerificationReport + CodePatch, interprets the factual signals
against a rubric, and produces a ReviewDecision (PASS or BLOCK).

Phase 2 enhancements:
- Escalation ladder: soft → firm → hard block → escalate (per README line 231)
- Rebuttal judging: accepts or rejects Coder's right-of-rebuttal
- Uses a DIFFERENT model family than the Coder to reduce blind spots
"""

from __future__ import annotations

from src.observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.contracts.schemas import (
    CodePatch,
    EscalationLevel,
    RebuttalJudgment,
    RebuttalOutcome,
    RebuttalRequest,
    ReviewDecision,
    ReviewIssue,
    Severity,
    Verdict,
    VerificationReport,
)

if TYPE_CHECKING:
    from src.gateway.llm_client import LLMClient

# ============================================================
# System Prompts
# ============================================================

_ESCALATION_PROMPTS: dict[EscalationLevel, str] = {
    EscalationLevel.SOFT: (
        "Tone: CONSTRUCTIVE and ENCOURAGING. "
        "This is iteration 1 — be helpful and guide the coder."
    ),
    EscalationLevel.FIRM: (
        "Tone: DIRECT and FIRM. "
        "This is iteration 2 — the coder has seen these issues before. "
        "Be precise about what must change."
    ),
    EscalationLevel.HARD_BLOCK: (
        "Tone: HARD BLOCK with EXHAUSTIVE detail. "
        "This is iteration 3+ — repeated failures. "
        "List every issue with exact line numbers and mandatory fixes."
    ),
    EscalationLevel.ESCALATE: (
        "Tone: ESCALATION. "
        "This has gone beyond iteration 3. Recommend escalation to Supervisor. "
        "Provide a comprehensive summary of all unresolved issues."
    ),
}


def _build_critic_system_prompt(escalation: EscalationLevel) -> str:
    """Build a system prompt with the appropriate escalation tone."""
    tone = _ESCALATION_PROMPTS[escalation]
    return f"""\
You are the Grounded Critic — a rigorous code reviewer. Your job is to
interpret FACTUAL verification signals (test results, type errors, lint
violations, security findings) and decide whether code should PASS or be BLOCKED.

Rules:
1. You make decisions based on EVIDENCE, not gut feeling.
2. If all verification signals are clean (tests pass, types check, lint clean,
   security clean) and the code correctly addresses the task, verdict is PASS.
3. If ANY signal is failing, verdict is BLOCK with specific issues.
4. For each issue, cite the EXACT source (pytest, mypy, ruff, bandit) and error.
5. Provide actionable, specific feedback — not vague suggestions.
6. Respond ONLY with the structured JSON output.

{tone}
"""


REBUTTAL_JUDGE_PROMPT = """\
You are the Grounded Critic judging a Coder's rebuttal.

The Coder disagrees with your BLOCK decision and has provided a justification.
Your task: decide if the rebuttal has merit.

Rules:
1. If the Coder correctly identifies a FALSE POSITIVE (e.g., "the failing test
   asserts wrong behavior; here's the spec"), ACCEPT the rebuttal.
2. If the Coder's justification is valid but incomplete, REJECT — they need
   to fix remaining issues.
3. If the Coder is simply disagreeing without evidence, REJECT firmly.
4. Respond ONLY with the structured JSON output.
"""


class CriticAgent(BaseAgent):
    """Grounded Critic — interprets verification signals and decides PASS/BLOCK.

    Uses the 'critic' model (different family than Coder) to reduce
    shared blind spots.

    Phase 2: implements escalation ladder and rebuttal judging.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model: str = "critic",
        agent_id: str = "critic-01",
        rubric_name: str = "code_review",
    ) -> None:
        super().__init__(agent_id=agent_id, role="critic", llm_client=llm_client)
        self.model = model
        self.rubric_name = rubric_name

    @trace_agent_invocation(agent_role="critic")

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
        escalation = self._get_escalation_level(patch.iteration)

        self.logger.info(
            "Reviewing: task=%s, iteration=%d, all_clean=%s, escalation=%s",
            patch.task_id,
            patch.iteration,
            report.all_clean,
            escalation.value,
        )

        return self._review_with_llm(patch, report, escalation)

    @trace_agent_invocation(agent_role="judge_rebuttal")

    def judge_rebuttal(
        self,
        rebuttal: RebuttalRequest,
        original_decision: ReviewDecision,
        report: VerificationReport,
    ) -> RebuttalJudgment:
        """Judge a Coder's rebuttal against a BLOCK decision.

        Args:
            rebuttal: The Coder's rebuttal with justification.
            original_decision: The BLOCK decision being challenged.
            report: The verification report for context.

        Returns:
            A RebuttalJudgment — ACCEPTED or REJECTED.
        """
        self.logger.info(
            "Judging rebuttal: task=%s, iteration=%d",
            rebuttal.task_id,
            rebuttal.iteration,
        )

        user_prompt = self._build_rebuttal_prompt(
            rebuttal, original_decision, report
        )

        messages = [
            {"role": "system", "content": REBUTTAL_JUDGE_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        result = self.llm_client.complete_structured(
            model=self.model,
            messages=messages,
            response_model=_RebuttalJudgeResponse,
        )

        judgment = RebuttalJudgment(
            task_id=rebuttal.task_id,
            workflow_id=rebuttal.workflow_id,
            iteration=rebuttal.iteration,
            outcome=RebuttalOutcome(result.outcome),
            reasoning=result.reasoning,
        )

        self.logger.info(
            "Rebuttal judged: outcome=%s, task=%s",
            judgment.outcome.value,
            rebuttal.task_id,
        )
        return judgment

    # ----------------------------------------------------------
    # Private
    # ----------------------------------------------------------

    @staticmethod
    def _get_escalation_level(iteration: int) -> EscalationLevel:
        """Map iteration number to escalation level."""
        if iteration <= 1:
            return EscalationLevel.SOFT
        if iteration == 2:  # noqa: PLR2004
            return EscalationLevel.FIRM
        if iteration == 3:  # noqa: PLR2004
            return EscalationLevel.HARD_BLOCK
        return EscalationLevel.ESCALATE

    def _review_with_llm(
        self,
        patch: CodePatch,
        report: VerificationReport,
        escalation: EscalationLevel,
    ) -> ReviewDecision:
        """Use the critic model to review code with verification context."""
        system_prompt = _build_critic_system_prompt(escalation)
        user_prompt = self._build_review_prompt(patch, report)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result = self.llm_client.complete_structured(
            model=self.model,
            messages=messages,
            response_model=_CriticResponse,
        )

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
            escalation_level=escalation,
        )

        self.logger.info(
            "Review complete: verdict=%s, issues=%d, escalation=%s",
            decision.verdict.value,
            len(decision.issues),
            escalation.value,
        )
        return decision

    def _build_review_prompt(
        self,
        patch: CodePatch,
        report: VerificationReport,
    ) -> str:
        """Build the review prompt with all verification context."""
        code_parts = []
        for f in patch.files:
            code_parts.append(f"### {f.path}\n```\n{f.content}\n```")
        code_section = "\n\n".join(code_parts)

        verification_parts = [
            f"- **Tests passed:** {report.tests_passed}",
            f"- **Type check passed:** {report.type_check_passed}",
            f"- **Lint passed:** {report.lint_passed}",
            f"- **Execution passed:** {report.execution_passed}",
            f"- **Security passed:** {report.security_passed}",
        ]

        if report.coverage_percent is not None:
            verification_parts.append(
                f"- **Coverage:** {report.coverage_percent:.1f}%"
            )
            if report.coverage_delta is not None:
                sign = "+" if report.coverage_delta >= 0 else ""
                verification_parts.append(
                    f"- **Coverage delta:** {sign}"
                    f"{report.coverage_delta:.1f}%"
                )

        if not report.tests_passed:
            for tr in report.test_results:
                icon = "✅" if tr.passed else "❌"
                verification_parts.append(
                    f"  - Test `{tr.name}`: {icon}"
                )
                if tr.output:
                    verification_parts.append(
                        f"    Output: {tr.output[:500]}"
                    )

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

        if not report.security_passed and report.security_output:
            sec_out = report.security_output[:1000]
            verification_parts.append(
                f"- **Security output:**\n```\n{sec_out}\n```"
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
            f"## Coder's Explanation\n"
            f"{patch.explanation or 'None provided.'}\n\n"
            f"## Verification Signals (Facts)\n{verification_section}\n\n"
            f"## Your Task\n"
            f"Review the code and verification signals. Decide PASS or BLOCK."
        )

    @staticmethod
    def _build_rebuttal_prompt(
        rebuttal: RebuttalRequest,
        decision: ReviewDecision,
        report: VerificationReport,
    ) -> str:
        """Build the rebuttal judging prompt."""
        disputed = "\n".join(
            f"- {d}" for d in rebuttal.disputed_issues
        ) or "No specific issues disputed."

        return (
            f"## Original BLOCK Decision\n"
            f"Justification: {decision.justification}\n"
            f"Issues: {len(decision.issues)}\n\n"
            f"## Coder's Rebuttal\n"
            f"Justification: {rebuttal.justification}\n"
            f"Disputed issues:\n{disputed}\n\n"
            f"## Verification Facts\n"
            f"- Tests passed: {report.tests_passed}\n"
            f"- Type check: {report.type_check_passed}\n"
            f"- Lint: {report.lint_passed}\n"
            f"- Security: {report.security_passed}\n\n"
            f"## Your Task\n"
            f"Judge whether this rebuttal has merit. "
            f"Respond with ACCEPTED or REJECTED."
        )


# ============================================================
# Internal response models (not inter-agent contracts)
# ============================================================

from pydantic import BaseModel, Field  # noqa: E402


class _CriticIssueResponse(BaseModel):
    """A single issue in the Critic's response."""

    description: str = Field(description="What the issue is.")
    severity: str = Field(description="low, medium, high, or critical.")
    suggestion: str = Field(default="", description="Suggested fix.")
    source: str = Field(
        default="", description="Source tool (pytest, mypy, ruff, bandit)."
    )


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


class _RebuttalJudgeResponse(BaseModel):
    """Structured response for rebuttal judging."""

    outcome: str = Field(description="accepted or rejected.")
    reasoning: str = Field(description="Why the rebuttal was accepted/rejected.")
