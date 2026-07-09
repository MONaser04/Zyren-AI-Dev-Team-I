"""
Orchestrator Graph — LangGraph Feedback Loop with Rebuttal
=============================================================

Phase 2 upgrade: adds the Agentic Pushback (rebuttal) edge:

    START → assign_task → coder → tester → critic
         ├─ PASS → complete
         └─ BLOCK → should_rebut?
              ├─ yes → coder_rebut → judge
              │    ├─ ACCEPTED → complete
              │    └─ REJECTED → increment → coder
              └─ no → increment → coder
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
    RebuttalOutcome,
    RebuttalRequest,
    ReviewDecision,
    TaskAssignment,
    Verdict,
    VerificationReport,
)
from state.events import (
    code_submitted_event,
    rebuttal_judged_event,
    rebuttal_submitted_event,
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

    # Phase 2: Rebuttal tracking
    rebuttal_used: bool
    rebuttal_request: dict[str, Any]
    rebuttal_outcome: str

    # Event versioning
    event_version: int
    last_event_id: str
    correlation_id: str


# ============================================================
# Node Helpers
# ============================================================


def _next_version(state: GraphState) -> int:
    """Get the next event version from state."""
    return state.get("event_version", 0) + 1


# ============================================================
# Node Functions
# ============================================================


def _assign_task_node(
    state: GraphState, event_store: EventStore
) -> dict[str, Any]:
    """Create the task and emit the first event."""
    workflow_id = state.get("workflow_id", uuid.uuid4().hex[:12])
    task_desc = state.get("task_description", "")
    max_iter = state.get("max_iterations", 3)

    event = task_created_event(
        workflow_id=workflow_id,
        task_description=task_desc,
        max_iterations=max_iter,
    )
    event_store.append(event)

    task = TaskAssignment(
        workflow_id=workflow_id,
        description=task_desc,
        language=state.get("language", "python"),
        constraints=state.get("constraints", []),
        iteration=1,
    )

    return {
        **state,
        "workflow_id": workflow_id,
        "current_iteration": 1,
        "task_assignment": task.model_dump(),
        "event_version": event.version,
        "last_event_id": event.event_id,
        "correlation_id": event.correlation_id or event.event_id,
        "rebuttal_used": False,
    }


def _coder_node(
    state: GraphState, coder: CoderAgent, event_store: EventStore
) -> dict[str, Any]:
    """Run the Coder agent and emit a CODE_SUBMITTED event."""
    task_data = state["task_assignment"]
    iteration = state["current_iteration"]

    # On retry, inject feedback from the Critic
    feedback = state.get("feedback", "")
    if feedback and iteration > 1:
        task_data = {**task_data, "iteration": iteration, "prior_feedback": feedback}

    task = TaskAssignment.model_validate(task_data)
    patch = coder.run(task)

    version = _next_version(state)
    event = code_submitted_event(
        workflow_id=state["workflow_id"],
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
        "event_version": version,
        "last_event_id": event.event_id,
        "rebuttal_used": False,  # Reset per iteration
    }


def _tester_node(
    state: GraphState, tester: TesterAgent, event_store: EventStore
) -> dict[str, Any]:
    """Run the Tester agent and emit a VERIFICATION_COMPLETED event."""
    patch = CodePatch.model_validate(state["code_patch"])
    report = tester.run(patch)

    version = _next_version(state)
    event = verification_completed_event(
        workflow_id=state["workflow_id"],
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
    state: GraphState, critic: CriticAgent, event_store: EventStore
) -> dict[str, Any]:
    """Run the Critic agent and emit a REVIEW_DECIDED event."""
    patch = CodePatch.model_validate(state["code_patch"])
    report = VerificationReport.model_validate(state["verification_report"])
    decision = critic.run(patch, report)

    version = _next_version(state)
    event = review_decided_event(
        workflow_id=state["workflow_id"],
        version=version,
        decision_data=decision.model_dump(mode="json"),
        iteration=state["current_iteration"],
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "review_decision": decision.model_dump(),
        "verdict": decision.verdict.value,
        "feedback": decision.feedback_for_coder,
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _coder_rebut_node(
    state: GraphState, coder: CoderAgent, event_store: EventStore
) -> dict[str, Any]:
    """Coder considers and optionally submits a rebuttal."""
    decision = ReviewDecision.model_validate(state["review_decision"])
    report = VerificationReport.model_validate(state["verification_report"])

    rebuttal = coder.rebut(decision, report)

    if rebuttal is None:
        # Coder accepts feedback, no rebuttal
        return {
            **state,
            "rebuttal_used": True,
            "rebuttal_request": {},
            "rebuttal_outcome": "",
        }

    version = _next_version(state)
    event = rebuttal_submitted_event(
        workflow_id=state["workflow_id"],
        version=version,
        rebuttal_data=rebuttal.model_dump(mode="json"),
        iteration=state["current_iteration"],
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "rebuttal_used": True,
        "rebuttal_request": rebuttal.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _judge_rebuttal_node(
    state: GraphState, critic: CriticAgent, event_store: EventStore
) -> dict[str, Any]:
    """Critic judges the Coder's rebuttal."""
    rebuttal_data = state.get("rebuttal_request", {})

    # No rebuttal was submitted
    if not rebuttal_data:
        return {
            **state,
            "rebuttal_outcome": "no_rebuttal",
        }

    rebuttal = RebuttalRequest.model_validate(rebuttal_data)
    decision = ReviewDecision.model_validate(state["review_decision"])
    report = VerificationReport.model_validate(state["verification_report"])

    judgment = critic.judge_rebuttal(rebuttal, decision, report)

    version = _next_version(state)
    event = rebuttal_judged_event(
        workflow_id=state["workflow_id"],
        version=version,
        judgment_data=judgment.model_dump(mode="json"),
        iteration=state["current_iteration"],
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "rebuttal_outcome": judgment.outcome.value,
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _complete_node(
    state: GraphState, event_store: EventStore
) -> dict[str, Any]:
    """Mark the workflow as completed."""
    version = _next_version(state)
    event = workflow_completed_event(
        workflow_id=state["workflow_id"],
        version=version,
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    logger.info("Workflow PASSED: %s", state["workflow_id"])
    return {
        **state,
        "verdict": Verdict.PASS.value,
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _fail_node(
    state: GraphState, event_store: EventStore
) -> dict[str, Any]:
    """Mark the workflow as failed due to iteration cap."""
    version = _next_version(state)
    reason = (
        f"Iteration cap ({state.get('max_iterations', 3)}) reached "
        f"at iteration {state['current_iteration']}."
    )
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
# Decision Routers
# ============================================================


def _should_continue(state: GraphState) -> str:
    """Route after the Critic's verdict.

    Returns:
        'complete' if PASS, 'should_rebut' if BLOCK and under cap,
        'fail' if cap reached.
    """
    verdict = state.get("verdict", "")
    if verdict == Verdict.PASS.value:
        return "complete"

    current = state.get("current_iteration", 1)
    max_iter = state.get("max_iterations", 3)

    if current >= max_iter:
        return "fail"

    # Under cap and BLOCK — check if rebuttal is available
    return "should_rebut"


def _should_rebut_router(state: GraphState) -> str:
    """Decide whether to attempt a rebuttal.

    Only rebut if:
    - Rebuttal has not been used this iteration
    - There are specific issues to dispute
    """
    if state.get("rebuttal_used", False):
        return "no_rebut"

    # Check if there are issues worth disputing
    decision_data = state.get("review_decision", {})
    issues = decision_data.get("issues", [])
    if not issues:
        return "no_rebut"

    return "try_rebut"


def _rebuttal_outcome_router(state: GraphState) -> str:
    """Route after rebuttal judgment.

    Returns:
        'accepted' if rebuttal was accepted → PASS.
        'rejected' if rejected or no rebuttal → retry loop.
    """
    outcome = state.get("rebuttal_outcome", "")
    if outcome == RebuttalOutcome.ACCEPTED.value:
        return "accepted"
    return "rejected"


# ============================================================
# Graph Builder
# ============================================================


def build_feedback_loop(
    event_store: EventStore,
    llm_client: LLMClient,
    coder_model: str = "frontier",
    critic_model: str = "critic",
) -> StateGraph[GraphState]:
    """Build the feedback loop with rebuttal as a LangGraph StateGraph.

    Architecture (Phase 2):
        assign_task → coder → tester → critic
             ├─ complete (PASS)
             ├─ coder_rebut → judge_rebuttal
             │    ├─ accepted → complete
             │    └─ rejected → increment → coder
             └─ fail (cap reached)

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
    graph.add_node("coder_rebut", lambda s: _coder_rebut_node(s, coder, event_store))
    graph.add_node("judge_rebuttal", lambda s: _judge_rebuttal_node(s, critic, event_store))
    graph.add_node("complete", lambda s: _complete_node(s, event_store))
    graph.add_node("fail", lambda s: _fail_node(s, event_store))
    graph.add_node("increment", lambda s: {**s, "current_iteration": s["current_iteration"] + 1})

    # Set entry point
    graph.set_entry_point("assign_task")

    # Linear edges
    graph.add_edge("assign_task", "coder")
    graph.add_edge("coder", "tester")
    graph.add_edge("tester", "critic")

    # After critic: PASS → complete, BLOCK under cap → should_rebut, cap → fail
    graph.add_conditional_edges(
        "critic",
        _should_continue,
        {
            "complete": "complete",
            "should_rebut": "coder_rebut",
            "fail": "fail",
        },
    )

    # After coder_rebut: if rebuttal was submitted → judge it, if not → increment
    graph.add_edge("coder_rebut", "judge_rebuttal")

    # After judge_rebuttal: accepted → complete, rejected → increment → coder
    graph.add_conditional_edges(
        "judge_rebuttal",
        _rebuttal_outcome_router,
        {
            "accepted": "complete",
            "rejected": "increment",
        },
    )

    # Increment loops back to coder
    graph.add_edge("increment", "coder")

    # Terminal nodes
    graph.add_edge("complete", END)
    graph.add_edge("fail", END)

    return graph
