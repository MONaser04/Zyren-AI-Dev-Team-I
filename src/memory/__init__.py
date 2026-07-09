"""
Memory Package — Episodic + Semantic Memory
=============================================

Components:
- episodic: Episodic memory (past runs/failures) via vector store.
- semantic: Semantic memory (project facts/conventions/ADRs).
- memory: Unified wrapper providing simplified API for tests and agents.
"""

from memory.episodic import (
    EpisodicMemoryManager,
)
from memory.memory import (
    EmbeddingProvider,
    EpisodeEntry,
    EpisodeResult,
    EpisodicStore,
    GLOBAL_EPISODIC_STORE,
    GLOBAL_SEMANTIC_STORE,
    SemanticStore,
)
from memory.semantic import (
    SemanticFact,
    SemanticMemoryManager,
)

__all__ = [
    # Unified wrapper (preferred for tests/agents)
    "EmbeddingProvider",
    "EpisodicStore",
    "EpisodeEntry",
    "EpisodeResult",
    "GLOBAL_EPISODIC_STORE",
    "SemanticStore",
    "GLOBAL_SEMANTIC_STORE",
    # Internal episodic
    "EpisodicMemoryManager",
    # Internal semantic
    "SemanticFact",
    "SemanticMemoryManager",
]