"""
Planner Agent — Phase 4
========================

Converts a PRD into a Task DAG with dependencies and agent assignments.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from src.contracts.schemas import ProductRequirementDoc, TaskDAG

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class PlannerAgent(BaseAgent):
    """Planner: produces a TaskDAG from a ProductRequirementDoc."""

    role: str = "planner"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "planner-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="planner", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="planner")

    def run(self, prd: ProductRequirementDoc) -> TaskDAG:
        prompt = self._build_prompt(prd)
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=TaskDAG,
            model=self.model,
            temperature=0.1,
        )

    def _build_prompt(self, prd: ProductRequirementDoc) -> str:
        user_stories = "\n".join(f"- {s}" for s in prd.user_stories)
        acceptance = "\n".join(f"- {c}" for c in prd.acceptance_criteria)
        return (
            f"PRD Summary:\n"
            f"User Stories:\n{user_stories}\n\n"
            f"Acceptance Criteria:\n{acceptance}\n\n"
            f"Constraints: {', '.join(prd.constraints) or 'None'}\n"
            f"Non-functional: {', '.join(prd.non_functional) or 'None'}\n\n"
            "Create a Task DAG as JSON with:\n"
            "- nodes: list of {id, description, depends_on[], agent_role, complexity}\n"
            "- critical_path: list of node IDs on the critical path\n"
            "Agent roles: architect, coder, ux, db_engineer, researcher, security\n"
            "Complexity: simple, medium, complex\n"
            "Ensure dependencies form a valid DAG."
        )

    def __repr__(self) -> str:
        return f"PlannerAgent(model={self.model})"