"""
Supervisor Agent — Phase 4 (Escalation Tie-Breaker)
====================================================

Stronger model; capped attempts → Break-Glass.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import ReviewDecision

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class SupervisorAgent(BaseAgent):
    """Supervisor: escalation tie-breaker (stronger model, capped attempts)."""

    role: str = "supervisor"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "supervisor-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="supervisor", llm_client=llm_client)
        self.model = model
        self._attempts = 0
        self._max_attempts = 3

    @trace_agent_invocation(agent_role="supervisor")

    def run(self, conflict: dict, state: dict) -> ReviewDecision:
        """Judge a deadlock between Coder and Critic."""
        self._attempts += 1
        if self._attempts > self._max_attempts:
            # Force resolution after max attempts
            return ReviewDecision(
                task_id=conflict.get("task_id", ""),
                workflow_id=conflict.get("workflow_id", ""),
                iteration=state.get("current_iteration", 1),
                verdict="PASS",  # Force pass after cap
                justification="Supervisor cap reached — forcing resolution via break-glass.",
                issues=[],
                feedback_for_coder="Human intervention required. Forced resolution applied.",
                escalation_level="ESCALATE",
            )

        prompt = self._build_prompt(conflict, state)
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=ReviewDecision,
            model=self.model,
            temperature=0.0,
        )

    def _build_prompt(self, conflict: dict, state: dict) -> str:
        return (
            f"Deadlock Context:\n{conflict}\n\n"
            f"Workflow State:\n{state}\n\n"
            "You are the Supervisor — final escalation authority. "
            "Review the Coder's rebuttal and Critic's position. "
            "Decide PASS (accept rebuttal) or BLOCK (uphold critique). "
            "Output ReviewDecision JSON. "
            f"This is attempt {self._attempts}/{self._max_attempts}."
        )

    def __repr__(self) -> str:
        return f"SupervisorAgent(model={self.model}, attempts={self._attempts})"