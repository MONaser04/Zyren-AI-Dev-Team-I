"""
Tester Agent — External Signal Generator
==========================================

Takes a CodePatch, delegates to VerificationRunner, and produces a
VerificationReport containing ONLY measured facts — no opinions.

Phase 2 refactor: all tool-running logic is now in the
verification.steps module. The TesterAgent is a thin orchestrator.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from verification.runner import VerificationRunner

if TYPE_CHECKING:
    from contracts.schemas import CodePatch, VerificationReport


class TesterAgent(BaseAgent):
    """Tester agent — runs external verification tools on code patches.

    Captures stdout/stderr/exit codes from real tools.
    Produces facts only — no opinions, no suggestions.

    Phase 2: delegates to VerificationRunner for composable step pipeline.
    """

    def __init__(
        self,
        agent_id: str = "tester-01",
        prior_coverage: float | None = None,
    ) -> None:
        # Tester doesn't need an LLM — it runs tools
        from gateway.llm_client import LLMClient

        super().__init__(
            agent_id=agent_id,
            role="tester",
            llm_client=LLMClient(),  # Unused but required by base
        )
        self.prior_coverage = prior_coverage

    @trace_agent_invocation(agent_role="tester")

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

        # Build file list for the runner
        files = [(f.path, f.content) for f in patch.files]

        # Delegate to the composable verification pipeline
        runner = VerificationRunner(prior_coverage=self.prior_coverage)
        report = runner.verify(
            task_id=patch.task_id,
            workflow_id=patch.workflow_id,
            iteration=patch.iteration,
            files=files,
        )

        self.logger.info(
            "Verification complete: all_clean=%s, task=%s",
            report.all_clean,
            patch.task_id,
        )
        return report
