"""
Product Analyst Agent — Phase 4
================================

Converts a raw task description into a structured Product Requirement Document (PRD)
with user stories, acceptance criteria, constraints, and non-functional requirements.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import ProductRequirementDoc

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class ProductAnalystAgent(BaseAgent):
    """Product Analyst: produces a ProductRequirementDoc from a task description."""

    role: str = "product_analyst"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "product_analyst-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="product_analyst", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="product_analyst")

    def run(
        self,
        task_description: str,
        constraints: list[str] | None = None,
    ) -> ProductRequirementDoc:
        prompt = self._build_prompt(task_description, constraints or [])
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=ProductRequirementDoc,
            complexity="complex",
            temperature=0.1,
        )

    def _build_prompt(self, task: str, constraints: list[str]) -> str:
        constraints_text = "\n".join(f"- {c}" for c in constraints) if constraints else "None specified."
        return (
            f"Task: {task}\n\n"
            f"Constraints:\n{constraints_text}\n\n"
            "Produce a Product Requirement Document (PRD) as JSON with:\n"
            "- user_stories: list of 'As a... I want... So that...'\n"
            "- acceptance_criteria: list of 'Given/When/Then' statements\n"
            "- constraints: technical, regulatory, timeline constraints\n"
            "- non_functional: performance, security, accessibility requirements"
        )

    def __repr__(self) -> str:
        return f"ProductAnalystAgent(model={self.model})"