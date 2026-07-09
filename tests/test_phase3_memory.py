"""Smoke tests for Phase 3 — Hierarchical Memory (Episodic + Semantic)."""

from memory.memory import EpisodicStore, EmbeddingProvider, SemanticStore


class TestEmbeddingProvider:
    """Verify the fake embedding provider."""

    def test_embedding_dimension(self) -> None:
        emb = EmbeddingProvider(dim=128)
        vec = emb.embed("hello world")
        assert len(vec) == 128

    def test_embedding_is_normalized(self) -> None:
        emb = EmbeddingProvider(dim=128)
        vec = emb.embed("test text")
        import math
        norm = math.sqrt(sum(v * v for v in vec))
        # normalized vectors have norm ≈ 1.0
        assert 0.99 <= norm <= 1.01

    def test_different_texts_different_vectors(self) -> None:
        emb = EmbeddingProvider(dim=128)
        v1 = emb.embed("hello")
        v2 = emb.embed("world")
        assert v1 != v2

    def test_same_text_same_vector(self) -> None:
        emb = EmbeddingProvider(dim=128)
        v1 = emb.embed("hello")
        v2 = emb.embed("hello")
        assert v1 == v2


class TestEpisodicStore:
    """Verify episodic memory store — past runs/failures retrieved by similarity."""

    def test_add_and_retrieve(self) -> None:
        emb = EmbeddingProvider(dim=128)
        store = EpisodicStore(embedding_provider=emb)

        store.add(
            event="Code patch X failed type-check due to missing imports.",
            event_type="failure",
            workflow_id="wf-001",
        )
        store.add(
            event="Code patch Y passed all tests and type-check cleanly.",
            event_type="success",
            workflow_id="wf-002",
        )
        store.add(
            event="Code patch Z failed tests due to wrong assertion logic.",
            event_type="failure",
            workflow_id="wf-003",
        )

        # Retrieve similar failures when new code fails type-check
        results = store.retrieve(query="type-check failed imports", k=2, event_type="failure")
        assert len(results) == 2
        # The most relevant should be the type-check failure
        # Check both contain event type and text
        for r in results:
            assert r.entry.event_type == "failure"
            assert "type-check" in r.entry.content.lower() or "failed" in r.entry.content.lower()

    def test_retrieve_empty_store(self) -> None:
        emb = EmbeddingProvider(dim=128)
        store = EpisodicStore(embedding_provider=emb)
        results = store.retrieve(query="anything")
        assert results == []

    def test_global_episodic_store(self) -> None:
        """Verify the singleton GLOBAL_STORE is accessible but can be reset."""
        # Reset to ensure clean state
        EpisodicStore.reset_global()

        from memory.memory import GLOBAL_EPISODIC_STORE
        store = GLOBAL_EPISODIC_STORE

        store.add(event="test event", event_type="test", workflow_id="wf-test")

        results = store.retrieve(query="test event", k=1)
        assert len(results) >= 1

    def test_entry_content(self) -> None:
        emb = EmbeddingProvider(dim=128)
        store = EpisodicStore(embedding_provider=emb)

        content = "Security scan found SQL injection vulnerability in endpoint X."
        store.add(event=content, event_type="security_issue", workflow_id="wf-sec")

        results = store.retrieve(query="SQL injection vulnerability", k=1)
        assert len(results) == 1
        assert "SQL injection" in results[0].entry.content


class TestSemanticStore:
    """Verify semantic memory store — consolidated project facts/conventions."""

    def test_store_and_retrieve_conventions(self) -> None:
        store = SemanticStore()

        store.store_convention("database", "Postgres is the mandated database for this project.")
        store.store_convention("testing", "All tests must use pytest with async support.")
        store.store_convention("code_style", "Use ruff for linting, line length 120.")

        # Retrieve relevant conventions
        db_result = store.retrieve_relevant(query="What database should we use?", k=1)
        assert len(db_result) == 1
        assert any("Postgres" in r for r in db_result)

        test_result = store.retrieve_relevant(query="testing framework expectations", k=1)
        assert len(test_result) == 1
        assert any("pytest" in r for r in test_result)

    def test_store_rule_violations(self) -> None:
        store = SemanticStore()

        store.store_violation(
            violated_convention="database",
            context="Architect proposed MongoDB instead of mandated Postgres.",
        )

        violations = store.get_violations()
        assert len(violations) == 1
        assert "MongoDB" in violations[0]["context"]

    def test_empty_store_returns_empty(self) -> None:
        store = SemanticStore()
        result = store.retrieve_relevant(query="anything")
        assert result == []

    def test_global_semantic_store(self) -> None:
        SemanticStore.reset_global()

        from memory.memory import GLOBAL_SEMANTIC_STORE
        store = GLOBAL_SEMANTIC_STORE

        store.store_convention("global_test", "Global semantic store is functional.")

        result = store.retrieve_relevant(query="global_test", k=1)
        assert len(result) == 1
        assert "functional" in result[0]