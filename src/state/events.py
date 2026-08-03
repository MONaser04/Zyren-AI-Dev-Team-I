"""
Event Model & Event Types
==========================

Immutable event records for the append-only event log.
Every mutation in the system is captured as an event with the
minimal schema specified in the README:

    {event_id, workflow_id, agent_id, event_type, payload,
     version, timestamp, causation_id, correlation_id}
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ============================================================
# Event Types
# ============================================================


class EventType(StrEnum):
    """Types of events in the system."""

    # Workflow lifecycle
    TASK_CREATED = "task_created"
    WORKFLOW_STARTED = "workflow_started"
    ROUTING_DECIDED = "routing_decided"

    # Coding cycle
    CODE_SUBMITTED = "code_submitted"
    VERIFICATION_COMPLETED = "verification_completed"
    REVIEW_DECIDED = "review_decided"

    # Workflow outcomes
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"

    # Iteration
    ITERATION_STARTED = "iteration_started"

    # Phase 2: Rebuttal flow
    REBUTTAL_SUBMITTED = "rebuttal_submitted"
    REBUTTAL_JUDGED = "rebuttal_judged"
    
    # Phase 4: Full SDLC
    PRODUCT_REQUIREMENTS_CREATED = "product_requirements_created"
    TASK_DAG_CREATED = "task_dag_created"
    ARCHITECT_DESIGN_CREATED = "architect_design_created"
    UX_DESIGN_CREATED = "ux_design_created"
    DB_SCHEMA_CREATED = "db_schema_created"
    SECURITY_REPORT_CREATED = "security_report_created"
    RESEARCH_NOTES_CREATED = "research_notes_created"
    DEEP_RESEARCH_COMPLETED = "deep_research_completed"
    INTEGRATION_COMPLETED = "integration_completed"
    DOCUMENTATION_CREATED = "documentation_created"


# ============================================================
# Event Model
# ============================================================


class Event(BaseModel):
    """An immutable event in the append-only log.

    Fields match the README's minimal event schema exactly:
    - event_id:       unique identifier for this event
    - workflow_id:    which workflow this belongs to
    - agent_id:       which agent produced this event
    - event_type:     what happened
    - payload:        arbitrary JSON data
    - version:        for optimistic locking (monotonically increasing per workflow)
    - timestamp:      when the event was created (UTC)
    - causation_id:   the event_id that directly caused this event
    - correlation_id: the root event_id of the causal chain (usually = first event)
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    event_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Globally unique event identifier.",
    )
    workflow_id: str = Field(
        description="Parent workflow identifier.",
    )
    agent_id: str = Field(
        description="ID of the agent that produced this event.",
    )
    event_type: EventType = Field(
        description="What kind of mutation occurred.",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data (JSON-serializable).",
    )
    version: int = Field(
        ge=0,
        description="Monotonically increasing version per workflow (for optimistic locking).",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="UTC timestamp when this event was created.",
    )
    causation_id: str | None = Field(
        default=None,
        description="Event ID that directly caused this event.",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Root event ID of the causal chain.",
    )


# ============================================================
# Event Factory Functions
# ============================================================


