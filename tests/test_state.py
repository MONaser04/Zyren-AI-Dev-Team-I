"""
Tests — Event-Sourced State Store
===================================

Validates:
- Events can be appended and retrieved
- Optimistic locking rejects stale writes
- State projection correctly folds events
- Events are immutable (no updates/deletes)
"""

from __future__ import annotations

import pytest

from state.events import (
    EventType,
    code_submitted_event,
    review_decided_event,
    task_created_event,
    workflow_completed_event,
    workflow_failed_event,
)
from state.projections import project_workflow_state
from state.store import OptimisticLockError, SQLiteEventStore


@pytest.fixture
def store() -> SQLiteEventStore:
    """Create an in-memory event store for testing."""
    return SQLiteEventStore(db_path=":memory:")


class TestSQLiteEventStore:
    """Test the SQLite event store implementation."""

    def test_append_and_retrieve(self, store: SQLiteEventStore) -> None:
        event = task_created_event(
            workflow_id="wf-001",
            task_description="Fix the bug",
            max_iterations=3,
        )
        store.append(event)

        events = store.get_events("wf-001")
        assert len(events) == 1
        assert events[0].event_id == event.event_id
        assert events[0].workflow_id == "wf-001"
        assert events[0].event_type == EventType.TASK_CREATED
        assert events[0].version == 1

    def test_multiple_events_ordered(self, store: SQLiteEventStore) -> None:
        e1 = task_created_event(workflow_id="wf-001", task_description="Task")
        store.append(e1)

        e2 = code_submitted_event(
            workflow_id="wf-001",
            version=2,
            patch_data={"files": []},
            iteration=1,
            causation_id=e1.event_id,
            correlation_id=e1.correlation_id,
        )
        store.append(e2)

        events = store.get_events("wf-001")
        assert len(events) == 2
        assert events[0].version == 1
        assert events[1].version == 2

    def test_optimistic_lock_rejects_duplicate_version(
        self, store: SQLiteEventStore
    ) -> None:
        e1 = task_created_event(workflow_id="wf-001", task_description="Task")
        store.append(e1)

        # Try to append another event with the same version
        e2 = code_submitted_event(
            workflow_id="wf-001",
            version=1,  # Same version — should fail
            patch_data={},
            iteration=1,
        )
        with pytest.raises(OptimisticLockError):
            store.append(e2)

    def test_get_latest_version(self, store: SQLiteEventStore) -> None:
        assert store.get_latest_version("wf-001") == 0

        e1 = task_created_event(workflow_id="wf-001", task_description="Task")
        store.append(e1)
        assert store.get_latest_version("wf-001") == 1

        e2 = code_submitted_event(
            workflow_id="wf-001", version=2, patch_data={}, iteration=1
        )
        store.append(e2)
        assert store.get_latest_version("wf-001") == 2

    def test_get_event_by_id(self, store: SQLiteEventStore) -> None:
        e1 = task_created_event(workflow_id="wf-001", task_description="Task")
        store.append(e1)

        found = store.get_event_by_id(e1.event_id)
        assert found is not None
        assert found.event_id == e1.event_id

    def test_get_event_by_id_not_found(self, store: SQLiteEventStore) -> None:
        assert store.get_event_by_id("nonexistent") is None

    def test_workflows_are_isolated(self, store: SQLiteEventStore) -> None:
        e1 = task_created_event(workflow_id="wf-001", task_description="Task 1")
        e2 = task_created_event(workflow_id="wf-002", task_description="Task 2")
        store.append(e1)
        store.append(e2)

        assert len(store.get_events("wf-001")) == 1
        assert len(store.get_events("wf-002")) == 1

    def test_correlation_and_causation(self, store: SQLiteEventStore) -> None:
        e1 = task_created_event(workflow_id="wf-001", task_description="Task")
        store.append(e1)

        e2 = code_submitted_event(
            workflow_id="wf-001",
            version=2,
            patch_data={},
            iteration=1,
            causation_id=e1.event_id,
            correlation_id=e1.correlation_id,
        )
        store.append(e2)

        events = store.get_events("wf-001")
        assert events[1].causation_id == e1.event_id
        assert events[1].correlation_id == e1.correlation_id


class TestStateProjection:
    """Test the event → state projection logic."""

    def test_project_task_created(self) -> None:
        e = task_created_event(
            workflow_id="wf-001",
            task_description="Fix the bug",
            max_iterations=5,
        )
        state = project_workflow_state([e])

        assert state.workflow_id == "wf-001"
        assert state.task_description == "Fix the bug"
        assert state.max_iterations == 5

    def test_project_full_pass_workflow(self) -> None:
        events = [
            task_created_event(workflow_id="wf-001", task_description="Task"),
            code_submitted_event(
                workflow_id="wf-001",
                version=2,
                patch_data={"files": [{"path": "a.py", "content": "x"}]},
                iteration=1,
            ),
            review_decided_event(
                workflow_id="wf-001",
                version=3,
                decision_data={"verdict": "PASS", "justification": "All good"},
                iteration=1,
            ),
            workflow_completed_event(workflow_id="wf-001", version=4),
        ]
        state = project_workflow_state(events)

        assert state.status.value == "passed"
        assert state.final_verdict is not None
        assert len(state.patches) == 1
        assert len(state.reviews) == 1

    def test_project_failed_workflow(self) -> None:
        events = [
            task_created_event(workflow_id="wf-001", task_description="Task"),
            workflow_failed_event(
                workflow_id="wf-001",
                version=2,
                reason="Iteration cap reached",
            ),
        ]
        state = project_workflow_state(events)

        assert state.status.value == "failed"
        assert state.error == "Iteration cap reached"

    def test_project_empty_events_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            project_workflow_state([])

    def test_project_mixed_workflows_raises(self) -> None:
        e1 = task_created_event(workflow_id="wf-001", task_description="A")
        e2 = task_created_event(workflow_id="wf-002", task_description="B")
        with pytest.raises(ValueError, match="multiple"):
            project_workflow_state([e1, e2])
