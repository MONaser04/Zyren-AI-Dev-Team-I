"""
UX Agent — Phase 4 (Conditional: Frontend Only)
===============================================

Produces UXDesign with wireframes, accessibility notes, design system refs.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import ArchitectDesign, ProductRequirementDoc, UXDesign

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class UXAgent(BaseAgent):
    """UX Designer: produces UXDesign (conditional: frontend tasks only)."""

    role: str = "ux"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "ux-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="ux", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="ux")

    def run(
        self,
        arch: ArchitectDesign,
        prd: ProductRequirementDoc,
    ) -> UXDesign:
        prompt = self._build_prompt(arch, prd)
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=UXDesign,
            complexity="complex",
            temperature=0.1,
        )

    def _build_prompt(self, arch: ArchitectDesign, prd: ProductRequirementDoc) -> str:
        return (
            f"Component Diagram: {arch.component_diagram}\n"
            f"Tech Choices: {', '.join(arch.tech_choices) or 'None'}\n"
            f"User Stories: {', '.join(prd.user_stories) or 'None'}\n\n"
            "Produce a UXDesign as JSON with:\n"
            "- wireframes: list of wireframe descriptions/paths\n"
            "- accessibility_notes: WCAG compliance notes\n"
            "- design_system_refs: design system component references"
        )

    def __repr__(self) -> str:
        return f"UXAgent(model={self.model})"