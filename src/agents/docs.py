"""
Docs Agent — Phase 4 (Milestone-Based)
=======================================

Runs twice: post-architecture (ADRs) and post-integration (README, OpenAPI, inline docs).
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import DocsOutput

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class DocsAgent(BaseAgent):
    """Docs Agent: milestone-based documentation (post-arch ADRs + post-integration READMEs/OpenAPI)."""

    role: str = "docs"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "docs-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="docs", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="docs")

    def run(self, milestone: str, context: dict) -> DocsOutput:
        prompt = self._build_prompt(milestone, context)
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=DocsOutput,
            model=self.model,
            temperature=0.1,
        )

    def _build_prompt(self, milestone: str, context: dict) -> str:
        if milestone == "post_architecture":
            arch = context.get("architect_design", {})
            adrs = arch.get("adrs", [])
            return (
                f"Architecture Design:\n{arch}\n\n"
                f"ADRs to document: {len(adrs)}\n\n"
                "Produce DocsOutput as JSON for milestone 'post_architecture' with:\n"
                "- adrs: list of Architecture Decision Records\n"
                "- readme: null\n"
                "- openapi_spec: null\n"
                "- inline_docs: null"
            )
        else:  # post_integration
            integ = context.get("integrator_output", {})
            return (
                f"Integrated Output:\n{integ}\n\n"
                "Produce DocsOutput as JSON for milestone 'post_integration' with:\n"
                "- adrs: null\n"
                "- readme: comprehensive README.md content\n"
                "- openapi_spec: OpenAPI/Swagger spec if APIs present\n"
                "- inline_docs: list of inline documentation comments"
            )

    def __repr__(self) -> str:
        return f"DocsAgent(model={self.model})"