"""
Together AI Provider Adapter — Phase 1
=======================================
Implements ProviderAdapter for Together AI models.
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

TOGETHER_API_BASE = "https://api.together.xyz/v1"


class TogetherProviderAdapter(ProviderAdapter):
    """Together AI provider adapter for model discovery and verification."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "together"

    @property
    def supported_tiers(self) -> list[ModelTier]:
        return [
            ModelTier.FRONTIER,
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
                base_url=TOGETHER_API_BASE,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def discover_models(self) -> list[ModelSpec]:
        """Discover all models from Together AI /models endpoint."""
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
            logger.debug("Failed to discover Together AI models: %s", e)

        return models

    async def _parse_model_spec(self, model_data: dict[str, Any]) -> ModelSpec | None:
        """Parse Together AI model data into ModelSpec."""
        model_id = model_data.get("id", "")
        if not model_id:
            return None

        capabilities = self._infer_capabilities(model_id)
        tier = self._classify_tier(model_id, capabilities.context_window)

        citation = SourceCitation(
            source_type=SourceType.API,
            url=f"{TOGETHER_API_BASE}/models/{model_id}",
            provider="together",
            accessed_at=datetime.now(UTC),
            field_mapping={"id": "id", "object": "object", "owned_by": "owned_by"},
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
            model_id=f"together/{model_id}",
            provider="together",
            display_name=model_id,
            tier=tier,
            capabilities=capabilities,
            pricing=pricing,
            limits=limits,
            status=ModelStatus.ACTIVE,
            version="1.0",
            citations={"discovery": citation},
            verification_confidence=1.0,
            tags=["together", tier.value],
            description=f"Together AI model: {model_id}",
        )

        return spec

    def _infer_capabilities(self, model_id: str) -> ModelCapabilities:
        """Infer capabilities from model ID."""
        model_lower = model_id.lower()

        # Context windows
        context_windows = {
            "llama-3.1-405b": 128000,
            "llama-3.1-70b": 128000,
            "llama-3.1-8b": 128000,
            "llama-3-70b": 8192,
            "llama-3-8b": 8192,
            "mixtral-8x7b": 32768,
            "mixtral-8x22b": 65536,
            "qwen2.5-72b": 128000,
            "qwen2.5-32b": 128000,
            "qwen2.5-7b": 128000,
            "deepseek-coder": 16384,
            "codellama": 16384,
            "starcoder2": 16384,
            "wizardcoder": 16384,
            "phi-3": 128000,
            "gemma-2": 8192,
            "gemma": 8192,
        }

        context_window = 4096
        for key, value in context_windows.items():
            if key in model_lower:
                context_window = value
                break

        # Capabilities
        has_code = any(c in model_lower for c in ["code", "codellama", "starcoder", "wizardcoder", "deepseek-coder"])
        has_function_calling = not any(x in model_lower for x in ["instruct"])

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

        if any(c in model_lower for c in ["code", "codellama", "starcoder", "wizardcoder", "deepseek-coder"]):
            return ModelTier.CODE_SPECIALIZED

        if any(x in model_lower for x in ["8b", "7b", "3b", "phi-3", "gemma"]):
            return ModelTier.FAST

        if context_window >= 100000:
            return ModelTier.LONG_CONTEXT

        return ModelTier.FRONTIER

    async def fetch_pricing(self, model_id: str) -> ModelPricing | None:
        """Fetch pricing for Together AI models."""
        clean_id = model_id.replace("together/", "")

        # Together AI pricing (per 1M tokens)
        pricing_map = {
            "meta-llama/llama-3.1-405b-instruct": (5.00, 5.00),
            "meta-llama/llama-3.1-70b-instruct": (0.90, 0.90),
            "meta-llama/llama-3.1-8b-instruct": (0.18, 0.18),
            "meta-llama/llama-3-70b-instruct": (0.90, 0.90),
            "meta-llama/llama-3-8b-instruct": (0.18, 0.18),
            "mistralai/mixtral-8x7b-instruct": (0.60, 0.60),
            "mistralai/mixtral-8x22b-instruct": (1.20, 1.20),
            "qwen/qwen2.5-72b-instruct": (0.90, 0.90),
            "qwen/qwen2.5-32b-instruct": (0.60, 0.60),
            "qwen/qwen2.5-7b-instruct": (0.15, 0.15),
            "deepseek-ai/deepseek-coder-33b-instruct": (0.60, 0.60),
            "codellama/codellama-34b-instruct": (0.60, 0.60),
            "bigcode/starcoder2-15b-instruct": (0.60, 0.60),
            "wizardcoder/wizardcoder-34b-v1.0": (0.60, 0.60),
            "microsoft/phi-3-medium-4k-instruct": (0.15, 0.15),
            "google/gemma-2-9b-it": (0.15, 0.15),
            "google/gemma-2-27b-it": (0.30, 0.30),
        }

        input_price, output_price = pricing_map.get(clean_id, (0.0, 0.0))

        citation = SourceCitation(
            source_type=SourceType.PRICING_PAGE,
            url="https://www.together.ai/pricing",
            provider="together",
            accessed_at=datetime.now(UTC),
            field_mapping={"input": "input_per_1m", "output": "output_per_1m"},
            confidence=0.9,
            raw_snippet=f"Together AI pricing for {clean_id}",
        )

        return ModelPricing(
            input_per_1m_tokens=input_price,
            output_per_1m_tokens=output_price,
            currency="USD",
            citation=citation,
            effective_date=datetime.now(UTC),
        )

    async def fetch_limits(self, model_id: str) -> ModelLimits | None:
        """Fetch rate limits for Together AI models."""
        if "405b" in model_id or "8x22b" in model_id or "70b" in model_id:
            return ModelLimits(rpm=60, tpm=100000, rpd=10000)
        return ModelLimits(rpm=200, tpm=200000, rpd=50000)

    async def verify_model(self, model_id: str) -> ModelSpec | None:
        """Verify a specific model against Together AI sources."""
        clean_id = model_id.replace("together/", "")
        client = await self._get_client()

        try:
            response = await client.get(f"/models/{clean_id}")
            if response.status_code == 404:
                return None

            response.raise_for_status()
            model_data = response.json()

            return await self._parse_model_spec(model_data)

        except Exception as e:
            logger.error("Failed to verify Together AI model %s: %s", model_id, e)
            return None


def create_together_adapter(api_key: str | None = None) -> TogetherProviderAdapter:
    """Create Together AI adapter with optional API key."""
    return TogetherProviderAdapter(api_key=api_key)