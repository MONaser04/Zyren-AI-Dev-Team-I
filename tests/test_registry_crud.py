"""
Tests for AutoModelRegistry CRUD Methods — Phase 1
=====================================================
Tests manual_add_model, manual_disable_model, manual_enable_model,
disable_provider_models, get_active_models.
NO real API calls.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gateway.model_registry import (
    AutoModelRegistry,
    ModelCapabilities,
    ModelLimits,
    ModelPricing,
    ModelSpec,
    ModelStatus,
    ModelTier,
    SourceCitation,
    SourceType,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def registry():
    """Create a fresh registry."""
    return AutoModelRegistry()


@pytest.fixture
def sample_spec():
    """Create a sample ModelSpec."""
    return ModelSpec(
        model_id="openai/gpt-4o",
        provider="openai",
        display_name="GPT-4o",
        tier=ModelTier.FRONTIER,
        capabilities=ModelCapabilities(
            context_window=128000,
            modalities=["text"],
            function_calling=True,
            structured_output=True,
        ),
        pricing=ModelPricing(
            input_per_1m_tokens=2.50,
            output_per_1m_tokens=10.00,
        ),
        limits=ModelLimits(rpm=500, tpm=30000),
        status=ModelStatus.ACTIVE,
        citations={
            "api": SourceCitation(
                source_type=SourceType.API,
                url="https://api.openai.com/v1/models",
                provider="openai",
                accessed_at=datetime.now(UTC),
                confidence=1.0,
            )
        },
        verification_confidence=0.95,
    )


@pytest.fixture
def populated_registry(registry, sample_spec):
    """Registry with one model already added."""
    registry.manual_add_model(sample_spec, added_by="test")
    return registry


# ============================================================
# manual_add_model Tests
# ============================================================


class TestManualAddModel:
    """Tests for manual_add_model."""

    def test_add_model_success(self, registry, sample_spec):
        """Should add a model to the registry."""
        registry.manual_add_model(sample_spec, added_by="test")

        result = registry.get(sample_spec.model_id)
        assert result is not None
        assert result.model_id == "openai/gpt-4o"
        assert result.status == ModelStatus.ACTIVE

    def test_add_model_duplicate(self, populated_registry, sample_spec):
        """Adding duplicate model should update it."""
        populated_registry.manual_add_model(sample_spec, added_by="test-update")
        result = populated_registry.get(sample_spec.model_id)
        assert result is not None


# ============================================================
# manual_disable_model Tests
# ============================================================


class TestManualDisableModel:
    """Tests for manual_disable_model."""

    def test_disable_existing_model(self, populated_registry):
        """Should disable an existing model."""
        success = populated_registry.manual_disable_model(
            "openai/gpt-4o", "testing", disabled_by="admin"
        )
        assert success is True

        model = populated_registry.get("openai/gpt-4o")
        assert model is not None
        assert model.status == ModelStatus.DISABLED

    def test_disable_nonexistent_model(self, registry):
        """Should return False for non-existent model."""
        success = registry.manual_disable_model(
            "nonexistent/model", "testing", disabled_by="admin"
        )
        assert success is False


# ============================================================
# manual_enable_model Tests
# ============================================================


class TestManualEnableModel:
    """Tests for manual_enable_model."""

    def test_enable_disabled_model(self, populated_registry):
        """Should re-enable a disabled model."""
        # First disable
        populated_registry.manual_disable_model(
            "openai/gpt-4o", "testing", disabled_by="admin"
        )
        model = populated_registry.get("openai/gpt-4o")
        assert model.status == ModelStatus.DISABLED

        # Then enable
        success = populated_registry.manual_enable_model(
            "openai/gpt-4o", enabled_by="admin"
        )
        assert success is True

        model = populated_registry.get("openai/gpt-4o")
        assert model.status == ModelStatus.ACTIVE

    def test_enable_nonexistent_model(self, registry):
        """Should return False for non-existent model."""
        success = registry.manual_enable_model(
            "nonexistent/model", enabled_by="admin"
        )
        assert success is False


# ============================================================
# get_active_models Tests
# ============================================================


class TestGetActiveModels:
    """Tests for get_active_models."""

    def test_active_models_returns_only_active(self, populated_registry, sample_spec):
        """Should only return ACTIVE models."""
        # Add another model
        spec2 = ModelSpec(
            model_id="anthropic/claude-3",
            provider="anthropic",
            display_name="Claude 3",
            tier=ModelTier.FRONTIER,
            capabilities=ModelCapabilities(),
            pricing=ModelPricing(),
            limits=ModelLimits(),
            status=ModelStatus.ACTIVE,
        )
        populated_registry.manual_add_model(spec2, added_by="test")

        # Disable one
        populated_registry.manual_disable_model(
            "openai/gpt-4o", "test", disabled_by="admin"
        )

        active = populated_registry.get_active_models()
        active_ids = [m.model_id for m in active]

        assert "anthropic/claude-3" in active_ids
        assert "openai/gpt-4o" not in active_ids

    def test_active_models_empty_registry(self, registry):
        """Should return empty list for empty registry."""
        active = registry.get_active_models()
        assert active == []


# ============================================================
# disable_provider_models Tests
# ============================================================


class TestDisableProviderModels:
    """Tests for disable_provider_models."""

    def test_disable_provider(self, registry):
        """Should disable all models from a provider."""
        # Add multiple models from same provider
        for i in range(3):
            spec = ModelSpec(
                model_id=f"openai/model-{i}",
                provider="openai",
                display_name=f"Model {i}",
                tier=ModelTier.FAST,
                capabilities=ModelCapabilities(),
                pricing=ModelPricing(),
                limits=ModelLimits(),
                status=ModelStatus.ACTIVE,
            )
            registry.manual_add_model(spec, added_by="test")

        count = registry.disable_provider_models("openai", "outage", disabled_by="admin")
        assert count == 3

        # Verify all disabled
        for i in range(3):
            model = registry.get(f"openai/model-{i}")
            assert model.status == ModelStatus.DISABLED

    def test_disable_nonexistent_provider(self, registry):
        """Should return 0 for non-existent provider."""
        count = registry.disable_provider_models("nonexistent", "test", disabled_by="admin")
        assert count == 0
