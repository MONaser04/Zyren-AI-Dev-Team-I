"""
Researcher Agent — Phase 4 (On-Demand)
======================================

Produces ResearchNotes for specific knowledge gaps.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import ResearchNotes

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class ResearcherAgent(BaseAgent):
    """Researcher: produces ResearchNotes (on-demand for specific topics)."""

    role: str = "researcher"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "researcher-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="researcher", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="researcher")

    def run(self, topic: str, context: str) -> ResearchNotes:
        prompt = self._build_prompt(topic, context)
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=ResearchNotes,
            model=self.model,
            temperature=0.2,
        )

    def _build_prompt(self, topic: str, context: str) -> str:
        return (
            f"The user has asked the following Research Question: '{topic}'\n"
            f"Context Data:\n{context}\n\n"
            "You are an expert Research Agent. Analyze the provided context and provide a DIRECT and SPECIFIC answer to the user's question.\n"
            "Produce ResearchNotes as JSON with:\n"
            "- findings: List of key analytical findings that directly address the user's question.\n"
            "- sources: List of source references (e.g., 'System Model Registry Status').\n"
            "- recommendations: Your final conclusion, actionable recommendations, or the explicit definitive answer to the user's query."
        )

    def __repr__(self) -> str:
        return f"ResearcherAgent(model={self.model})"