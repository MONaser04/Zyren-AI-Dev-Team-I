"""
State Projections
==================

Fold a list of events into the current WorkflowState.
This is the "read model" — derived entirely from the event log.
"""

from __future__ import annotations

from contracts.schemas import Verdict, WorkflowState, WorkflowStatus
from state.events import Event, EventType


def project_workflow_state(events: list[Event]) -> WorkflowState:
    """Project a list of events into a WorkflowState.

    Replays events in order to build the current state.
    This is a pure function — no side effects.

    Args:
        events: List of events for a single workflow, ordered by version.

    Returns:
        The current WorkflowState derived from the events.

    Raises:
        ValueError: If events list is empty or contains mixed workflow_ids.
    """
    if not events:
        msg = "Cannot project state from empty event list."
        raise ValueError(msg)

    workflow_ids = {e.workflow_id for e in events}
    if len(workflow_ids) > 1:
        msg = f"Events contain multiple workflow_ids: {workflow_ids}"
        raise ValueError(msg)

    workflow_id = events[0].workflow_id

    state = WorkflowState(workflow_id=workflow_id)

    for event in events:
        state = _apply_event(state, event)

    return state


def _apply_event(state: WorkflowState, event: Event) -> WorkflowState:
    """Apply a single event to the state, returning a new state."""
    match event.event_type:
        case EventType.TASK_CREATED:
            return state.model_copy(
                update={
                    "status": WorkflowStatus.PENDING,
                    "task_description": event.payload.get("task_description", ""),
                    "max_iterations": event.payload.get("max_iterations", 3),
                }
            )

        case EventType.WORKFLOW_STARTED:
            return state.model_copy(
                update={
                    "status": WorkflowStatus.IN_PROGRESS,
                }
            )

        case EventType.ITERATION_STARTED:
            return state.model_copy(
                update={
                    "status": WorkflowStatus.IN_PROGRESS,
                    "current_iteration": event.payload.get(
                        "iteration", state.current_iteration + 1
                    ),
                }
            )

        case EventType.CODE_SUBMITTED:
            patches = [*state.patches, event.payload.get("patch", {})]
            return state.model_copy(
                update={
                    "patches": patches,
                }
            )

        case EventType.VERIFICATION_COMPLETED:
            return state  # Report data is transient; only the review matters

        case EventType.REVIEW_DECIDED:
            decision = event.payload.get("decision", {})
            reviews = [*state.reviews, decision]
            return state.model_copy(
                update={
                    "reviews": reviews,
                }
            )

        case EventType.WORKFLOW_COMPLETED:
            return state.model_copy(
                update={
                    "status": WorkflowStatus.PASSED,
                    "final_verdict": Verdict.PASS,
                }
            )

        case EventType.WORKFLOW_FAILED:
            return state.model_copy(
                update={
                    "status": WorkflowStatus.FAILED,
                    "error": event.payload.get("reason", "Unknown error"),
                }
            )

        case _:
            # Unknown event types are silently ignored for forward compatibility
            return state
