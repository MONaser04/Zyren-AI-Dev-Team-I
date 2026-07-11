"""
DB Engineer Agent — Phase 4 (Conditional: Persistence Only)
============================================================

Produces DataSchema with tables, migrations, indexes.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from src.agents.base import BaseAgent
from contracts.schemas import ArchitectDesign, DataSchema, TaskDAG

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class DBEngineerAgent(BaseAgent):
    """DB Engineer: produces DataSchema (conditional: persistence tasks only)."""

    role: str = "db_engineer"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "db_engineer-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="db_engineer", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="db_engineer")

    def run(
        self,
        arch: ArchitectDesign,
        dag: TaskDAG,
    ) -> DataSchema:
        prompt = self._build_prompt(arch, dag)
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=DataSchema,
            model=self.model,
            temperature=0.1,
        )

    def _build_prompt(self, arch: ArchitectDesign, dag: TaskDAG) -> str:
        return (
            f"Component Diagram: {arch.component_diagram}\n"
            f"Interfaces: {', '.join(i.name for i in arch.interfaces) or 'None'}\n"
            f"Task Nodes: {', '.join(n.description for n in dag.nodes if n.agent_role == 'db_engineer') or 'None'}\n\n"
            "Produce a DataSchema as JSON with:\n"
            "- tables: list of {name, columns[], primary_key[], foreign_keys[]}\n"
            "- migrations: list of migration descriptions\n"
            "- indexes: list of index definitions"
        )

    def __repr__(self) -> str:
        return f"DBEngineerAgent(model={self.model})"