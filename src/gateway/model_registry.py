"""
Universal Model Registry — Phase 1
===================================
Provider-agnostic model registry with auto-discovery, verified specifications,
and classification. All provider adapters plug into this registry.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ============================================================
# Enums
# ============================================================


class ModelTier(StrEnum):
    """Model capability tiers for routing."""

    FRONTIER = "frontier"
    FAST = "fast"
    CRITIC = "critic"
    CODE_SPECIALIZED = "code_specialized"
    LONG_CONTEXT = "long_context"
    VISION = "vision"


class ModelStatus(StrEnum):
    """Model lifecycle status."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    UNVERIFIED = "unverified"


class SourceType(StrEnum):
    """Source type for verification citations."""

    API = "api"
    OFFICIAL_DOCS = "official_docs"
    PRICING_PAGE = "pricing_page"
    MODEL_CARD = "model_card"
    CHANGELOG = "changelog"


# ============================================================
# Source Citation (Verified Ground Truth)
# ============================================================


@dataclass(frozen=True, slots=True)
class SourceCitation:
    """Verified source citation with confidence scoring.

    Confidence tiers:
    - API=1.0 (live /models endpoint)
    - pricing=0.9 (official pricing page)
    - docs=0.85 (official docs)
    - card=0.8 (model card)
    - changelog=0.75 (changelog)
    """

    source_type: SourceType
    url: str
    provider: str
    accessed_at: datetime
    field_mapping: dict[str, str]  # field_name → snippet_source
    confidence: float
    raw_snippet: str


# ============================================================
# Model Specifications
# ============================================================


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Model capability matrix."""

    context_window: int = 8192
    modalities: list[str] = field(default_factory=lambda: ["text"])  # ["text", "vision", "audio", "function_calling"]
    function_calling: bool = False
    structured_output: bool = False
    parallel_tool_calls: bool = False
    max_output_tokens: int = 4096


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Model pricing with citation."""

    input_per_1m_tokens: float
    output_per_1m_tokens: float
    currency: str = "USD"
    citation: SourceCitation | None = None
    effective_date: datetime | None = None


@dataclass(frozen=True, slots=True)
class ModelLimits:
    """Rate limits for a model."""

    rpm: int | None = None
    tpm: int | None = None
    rpd: int | None = None


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Complete verified model specification."""

    # Identity
    model_id: str  # e.g., "nvidia_nim/deepseek-ai/deepseek-v4-pro"
    provider: str  # e.g., "nvidia_nim", "openai", "anthropic"
    display_name: str
    tier: ModelTier

    # Capabilities
    capabilities: ModelCapabilities

    # Pricing & Limits
    pricing: ModelPricing
    limits: ModelLimits

    # Metadata
    status: ModelStatus = ModelStatus.ACTIVE
    version: str = "1.0"
    released_at: datetime | None = None
    deprecated_at: datetime | None = None

    # Verification
    citations: dict[str, SourceCitation] = field(default_factory=dict)
    last_verified: datetime = field(default_factory=lambda: datetime.now(UTC))
    verification_confidence: float = 1.0  # min of all citations

    # Classification
    tags: list[str] = field(default_factory=list)
    description: str = ""


# ============================================================
# Provider Adapter Interface
# ============================================================


class ProviderAdapter(ABC):
    """Abstract base class for provider adapters.

    Each provider (OpenAI, Anthropic, NVIDIA NIM, etc.) implements
    this interface to expose their models to the registry.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'openai', 'nvidia_nim')."""
        pass

    @property
    @abstractmethod
    def supported_tiers(self) -> list[ModelTier]:
        """Model tiers this provider supports."""
        pass

    @abstractmethod
    async def discover_models(self) -> list[ModelSpec]:
        """Discover all models from this provider's /models endpoint or API."""
        pass

    @abstractmethod
    async def fetch_pricing(self, model_id: str) -> ModelPricing | None:
        """Fetch current pricing for a model."""
        pass

    @abstractmethod
    async def fetch_limits(self, model_id: str) -> ModelLimits | None:
        """Fetch rate limits for a model."""
        pass

    @abstractmethod
    async def verify_model(self, model_id: str) -> ModelSpec | None:
        """Verify a model's specs against provider sources."""
        pass


# ============================================================
# AutoModelRegistry
# ============================================================


