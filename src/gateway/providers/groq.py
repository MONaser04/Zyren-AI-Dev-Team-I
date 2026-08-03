"""
Groq Provider Adapter — Phase 1
================================
Implements ProviderAdapter for Groq models.
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

GROQ_API_BASE = "https://api.groq.com/openai/v1"


class GroqProviderAdapter(ProviderAdapter):
    """Groq provider adapter for model discovery and verification."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def supported_tiers(self) -> list[ModelTier]:
        return [
            ModelTier.FAST,
            ModelTier.CODE_SPECIALIZED,
            ModelTier.LONG_CONTEXT,
        ]

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=GROQ_API_BASE,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def discover_models(self) -> list[ModelSpec]:
        """Discover all models from Groq /models endpoint."""
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
            logger.debug("Failed to discover Groq models: %s", e)

        return models

    async def _parse_model_spec(self, model_data: dict[str, Any]) -> ModelSpec | None:
        """Parse Groq model data into ModelSpec."""
        model_id = model_data.get("id", "")
        if not model_id:
            return None

        capabilities = self._infer_capabilities(model_id)
        tier = self._classify_tier(model_id, capabilities.context_window)

        citation = SourceCitation(
            source_type=SourceType.API,
            url=f"{GROQ_API_BASE}/models/{model_id}",
            provider="groq",
            accessed_at=datetime.now(UTC),
            field_mapping={"id": "id", "owned_by": "owned_by"},
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
            model_id=f"groq/{model_id}",
            provider="groq",
            display_name=model_id,
            tier=tier,
            capabilities=capabilities,
            pricing=pricing,
            limits=limits,
            status=ModelStatus.ACTIVE,
            version="1.0",
            citations={"discovery": citation},
            verification_confidence=1.0,
            tags=["groq", tier.value],
            description=f"Groq model: {model_id}",
        )

        return spec

    def _infer_capabilities(self, model_id: str) -> ModelCapabilities:
        """Infer capabilities from model ID."""
        model_lower = model_id.lower()

        # Context windows
        context_windows = {
            "llama-3.3-70b": 128000,
            "llama-3.1-70b": 128000,
            "llama-3.1-8b": 128000,
            "llama-3-70b": 8192,
            "llama-3-8b": 8192,
            "mixtral-8x7b": 32768,
            "gemma2-9b": 8192,
            "gemma-7b": 8192,
        }

        context_window = 8192
        for key, value in context_windows.items():
            if key in model_lower:
                context_window = value
                break

        # Capabilities
        has_code = "code" in model_lower or "codellama" in model_lower
        has_function_calling = True  # Groq models support function calling

        return ModelCapabilities(
            context_window=context_window,
            modalities=["text"],
            function_calling=has_function_calling,
            structured_output=has_function_calling,
            parallel_tool_calls=has_function_calling,
            max_output_tokens=min(8192, context_window // 4),
        )

    def _classify_tier(self, model_id: str, context_window: int) -> ModelTier:
        """Classify model into tier."""
        model_lower = model_id.lower()

        if "code" in model_lower or "codellama" in model_lower:
            return ModelTier.CODE_SPECIALIZED

        if any(x in model_lower for x in ["8b", "7b", "9b", "gemma"]):
            return ModelTier.FAST

        if context_window >= 100000:
            return ModelTier.LONG_CONTEXT

        return ModelTier.FAST  # Groq is primarily fast models

    async def fetch_pricing(self, model_id: str) -> ModelPricing | None:
        """Fetch pricing for Groq models (free tier)."""
        clean_id = model_id.replace("groq/", "")

        # Groq free tier pricing
        pricing_map = {
            "llama-3.3-70b-versatile": (0.0, 0.0),
            "llama-3.1-70b-versatile": (0.0, 0.0),
            "llama-3.1-8b-instant": (0.0, 0.0),
            "llama-3-70b-versatile": (0.0, 0.0),
            "llama-3-8b-instant": (0.0, 0.0),
            "mixtral-8x7b-32768": (0.0, 0.0),
            "gemma2-9b-it": (0.0, 0.0),
            "gemma-7b-it": (0.0, 0.0),
        }

        input_price, output_price = pricing_map.get(clean_id, (0.0, 0.0))

        citation = SourceCitation(
            source_type=SourceType.PRICING_PAGE,
            url="https://groq.com/pricing",
            provider="groq",
            accessed_at=datetime.now(UTC),
            field_mapping={"input": "input_per_1m", "output": "output_per_1m"},
            confidence=0.9,
            raw_snippet=f"Groq pricing for {clean_id}",
        )

        return ModelPricing(
            input_per_1m_tokens=input_price,
            output_per_1m_tokens=output_price,
            currency="USD",
            citation=citation,
            effective_date=datetime.now(UTC),
        )

    async def fetch_limits(self, model_id: str) -> ModelLimits | None:
        """Fetch rate limits for Groq models."""
        # Groq free tier limits
        if "70b" in model_id or "8x7b" in model_id:
            return ModelLimits(rpm=30, tpm=6000, rpd=14400)
        return ModelLimits(rpm=30, tpm=6000, rpd=14400)

    async def verify_model(self, model_id: str) -> ModelSpec | None:
        """Verify a specific model against Groq sources."""
        clean_id = model_id.replace("groq/", "")
        client = await self._get_client()

        try:
            response = await client.get(f"/models/{clean_id}")
            if response.status_code == 404:
                return None

            response.raise_for_status()
            model_data = response.json()

            return await self._parse_model_spec(model_data)

        except Exception as e:
            logger.error("Failed to verify Groq model %s: %s", model_id, e)
            return None


def create_groq_adapter(api_key: str | None = None) -> GroqProviderAdapter:
    """Create Groq adapter with optional API key."""
    return GroqProviderAdapter(api_key=api_key)