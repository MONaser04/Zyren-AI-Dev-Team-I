"""
Orchestrator Graph — LangGraph Minimal Feedback Loop
======================================================

Implements the evaluator-optimizer pattern as a LangGraph StateGraph:

    START → assign_task → coder → tester → critic → [decision]
                                                         ├─ PASS → complete
                                                         └─ BLOCK → coder (loop)
                                                              └─ cap → fail

Every transition emits an event to the Event Store.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, TypedDict

from langgraph.graph import END, StateGraph

from agents.coder import CoderAgent
from agents.critic import CriticAgent
from agents.tester import TesterAgent
from contracts.schemas import (
    CodePatch,
    ReviewDecision,
    TaskAssignment,
    Verdict,
    VerificationReport,
)
from state.events import (
    code_submitted_event,
    review_decided_event,
    task_created_event,
    verification_completed_event,
    workflow_completed_event,
    workflow_failed_event,
)

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore

logger = logging.getLogger(__name__)

# ============================================================
# Graph State
# ============================================================


class GraphState(TypedDict, total=False):
    """Typed state for the LangGraph feedback loop.

    All data flows through this state dict. LangGraph manages
    state transitions and checkpointing.
    """

    # Workflow metadata
    workflow_id: str
    task_description: str
    language: str
    constraints: list[str]
    max_iterations: int

    # Iteration tracking
    current_iteration: int

    # Agent outputs (latest)
    task_assignment: dict[str, Any]
    code_patch: dict[str, Any]
    verification_report: dict[str, Any]
    review_decision: dict[str, Any]

    # Loop control
    verdict: str
    feedback: str
    error: str

    # Event tracking
    event_version: int
    correlation_id: str
    last_event_id: str


# ============================================================
# Node Functions
# ============================================================


def _assign_task_node(
    state: GraphState,
    event_store: EventStore,
) -> GraphState:
    """Create the initial task assignment and emit TASK_CREATED event."""
    workflow_id = state["workflow_id"]
    version = state.get("event_version", 0) + 1

    event = task_created_event(
        workflow_id=workflow_id,
        task_description=state["task_description"],
        max_iterations=state.get("max_iterations", 3),
    )
    event_store.append(event)

    task = TaskAssignment(
        workflow_id=workflow_id,
        description=state["task_description"],
        language=state.get("language", "python"),
        constraints=state.get("constraints", []),
        iteration=1,
    )

    return {
        **state,
        "current_iteration": 1,
        "task_assignment": task.model_dump(),
        "event_version": version,
        "correlation_id": event.correlation_id or event.event_id,
        "last_event_id": event.event_id,
    }


def _coder_node(
    state: GraphState,
    coder: CoderAgent,
    event_store: EventStore,
) -> GraphState:
    """Run the Coder agent and emit CODE_SUBMITTED event."""
    iteration = state["current_iteration"]
    workflow_id = state["workflow_id"]

    # Build task assignment with feedback if this is a retry
    feedback = state.get("feedback")
    task = TaskAssignment(
        workflow_id=workflow_id,
        task_id=state["task_assignment"].get("task_id", uuid.uuid4().hex[:12]),
        description=state["task_description"],
        language=state.get("language", "python"),
        constraints=state.get("constraints", []),
        iteration=iteration,
        prior_feedback=feedback if iteration > 1 else None,
    )

    # Run coder
    patch: CodePatch = coder.run(task=task)

    # Emit event
    version = state.get("event_version", 0) + 1
    event = code_submitted_event(
        workflow_id=workflow_id,
        version=version,
        patch_data=patch.model_dump(mode="json"),
        iteration=iteration,
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "code_patch": patch.model_dump(),
        "task_assignment": task.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _tester_node(
    state: GraphState,
    tester: TesterAgent,
    event_store: EventStore,
) -> GraphState:
    """Run the Tester agent and emit VERIFICATION_COMPLETED event."""
    workflow_id = state["workflow_id"]
    patch = CodePatch.model_validate(state["code_patch"])

    # Run tester
    report: VerificationReport = tester.run(patch=patch)

    # Emit event
    version = state.get("event_version", 0) + 1
    event = verification_completed_event(
        workflow_id=workflow_id,
        version=version,
        report_data=report.model_dump(mode="json"),
        iteration=state["current_iteration"],
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "verification_report": report.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _critic_node(
    state: GraphState,
    critic: CriticAgent,
    event_store: EventStore,
) -> GraphState:
    """Run the Grounded Critic and emit REVIEW_DECIDED event."""
    workflow_id = state["workflow_id"]
    patch = CodePatch.model_validate(state["code_patch"])
    report = VerificationReport.model_validate(state["verification_report"])

    # Run critic
    decision: ReviewDecision = critic.run(patch=patch, report=report)

    # Emit event
    version = state.get("event_version", 0) + 1
    event = review_decided_event(
        workflow_id=workflow_id,
        version=version,
        decision_data=decision.model_dump(mode="json"),
        iteration=state["current_iteration"],
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "review_decision": decision.model_dump(mode="json"),
        "verdict": decision.verdict.value,
        "feedback": decision.feedback_for_coder,
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _complete_node(
    state: GraphState,
    event_store: EventStore,
) -> GraphState:
    """Mark workflow as completed and emit WORKFLOW_COMPLETED event."""
    version = state.get("event_version", 0) + 1
    event = workflow_completed_event(
        workflow_id=state["workflow_id"],
        version=version,
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    logger.info("Workflow COMPLETED: %s", state["workflow_id"])
    return {**state, "event_version": version, "last_event_id": event.event_id}


def _fail_node(
    state: GraphState,
    event_store: EventStore,
) -> GraphState:
    """Mark workflow as failed and emit WORKFLOW_FAILED event."""
    version = state.get("event_version", 0) + 1
    reason = f"Iteration cap reached ({state.get('max_iterations', 3)} iterations)"
    event = workflow_failed_event(
        workflow_id=state["workflow_id"],
        version=version,
        reason=reason,
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    logger.info("Workflow FAILED: %s — %s", state["workflow_id"], reason)
    return {
        **state,
        "error": reason,
        "event_version": version,
        "last_event_id": event.event_id,
    }


# ============================================================
# Decision Router
# ============================================================


def _should_continue(state: GraphState) -> str:
    """Route based on the Critic's verdict and iteration cap.

    Returns:
        'complete' if PASS, 'retry' if BLOCK and under cap, 'fail' if cap reached.
    """
    verdict = state.get("verdict", "")
    if verdict == Verdict.PASS.value:
        return "complete"

    current = state.get("current_iteration", 1)
    max_iter = state.get("max_iterations", 3)

    if current >= max_iter:
        return "fail"

    return "retry"


# ============================================================
# Graph Builder
# ============================================================


def build_feedback_loop(
    event_store: EventStore,
    llm_client: LLMClient,
    coder_model: str = "frontier",
    critic_model: str = "critic",
) -> StateGraph[GraphState]:
    """Build the minimal feedback loop as a LangGraph StateGraph.

    Architecture:
        assign_task → coder → tester → critic → [PASS|BLOCK|CAP]
                                                     ├─ complete
                                                     ├─ retry → increment → coder
                                                     └─ fail

    Args:
        event_store: The event store for persisting events.
        llm_client: The LLM client for agent calls.
        coder_model: Model alias for the Coder agent.
        critic_model: Model alias for the Critic agent.

    Returns:
        A compiled LangGraph StateGraph.
    """
    # Create agents
    coder = CoderAgent(llm_client=llm_client, model=coder_model)
    tester = TesterAgent()
    critic = CriticAgent(llm_client=llm_client, model=critic_model)

    # Build graph
    graph = StateGraph(GraphState)

    # Add nodes (using closures to inject dependencies)
    graph.add_node("assign_task", lambda s: _assign_task_node(s, event_store))
    graph.add_node("coder", lambda s: _coder_node(s, coder, event_store))
    graph.add_node("tester", lambda s: _tester_node(s, tester, event_store))
    graph.add_node("critic", lambda s: _critic_node(s, critic, event_store))
    graph.add_node("complete", lambda s: _complete_node(s, event_store))
    graph.add_node("fail", lambda s: _fail_node(s, event_store))
    graph.add_node("increment", lambda s: {**s, "current_iteration": s["current_iteration"] + 1})

    # Set entry point
    graph.set_entry_point("assign_task")

    # Add edges
    graph.add_edge("assign_task", "coder")
    graph.add_edge("coder", "tester")
    graph.add_edge("tester", "critic")

    # Conditional edges from critic
    graph.add_conditional_edges(
        "critic",
        _should_continue,
        {
            "complete": "complete",
            "retry": "increment",
            "fail": "fail",
        },
    )

    # Increment loops back to coder
    graph.add_edge("increment", "coder")

    # Terminal nodes
    graph.add_edge("complete", END)
    graph.add_edge("fail", END)

    return graph
