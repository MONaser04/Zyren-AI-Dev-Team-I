"""
Workflow Runner — Entry Point for the Minimal Feedback Loop
=============================================================

Provides a simple API to run a coding task through the full
Orchestrator → Coder → Tester → Grounded Critic loop.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from gateway.llm_client import LLMClient
from orchestrator.graph import GraphState, build_feedback_loop
from state.projections import project_workflow_state
from state.store import EventStore, SQLiteEventStore

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# Workflow Result
# ============================================================


@dataclass
class WorkflowResult:
    """Result of running a workflow through the feedback loop."""

    workflow_id: str
    success: bool
    iterations: int
    final_code: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    events_count: int = 0


# ============================================================
# Runner
# ============================================================


def run_workflow(
    task_description: str,
    *,
    language: str = "python",
    constraints: list[str] | None = None,
    max_iterations: int = 3,
    event_store: EventStore | None = None,
    llm_client: LLMClient | None = None,
    coder_model: str = "frontier",
    critic_model: str = "critic",
    db_path: str | Path | None = None,
) -> WorkflowResult:
    """Run a coding task through the minimal feedback loop.

    This is the main entry point for the system. It:
    1. Creates a workflow in the event store
    2. Builds and runs the LangGraph feedback loop
    3. Returns the result

    Args:
        task_description: Natural-language description of the coding task.
        language: Target programming language.
        constraints: Additional constraints or requirements.
        max_iterations: Maximum feedback loop iterations (hard cap).
        event_store: Pre-existing event store (creates one if None).
        llm_client: Pre-existing LLM client (creates one if None).
        coder_model: Model alias for the Coder agent.
        critic_model: Model alias for the Critic agent.
        db_path: Path for the SQLite database (None = in-memory).

    Returns:
        A WorkflowResult with the outcome.
    """
    # Initialize dependencies
    if event_store is None:
        event_store = SQLiteEventStore(db_path=db_path or ":memory:")
    if llm_client is None:
        llm_client = LLMClient()

    workflow_id = uuid.uuid4().hex[:16]

    logger.info(
        "Starting workflow %s: %s (max_iterations=%d)",
        workflow_id,
        task_description[:80],
        max_iterations,
    )

    # Build the graph
    graph = build_feedback_loop(
        event_store=event_store,
        llm_client=llm_client,
        coder_model=coder_model,
        critic_model=critic_model,
    )

    # Compile the graph
    compiled = graph.compile()

    # Initial state
    initial_state: GraphState = {
        "workflow_id": workflow_id,
        "task_description": task_description,
        "language": language,
        "constraints": constraints or [],
        "max_iterations": max_iterations,
        "current_iteration": 0,
        "event_version": 0,
    }

    # Run the graph
    try:
        final_state = compiled.invoke(initial_state)
    except Exception as e:
        logger.exception("Workflow %s failed with exception", workflow_id)
        return WorkflowResult(
            workflow_id=workflow_id,
            success=False,
            iterations=0,
            error=str(e),
        )

    # Extract results
    events = event_store.get_events(workflow_id)
    # Validate that events can be projected (catches schema drift)
    if events:
        project_workflow_state(events)

    # Extract final code files
    final_code: dict[str, str] = {}
    code_patch = final_state.get("code_patch", {})
    if isinstance(code_patch, dict) and "files" in code_patch:
        for f in code_patch["files"]:
            if isinstance(f, dict):
                final_code[f.get("path", "unknown")] = f.get("content", "")

    success = final_state.get("verdict") == "PASS"

    result = WorkflowResult(
        workflow_id=workflow_id,
        success=success,
        iterations=final_state.get("current_iteration", 0),
        final_code=final_code,
        error=final_state.get("error"),
        events_count=len(events),
    )

    logger.info(
        "Workflow %s finished: success=%s, iterations=%d, events=%d",
        workflow_id,
        result.success,
        result.iterations,
        result.events_count,
    )

    return result
