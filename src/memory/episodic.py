"""
Episodic Memory — Past Run/Failure Retrieval via Vector Store
===============================================================

Stores past workflow events, failures, and outcomes in Qdrant vector store.
Agents retrieve similar past experiences by embedding similarity.

READ Phase 3 deliverable:
  'Episodic memory — past runs/failures in a vector store; retrieve by similarity.'
  'Use mem0 or LangMem (native to LangGraph).'
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# Episodic Memory Entry
# ============================================================


@dataclass
class Episode:
    """A single episodic memory — one past workflow experience."""

    episode_id: str
    workflow_id: str
    agent_id: str
    event_type: str  # "success", "failure", "bug_fix", "pattern"
    description: str
    timestamp: datetime
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_event(
        cls,
        workflow_id: str,
        agent_id: str,
        event_type: str,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> Episode:
        """Create an episode from a workflow event."""
        return cls(
            episode_id=uuid.uuid4().hex[:16],
            workflow_id=workflow_id,
            agent_id=agent_id,
            event_type=event_type,
            description=description,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {},
        )


# ============================================================
# Episodic Memory Store Interface
# ============================================================


class EpisodicStore:
    """Abstract interface for episodic memory storage.

    Stores episodes in a vector database for similarity-based retrieval.
    Uses Qdrant for v1 (see docker-compose.yml).
    """

    def __init__(self, collection_name: str = "aidev_episodes") -> None:
        self._collection = collection_name
        self._episodes: dict[str, Episode] = {}

    # ----------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------

    def store(self, episode: Episode) -> None:
        """Store an episode in memory.

        In the full implementation, this would embed the description
        and upsert to the Qdrant collection. For v0, we store in-memory
        with simple text search.
        """
        self._episodes[episode.episode_id] = episode
        logger.debug("Stored episode: %s (%s)", episode.episode_id, episode.event_type)

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        event_type: str | None = None,
    ) -> list[Episode]:
        """Retrieve similar episodes by text similarity (v0).

        In v1, this would use Qdrant's vector similarity search.
        For v0, we use simple keyword matching.

        Args:
            query: The search query (description of current situation).
            limit: Max number of episodes to return.
            event_type: Optional filter by event type.

        Returns:
            List of matching episodes, most relevant first.
        """
        # Simple keyword-based retrieval for v0
        query_lower = query.lower()
        scored: list[tuple[float, Episode]] = []

        for episode in self._episodes.values():
            # Filter by type
            if event_type and episode.event_type != event_type:
                continue

            # Simple relevance scoring: count keyword matches
            keywords = set(query_lower.split())
            desc_lower = episode.description.lower()
            score = sum(1 for kw in keywords if kw in desc_lower)
            if score > 0:
                scored.append((score, episode))

        # Sort by score descending, then by timestamp (newer first)
        scored.sort(key=lambda x: (-x[0], -x[1].timestamp.timestamp()))
        return [ep for _, ep in scored[:limit]]

    def retrieve_by_workflow(self, workflow_id: str) -> list[Episode]:
        """Retrieve all episodes for a specific workflow."""
        return [
            ep
            for ep in self._episodes.values()
            if ep.workflow_id == workflow_id
        ]

    def count(self) -> int:
        """Return the number of stored episodes."""
        return len(self._episodes)

    def clear(self) -> None:
        """Clear all episodes (for testing)."""
        self._episodes.clear()


# ============================================================
# Embedding Provider (for v1 vector search)
# ============================================================


class EmbeddingProvider:
    """Generate embeddings for episodic memory retrieval.

    Uses litellm's embedding support or a local model.
    For v0, provides a simple hash-based fallback.
    """

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        self._model = model

    def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.

        v0 fallback: deterministic hash-based pseudo-embedding.
        v1: use litellm.embedding() with OpenAI-compatible API.
        """
        # Simple hash-based vector for v0 (placeholder)
        # Each character contributes to a dimension
        h = hashlib.sha256(text.encode()).digest()
        # Convert first 128 bytes to 128 float dimensions
        vector = [float(b) / 255.0 for b in h[:128]]
        # Normalize
        magnitude = sum(v * v for v in vector) ** 0.5
        if magnitude > 0:
            vector = [v / magnitude for v in vector]
        return vector


# ============================================================
# Memory Manager (Episodic)
# ============================================================


