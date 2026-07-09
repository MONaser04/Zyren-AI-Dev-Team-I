"""
Semantic Memory — Consolidated Project Facts & Conventions
=============================================================

Stores long-lived project knowledge: coding conventions, architectural
decisions, technology mandates, naming patterns.

READ Phase 3 deliverable:
  'Semantic memory — consolidated project facts/conventions
   ("Postgres is mandated").'
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# Semantic Fact
# ============================================================


@dataclass
class SemanticFact:
    """A single semantic fact — a project convention, rule, or decision."""

    fact_id: str
    category: str  # "convention", "decision", "mandate", "pattern"
    key: str  # short identifier, e.g., "database-choice"
    value: str  # the fact: "Postgres is the mandated database."
    source: str  # which agent/process established this fact
    timestamp: datetime
    confidence: float = 1.0  # 0.0–1.0, facts can be soft or hard
    tags: list[str] = field(default_factory=list)


# ============================================================
# Semantic Store
# ============================================================


class SemanticStore:
    """Stores and retrieves project semantic facts.

    Simple key-value store with category filtering and confidence scoring.
    """

    def __init__(self) -> None:
        self._facts: dict[str, SemanticFact] = {}

    # ----------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------

    def store(self, fact: SemanticFact) -> None:
        """Store or update a semantic fact by key."""
        existing = self._facts.get(fact.key)
        if existing:
            # Update only if newer or higher confidence
            if fact.timestamp > existing.timestamp or fact.confidence > existing.confidence:
                self._facts[fact.key] = fact
                logger.debug("Updated fact: %s = %s", fact.key, fact.value)
        else:
            self._facts[fact.key] = fact
            logger.debug("Stored fact: %s = %s", fact.key, fact.value)

    def get(self, key: str) -> SemanticFact | None:
        """Get a fact by key."""
        return self._facts.get(key)

    def delete(self, key: str) -> None:
        """Remove a fact."""
        self._facts.pop(key, None)

    # ----------------------------------------------------------
    # Query
    # ----------------------------------------------------------

    def list_all(self) -> list[SemanticFact]:
        """Return all facts sorted by confidence (hardest first)."""
        return sorted(
            self._facts.values(),
            key=lambda f: (-f.confidence, f.timestamp.timestamp()),
        )

    def list_by_category(self, category: str) -> list[SemanticFact]:
        """Return facts filtered by category."""
        return [
            f
            for f in self._facts.values()
            if f.category == category
        ]

    def list_by_tag(self, tag: str) -> list[SemanticFact]:
        """Return facts that have a specific tag."""
        return [f for f in self._facts.values() if tag in f.tags]

    def search(self, query: str) -> list[SemanticFact]:
        """Simple text search across fact keys and values."""
        query_lower = query.lower()
        results: list[tuple[int, SemanticFact]] = []
        for fact in self._facts.values():
            score = 0
            if query_lower in fact.key.lower():
                score += 10
            if query_lower in fact.value.lower():
                score += 5
            if score > 0:
                results.append((score, fact))
        results.sort(key=lambda x: (-x[0], -x[1].confidence))
        return [f for _, f in results]

    def count(self) -> int:
        """Return number of stored facts."""
        return len(self._facts)

    def clear(self) -> None:
        """Clear all facts (for testing)."""
        self._facts.clear()


# ============================================================
# Semantic Memory Manager
# ============================================================


class SemanticMemoryManager:
    """Manage project semantic memory (conventions, decisions, facts).

    Agents consult this to stay aligned with project conventions.
    Architecture decisions (ADRs) are stored here after approval.
    """

    # Standard categories
    CATEGORY_CONVENTION = "convention"
    CATEGORY_DECISION = "decision"
    CATEGORY_MANDATE = "mandate"
    CATEGORY_PATTERN = "pattern"

    def __init__(self, store: SemanticStore | None = None) -> None:
        self._store = store or SemanticStore()

    # ----------------------------------------------------------
    # Recording
    # ----------------------------------------------------------

    def record(
        self,
        key: str,
        value: str,
        category: str = "convention",
        source: str = "unknown",
        confidence: float = 1.0,
        tags: list[str] | None = None,
    ) -> SemanticFact:
        """Record a new semantic fact.

        Args:
            key: Short identifier (e.g., "db-choice").
            value: The fact text (e.g., "Postgres is the mandated database.").
            category: convention, decision, mandate, pattern.
            source: Agent or process that established this fact.
            confidence: 1.0 = hard mandate, 0.5 = soft preference.
            tags: Optional tags for filtering.

        Returns:
            The created SemanticFact.
        """
        from uuid import uuid4

        fact = SemanticFact(
            fact_id=uuid4().hex[:12],
            category=category,
            key=key,
            value=value,
            source=source,
            timestamp=datetime.now(timezone.utc),
            confidence=confidence,
            tags=tags or [],
        )
        self._store.store(fact)
        logger.info("Recorded semantic fact: [%s] %s = %s", category, key, value[:100])
        return fact

    def record_convention(
        self,
        key: str,
        value: str,
        source: str = "architect",
    ) -> SemanticFact:
        """Record a coding convention."""
        return self.record(key, value, self.CATEGORY_CONVENTION, source, confidence=0.8)

    def record_decision(
        self,
        key: str,
        value: str,
        source: str = "architect",
    ) -> SemanticFact:
        """Record an architectural decision (ADR)."""
        return self.record(key, value, self.CATEGORY_DECISION, source, confidence=0.9)

    def record_mandate(
        self,
        key: str,
        value: str,
        source: str = "supervisor",
    ) -> SemanticFact:
        """Record a hard mandate (e.g., 'use Postgres')."""
        return self.record(key, value, self.CATEGORY_MANDATE, source, confidence=1.0)

    # ----------------------------------------------------------
    # Retrieval
    # ----------------------------------------------------------

    def get(self, key: str) -> SemanticFact | None:
        """Get a specific fact by key."""
        return self._store.get(key)

    def get_all_conventions(self) -> list[SemanticFact]:
        """Get all coding conventions."""
        return self._store.list_by_category(self.CATEGORY_CONVENTION)

    def get_all_decisions(self) -> list[SemanticFact]:
        """Get all architectural decisions."""
        return self._store.list_by_category(self.CATEGORY_DECISION)

    def get_all_mandates(self) -> list[SemanticFact]:
        """Get all hard mandates (highest priority)."""
        return self._store.list_by_category(self.CATEGORY_MANDATE)

    def search(self, query: str) -> list[SemanticFact]:
        """Search across all facts."""
        return self._store.search(query)

    # ----------------------------------------------------------
    # Context Builder (for LLM prompts)
    # ----------------------------------------------------------

    def build_context(self) -> str:
        """Build a context string of all semantic facts for LLM prompts.

        Mandates first, then decisions, then conventions.
        """
        mandates = self.get_all_mandates()
        decisions = self.get_all_decisions()
        conventions = self.get_all_conventions()

        if not mandates and not decisions and not conventions:
            return ""

        lines: list[str] = [
            "## 📋 Project Conventions & Rules",
            "",
        ]

        if mandates:
            lines.append("### 🔴 Hard Mandates (Must Follow)")
            lines.append("")
            for f in mandates:
                lines.append(f"- **{f.key}**: {f.value} (source: {f.source})")
            lines.append("")

        if decisions:
            lines.append("### 🟠 Architectural Decisions (ADRs)")
            lines.append("")
            for f in decisions:
                lines.append(f"- **{f.key}**: {f.value} (source: {f.source})")
            lines.append("")

        if conventions:
            lines.append("### 🟡 Coding Conventions")
            lines.append("")
            for f in conventions:
                lines.append(f"- **{f.key}**: {f.value}")

        return "\n".join(lines)

    # ----------------------------------------------------------
    # Introspection
    # ----------------------------------------------------------

    @property
    def fact_count(self) -> int:
        """Number of stored facts."""
        return self._store.count()

    def stats(self) -> dict[str, int]:
        """Return count by category."""
        stats: dict[str, int] = {}
        for f in self._store._facts.values():  # noqa: SLF001
            stats[f.category] = stats.get(f.category, 0) + 1
        return stats