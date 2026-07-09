"""
Coder Agent — Core Code Producer
==================================

Takes a TaskAssignment, calls the frontier model, produces a CodePatch.
On retry iterations, incorporates prior feedback from the Grounded Critic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import CodePatch, FileContent, TaskAssignment

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

    def run(self, task: TaskAssignment) -> CodePatch:  # type: ignore[override]
        """Generate a code patch for the given task assignment.

        Args:
            task: The task assignment with description and constraints.

        Returns:
            A CodePatch with the generated files.
        """
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
            model=self.model,
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


# ============================================================
# Internal response model (not an inter-agent contract)
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
