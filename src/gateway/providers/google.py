"""
Google Provider Adapter — Phase 1
=================================
Implements ProviderAdapter for Google models (Vertex AI / AI Studio).
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

GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GoogleProviderAdapter(ProviderAdapter):
    """Google provider adapter for model discovery and verification."""

    def __init__(self, api_key: str | None = None, project_id: str | None = None) -> None:
        self.api_key = api_key
        self.project_id = project_id
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "google"

    @property
    def supported_tiers(self) -> list[ModelTier]:
        return [
            ModelTier.FRONTIER,
            ModelTier.FAST,
            ModelTier.LONG_CONTEXT,
            ModelTier.CODE_SPECIALIZED,
            ModelTier.VISION,
        ]

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            params = {}
            if self.api_key:
                params["key"] = self.api_key
            self._client = httpx.AsyncClient(
                base_url=GOOGLE_API_BASE,
                params=params,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def discover_models(self) -> list[ModelSpec]:
        """Discover all models from Google /models endpoint."""
        client = await self._get_client()
        models = []

        try:
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()

            for model_data in data.get("models", []):
                spec = await self._parse_model_spec(model_data)
                if spec:
                    models.append(spec)

        except Exception as e:
            logger.debug("Failed to discover Google models: %s", e)

        return models

    async def _parse_model_spec(self, model_data: dict[str, Any]) -> ModelSpec | None:
        """Parse Google model data into ModelSpec."""
        model_id = model_data.get("name", "").split("/")[-1]
        if not model_id:
            return None

        capabilities = self._infer_capabilities(model_id)
        tier = self._classify_tier(model_id, capabilities.context_window)

        citation = SourceCitation(
            source_type=SourceType.API,
            url=f"{GOOGLE_API_BASE}/models/{model_id}",
            provider="google",
            accessed_at=datetime.now(UTC),
            field_mapping={"name": "name", "displayName": "display_name", "version": "version"},
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
            model_id=f"google/{model_id}",
            provider="google",
            display_name=model_data.get("displayName", model_id),
            tier=tier,
            capabilities=capabilities,
            pricing=pricing,
            limits=limits,
            status=ModelStatus.ACTIVE,
            version=model_data.get("version", "1.0"),
            citations={"discovery": citation},
            verification_confidence=1.0,
            tags=["google", tier.value],
            description=f"Google model: {model_id}",
        )

        return spec

    def _infer_capabilities(self, model_id: str) -> ModelCapabilities:
        """Infer capabilities from model ID."""
        model_lower = model_id.lower()

        # Context windows
        context_windows = {
            "gemini-1.5-pro": 2000000,
            "gemini-1.5-flash": 1000000,
            "gemini-1.5-flash-8b": 1000000,
            "gemini-1.0-pro": 32768,
            "gemini-1.0-pro-vision": 32768,
        }

        context_window = 32768
        for key, value in context_windows.items():
            if key in model_lower:
                context_window = value
                break

        # Capabilities
        has_vision = "vision" in model_lower or "pro" in model_lower
        has_code = "code" in model_lower or "gemini" in model_lower

        return ModelCapabilities(
            context_window=context_window,
            modalities=["text", "vision", "function_calling"] if has_vision else ["text", "function_calling"],
            function_calling=True,
            structured_output=True,
            parallel_tool_calls=True,
            max_output_tokens=8192,
        )

    def _classify_tier(self, model_id: str, context_window: int) -> ModelTier:
        """Classify model into tier."""
        model_lower = model_id.lower()

        if "flash-8b" in model_lower or "flash" in model_lower:
            return ModelTier.FAST

        if "code" in model_lower:
            return ModelTier.CODE_SPECIALIZED

        if context_window >= 1000000:
            return ModelTier.LONG_CONTEXT

        if "pro" in model_lower:
            return ModelTier.FRONTIER

        return ModelTier.FAST

    async def fetch_pricing(self, model_id: str) -> ModelPricing | None:
        """Fetch pricing for a model."""
        clean_id = model_id.replace("google/", "")

        # Google AI Studio / Vertex AI pricing
        pricing_map = {
            "gemini-1.5-pro": (3.50, 10.50),
            "gemini-1.5-flash": (0.075, 0.30),
            "gemini-1.5-flash-8b": (0.0375, 0.15),
            "gemini-1.0-pro": (0.50, 1.50),
            "gemini-1.0-pro-vision": (0.50, 1.50),
        }

        input_price, output_price = pricing_map.get(clean_id, (0.0, 0.0))

        citation = SourceCitation(
            source_type=SourceType.PRICING_PAGE,
            url="https://ai.google.dev/pricing",
            provider="google",
            accessed_at=datetime.now(UTC),
            field_mapping={"input": "input_per_1m", "output": "output_per_1m"},
            confidence=0.9,
            raw_snippet=f"Google AI Studio pricing for {clean_id}",
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
        if "flash" in model_id.lower():
            return ModelLimits(rpm=1000, tpm=250000, rpd=50000)
        return ModelLimits(rpm=60, tpm=60000, rpd=10000)

    async def verify_model(self, model_id: str) -> ModelSpec | None:
        """Verify a specific model against Google sources."""
        clean_id = model_id.replace("google/", "")
        client = await self._get_client()

        try:
            response = await client.get(f"/models/{clean_id}")
            if response.status_code == 404:
                return None

            response.raise_for_status()
            model_data = response.json()

            return await self._parse_model_spec(model_data)

        except Exception as e:
            logger.error("Failed to verify Google model %s: %s", model_id, e)
            return None


def create_google_adapter(api_key: str | None = None, project_id: str | None = None) -> GoogleProviderAdapter:
    """Create Google adapter with optional API key and project ID."""
    return GoogleProviderAdapter(api_key=api_key, project_id=project_id)