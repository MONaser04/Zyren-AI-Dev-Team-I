"""
Feedback Contract — Phase 5
============================
Structured feedback from one agent to another during the autonomous loop.
Used by Critic → Coder, Architect → Coder, Supervisor → any agent.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IssueType(str, Enum):
    """Classification of feedback issues."""
    TEST_FAILURE = "test_failure"
    TYPE_ERROR = "type_error"
    LINT_VIOLATION = "lint_violation"
    SECURITY_ISSUE = "security_issue"
    ARCHITECTURE_FLAW = "architecture_flaw"
    LOGIC_ERROR = "logic_error"
    MISSING_REQUIREMENT = "missing_requirement"
    CODE_QUALITY = "code_quality"
    DOCUMENTATION = "documentation"
    OTHER = "other"


class Severity(str, Enum):
    """Issue severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FeedbackItem(BaseModel):
    """A single feedback point."""
    issue_type: IssueType = Field(description="Classification of the issue")
    severity: Severity = Field(default=Severity.WARNING)
    message: str = Field(description="Human-readable description of the issue")
    file_path: str | None = Field(default=None, description="Affected file, if applicable")
    line_numbers: list[int] = Field(default_factory=list, description="Affected line numbers")
    suggested_fix: str | None = Field(default=None, description="Concrete suggestion for fixing")
    evidence: str | None = Field(default=None, description="Test output, lint message, etc. that proves the issue")


class Feedback(BaseModel):
    """Complete feedback package from one agent to another."""

    feedback_id: str = Field(description="Unique feedback identifier")
    workflow_id: str = Field(description="Parent workflow")
    iteration: int = Field(default=0, description="Which iteration this feedback belongs to")

    # Agents
    source_agent: str = Field(description="Agent providing feedback (e.g., critic-01)")
    target_agent: str = Field(description="Agent receiving feedback (e.g., coder-01)")

    # Decision
    overall_decision: str = Field(default="BLOCK", description="PASS or BLOCK")
    items: list[FeedbackItem] = Field(default_factory=list)

    # Escalation
    escalation_tone: str = Field(default="constructive", description="constructive / direct / firm / hard_block")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    previous_iteration_referenced: int | None = Field(default=None, description="If referencing prior feedback")

    @property
    def is_pass(self) -> bool:
        """True if this feedback allows progression."""
        return self.overall_decision == "PASS"

    @property
    def is_block(self) -> bool:
        """True if this feedback blocks progression (needs retry)."""
        return self.overall_decision == "BLOCK"

    @property
    def critical_count(self) -> int:
        """Number of critical-severity items."""
        return sum(1 for i in self.items if i.severity == Severity.CRITICAL)

    @property
    def error_count(self) -> int:
        """Number of error + critical items."""
        return sum(1 for i in self.items if i.severity in (Severity.ERROR, Severity.CRITICAL))

    def to_human_readable(self) -> str:
        """Format feedback as a human-readable string for the coder."""
        lines = [f"## Feedback from {self.source_agent} (Iteration {self.iteration})", ""]
        lines.append(f"**Decision: {self.overall_decision}**")
        lines.append(f"**Tone: {self.escalation_tone}**")
        lines.append("")
        for i, item in enumerate(self.items, 1):
            lines.append(f"### Issue {i}: [{item.severity.value}] {item.issue_type.value}")
            lines.append(f"**Message:** {item.message}")
            if item.file_path:
                loc = f"{item.file_path}"
                if item.line_numbers:
                    loc += f" (lines {', '.join(map(str, item.line_numbers))})"
                lines.append(f"**Location:** {loc}")
            if item.evidence:
                lines.append(f"**Evidence:** {item.evidence}")
            if item.suggested_fix:
                lines.append(f"**Suggested Fix:** {item.suggested_fix}")
            lines.append("")
        return "\n".join(lines)


# ============================================================
# Feedback Loop (for optimisation)
# ============================================================


class FeedbackLoop:
    """Manages feedback records for optimisation analysis."""

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def record(
        self,
        workflow_id: str,
        source: str,
        severity: str,
        message: str,
    ) -> None:
        """Record a feedback item for later analysis."""
        self._records.append({
            "workflow_id": workflow_id,
            "source": source,
            "severity": severity,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_records(self) -> list[dict[str, Any]]:
        """Get all recorded feedback."""
        return self._records

    def clear(self) -> None:
        """Clear all records."""
        self._records.clear()

    def tuning_record(
        self,
        agent: str,
        original_prompt: str,
        variants: list[str],
        evaluations: list[dict[str, Any]],
    ) -> None:
        """Record a prompt tuning session."""
        self._records.append({
            "type": "tuning",
            "agent": agent,
            "original_prompt": original_prompt,
            "variants": variants,
            "evaluations": evaluations,
            "timestamp": datetime.utcnow().isoformat(),
        })


# Need to import Any for the type hint
from typing import Any