def _make_event(
    *,
    workflow_id: str,
    agent_id: str,
    event_type: EventType,
    version: int,
    payload: dict[str, Any] | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Internal factory for creating events with sensible defaults."""
    return Event(
        workflow_id=workflow_id,
        agent_id=agent_id,
        event_type=event_type,
        payload=payload or {},
        version=version,
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def task_created_event(
    *,
    workflow_id: str,
    task_description: str,
    max_iterations: int = 3,
    correlation_id: str | None = None,
) -> Event:
    """Create a TASK_CREATED event (always version 1)."""
    event = _make_event(
        workflow_id=workflow_id,
        agent_id="orchestrator",
        event_type=EventType.TASK_CREATED,
        version=1,
        payload={
            "task_description": task_description,
            "max_iterations": max_iterations,
        },
        correlation_id=correlation_id,
    )
    # Set correlation_id to self if this is the root event
    if correlation_id is None:
        # Re-create with correlation_id = event_id (root of chain)
        return Event(
            event_id=event.event_id,
            workflow_id=event.workflow_id,
            agent_id=event.agent_id,
            event_type=event.event_type,
            payload=event.payload,
            version=event.version,
            timestamp=event.timestamp,
            causation_id=event.causation_id,
            correlation_id=event.event_id,
        )
    return event


def code_submitted_event(
    *,
    workflow_id: str,
    version: int,
    patch_data: dict[str, Any],
    iteration: int,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Create a CODE_SUBMITTED event."""
    return _make_event(
        workflow_id=workflow_id,
        agent_id="coder",
        event_type=EventType.CODE_SUBMITTED,
        version=version,
        payload={"patch": patch_data, "iteration": iteration},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def verification_completed_event(
    *,
    workflow_id: str,
    version: int,
    report_data: dict[str, Any],
    iteration: int,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Create a VERIFICATION_COMPLETED event."""
    return _make_event(
        workflow_id=workflow_id,
        agent_id="tester",
        event_type=EventType.VERIFICATION_COMPLETED,
        version=version,
        payload={"report": report_data, "iteration": iteration},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def review_decided_event(
    *,
    workflow_id: str,
    version: int,
    decision_data: dict[str, Any],
    iteration: int,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Create a REVIEW_DECIDED event."""
    return _make_event(
        workflow_id=workflow_id,
        agent_id="critic",
        event_type=EventType.REVIEW_DECIDED,
        version=version,
        payload={"decision": decision_data, "iteration": iteration},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def workflow_completed_event(
    *,
    workflow_id: str,
    version: int,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Create a WORKFLOW_COMPLETED event."""
    return _make_event(
        workflow_id=workflow_id,
        agent_id="orchestrator",
        event_type=EventType.WORKFLOW_COMPLETED,
        version=version,
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def workflow_failed_event(
    *,
    workflow_id: str,
    version: int,
    reason: str,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Create a WORKFLOW_FAILED event."""
    return _make_event(
        workflow_id=workflow_id,
        agent_id="orchestrator",
        event_type=EventType.WORKFLOW_FAILED,
        version=version,
        payload={"reason": reason},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def rebuttal_submitted_event(
    *,
    workflow_id: str,
    version: int,
    rebuttal_data: dict[str, Any],
    iteration: int,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Create a REBUTTAL_SUBMITTED event."""
    return _make_event(
        workflow_id=workflow_id,
        agent_id="coder",
        event_type=EventType.REBUTTAL_SUBMITTED,
        version=version,
        payload={"rebuttal": rebuttal_data, "iteration": iteration},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def rebuttal_judged_event(
    *,
    workflow_id: str,
    version: int,
    judgment_data: dict[str, Any],
    iteration: int,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Create a REBUTTAL_JUDGED event."""
    return _make_event(
        workflow_id=workflow_id,
        agent_id="critic",
        event_type=EventType.REBUTTAL_JUDGED,
        version=version,
        payload={"judgment": judgment_data, "iteration": iteration},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def routing_decided_event(
    *,
    workflow_id: str,
    version: int,
    decision_data: dict[str, Any],
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Create a ROUTING_DECIDED event."""
    return _make_event(
        workflow_id=workflow_id,
        agent_id="orchestrator",
        event_type=EventType.ROUTING_DECIDED,
        version=version,
        payload={"decision": decision_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def architect_design_event(
    *,
    workflow_id: str,
    version: int,
    design_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return _make_event(
        workflow_id=workflow_id,
        agent_id="architect",
        event_type=EventType.ARCHITECT_DESIGN_CREATED,
        version=version,
        payload={"design": design_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )

def ux_design_event(
    *,
    workflow_id: str,
    version: int,
    design_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return _make_event(
        workflow_id=workflow_id,
        agent_id="ux",
        event_type=EventType.UX_DESIGN_CREATED,
        version=version,
        payload={"design": design_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )

def db_schema_event(
    *,
    workflow_id: str,
    version: int,
    schema_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return _make_event(
        workflow_id=workflow_id,
        agent_id="db_engineer",
        event_type=EventType.DB_SCHEMA_CREATED,
        version=version,
        payload={"schema": schema_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )

def security_report_event(
    *,
    workflow_id: str,
    version: int,
    report_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return _make_event(
        workflow_id=workflow_id,
        agent_id="security",
        event_type=EventType.SECURITY_REPORT_CREATED,
        version=version,
        payload={"report": report_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )

def research_notes_event(
    *,
    workflow_id: str,
    version: int,
    notes_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return _make_event(
        workflow_id=workflow_id,
        agent_id="researcher",
        event_type=EventType.RESEARCH_NOTES_CREATED,
        version=version,
        payload={"notes": notes_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )


def deep_research_completed_event(
    *,
    workflow_id: str,
    version: int,
    report_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    """Create a DEEP_RESEARCH_COMPLETED event."""
    return _make_event(
        workflow_id=workflow_id,
        agent_id="deep_researcher",
        event_type=EventType.DEEP_RESEARCH_COMPLETED,
        version=version,
        payload={"report": report_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )

def integration_event(
    *,
    workflow_id: str,
    version: int,
    integrator_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return _make_event(
        workflow_id=workflow_id,
        agent_id="integrator",
        event_type=EventType.INTEGRATION_COMPLETED,
        version=version,
        payload={"integration": integrator_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )

def documentation_event(
    *,
    workflow_id: str,
    version: int,
    docs_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return _make_event(
        workflow_id=workflow_id,
        agent_id="docs",
        event_type=EventType.DOCUMENTATION_CREATED,
        version=version,
        payload={"docs": docs_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )

def product_requirements_event(
    *,
    workflow_id: str,
    version: int,
    prd_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return _make_event(
        workflow_id=workflow_id,
        agent_id="product_analyst",
        event_type=EventType.PRODUCT_REQUIREMENTS_CREATED,
        version=version,
        payload={"prd": prd_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )

def task_dag_event(
    *,
    workflow_id: str,
    version: int,
    dag_data: dict,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> Event:
    return _make_event(
        workflow_id=workflow_id,
        agent_id="planner",
        event_type=EventType.TASK_DAG_CREATED,
        version=version,
        payload={"dag": dag_data},
        causation_id=causation_id,
        correlation_id=correlation_id,
    )
