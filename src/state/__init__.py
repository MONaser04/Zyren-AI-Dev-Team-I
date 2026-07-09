# State — Event store, projections, optimistic locking
"""State module: event-sourced append-only log and state projections."""

from state.events import Event, EventType
from state.projections import project_workflow_state
from state.store import EventStore, OptimisticLockError, SQLiteEventStore

__all__ = [
    "Event",
    "EventStore",
    "EventType",
    "OptimisticLockError",
    "SQLiteEventStore",
    "project_workflow_state",
]