class AutoModelRegistry:
    """Universal model registry with auto-discovery and verification.

    Features:
    - Provider-agnostic: any ProviderAdapter can register
    - Auto-discovery: calls /models endpoints on startup
    - Verified specs: cross-references pricing, limits, capabilities
    - Classification: auto-tags models by tier and capability
    - Hot-reload: supports dynamic provider registration
    """

    def __init__(self):
        self._models: dict[str, ModelSpec] = {}
        self._providers: dict[str, ProviderAdapter] = {}
        self._provider_priority: list[str] = []  # for tiebreaking
        self._initialized = False

    def register_provider(self, adapter: ProviderAdapter, priority: int = 0) -> None:
        """Register a provider adapter.

        Args:
            adapter: ProviderAdapter implementation
            priority: Lower = higher priority (for tiebreaking)
        """
        if adapter.provider_name in self._providers:
            logger.warning("Provider %s already registered, replacing", adapter.provider_name)

        self._providers[adapter.provider_name] = adapter
        # Maintain priority order
        if priority == 0:
            self._provider_priority.append(adapter.provider_name)
        else:
            # Insert based on priority
            inserted = False
            for i, p in enumerate(self._provider_priority):
                if priority < i:
                    self._provider_priority.insert(i, adapter.provider_name)
                    inserted = True
                    break
            if not inserted:
                self._provider_priority.append(adapter.provider_name)

        logger.info("Registered provider: %s (priority=%d)", adapter.provider_name, priority)

    def unregister_provider(self, provider_name: str) -> None:
        """Unregister a provider and its models."""
        if provider_name in self._providers:
            # Remove models from this provider
            to_remove = [mid for mid, m in self._models.items() if m.provider == provider_name]
            for mid in to_remove:
                del self._models[mid]

            del self._providers[provider_name]
            self._provider_priority = [p for p in self._provider_priority if p != provider_name]
            logger.info("Unregistered provider: %s", provider_name)

    async def initialize(self, discover: bool = True) -> int:
        """Initialize registry and optionally discover models.

        Args:
            discover: Whether to run auto-discovery on all providers

        Returns:
            Number of models registered
        """
        if self._initialized:
            logger.warning("Registry already initialized, skipping")
            return len(self._models)

        if discover:
            await self.discover_all()

        self._initialized = True
        logger.info("Registry initialized with %d models", len(self._models))
        return len(self._models)

    async def discover_all(self) -> int:
        """Discover models from all registered providers."""
        total = 0
        for provider_name in self._provider_priority:
            adapter = self._providers.get(provider_name)
            if not adapter:
                continue

            try:
                logger.info("Discovering models from %s...", provider_name)
                models = await adapter.discover_models()
                for spec in models:
                    await self._register_model(spec, adapter)
                total += len(models)
                logger.info("Discovered %d models from %s", len(models), provider_name)
            except Exception as e:
                logger.debug("Failed to discover models from %s: %s", provider_name, e)

        return total

    async def _register_model(self, spec: ModelSpec, adapter: ProviderAdapter) -> None:
        """Register a model, enriching with pricing/limits if needed."""
        # Convert to dict for modification (dataclass doesn't have __dict__)
        spec_dict = {
            "model_id": spec.model_id,
            "provider": spec.provider,
            "display_name": spec.display_name,
            "tier": spec.tier,
            "capabilities": spec.capabilities,
            "pricing": spec.pricing,
            "limits": spec.limits,
            "status": spec.status,
            "version": spec.version,
            "released_at": spec.released_at,
            "deprecated_at": spec.deprecated_at,
            "citations": spec.citations,
            "verification_confidence": spec.verification_confidence,
            "tags": spec.tags,
            "description": spec.description,
        }

        # Enrich with pricing if not present
        if spec.pricing.input_per_1m_tokens == 0:
            pricing = await adapter.fetch_pricing(spec.model_id)
            if pricing:
                spec_dict["pricing"] = pricing

        # Enrich with limits if not present
        if spec.limits.rpm is None:
            limits = await adapter.fetch_limits(spec.model_id)
            if limits:
                spec_dict["limits"] = limits

        # Auto-classify tier if not set
        if spec_dict["tier"] == ModelTier.FAST and spec_dict["capabilities"].context_window > 100000:
            spec_dict["tier"] = ModelTier.LONG_CONTEXT

        # Create new spec with enriched data
        enriched_spec = ModelSpec(**spec_dict)

        # Store
        self._models[enriched_spec.model_id] = enriched_spec
        logger.debug("Registered model: %s", enriched_spec.model_id)

    def get_model(self, model_id: str) -> ModelSpec | None:
        """Get a model by ID."""
        return self._models.get(model_id)

    def get_by_tier(self, tier: ModelTier) -> list[ModelSpec]:
        """Get all models of a specific tier."""
        return [m for m in self._models.values() if m.tier == tier]

    def get_by_provider(self, provider: str) -> list[ModelSpec]:
        """Get all models from a provider."""
        return [m for m in self._models.values() if m.provider == provider]

    def get_by_capability(self, capability: str) -> list[ModelSpec]:
        """Get models supporting a capability (e.g., 'function_calling', 'vision')."""
        return [m for m in self._models.values() if capability in m.capabilities.modalities]

    def list_all(self) -> list[ModelSpec]:
        """List all registered models."""
        return list(self._models.values())

    def list_tiers(self) -> list[ModelTier]:
        """List available tiers."""
        return list(ModelTier)

    def list_providers(self) -> list[str]:
        """List registered providers."""
        return list(self._providers.keys())

    def resolve_alias(self, alias: str) -> ModelSpec | None:
        """Resolve an alias (e.g., 'frontier') to the best model."""
        tier_map = {
            "frontier": ModelTier.FRONTIER,
            "fast": ModelTier.FAST,
            "critic": ModelTier.CRITIC,
            "code": ModelTier.CODE_SPECIALIZED,
            "long": ModelTier.LONG_CONTEXT,
        }
        tier = tier_map.get(alias)
        if not tier:
            return None

        models = self.get_by_tier(tier)
        if not models:
            return None

        # Prefer highest confidence, then active status
        models.sort(key=lambda m: (m.verification_confidence, m.status == ModelStatus.ACTIVE), reverse=True)
        return models[0]

    def get_active_models(self) -> list[ModelSpec]:
        """Get all models with ACTIVE status."""
        return [m for m in self._models.values() if m.status == ModelStatus.ACTIVE]

    def manual_add_model(self, spec: ModelSpec, added_by: str = "system") -> None:
        """Manually add a model to the registry (via Liaison or API).

        Args:
            spec: Complete ModelSpec to register.
            added_by: Who added the model (for audit trail).
        """
        self._models[spec.model_id] = spec
        logger.info("Model %s manually added by %s", spec.model_id, added_by)

    def manual_disable_model(self, model_id: str, reason: str = "", disabled_by: str = "system") -> bool:
        """Disable a model (mark as DISABLED, keeps data for re-enable).

        Args:
            model_id: Model to disable.
            reason: Reason for disabling.
            disabled_by: Who disabled the model.

        Returns:
            True if model was found and disabled.
        """
        spec = self._models.get(model_id)
        if not spec:
            logger.warning("Cannot disable unknown model: %s", model_id)
            return False

        # Create a new spec with DISABLED status (dataclass is frozen)
        disabled_spec = ModelSpec(
            model_id=spec.model_id,
            provider=spec.provider,
            display_name=spec.display_name,
            tier=spec.tier,
            capabilities=spec.capabilities,
            pricing=spec.pricing,
            limits=spec.limits,
            status=ModelStatus.DISABLED,
            version=spec.version,
            released_at=spec.released_at,
            deprecated_at=spec.deprecated_at,
            citations=spec.citations,
            verification_confidence=spec.verification_confidence,
            tags=spec.tags,
            description=f"{spec.description} [DISABLED: {reason}]" if reason else spec.description,
        )
        self._models[model_id] = disabled_spec
        logger.info("Model %s disabled by %s: %s", model_id, disabled_by, reason)
        return True

    def manual_enable_model(self, model_id: str, enabled_by: str = "system") -> bool:
        """Re-enable a previously disabled model.

        Args:
            model_id: Model to enable.
            enabled_by: Who enabled the model.

        Returns:
            True if model was found and enabled.
        """
        spec = self._models.get(model_id)
        if not spec:
            logger.warning("Cannot enable unknown model: %s", model_id)
            return False

        enabled_spec = ModelSpec(
            model_id=spec.model_id,
            provider=spec.provider,
            display_name=spec.display_name,
            tier=spec.tier,
            capabilities=spec.capabilities,
            pricing=spec.pricing,
            limits=spec.limits,
            status=ModelStatus.ACTIVE,
            version=spec.version,
            released_at=spec.released_at,
            deprecated_at=spec.deprecated_at,
            citations=spec.citations,
            verification_confidence=spec.verification_confidence,
            tags=spec.tags,
            description=spec.description.replace("[DISABLED:", "").rstrip(" ]"),
        )
        self._models[model_id] = enabled_spec
        logger.info("Model %s enabled by %s", model_id, enabled_by)
        return True

    def disable_provider_models(self, provider: str, reason: str = "", disabled_by: str = "system") -> int:
        """Disable all models from a provider.

        Args:
            provider: Provider name whose models should be disabled.
            reason: Reason for disabling.
            disabled_by: Who disabled the models.

        Returns:
            Number of models disabled.
        """
        count = 0
        for model_id in list(self._models.keys()):
            if self._models[model_id].provider == provider:
                self.manual_disable_model(model_id, reason, disabled_by)
                count += 1
        logger.info("Disabled %d models from provider %s by %s", count, provider, disabled_by)
        return count

    def list_models(self, filters: dict[str, Any] | None = None) -> list[ModelSpec]:
        """List models with optional filtering.

        Args:
            filters: Optional dict with keys like 'tier', 'provider', 'status', 'capability'.

        Returns:
            Filtered list of ModelSpec.
        """
        models = list(self._models.values())
        if not filters:
            return models

        if "tier" in filters:
            tier = ModelTier(filters["tier"]) if isinstance(filters["tier"], str) else filters["tier"]
            models = [m for m in models if m.tier == tier]
        if "provider" in filters:
            models = [m for m in models if m.provider == filters["provider"]]
        if "status" in filters:
            status = ModelStatus(filters["status"]) if isinstance(filters["status"], str) else filters["status"]
            models = [m for m in models if m.status == status]
        if "capability" in filters:
            models = [m for m in models if filters["capability"] in m.capabilities.modalities]

        return models

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_models": len(self._models),
            "active_models": len(self.get_active_models()),
            "providers": len(self._providers),
            "by_tier": {t.value: len(self.get_by_tier(t)) for t in ModelTier},
            "by_provider": {p: len(self.get_by_provider(p)) for p in self._providers},
            "by_status": {s.value: len([m for m in self._models.values() if m.status == s]) for s in ModelStatus},
        }


