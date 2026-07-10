"""
Feedback Store — Phase 5
=========================
SQLite-based persistent store for feedback records, tuning history,
and model performance data. Used by analyser, tuner, and reporter.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Data Models ────────────────────────────────────────────────────────────────


@dataclass
class FeedbackRecord:
    """A structured piece of feedback from the evaluation loop."""

    workflow_id: str
    source: str  # "tester", "linter", "critic", "security", "verifier"
    severity: str  # "error", "warning", "info"
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "source": self.source,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


# ── SQLite Store ────────────────────────────────────────────────────────────────


class FeedbackStore:
    """Persistent store for Phase 5 feedback, tunings, and model stats.

    Tables:
      - feedback     : individual feedback records
      - tunings      : prompt-tuning history
      - model_stats  : per-model performance tracking
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        workflow_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        message TEXT NOT NULL,
                        details TEXT DEFAULT '{}',
                        timestamp TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tunings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent TEXT NOT NULL,
                        original_prompt TEXT NOT NULL,
                        variants TEXT NOT NULL,
                        evaluations TEXT DEFAULT '[]',
                        best_variant TEXT DEFAULT '',
                        best_score REAL DEFAULT 0.0,
                        timestamp TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS model_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        model TEXT NOT NULL,
                        workflow_id TEXT NOT NULL,
                        success INTEGER NOT NULL DEFAULT 0,
                        prompt_tokens INTEGER DEFAULT 0,
                        completion_tokens INTEGER DEFAULT 0,
                        latency_s REAL DEFAULT 0.0,
                        cost_usd REAL DEFAULT 0.0,
                        timestamp TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_feedback_workflow ON feedback(workflow_id)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_feedback_source ON feedback(source)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_feedback_severity ON feedback(severity)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_tunings_agent ON tunings(agent)
                    """
                )
                conn.commit()
            finally:
                conn.close()

    # ── Feedback CRUD ──────────────────────────────────────────────────────────

    def insert(self, record: FeedbackRecord) -> int:
        """Insert a single feedback record. Returns the row id."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.execute(
                    "INSERT INTO feedback (workflow_id, source, severity, message, details, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        record.workflow_id,
                        record.source,
                        record.severity,
                        record.message,
                        json.dumps(record.details),
                        record.timestamp,
                    ),
                )
                conn.commit()
                return cursor.lastrowid or 0
            finally:
                conn.close()

    def insert_batch(self, records: list[FeedbackRecord]) -> int:
        """Insert multiple feedback records efficiently."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.executemany(
                    "INSERT INTO feedback (workflow_id, source, severity, message, details, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            r.workflow_id,
                            r.source,
                            r.severity,
                            r.message,
                            json.dumps(r.details),
                            r.timestamp,
                        )
                        for r in records
                    ],
                )
                conn.commit()
                return len(records)
            finally:
                conn.close()

    def query(
        self,
        *,
        workflow_id: str | None = None,
        source: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query feedback records with optional filters."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            try:
                conditions: list[str] = []
                params: list[Any] = []

                if workflow_id:
                    conditions.append("workflow_id = ?")
                    params.append(workflow_id)
                if source:
                    conditions.append("source = ?")
                    params.append(source)
                if severity:
                    conditions.append("severity = ?")
                    params.append(severity)

                where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                rows = conn.execute(
                    f"SELECT * FROM feedback {where} ORDER BY timestamp DESC LIMIT ?",
                    params + [limit],
                ).fetchall()

                return [dict(r) for r in rows]
            finally:
                conn.close()

    def count_by_source(self) -> dict[str, int]:
        """Count feedback records grouped by source."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                rows = conn.execute(
                    "SELECT source, COUNT(*) as cnt FROM feedback GROUP BY source"
                ).fetchall()
                return {r[0]: r[1] for r in rows}
            finally:
                conn.close()

    def count_by_severity(self) -> dict[str, int]:
        """Count feedback records grouped by severity."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                rows = conn.execute(
                    "SELECT severity, COUNT(*) as cnt FROM feedback GROUP BY severity"
                ).fetchall()
                return {r[0]: r[1] for r in rows}
            finally:
                conn.close()

    def get_error_patterns(self, min_count: int = 2) -> list[dict[str, Any]]:
        """Find recurring error messages (potential patterns to fix)."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                rows = conn.execute(
                    """
                    SELECT message, COUNT(*) as cnt, source, severity
                    FROM feedback
                    WHERE severity = 'error'
                    GROUP BY message
                    HAVING cnt >= ?
                    ORDER BY cnt DESC
                    """,
                    (min_count,),
                ).fetchall()
                return [
                    {"message": r[0], "count": r[1], "source": r[2], "severity": r[3]}
                    for r in rows
                ]
            finally:
                conn.close()

    # ── Tuning History ─────────────────────────────────────────────────────────

    def save_tuning(
        self,
        *,
        agent: str,
        original_prompt: str,
        variants: list[str],
        evaluations: list[dict[str, Any]],
        best_variant: str = "",
        best_score: float = 0.0,
    ) -> int:
        """Record a prompt-tuning run."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.execute(
                    "INSERT INTO tunings (agent, original_prompt, variants, evaluations, best_variant, best_score, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        agent,
                        original_prompt,
                        json.dumps(variants),
                        json.dumps(evaluations),
                        best_variant,
                        best_score,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
                return cursor.lastrowid or 0
            finally:
                conn.close()

    def get_tuning_history(
        self, *, agent: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Retrieve past tuning runs."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                if agent:
                    rows = conn.execute(
                        "SELECT * FROM tunings WHERE agent = ? ORDER BY timestamp DESC LIMIT ?",
                        (agent, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM tunings ORDER BY timestamp DESC LIMIT ?",
                        (limit,),
                    ).fetchall()

                results = []
                for r in rows:
                    results.append(
                        {
                            "id": r[0],
                            "agent": r[1],
                            "original_prompt": r[2],
                            "variants": json.loads(r[3]),
                            "evaluations": json.loads(r[4]),
                            "best_variant": r[5],
                            "best_score": r[6],
                            "timestamp": r[7],
                        }
                    )
                return results
            finally:
                conn.close()

    def get_best_prompt(self, agent: str) -> str | None:
        """Return the best-known prompt for an agent (highest score)."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                row = conn.execute(
                    "SELECT best_variant FROM tunings WHERE agent = ? ORDER BY best_score DESC LIMIT 1",
                    (agent,),
                ).fetchone()
                return row[0] if row else None
            finally:
                conn.close()

    # ── Model Stats ─────────────────────────────────────────────────────────────

    def record_model_usage(
        self,
        *,
        model: str,
        workflow_id: str,
        success: bool,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_s: float = 0.0,
        cost_usd: float = 0.0,
    ) -> int:
        """Record a model call's performance."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.execute(
                    "INSERT INTO model_stats (model, workflow_id, success, prompt_tokens, completion_tokens, latency_s, cost_usd, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        model,
                        workflow_id,
                        1 if success else 0,
                        prompt_tokens,
                        completion_tokens,
                        latency_s,
                        cost_usd,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
                return cursor.lastrowid or 0
            finally:
                conn.close()

    def get_model_performance(self, model: str) -> dict[str, Any]:
        """Get aggregate performance stats for a model."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(*) as total, SUM(success) as successes,
                           AVG(latency_s) as avg_latency, SUM(cost_usd) as total_cost
                    FROM model_stats
                    WHERE model = ?
                    """,
                    (model,),
                ).fetchone()
                total = row[0] or 0
                successes = row[1] or 0
                return {
                    "model": model,
                    "total_calls": total,
                    "successes": successes,
                    "success_rate": round(successes / total, 4) if total > 0 else 0.0,
                    "avg_latency_s": round(row[2], 4) if row[2] else 0.0,
                    "total_cost_usd": round(row[3], 4) if row[3] else 0.0,
                }
            finally:
                conn.close()

    # ── Maintenance ────────────────────────────────────────────────────────────

    def vacuum(self) -> None:
        """Reclaim disk space."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute("VACUUM")
            finally:
                conn.close()

    def stats(self) -> dict[str, int]:
        """Return table row counts."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                feedback_count = conn.execute(
                    "SELECT COUNT(*) FROM feedback"
                ).fetchone()[0]
                tuning_count = conn.execute(
                    "SELECT COUNT(*) FROM tunings"
                ).fetchone()[0]
                model_count = conn.execute(
                    "SELECT COUNT(*) FROM model_stats"
                ).fetchone()[0]
                return {
                    "feedback_records": feedback_count,
                    "tuning_runs": tuning_count,
                    "model_usage_records": model_count,
                    "total_evals": feedback_count,  # alias for test compatibility
                }
            finally:
                conn.close()

    # ── Convenience Methods (for test compatibility) ────────────────────────────

    def record_eval(self, eval_result: "EvalResult") -> None:
        """Record an EvalResult as feedback items."""
        from src.contracts.eval_result import EvalResult
        for issue in eval_result.issues:
            self.insert(
                FeedbackRecord(
                    workflow_id=eval_result.workflow_id,
                    source="evaluator",
                    severity="error" if "error" in issue.lower() else "warning",
                    message=issue,
                    details={"task_id": eval_result.task_id, "score": eval_result.overall_score},
                )
            )

    def get_stats(self) -> dict[str, int]:
        """Alias for stats() for backward compatibility."""
        return self.stats()


# ── Convenience Factory ────────────────────────────────────────────────────────


def get_feedback_store(db_path: str | Path = "optim/feedback.db") -> FeedbackStore:
    """Get or create a FeedbackStore with the default path."""
    return FeedbackStore(db_path)