"""
NVIDIA NIM Provider Adapter — Phase 1
=====================================
Implements ProviderAdapter for NVIDIA NIM models.
Uses NVIDIA NIM API endpoints for model discovery and verification.
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

# NVIDIA NIM API endpoints
NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_NIM_MODELS_URL = f"{NVIDIA_NIM_BASE_URL}/models"


class NVIDIAProviderAdapter(ProviderAdapter):
    """Provider adapter for NVIDIA NIM models."""

    def __init__(self, api_key: str | None = None, base_url: str = NVIDIA_NIM_BASE_URL):
        self._api_key = api_key
        self._base_url = base_url
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "nvidia_nim"

    @property
    def supported_tiers(self) -> list[ModelTier]:
        return [
            ModelTier.FRONTIER,
            ModelTier.FAST,
            ModelTier.CRITIC,
            ModelTier.CODE_SPECIALIZED,
            ModelTier.LONG_CONTEXT,
        ]

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def discover_models(self) -> list[ModelSpec]:
        """Discover all models from NVIDIA NIM /models endpoint."""
        client = await self._get_client()

        try:
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("data", []):
                spec = await self._parse_model_spec(model_data)
                if spec:
                    models.append(spec)

            logger.info("Discovered %d NVIDIA NIM models", len(models))
            return models

        except Exception as e:
            logger.debug("Failed to discover NVIDIA NIM models: %s", e)
            return []

    async def _parse_model_spec(self, model_data: dict[str, Any]) -> ModelSpec | None:
        """Parse NVIDIA NIM model data into ModelSpec."""
        model_id = model_data.get("id", "")
        if not model_id:
            return None

        # SKIP embedding, reranking, and specific vision/guardrail models that don't support chat
        skip_keywords = ["embed", "bge-", "rerank", "retrieval", "sdxl", "guardrails", "yolo", "m3"]
        if any(kw in model_id.lower() for kw in skip_keywords):
            return None

        # Create provider-prefixed ID
        full_model_id = f"nvidia_nim/{model_id}"

        # Extract capabilities from model data
        # NVIDIA NIM models typically have these fields
        context_window = model_data.get("max_context_length", 4096)
        owned_by = model_data.get("owned_by", "nvidia")
        
        # Attempt to read official parameter size from API metadata (if provided)
        parameter_size_b = None
        metadata = model_data.get("metadata", {})
        if "parameter_count" in metadata:
            try:
                parameter_size_b = float(metadata["parameter_count"])
            except (ValueError, TypeError):
                pass
        elif "parameters" in model_data:
            try:
                parameter_size_b = float(model_data["parameters"])
            except (ValueError, TypeError):
                pass

        # Determine tier based on model name and capabilities
        tier = self._classify_tier(model_id, context_window)

        # Build capabilities
        capabilities = ModelCapabilities(
            context_window=context_window,
            modalities=["text", "function_calling"],
            function_calling=True,
            structured_output=True,
            parallel_tool_calls=True,
            max_output_tokens=min(8192, context_window // 4),
            parameter_size_b=parameter_size_b,
        )

        # Default pricing (NVIDIA NIM is often free tier)
        pricing = ModelPricing(
            input_per_1m_tokens=0.0,
            output_per_1m_tokens=0.0,
            currency="USD",
        )

        # Default limits
        limits = ModelLimits(rpm=60, tpm=100000)

        # Citation from API discovery
        citation = SourceCitation(
            source_type=SourceType.API,
            url=NVIDIA_NIM_MODELS_URL,
            provider="nvidia_nim",
            accessed_at=datetime.now(UTC),
            field_mapping={
                "model_id": "id",
                "context_window": "max_context_length",
                "owned_by": "owned_by",
            },
            confidence=1.0,
            raw_snippet=str(model_data),
        )

        spec = ModelSpec(
            model_id=full_model_id,
            provider="nvidia_nim",
            display_name=model_id,
            tier=tier,
            capabilities=capabilities,
            pricing=pricing,
            limits=limits,
            status=ModelStatus.ACTIVE,
            version=model_data.get("version", "1.0"),
            citations={"discovery": citation},
            verification_confidence=1.0,
            tags=["nvidia", "nim", tier.value],
            description=f"NVIDIA NIM model: {model_id}",
        )

        return spec

    def _classify_tier(self, model_id: str, context_window: int) -> ModelTier:
        """Classify model into tier based on name and capabilities."""
        model_lower = model_id.lower()

        # Code-specialized models
        if any(keyword in model_lower for keyword in ["code", "codellama", "starcoder", "deepseek-coder"]):
            return ModelTier.CODE_SPECIALIZED

        # Vision models
        if any(keyword in model_lower for keyword in ["vision", "llava", "pixtral"]):
            return ModelTier.VISION

        # Long context models
        if context_window >= 100000 or "long" in model_lower:
            return ModelTier.LONG_CONTEXT

        # Critic models (different architecture for critique)
        if any(keyword in model_lower for keyword in ["critic", "gemma", "nemotron-3-ultra"]):
            return ModelTier.CRITIC

        # Fast models (smaller, faster)
        if any(keyword in model_lower for keyword in ["mini", "small", "mistral-7b", "llama-3.1-8b"]):
            return ModelTier.FAST

        # Default to frontier for large models
        return ModelTier.FRONTIER

    async def fetch_pricing(self, model_id: str) -> ModelPricing | None:
        """Fetch pricing for a model.
        NVIDIA NIM models are typically free (included with NVIDIA AI Enterprise)."""
        # Strip provider prefix if present
        clean_id = model_id.replace("nvidia_nim/", "")

        # NVIDIA NIM pricing is typically $0 (included with license)
        citation = SourceCitation(
            source_type=SourceType.PRICING_PAGE,
            url="https://www.nvidia.com/en-us/ai-data-science/products/nim/",
            provider="nvidia_nim",
            accessed_at=datetime.now(UTC),
            field_mapping={"pricing": "pricing page"},
            confidence=0.9,
            raw_snippet="NVIDIA NIM models included with NVIDIA AI Enterprise license",
        )

        return ModelPricing(
            input_per_1m_tokens=0.0,
            output_per_1m_tokens=0.0,
            currency="USD",
            citation=citation,
            effective_date=datetime.now(UTC),
        )

    async def fetch_limits(self, model_id: str) -> ModelLimits | None:
        """Fetch rate limits for a model.
        NVIDIA NIM defaults - actual limits depend on deployment."""
        # Strip provider prefix
        clean_id = model_id.replace("nvidia_nim/", "")

        # Default limits for NVIDIA NIM
        return ModelLimits(rpm=60, tpm=100000, rpd=10000)

    async def verify_model(self, model_id: str) -> ModelSpec | None:
        """Verify a specific model against NVIDIA NIM sources."""
        clean_id = model_id.replace("nvidia_nim/", "")
        client = await self._get_client()

        try:
            response = await client.get(f"/models/{clean_id}")
            if response.status_code == 404:
                return None

            response.raise_for_status()
            model_data = response.json()

            return await self._parse_model_spec(model_data)

        except Exception as e:
            logger.error("Failed to verify NVIDIA NIM model %s: %s", model_id, e)
            return None


# Convenience function for creating the factory function
def create_nvidia_nim_adapter(api_key: str | None = None) -> NVIDIAProviderAdapter:
    """Create NVIDIA NIM adapter with optional API key."""
    return NVIDIAProviderAdapter(api_key=api_key)