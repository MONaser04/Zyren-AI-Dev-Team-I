"""
Security Agent — Phase 4 (Dedicated Critic)
============================================

OWASP-aligned security review with SAST scanning.
Dedicated critic for Coder, Architect, and Security roles.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from agents.base import BaseAgent
from contracts.schemas import SecurityReport

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore


class SecurityAgent(BaseAgent):
    """Security Agent: produces SecurityReport (dedicated critic)."""

    role: str = "security"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "security-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="security", llm_client=llm_client)
        self.model = model

    @trace_agent_invocation(agent_role="security")

    def run(self, code_patch: dict, architect_design: dict) -> SecurityReport:
        prompt = self._build_prompt(code_patch, architect_design)
        return self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=SecurityReport,
            complexity="complex",
            temperature=0.0,
        )

    def _build_prompt(self, code_patch: dict, arch_design: dict) -> str:
        return (
            f"Code Patch:\n{code_patch}\n\n"
            f"Architect Design:\n{arch_design}\n\n"
            "Perform a security review aligned with OWASP Top 10 for Agentic Applications (2026).\n"
            "Produce SecurityReport as JSON with:\n"
            "- vulnerabilities: list of {id, severity, description, file, line, fix_hint}\n"
            "- sast_summary: summary of static analysis findings\n"
            "- recommendations: list of actionable recommendations\n"
            "- risk_level: low | medium | high | critical"
        )

    def __repr__(self) -> str:
        return f"SecurityAgent(model={self.model})"