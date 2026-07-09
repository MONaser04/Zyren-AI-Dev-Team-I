"""
Event Store — Append-Only Log with Optimistic Locking
======================================================

Abstract base + SQLite implementation for v0.
Every mutation is an immutable event. Current state is a projection.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from state.events import Event, EventType

if TYPE_CHECKING:
    from pathlib import Path

# ============================================================
# Exceptions
# ============================================================


class OptimisticLockError(Exception):
    """Raised when a write conflicts with the current version.

    This happens when two concurrent writers try to append an event
    with the same version number for the same workflow.
    """


class EventNotFoundError(Exception):
    """Raised when no events are found for a given workflow."""


# ============================================================
# Abstract Event Store
# ============================================================


class EventStore(ABC):
    """Abstract interface for the event store.

    All implementations must guarantee:
    - Append-only (no updates or deletes)
    - Optimistic locking via version field
    - Events are immutable once written
    """

    @abstractmethod
    def append(self, event: Event) -> None:
        """Append an event to the log.

        Raises:
            OptimisticLockError: If the version conflicts with the current state.
        """

    @abstractmethod
    def get_events(self, workflow_id: str) -> list[Event]:
        """Retrieve all events for a workflow, ordered by version."""

    @abstractmethod
    def get_latest_version(self, workflow_id: str) -> int:
        """Get the latest version number for a workflow (0 if no events)."""

    @abstractmethod
    def get_event_by_id(self, event_id: str) -> Event | None:
        """Retrieve a single event by its ID."""


# ============================================================
# SQLite Event Store (v0)
# ============================================================

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    event_id       TEXT PRIMARY KEY,
    workflow_id    TEXT NOT NULL,
    agent_id       TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    payload        TEXT NOT NULL DEFAULT '{}',
    version        INTEGER NOT NULL,
    timestamp      TEXT NOT NULL,
    causation_id   TEXT,
    correlation_id TEXT,

    -- Enforce: one version per workflow (optimistic locking)
    UNIQUE(workflow_id, version)
);

CREATE INDEX IF NOT EXISTS idx_events_workflow
    ON events(workflow_id, version);

CREATE INDEX IF NOT EXISTS idx_events_correlation
    ON events(correlation_id);
"""


class SQLiteEventStore(EventStore):
    """SQLite-backed event store for local development (v0).

    Uses a UNIQUE constraint on (workflow_id, version) to enforce
    optimistic locking if two writers race.
    """

    def __init__(self, db_path: str = "events.db") -> None:
        """Initialize the SQLite event store."""
        self._db_path = db_path
        # LangGraph runs parallel nodes in separate threads, so check_same_thread=False is required.
        import threading
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(_CREATE_TABLE_SQL)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def append(self, event: Event) -> None:
        """Append an event to the append-only log, auto-incrementing version if version is 0."""
        import time
        max_retries = 10
        with self._lock:
            for attempt in range(max_retries):
                try:
                    if event.version == 0:
                        cursor = self._conn.execute(
                            "SELECT MAX(version) FROM events WHERE workflow_id = ?",
                            (event.workflow_id,),
                        )
                        row = cursor.fetchone()
                        latest_version = row[0] if row and row[0] is not None else 0
                        actual_version = latest_version + 1
                    else:
                        actual_version = event.version

                    self._conn.execute(
                        "INSERT INTO events (event_id, workflow_id, agent_id, event_type, payload, version, timestamp, causation_id, correlation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            event.event_id,
                            event.workflow_id,
                            event.agent_id,
                            event.event_type.value,
                            json.dumps(event.payload),
                            actual_version,
                            event.timestamp.isoformat(),
                            event.causation_id,
                            event.correlation_id,
                        ),
                    )
                    self._conn.commit()
                    return  # Success
                except sqlite3.IntegrityError as e:
                    self._conn.rollback()
                    if "version" in str(e) or "UNIQUE" in str(e):
                        if event.version == 0 and attempt < max_retries - 1:
                            time.sleep(0.05)  # Wait and retry with new max version
                            continue
                        raise OptimisticLockError(
                            f"Version conflict: workflow={event.workflow_id}, version={actual_version} already exists."
                        ) from e

    def get_events(self, workflow_id: str) -> list[Event]:
        """Retrieve all events for a workflow, ordered by version."""
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT event_id, workflow_id, agent_id, event_type,
                       payload, version, timestamp, causation_id, correlation_id
                FROM events
                WHERE workflow_id = ?
                ORDER BY version ASC
                """,
                (workflow_id,),
            )
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def get_latest_version(self, workflow_id: str) -> int:
        """Get the latest version number for a workflow (0 if no events)."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT MAX(version) FROM events WHERE workflow_id = ?",
                (workflow_id,),
            )
            row = cursor.fetchone()
            return row[0] if row[0] is not None else 0

    def get_event_by_id(self, event_id: str) -> Event | None:
        """Retrieve a single event by its ID."""
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT event_id, workflow_id, agent_id, event_type,
                       payload, version, timestamp, causation_id, correlation_id
                FROM events
                WHERE event_id = ?
                """,
                (event_id,),
            )
            row = cursor.fetchone()
            return self._row_to_event(row) if row else None

    @staticmethod
    def _row_to_event(row: tuple) -> Event:  # type: ignore[type-arg]
        """Convert a database row to an Event model."""
        from datetime import datetime

        return Event(
            event_id=row[0],
            workflow_id=row[1],
            agent_id=row[2],
            event_type=EventType(row[3]),
            payload=json.loads(row[4]),
            version=row[5],
            timestamp=datetime.fromisoformat(row[6]),
            causation_id=row[7],
            correlation_id=row[8],
        )
