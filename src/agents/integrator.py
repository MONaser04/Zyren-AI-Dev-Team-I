"""
Integrator Agent — Phase 4
===========================

Fan-in merge: consolidates outputs from parallel fan-out agents into a unified result.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import IntegratorOutput

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class IntegratorAgent(BaseAgent):
    """Integrator: merges fan-out outputs into IntegratorOutput."""

    role: str = "integrator"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "integrator-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="integrator", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="integrator")

    def run(self, fan_out_outputs: dict[str, object]) -> IntegratorOutput:
        prompt = self._build_prompt(fan_out_outputs)
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=IntegratorOutput,
            complexity="complex",
            temperature=0.1,
        )

    def _build_prompt(self, outputs: dict[str, object]) -> str:
        parts = []
        for role, output in outputs.items():
            if output:
                parts.append(f"=== {role.upper()} ===\n{output}")
        joined = "\n\n".join(parts)
        return (
            f"Merge the following parallel agent outputs into a coherent whole:\n\n"
            f"{joined}\n\n"
            "Produce IntegratorOutput as JSON with:\n"
            "- merged_files: list of {path, action, content}\n"
            "- conflicts_resolved: list of conflict descriptions\n"
            "- rollback_plan: step-by-step rollback procedure"
        )

    def __repr__(self) -> str:
        return f"IntegratorAgent(model={self.model})"