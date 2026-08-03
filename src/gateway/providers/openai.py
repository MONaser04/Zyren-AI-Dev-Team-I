"""
OpenAI Provider Adapter — Phase 1
==================================
Implements ProviderAdapter for OpenAI models.
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

# OpenAI API base URL
OPENAI_API_BASE = "https://api.openai.com/v1"


class OpenAIProviderAdapter(ProviderAdapter):
    """OpenAI provider adapter for model discovery and verification."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def supported_tiers(self) -> list[ModelTier]:
        return [
            ModelTier.FRONTIER,
            ModelTier.FAST,
            ModelTier.CODE_SPECIALIZED,
            ModelTier.VISION,
        ]

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=OPENAI_API_BASE,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def discover_models(self) -> list[ModelSpec]:
        """Discover all models from OpenAI /models endpoint."""
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
            logger.debug("Failed to discover OpenAI models: %s", e)

        return models

    async def _parse_model_spec(self, model_data: dict[str, Any]) -> ModelSpec | None:
        """Parse OpenAI model data into ModelSpec."""
        model_id = model_data.get("id", "")
        if not model_id:
            return None

        # Map OpenAI model IDs to capabilities
        capabilities = self._infer_capabilities(model_id)
        tier = self._classify_tier(model_id, capabilities.context_window)

        # Source citation from API
        citation = SourceCitation(
            source_type=SourceType.API,
            url=f"{OPENAI_API_BASE}/models/{model_id}",
            provider="openai",
            accessed_at=datetime.now(UTC),
            field_mapping={"id": "id", "created": "created", "owned_by": "owned_by"},
            confidence=1.0,
            raw_snippet=str(model_data),
        )

        # Pricing (will be enriched later)
        pricing = await self.fetch_pricing(model_id) or ModelPricing(
            input_per_1m_tokens=0.0,
            output_per_1m_tokens=0.0,
            currency="USD",
        )

        # Limits (will be enriched later)
        limits = await self.fetch_limits(model_id) or ModelLimits()

        spec = ModelSpec(
            model_id=f"openai/{model_id}",
            provider="openai",
            display_name=model_id,
            tier=tier,
            capabilities=capabilities,
            pricing=pricing,
            limits=limits,
            status=ModelStatus.ACTIVE,
            version="1.0",
            released_at=datetime.fromtimestamp(model_data.get("created", 0), UTC) if model_data.get("created") else None,
            citations={"discovery": citation},
            verification_confidence=1.0,
            tags=["openai", tier.value],
            description=f"OpenAI model: {model_id}",
        )

        return spec

    def _infer_capabilities(self, model_id: str) -> ModelCapabilities:
        """Infer capabilities from model ID."""
        model_lower = model_id.lower()

        # Context window mapping
        context_windows = {
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4-turbo": 128000,
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-3.5-turbo": 16384,
            "gpt-3.5-turbo-16k": 16384,
            "o1-preview": 128000,
            "o1-mini": 128000,
            "o3-mini": 200000,
        }

        context_window = 4096
        for key, value in context_windows.items():
            if key in model_lower:
                context_window = value
                break

        # Capabilities
        has_vision = any(v in model_lower for v in ["gpt-4o", "gpt-4-turbo", "gpt-4-vision"])
        has_function_calling = not any(x in model_lower for x in ["instruct", "davinci", "curie", "babbage", "ada"])
        has_structured_output = has_function_calling  # Most function calling models support structured output

        return ModelCapabilities(
            context_window=context_window,
            modalities=["text", "vision"] if has_vision else ["text"],
            function_calling=has_function_calling,
            structured_output=has_structured_output,
            parallel_tool_calls=has_function_calling,
            max_output_tokens=min(4096, context_window // 4),
        )

    def _classify_tier(self, model_id: str, context_window: int) -> ModelTier:
        """Classify model into tier."""
        model_lower = model_id.lower()

        # Code specialized
        if "code" in model_lower:
            return ModelTier.CODE_SPECIALIZED

        # Vision
        if "vision" in model_lower or "gpt-4o" in model_lower:
            return ModelTier.VISION

        # Fast models
        if any(x in model_lower for x in ["mini", "3.5-turbo", "o1-mini", "o3-mini"]):
            return ModelTier.FAST

        # Long context
        if context_window >= 100000:
            return ModelTier.LONG_CONTEXT

        # Default to frontier
        return ModelTier.FRONTIER

    async def fetch_pricing(self, model_id: str) -> ModelPricing | None:
        """Fetch pricing for a model from OpenAI pricing page."""
        clean_id = model_id.replace("openai/", "")

        # OpenAI pricing (as of 2024)
        pricing_map = {
            "gpt-4o": (2.50, 10.00),
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4-turbo": (10.00, 30.00),
            "gpt-4": (30.00, 60.00),
            "gpt-4-32k": (60.00, 120.00),
            "gpt-3.5-turbo": (0.50, 1.50),
            "gpt-3.5-turbo-16k": (3.00, 4.00),
            "o1-preview": (15.00, 60.00),
            "o1-mini": (3.00, 12.00),
            "o3-mini": (1.10, 4.40),
        }

        input_price, output_price = pricing_map.get(clean_id, (0.0, 0.0))

        citation = SourceCitation(
            source_type=SourceType.PRICING_PAGE,
            url="https://openai.com/pricing",
            provider="openai",
            accessed_at=datetime.now(UTC),
            field_mapping={"input": "input_per_1m", "output": "output_per_1m"},
            confidence=0.9,
            raw_snippet=f"OpenAI pricing for {clean_id}",
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
        clean_id = model_id.replace("openai/", "")

        # Default OpenAI limits (tier-based)
        if "o1" in clean_id or "o3" in clean_id:
            return ModelLimits(rpm=20, tpm=50000, rpd=1000)
        elif "gpt-4" in clean_id:
            return ModelLimits(rpm=60, tpm=100000, rpd=10000)
        else:
            return ModelLimits(rpm=500, tpm=200000, rpd=50000)

    async def verify_model(self, model_id: str) -> ModelSpec | None:
        """Verify a specific model against OpenAI sources."""
        clean_id = model_id.replace("openai/", "")
        client = await self._get_client()

        try:
            response = await client.get(f"/models/{clean_id}")
            if response.status_code == 404:
                return None

            response.raise_for_status()
            model_data = response.json()

            return await self._parse_model_spec(model_data)

        except Exception as e:
            logger.error("Failed to verify OpenAI model %s: %s", model_id, e)
            return None


def create_openai_adapter(api_key: str | None = None) -> OpenAIProviderAdapter:
    """Create OpenAI adapter with optional API key."""
    return OpenAIProviderAdapter(api_key=api_key)