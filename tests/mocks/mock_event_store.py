"""Mock Event Store for testing."""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
from uuid import uuid4


@dataclass
class MockEvent:
    """Mock event for testing."""
    event_id: str = field(default_factory=lambda: uuid4().hex[:16])
    event_type: str = "mock"
    workflow_id: str = ""
    iteration: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    payload: dict = field(default_factory=dict)


class MockEventStore:
    """In-memory event store for testing."""
    
    def __init__(self):
        self._events: dict[str, list] = {}  # workflow_id -> events
        self._event_counter = 0
    
    def append(self, event: MockEvent) -> MockEvent:
        """Append an event to the store."""
        if event.workflow_id not in self._events:
            self._events[event.workflow_id] = []
        event.event_id = event.event_id or f"evt-{self._event_counter}"
        self._event_counter += 1
        self._events[event.workflow_id].append(event)
        return event
    
    def get_events(self, workflow_id: str) -> list[MockEvent]:
        """Get all events for a workflow."""
        return self._events.get(workflow_id, []).copy()
    
    def get_latest_event(self, workflow_id: str, event_type: str = None) -> Optional[MockEvent]:
        """Get the latest event for a workflow, optionally filtered by type."""
        events = self.get_events(workflow_id)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-1] if events else None
    
    def clear(self, workflow_id: str = None):
        """Clear events for a workflow or all workflows."""
        if workflow_id:
            self._events.pop(workflow_id, None)
        else:
            self._events.clear()
            self._event_counter = 0
    
    def get_workflow_ids(self) -> list[str]:
        """Get all workflow IDs."""
        return list(self._events.keys())
    
    def event_count(self, workflow_id: str = None) -> int:
        """Get total event count."""
        if workflow_id:
            return len(self._events.get(workflow_id, []))
        return sum(len(events) for events in self._events.values())


# Pre-configured event stores for common test scenarios

def create_populated_event_store(workflow_id: str = "test-wf-001") -> MockEventStore:
    """Create an event store with some sample events."""
    store = MockEventStore()
    store.append(MockEvent(
        event_type="workflow_started",
        workflow_id=workflow_id,
        iteration=0,
        payload={"task_description": "Write a fibonacci function"},
    ))
    store.append(MockEvent(
        event_type="code_submitted",
        workflow_id=workflow_id,
        iteration=1,
        payload={"code": "def fib(n): return n if n < 2 else fib(n-1)+fib(n-2)"},
    ))
    store.append(MockEvent(
        event_type="tests_passed",
        workflow_id=workflow_id,
        iteration=1,
        payload={"tests": [{"name": "test_fib", "passed": True}]},
    ))
    store.append(MockEvent(
        event_type="workflow_completed",
        workflow_id=workflow_id,
        iteration=1,
        payload={"verdict": "PASS"},
    ))
    return store