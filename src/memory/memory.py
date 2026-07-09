"""Memory wrapper — unified interface for episodic + semantic memory.

Provides a convenient top-level API so tests and agents don't need to know
about the episodic/semantic split internally.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any

from pydantic import BaseModel, Field

# ============================================================
# EmbeddingProvider — Fake / Mock Embeddings
# ============================================================


class EmbeddingProvider:
    """Deterministic fake embedding provider for local testing.

    Uses SHA-256 hash → first *dim* bytes normalized to unit vector.
    Not for production — swap with a real embedding model when needed.
    """

    def __init__(self, dim: int = 128) -> None:
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        """Return a normalized pseudo-embedding vector of length *dim*."""
        h = hashlib.sha256(text.encode()).digest()
        # expand hash bytes into enough floats
        floats: list[float] = []
        seed = int.from_bytes(h[:4], "big")
        rng = random.Random(seed)
        for _ in range(self._dim):
            floats.append(rng.uniform(-1.0, 1.0))

        # normalize to unit vector
        norm = math.sqrt(sum(v * v for v in floats))
        if norm > 0:
            floats = [v / norm for v in floats]

        return floats


# ============================================================
# Episodic Memory
# ============================================================


class EpisodeEntry(BaseModel):
    """A single episodic memory entry."""

    content: str
    event_type: str  # "failure", "success", "security_issue", etc.
    workflow_id: str
    embedding: list[float] | None = None


class EpisodeResult(BaseModel):
    """A retrieval result with similarity score."""

    entry: EpisodeEntry
    score: float


class EpisodicStore:
    """In-memory episodic store with cosine-similarity retrieval.

    Stores past run events (failures, successes) and retrieves similar
    entries by embedding similarity.
    """

    _global: EpisodicStore | None = None

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._entries: list[EpisodeEntry] = []
        self._emb = embedding_provider or EmbeddingProvider(dim=128)

    def add(self, event: str, event_type: str, workflow_id: str) -> None:
        """Add an event to the episodic store."""
        embedding = self._emb.embed(event)
        entry = EpisodeEntry(
            content=event,
            event_type=event_type,
            workflow_id=workflow_id,
            embedding=embedding,
        )
        self._entries.append(entry)

    def retrieve(
        self,
        query: str,
        k: int = 5,
        event_type: str | None = None,
    ) -> list[EpisodeResult]:
        """Retrieve top-k similar entries, optionally filtered by event_type."""
        if not self._entries:
            return []

        query_vec = self._emb.embed(query)

        scored: list[EpisodeResult] = []
        for entry in self._entries:
            if event_type is not None and entry.event_type != event_type:
                continue
            if entry.embedding is None:
                continue
            score = self._cosine_similarity(query_vec, entry.embedding)
            scored.append(EpisodeResult(entry=entry, score=score))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        return dot  # both are already unit vectors

    @staticmethod
    def reset_global() -> None:
        EpisodicStore._global = None

    @staticmethod
    def get_global() -> EpisodicStore:
        if EpisodicStore._global is None:
            EpisodicStore._global = EpisodicStore()
        return EpisodicStore._global


GLOBAL_EPISODIC_STORE = EpisodicStore.get_global()


# ============================================================
# Semantic Memory
# ============================================================


class SemanticStore:
    """In-memory semantic store for project facts, conventions, ADRs.

    Stores key-value conventions and violation records.
    """

    _global: SemanticStore | None = None

    def __init__(self) -> None:
        self._conventions: dict[str, str] = {}  # category → convention text
        self._violations: list[dict[str, str]] = []

    def store_convention(self, category: str, text: str) -> None:
        """Store a project convention by category."""
        self._conventions[category] = text

    def retrieve_relevant(self, query: str, k: int = 5) -> list[str]:
        """Retrieve relevant convention texts for a query.

        Simple substring match — replace with embeddings when needed.
        """
        q = query.lower()
        q_words = q.split()

        results: list[str] = []
        for text in self._conventions.values():
            text_lower = text.lower()
            # Full query substring match
            if q in text_lower:
                results.append(text)
                continue
            # Individual word match (partial prefix match for words >= 4 chars)
            for word in q_words:
                if len(word) >= 4:
                    # Check if text contains word OR word prefix matches (e.g. "testing" → "test")
                    if word in text_lower:
                        results.append(text)
                        break
                    # Prefix: "testing" matches "tests", "tested", "test"
                    prefix = word[:4]
                    if prefix in text_lower:
                        results.append(text)
                        break
                elif word in text_lower:
                    results.append(text)
                    break

        return results[:k] if results else list(self._conventions.values())[:k]

    def store_violation(self, violated_convention: str, context: str) -> None:
        """Record a convention violation."""
        self._violations.append({
            "violated_convention": violated_convention,
            "context": context,
        })

    def get_violations(self) -> list[dict[str, str]]:
        """Return all recorded violations."""
        return list(self._violations)

    @staticmethod
    def reset_global() -> None:
        SemanticStore._global = None

    @staticmethod
    def get_global() -> SemanticStore:
        if SemanticStore._global is None:
            SemanticStore._global = SemanticStore()
        return SemanticStore._global


GLOBAL_SEMANTIC_STORE = SemanticStore.get_global()