class EpisodicMemoryManager:
    """Manage episodic memory recording and retrieval.

    Automatically records key workflow events as episodes,
    and provides retrieval for agents to learn from past experience.
    """

    def __init__(
        self,
        store: EpisodicStore | None = None,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        self._store = store or EpisodicStore()
        self._embedder = embedder or EmbeddingProvider()

    # ----------------------------------------------------------
    # Recording
    # ----------------------------------------------------------

    def record(
        self,
        workflow_id: str,
        agent_id: str,
        event_type: str,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> Episode:
        """Record a new episodic memory.

        Args:
            workflow_id: The workflow this episode belongs to.
            agent_id: The agent that generated this event.
            event_type: "success", "failure", "bug_fix", "pattern".
            description: Human-readable description of what happened.
            metadata: Optional extra structured data.

        Returns:
            The created Episode.
        """
        episode = Episode.from_event(
            workflow_id=workflow_id,
            agent_id=agent_id,
            event_type=event_type,
            description=description,
            metadata=metadata,
        )
        # Generate embedding for vector search (v1)
        if self._embedder:
            episode.embedding = self._embedder.embed(description)

        self._store.store(episode)
        logger.info("Recorded episode: %s — %s — %s", workflow_id, event_type, description[:80])
        return episode

    def record_success(
        self,
        workflow_id: str,
        agent_id: str,
        description: str,
    ) -> Episode:
        """Shorthand for recording a success event."""
        return self.record(workflow_id, agent_id, "success", description, {"outcome": "pass"})

    def record_failure(
        self,
        workflow_id: str,
        agent_id: str,
        description: str,
        error_details: str = "",
    ) -> Episode:
        """Shorthand for recording a failure event."""
        return self.record(
            workflow_id,
            agent_id,
            "failure",
            description,
            {"outcome": "fail", "error": error_details[:500]},
        )

    def record_bug_fix(
        self,
        workflow_id: str,
        agent_id: str,
        bug_description: str,
        fix_description: str,
    ) -> Episode:
        """Shorthand for recording a bug-fix pattern."""
        return self.record(
            workflow_id,
            agent_id,
            "bug_fix",
            f"Bug: {bug_description} | Fix: {fix_description}",
            {"bug": bug_description[:500], "fix": fix_description[:500]},
        )

    # ----------------------------------------------------------
    # Retrieval
    # ----------------------------------------------------------

    def retrieve_similar(
        self,
        query: str,
        limit: int = 5,
    ) -> list[Episode]:
        """Retrieve episodes similar to the query."""
        return self._store.retrieve(query, limit=limit)

    def retrieve_similar_failures(
        self,
        query: str,
        limit: int = 3,
    ) -> list[Episode]:
        """Retrieve only past failures similar to the query."""
        return self._store.retrieve(query, limit=limit, event_type="failure")

    def retrieve_similar_successes(
        self,
        query: str,
        limit: int = 3,
    ) -> list[Episode]:
        """Retrieve only past successes similar to the query."""
        return self._store.retrieve(query, limit=limit, event_type="success")

    def retrieve_similar_bug_fixes(
        self,
        query: str,
        limit: int = 3,
    ) -> list[Episode]:
        """Retrieve past bug fixes similar to the query (pattern reuse)."""
        return self._store.retrieve(query, limit=limit, event_type="bug_fix")

    def get_workflow_history(self, workflow_id: str) -> list[Episode]:
        """Get all episodes for a specific workflow."""
        return self._store.retrieve_by_workflow(workflow_id)

    # ----------------------------------------------------------
    # Context Builder (for LLM prompts)
    # ----------------------------------------------------------

    def build_context(
        self,
        query: str,
        max_episodes: int = 3,
    ) -> str:
        """Build a context string from relevant past episodes.

        Injects into agent prompts: 'Here's what happened in similar situations...'

        Args:
            query: Current situation description.
            max_episodes: Max episodes to include.

        Returns:
            A formatted string for LLM context injection.
        """
        episodes = self.retrieve_similar(query, limit=max_episodes)
        if not episodes:
            return ""

        lines: list[str] = [
            "## 📚 Relevant Past Experiences",
            "",
        ]
        for i, ep in enumerate(episodes, 1):
            lines.append(f"**Episode {i}** ({ep.event_type}, {ep.timestamp.strftime('%Y-%m-%d %H:%M')})")
            lines.append(f"- Workflow: `{ep.workflow_id}`")
            lines.append(f"- Agent: `{ep.agent_id}`")
            lines.append(f"- Description: {ep.description[:500]}")
            if ep.metadata:
                lines.append(f"- Details: {ep.metadata}")
            lines.append("")

        return "\n".join(lines)

    # ----------------------------------------------------------
    # Introspection
    # ----------------------------------------------------------

    @property
    def episode_count(self) -> int:
        """Number of stored episodes."""
        return self._store.count()

    def stats(self) -> dict[str, int]:
        """Return count by event type."""
        stats: dict[str, int] = {}
        for ep in self._store._episodes.values():  # noqa: SLF001 — internal for stats
            stats[ep.event_type] = stats.get(ep.event_type, 0) + 1
        return stats
