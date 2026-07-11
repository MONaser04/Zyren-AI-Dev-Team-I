"""
Liaison Agent — Phase 4 (Human Interface)
==========================================

The ONLY human interface; translates state ⇄ operator.
HITL only — no regular run() method.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from src.agents.base import BaseAgent

if TYPE_CHECKING:
    from src.gateway.llm_client import LLMClient
    from src.state.store import EventStore


class LiaisonAgent(BaseAgent):
    """Liaison: human interface — translates workflow state to operator and vice versa.

    This agent does NOT have a run() method. It operates via HITL interrupts
    and state notifications only.
    """

    role: str = "liaison"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "liaison-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="liaison", llm_client=llm_client)
        self.model = model

    def notify_human(self, workflow_id: str, message: str, severity: str = "info") -> None:
        """Send a notification to the human operator.

        In production, this would integrate with Slack, email, dashboard, etc.
        For now, logs the message.
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.log(
            {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}.get(severity, logging.INFO),
            "[LIAISON] Workflow %s: %s", workflow_id, message
        )

    def request_human_input(self, workflow_id: str, question: str, options: list[str] | None = None) -> str:
        """Request input from human operator (blocking).

        In production, this would pause the workflow and wait for human response
        via a dashboard or chat interface.
        """
        # For now, simulate with a simple prompt
        import sys
        prompt = f"\n[HUMAN INPUT REQUIRED] Workflow {workflow_id}: {question}"
        if options:
            prompt += f"\nOptions: {', '.join(options)}"
        prompt += "\n> "
        return input(prompt)

    def __repr__(self) -> str:
        return f"LiaisonAgent(model={self.model})"