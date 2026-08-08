"""
Coder Agent — Core Code Producer
==================================

Takes a TaskAssignment, calls the frontier model, produces a CodePatch.
On retry iterations, incorporates prior feedback from the Grounded Critic.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import (
    CodePatch,
    FileContent,
    RebuttalRequest,
    ReviewDecision,
    TaskAssignment,
    VerificationReport,
)

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient

# ============================================================
# System Prompt
# ============================================================

CODER_SYSTEM_PROMPT = """\
You are an expert software engineer. Your job is to produce clean, correct,
production-quality code for the given task.

Rules:
1. Write COMPLETE file contents — no placeholders, no TODOs, no "...".
2. Include proper type hints, docstrings, and error handling.
3. Follow the language's idiomatic style and best practices.
4. If tests are expected, include them in a separate test file.
5. Respond ONLY with the structured JSON output — no prose before or after.
6. If the task requires modifying an existing file (like JSON, text, config, or existing code), output the FULL modified content of THAT file directly in your response. Do NOT write a separate script to modify it unless explicitly asked to do so.
7. ANTI-HALLUCINATION (CRITICAL): If the task asks to "undo", "recover", or "restore" a deleted file, you MUST NOT recreate or rewrite it from scratch using your imagination. You do not have an undo tool. You must refuse the request or output an empty patch. NEVER write fake replacement code to pretend you successfully recovered a file.

If you receive feedback from a prior iteration, carefully address every
issue raised. Do NOT repeat the same mistakes.
"""


class CoderAgent(BaseAgent):
    """Coder agent — generates code patches from task assignments.

    Uses the 'frontier' model for maximum code quality.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model: str = "frontier",
        agent_id: str = "coder-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="coder", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="coder")

    def run(self, task: TaskAssignment) -> CodePatch:  # type: ignore[override]
        """Generate a code patch for the given task assignment.

        Args:
            task: The task assignment with description and constraints.

        Returns:
            A CodePatch with the generated files.
        """
        # LangGraph may pass states as dicts depending on channel definitions
        if isinstance(task, dict):
            task = TaskAssignment(**task)

        self.logger.info(
            "Generating code for task=%s, iteration=%d", task.task_id, task.iteration
        )

        user_prompt = self._build_prompt(task)

        messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Use structured output to guarantee contract compliance
        result = self.llm_client.complete_structured(
            complexity="complex",
            messages=messages,
            response_model=_CoderResponse,
        )

        # Convert to CodePatch contract
        files = [
            FileContent(path=f.path, content=f.content)
            for f in result.files
        ]

        patch = CodePatch(
            task_id=task.task_id,
            workflow_id=task.workflow_id,
            iteration=task.iteration,
            files=files,
            explanation=result.explanation,
        )

        self.logger.info(
            "Code generated: %d files, task=%s", len(patch.files), task.task_id
        )
        return patch

    @trace_agent_invocation(agent_role="coder_rebut")

    def rebut(
        self,
        decision: ReviewDecision,
        report: VerificationReport,
    ) -> RebuttalRequest | None:
        """Generate a rebuttal against a BLOCK decision.

        Per README line 232: the Coder may reject feedback **once per
        iteration** with a logical justification.

        Returns None if the Coder agrees with the feedback (no rebuttal).
        """
        self.logger.info(
            "Considering rebuttal: task=%s, iteration=%d, issues=%d",
            decision.task_id,
            decision.iteration,
            len(decision.issues),
        )

        user_prompt = self._build_rebuttal_prompt(decision, report)

        messages = [
            {"role": "system", "content": REBUTTAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        result = self.llm_client.complete_structured(
            complexity="complex",
            messages=messages,
            response_model=_RebuttalResponse,
        )

        if not result.should_rebut:
            self.logger.info("Coder accepts feedback, no rebuttal.")
            return None

        rebuttal = RebuttalRequest(
            task_id=decision.task_id,
            workflow_id=decision.workflow_id,
            iteration=decision.iteration,
            justification=result.justification,
            disputed_issues=result.disputed_issues,
        )

        self.logger.info(
            "Rebuttal generated: %d disputed issues",
            len(rebuttal.disputed_issues),
        )
        return rebuttal

    def _build_prompt(self, task: TaskAssignment) -> str:
        """Build the user prompt for the Coder."""
        parts = [
            f"## Task\n{task.description}",
            f"\n## Language\n{task.language}",
        ]

        if task.constraints:
            constraints_text = "\n".join(f"- {c}" for c in task.constraints)
            parts.append(f"\n## Constraints\n{constraints_text}")

        if task.prior_feedback:
            parts.append(
                f"\n## Feedback from Previous Iteration (iteration {task.iteration - 1})\n"
                f"Address ALL of the following issues:\n{task.prior_feedback}"
            )

        parts.append(f"\n## Iteration\nThis is attempt #{task.iteration}.")

        return "\n".join(parts)

    @staticmethod
    def _build_rebuttal_prompt(
        decision: ReviewDecision,
        report: VerificationReport,
    ) -> str:
        """Build the prompt for the Coder to consider a rebuttal."""
        issues_text = "\n".join(
            f"- [{i.severity.value}] {i.description} (source: {i.source})"
            for i in decision.issues
        ) or "No specific issues listed."

        return (
            f"## Critic's BLOCK Decision\n"
            f"Justification: {decision.justification}\n\n"
            f"## Issues Raised\n{issues_text}\n\n"
            f"## Feedback\n{decision.feedback_for_coder}\n\n"
            f"## Verification Facts\n"
            f"- Tests passed: {report.tests_passed}\n"
            f"- Type check: {report.type_check_passed}\n"
            f"- Lint: {report.lint_passed}\n"
            f"- Security: {report.security_passed}\n\n"
            f"## Your Task\n"
            f"Decide if you should rebut any of these issues. "
            f"Only rebut if you have strong evidence the feedback is wrong."
        )


# ============================================================
# System Prompt for Rebuttal
# ============================================================

REBUTTAL_SYSTEM_PROMPT = """\
You are an expert software engineer reviewing feedback from a code reviewer.

Decide whether to REBUT any of the reviewer's issues. Only rebut if:
1. A failing test asserts WRONG behavior (cite the spec).
2. A lint/type error is a FALSE POSITIVE (explain why).
3. The feedback misunderstands the requirements.

Do NOT rebut if the issues are legitimate. Be honest.
Respond ONLY with the structured JSON output.
"""


# ============================================================
# Internal response models (not inter-agent contracts)
# ============================================================

from pydantic import BaseModel, Field  # noqa: E402


class _CoderFileResponse(BaseModel):
    """A single file in the Coder's response."""

    path: str = Field(description="Relative file path.")
    content: str = Field(description="Full file content.")


class _CoderResponse(BaseModel):
    """Structured response from the Coder LLM call."""

    files: list[_CoderFileResponse] = Field(
        min_length=1,
        description="Files produced.",
    )
    explanation: str = Field(
        default="",
        description="Brief explanation of the approach.",
    )


class _RebuttalResponse(BaseModel):
    """Structured response for rebuttal consideration."""

    should_rebut: bool = Field(
        description="True if the Coder wants to rebut.",
    )
    justification: str = Field(
        default="I accept the feedback.",
        description="Why the Coder is rebutting (or accepting).",
    )
    disputed_issues: list[str] = Field(
        default_factory=list,
        description="Descriptions of issues being disputed.",
    )
