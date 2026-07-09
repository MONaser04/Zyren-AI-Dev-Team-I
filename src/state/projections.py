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

        case EventType.REBUTTAL_SUBMITTED:
            rebuttals = [*state.rebuttals, event.payload.get("rebuttal", {})]
            return state.model_copy(
                update={
                    "rebuttals": rebuttals,
                }
            )

        case EventType.REBUTTAL_JUDGED:
            judgments = [*state.rebuttal_judgments, event.payload.get("judgment", {})]
            return state.model_copy(
                update={
                    "rebuttal_judgments": judgments,
                }
            )

        case EventType.PRODUCT_REQUIREMENTS_CREATED:
            return state.model_copy(update={'product_requirements': event.payload.get('prd')})

        case EventType.TASK_DAG_CREATED:
            return state.model_copy(update={'task_dag': event.payload.get('dag')})

        case EventType.ARCHITECT_DESIGN_CREATED:
            return state.model_copy(update={'architect_design': event.payload.get('design')})

        case EventType.UX_DESIGN_CREATED:
            return state.model_copy(update={'ux_design': event.payload.get('design')})

        case EventType.DB_SCHEMA_CREATED:
            return state.model_copy(update={'data_schema': event.payload.get('schema')})

        case EventType.SECURITY_REPORT_CREATED:
            return state.model_copy(update={'security_report': event.payload.get('report')})

        case EventType.RESEARCH_NOTES_CREATED:
            return state.model_copy(update={'research_notes': event.payload.get('notes')})

        case EventType.INTEGRATION_COMPLETED:
            return state.model_copy(update={'integrator_output': event.payload.get('integration')})

        case EventType.DOCUMENTATION_CREATED:
            docs = event.payload.get('docs', {})
            if 'adr_id' in docs or docs.get('title', '').startswith('ADR'):
                return state.model_copy(update={'docs_adr': docs})
            return state.model_copy(update={'docs_final': docs})

        case _:
            # Unknown event types are silently ignored for forward compatibility
            return state