# Global registry instance
_global_registry: AutoModelRegistry | None = None


def get_registry() -> AutoModelRegistry:
    """Get the global registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = AutoModelRegistry()
        
        # Phase 1: Auto-register known providers to prevent empty registry
        try:
            from gateway.providers.openai import OpenAIProviderAdapter
            from gateway.providers.anthropic import AnthropicProviderAdapter
            from gateway.providers.google import GoogleProviderAdapter
            from gateway.providers.nvidia_nim import NVIDIAProviderAdapter
            
            _global_registry.register_provider(OpenAIProviderAdapter())
            _global_registry.register_provider(AnthropicProviderAdapter())
            _global_registry.register_provider(GoogleProviderAdapter())
            _global_registry.register_provider(NVIDIAProviderAdapter())
        except ImportError:
            pass

        # Seed with default models — only for providers that have API keys
        import os

        if os.environ.get("OPENAI_API_KEY"):
            _global_registry.manual_add_model(ModelSpec(
                model_id="openai/gpt-4o-mini",
                provider="openai",
                display_name="GPT-4o Mini",
                tier=ModelTier.FAST,
                capabilities=ModelCapabilities(128000, ["text", "vision"], True, True, True, 8192),
                pricing=ModelPricing(0.15, 0.60, "USD"),
                limits=ModelLimits()
            ))

        if os.environ.get("GEMINI_API_KEY"):
            _global_registry.manual_add_model(ModelSpec(
                model_id="google/gemini-2.5-flash",
                provider="google",
                display_name="Gemini 2.5 Flash",
                tier=ModelTier.FRONTIER,
                capabilities=ModelCapabilities(1000000, ["text", "vision"], True, True, True, 8192),
                pricing=ModelPricing(0.0, 0.0, "USD"),
                limits=ModelLimits()
            ))

        if os.environ.get("ANTHROPIC_API_KEY"):
            _global_registry.manual_add_model(ModelSpec(
                model_id="anthropic/claude-3-haiku",
                provider="anthropic",
                display_name="Claude 3 Haiku",
                tier=ModelTier.CRITIC,
                capabilities=ModelCapabilities(128000, ["text", "vision"], True, True, True, 4096),
                pricing=ModelPricing(0.25, 1.25, "USD"),
                limits=ModelLimits()
            ))

        if os.environ.get("NVIDIA_NIM_API_KEY"):
            _global_registry.manual_add_model(ModelSpec(
                model_id="nvidia_nim/meta/llama-3.3-70b-instruct",
                provider="nvidia_nim",
                display_name="Llama 3.3 70B Instruct",
                tier=ModelTier.FRONTIER,
                capabilities=ModelCapabilities(128000, ["text"], True, True, True, 8192),
                pricing=ModelPricing(0.0, 0.0, "USD"),
                limits=ModelLimits()
            ))
            _global_registry.manual_add_model(ModelSpec(
                model_id="nvidia_nim/meta/llama-3.1-8b-instruct",
                provider="nvidia_nim",
                display_name="Llama 3.1 8B Instruct",
                tier=ModelTier.FAST,
                capabilities=ModelCapabilities(128000, ["text"], True, True, True, 4096),
                pricing=ModelPricing(0.0, 0.0, "USD"),
                limits=ModelLimits()
            ))
            _global_registry.manual_add_model(ModelSpec(
                model_id="nvidia_nim/meta/llama-3.1-70b-instruct",
                provider="nvidia_nim",
                display_name="Llama 3.1 70B Instruct",
                tier=ModelTier.CRITIC,
                capabilities=ModelCapabilities(128000, ["text"], True, True, True, 4096),
                pricing=ModelPricing(0.0, 0.0, "USD"),
                limits=ModelLimits()
            ))
        
    return _global_registry


def set_registry(registry: AutoModelRegistry) -> None:
    """Set the global registry instance (for testing)."""
    global _global_registry
    _global_registry = registry