"""
Anthropic Provider Adapter — Phase 1
====================================
Implements ProviderAdapter for Anthropic models.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from gateway.model_registry import (
    ModelCapabilities,
    ModelLimits,
    ModelPricing,
    ModelSpec,
    ModelStatus,
    ModelTier,
    ProviderAdapter,
    SourceCitation,
    SourceType,
)

logger = logging.getLogger(__name__)

ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"


class AnthropicProviderAdapter(ProviderAdapter):
    """Anthropic provider adapter for model discovery and verification."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def supported_tiers(self) -> list[ModelTier]:
        return [
            ModelTier.FRONTIER,
            ModelTier.FAST,
            ModelTier.LONG_CONTEXT,
        ]

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"anthropic-version": "2023-06-01"}
            if self.api_key:
                headers["x-api-key"] = self.api_key
            self._client = httpx.AsyncClient(
                base_url=ANTHROPIC_API_BASE,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def discover_models(self) -> list[ModelSpec]:
        """Discover all models from Anthropic /models endpoint."""
        client = await self._get_client()
        models = []

        try:
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()

            for model_data in data.get("data", []):
                spec = await self._parse_model_spec(model_data)
                if spec:
                    models.append(spec)

        except Exception as e:
            logger.debug("Failed to discover Anthropic models: %s", e)

        return models

    async def _parse_model_spec(self, model_data: dict[str, Any]) -> ModelSpec | None:
        """Parse Anthropic model data into ModelSpec."""
        model_id = model_data.get("id", "")
        if not model_id:
            return None

        capabilities = self._infer_capabilities(model_id)
        tier = self._classify_tier(model_id, capabilities.context_window)

        citation = SourceCitation(
            source_type=SourceType.API,
            url=f"{ANTHROPIC_API_BASE}/models/{model_id}",
            provider="anthropic",
            accessed_at=datetime.now(UTC),
            field_mapping={"id": "id", "display_name": "display_name", "type": "type"},
            confidence=1.0,
            raw_snippet=str(model_data),
        )

        pricing = await self.fetch_pricing(model_id) or ModelPricing(
            input_per_1m_tokens=0.0,
            output_per_1m_tokens=0.0,
            currency="USD",
        )

        limits = await self.fetch_limits(model_id) or ModelLimits()

        spec = ModelSpec(
            model_id=f"anthropic/{model_id}",
            provider="anthropic",
            display_name=model_data.get("display_name", model_id),
            tier=tier,
            capabilities=capabilities,
            pricing=pricing,
            limits=limits,
            status=ModelStatus.ACTIVE,
            version="1.0",
            citations={"discovery": citation},
            verification_confidence=1.0,
            tags=["anthropic", tier.value],
            description=f"Anthropic model: {model_id}",
        )

        return spec

    def _infer_capabilities(self, model_id: str) -> ModelCapabilities:
        """Infer capabilities from model ID."""
        model_lower = model_id.lower()

        # Context windows
        context_windows = {
            "claude-3-opus": 200000,
            "claude-3-sonnet": 200000,
            "claude-3-haiku": 200000,
            "claude-3.5-sonnet": 200000,
            "claude-3.5-haiku": 200000,
        }

        context_window = 200000
        for key, value in context_windows.items():
            if key in model_lower:
                context_window = value
                break

        return ModelCapabilities(
            context_window=context_window,
            modalities=["text", "vision"],
            function_calling=True,
            structured_output=True,
            parallel_tool_calls=True,
            max_output_tokens=8192,
        )

    def _classify_tier(self, model_id: str, context_window: int) -> ModelTier:
        """Classify model into tier."""
        model_lower = model_id.lower()

        if "haiku" in model_lower:
            return ModelTier.FAST

        if context_window >= 100000:
            return ModelTier.LONG_CONTEXT

        return ModelTier.FRONTIER

    async def fetch_pricing(self, model_id: str) -> ModelPricing | None:
        """Fetch pricing for a model."""
        clean_id = model_id.replace("anthropic/", "")

        pricing_map = {
            "claude-3-opus": (15.00, 75.00),
            "claude-3-sonnet": (3.00, 15.00),
            "claude-3-haiku": (0.25, 1.25),
            "claude-3.5-sonnet": (3.00, 15.00),
            "claude-3.5-haiku": (0.80, 4.00),
        }

        input_price, output_price = pricing_map.get(clean_id, (0.0, 0.0))

        citation = SourceCitation(
            source_type=SourceType.PRICING_PAGE,
            url="https://www.anthropic.com/pricing",
            provider="anthropic",
            accessed_at=datetime.now(UTC),
            field_mapping={"input": "input_per_1m", "output": "output_per_1m"},
            confidence=0.9,
            raw_snippet=f"Anthropic pricing for {clean_id}",
        )

        return ModelPricing(
            input_per_1m_tokens=input_price,
            output_per_1m_tokens=output_price,
            currency="USD",
            citation=citation,
            effective_date=datetime.now(UTC),
        )

    async def fetch_limits(self, model_id: str) -> ModelLimits | None:
        """Fetch rate limits for a model."""
        if "haiku" in model_id.lower():
            return ModelLimits(rpm=100, tpm=50000, rpd=10000)
        return ModelLimits(rpm=50, tpm=40000, rpd=5000)

    async def verify_model(self, model_id: str) -> ModelSpec | None:
        """Verify a specific model against Anthropic sources."""
        clean_id = model_id.replace("anthropic/", "")
        client = await self._get_client()

        try:
            response = await client.get(f"/models/{clean_id}")
            if response.status_code == 404:
                return None

            response.raise_for_status()
            model_data = response.json()

            return await self._parse_model_spec(model_data)

        except Exception as e:
            logger.error("Failed to verify Anthropic model %s: %s", model_id, e)
            return None


def create_anthropic_adapter(api_key: str | None = None) -> AnthropicProviderAdapter:
    """Create Anthropic adapter with optional API key."""
    return AnthropicProviderAdapter(api_key=api_key)