"""
Dynamic Supervisor Agent
========================
Replaces static graph edges with a dynamic, LLM-driven runtime routing engine.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field

from agents.base import BaseAgent, AgentResult

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient


class SupervisorDecision(BaseModel):
    next_agent: str = Field(
        ...,
        description="The exact name of the next agent to call. Must be one of: "
                    "['planner', 'architect', 'ux', 'db', 'security', 'coder', "
                    "'tester', 'critic', 'integrator', 'docs', 'complete', 'fail']"
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of why this agent is the logical next step."
    )


class SupervisorAgent(BaseAgent):
    """Dynamically routes tasks by analyzing the current state of the workflow."""

    def __init__(self, agent_id: str, llm_client: LLMClient) -> None:
        super().__init__(agent_id=agent_id, role="supervisor", llm_client=llm_client)

    def run(self, task_description: str, events: list[dict[str, Any]]) -> AgentResult:
        """
        Evaluate the graph history and determine the next step.
        """
        self.logger.info(f"Analyzing {len(events)} past events to determine next route.")

        # Build context from past events
        history_str = "No steps taken yet. We are at the beginning."
        if events:
            history_lines = []
            for ev in events:
                node = ev.get("source_node", "unknown")
                msg = ev.get("message", "")
                if msg:
                    # Summarize the message to save tokens if it's too long
                    if len(msg) > 300:
                        msg = msg[:300] + "... [truncated]"
                history_lines.append(f"- Node [{node}]: {msg}")
            history_str = "\n".join(history_lines)

        sys_prompt = (
            "You are the central Routing Supervisor (Maestro) in an Autonomous Multi-Agent Software Agency.\n"
            "Your job is to look at the user's initial task, look at the steps completed so far, "
            "and dynamically decide which specialist agent should act next.\n\n"
            "AVAILABLE AGENTS:\n"
            "- planner: Breaks down the feature roadmap.\n"
            "- architect: Designs system architecture.\n"
            "- ux: Designs user interfaces and dark mode/animations.\n"
            "- db: Database schema engineering.\n"
            "- security: Security audits.\n"
            "- coder: Writes or refactors actual code based on plans.\n"
            "- tester: Tests the code written by the coder.\n"
            "- critic: Reviews code and UX design for quality.\n"
            "- integrator: Integrates multiple pieces together.\n"
            "- docs: Writes documentation.\n"
            "- complete: Use this when the task is fully tested, reviewed, and done.\n"
            "- fail: Use this if the system is stuck in an infinite loop of failures.\n\n"
            "CRITICAL RULES:\n"
            "1. Do not repeat agents needlessly if their job is done.\n"
            "2. If code was just written, it usually needs to go to 'tester' next.\n"
            "3. If 'tester' passes and there is a UX component, send to 'critic'.\n"
            "4. If 'critic' complains, send back to 'coder'.\n"
            "5. You MUST return valid JSON matching the schema."
        )

        user_prompt = (
            f"ORIGINAL TASK:\n{task_description}\n\n"
            f"EXECUTION HISTORY:\n{history_str}\n\n"
            "Analyze the history and decide the exact next_agent to call."
        )

        try:
            decision = self.llm_client.complete_structured(
                complexity="complex",
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_model=SupervisorDecision,
                temperature=0.0
            )

            self.logger.info(f"Routing to: {decision.next_agent} (Reasoning: {decision.reasoning})")
            
            return AgentResult(
                verdict="success",
                data={"next_agent": decision.next_agent, "reasoning": decision.reasoning},
                summary=f"Routing to {decision.next_agent}"
            )

        except Exception as e:
            self.logger.error(f"Supervisor routing failed: {e}")
            # Fallback to complete to avoid infinite loops on failure
            return AgentResult(
                verdict="error",
                data={"next_agent": "complete", "reasoning": str(e)},
                summary="Fallback due to routing error"
            )
