"""
WorkflowRun Contract — Phase 5
===============================
Complete record of a single workflow execution through the autonomous loop.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentInvocation(BaseModel):
    """Record of a single agent invocation within a workflow."""
    agent_role: str = Field(description="e.g., coder, tester, critic")
    agent_id: str = Field(description="e.g., coder-01")
    iteration: int = Field(default=0, description="Which iteration this invocation belongs to")
    duration_seconds: float = Field(default=0.0)
    tokens_used: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    success: bool = Field(default=True)
    error_message: str | None = Field(default=None)


class WorkflowRun(BaseModel):
    """Complete record of a workflow execution."""

    workflow_id: str = Field(description="Unique workflow identifier (UUID)")
    task_description: str = Field(description="Original task description")
    language: str = Field(default="python", description="Target programming language")
    max_iterations: int = Field(default=3, description="Maximum allowed iterations")

    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = Field(default=None)
    total_duration_seconds: float = Field(default=0.0)

    # Iterations
    iterations_completed: int = Field(default=0)
    converged: bool = Field(default=False, description="Did the loop converge (no more improvement)?")

    # Agents invoked
    agent_invocations: list[AgentInvocation] = Field(default_factory=list)

    # Final output
    success: bool = Field(default=False, description="Overall workflow success")
    final_code: dict[str, str] = Field(default_factory=dict, description="filename → content")
    error: str | None = Field(default=None, description="Final error message if failed")

    # Cost
    total_cost_usd: float = Field(default=0.0)
    budget_exceeded: bool = Field(default=False)

    # HITL
    human_interventions: int = Field(default=0, description="Number of HITL pauses")

    # State events count
    events_count: int = Field(default=0, description="Total events recorded in EventStore")

    # Artifact path
    artifact_path: str | None = Field(default=None, description="Path to persisted artifacts")

    def add_invocation(self, inv: AgentInvocation) -> None:
        """Add an agent invocation record."""
        self.agent_invocations.append(inv)
        self.total_cost_usd += inv.cost_usd

    def summary(self) -> dict[str, Any]:
        """Flat summary dict."""
        return {
            "workflow_id": self.workflow_id,
            "success": self.success,
            "iterations": self.iterations_completed,
            "converged": self.converged,
            "agents_invoked": len(self.agent_invocations),
            "total_cost_usd": self.total_cost_usd,
            "duration_s": self.total_duration_seconds,
            "files_produced": len(self.final_code),
            "budget_exceeded": self.budget_exceeded,
            "human_interventions": self.human_interventions,
        }