"""
Architect Agent — Phase 4
=========================

Produces an ArchitectDesign with ADRs, component diagram, tech choices, and interfaces.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from contracts.schemas import ArchitectDesign, ProductRequirementDoc, TaskDAG

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class ArchitectAgent(BaseAgent):
    """Architect: produces an ArchitectDesign from PRD + TaskDAG."""

    role: str = "architect"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "architect-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="architect", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="architect")

    def run(
        self,
        prd: ProductRequirementDoc,
        dag: TaskDAG,
    ) -> ArchitectDesign:
        prompt = self._build_prompt(prd, dag)
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=ArchitectDesign,
            model=self.model,
            temperature=0.1,
        )

    def _build_prompt(self, prd: ProductRequirementDoc, dag: TaskDAG) -> str:
        nodes = "\n".join(f"- {n.id}: {n.description} (role={n.agent_role})" for n in dag.nodes)
        return (
            f"PRD Constraints: {', '.join(prd.constraints) or 'None'}\n"
            f"Non-functional: {', '.join(prd.non_functional) or 'None'}\n\n"
            f"Task DAG Nodes:\n{nodes}\n\n"
            "Produce an ArchitectDesign as JSON with:\n"
            "- adrs: list of {title, context, decision, consequences, status}\n"
            "- component_diagram: mermaid/plantuml diagram\n"
            "- tech_choices: list of technology decisions\n"
            "- interfaces: list of {name, protocol, contract} (REST, gRPC, GraphQL, async)"
        )

    def __repr__(self) -> str:
        return f"ArchitectAgent(model={self.model})"