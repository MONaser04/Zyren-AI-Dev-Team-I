"""
Ollama Provider Adapter — Phase 1
==================================
Implements ProviderAdapter for Ollama local models.
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

# Default Ollama API base
OLLAMA_API_BASE = "http://localhost:11434"


class OllamaProviderAdapter(ProviderAdapter):
    """Ollama provider adapter for local model discovery and verification."""

    def __init__(self, base_url: str = OLLAMA_API_BASE) -> None:
        self.base_url = base_url
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "ollama"

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
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def discover_models(self) -> list[ModelSpec]:
        """Discover models from Ollama /api/tags endpoint."""
        client = await self._get_client()
        models = []

        try:
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()

            for model_data in data.get("models", []):
                spec = await self._parse_model_spec(model_data)
                if spec:
                    models.append(spec)

        except Exception as e:
            logger.debug("Failed to discover Ollama models: %s", e)

        return models

    async def _parse_model_spec(self, model_data: dict[str, Any]) -> ModelSpec | None:
        """Parse Ollama model data into ModelSpec."""
        model_id = model_data.get("name", "")
        if not model_id:
            return None

        # Remove tag if present (e.g., "llama3.1:8b" -> "llama3.1-8b")
        clean_id = model_id.replace(":", "-")

        capabilities = self._infer_capabilities(model_id)
        tier = self._classify_tier(model_id, capabilities.context_window)

        citation = SourceCitation(
            source_type=SourceType.API,
            url=f"{self.base_url}/api/show",
            provider="ollama",
            accessed_at=datetime.now(UTC),
            field_mapping={"name": "name", "size": "size", "digest": "digest"},
            confidence=1.0,
            raw_snippet=str(model_data),
        )

        # Ollama models are free (local)
        pricing = ModelPricing(
            input_per_1m_tokens=0.0,
            output_per_1m_tokens=0.0,
            currency="USD",
        )

        limits = ModelLimits(rpm=1000, tpm=1000000, rpd=100000)

        spec = ModelSpec(
            model_id=f"ollama/{clean_id}",
            provider="ollama",
            display_name=model_id,
            tier=tier,
            capabilities=capabilities,
            pricing=pricing,
            limits=limits,
            status=ModelStatus.ACTIVE,
            version=model_data.get("details", {}).get("family", "1.0"),
            citations={"discovery": citation},
            verification_confidence=1.0,
            tags=["ollama", "local", tier.value],
            description=f"Ollama local model: {model_id}",
        )

        return spec

    def _infer_capabilities(self, model_id: str) -> ModelCapabilities:
        """Infer capabilities from model ID."""
        model_lower = model_id.lower()

        # Context windows for known Ollama models
        context_windows = {
            "llama3.1": 128000,
            "llama3": 8192,
            "llama2": 4096,
            "codellama": 16384,
            "mistral": 32768,
            "mixtral": 32768,
            "phi3": 128000,
            "phi3.5": 128000,
            "gemma2": 8192,
            "gemma": 8192,
            "qwen2": 32768,
            "qwen2.5": 128000,
            "nemotron": 128000,
            "command-r": 128000,
        }

        context_window = 4096
        for key, value in context_windows.items():
            if key in model_lower:
                context_window = value
                break

        # Capabilities
        has_vision = any(v in model_lower for v in ["llava", "bakllava", "moondream", "vision"])
        has_code = any(c in model_lower for c in ["code", "codellama", "starcoder", "wizardcoder"])
        has_function_calling = any(f in model_lower for f in ["llama3.1", "llama3", "phi3", "qwen2", "nemotron"])

        return ModelCapabilities(
            context_window=context_window,
            modalities=["text", "vision"] if has_vision else ["text"],
            function_calling=has_function_calling,
            structured_output=has_function_calling,
            parallel_tool_calls=has_function_calling,
            max_output_tokens=min(8192, context_window // 4),
        )

    def _classify_tier(self, model_id: str, context_window: int) -> ModelTier:
        """Classify model into tier."""
        model_lower = model_id.lower()

        if "code" in model_lower or "codellama" in model_lower or "starcoder" in model_lower:
            return ModelTier.CODE_SPECIALIZED

        if any(x in model_lower for x in ["8b", "7b", "3b", "1b", "small", "mini", "phi3", "gemma"]):
            return ModelTier.FAST

        if context_window >= 100000:
            return ModelTier.LONG_CONTEXT

        return ModelTier.FRONTIER

    async def fetch_pricing(self, model_id: str) -> ModelPricing | None:
        """Ollama models are free (local)."""
        clean_id = model_id.replace("ollama/", "")

        citation = SourceCitation(
            source_type=SourceType.OFFICIAL_DOCS,
            url="https://ollama.com/",
            provider="ollama",
            accessed_at=datetime.now(UTC),
            field_mapping={"pricing": "free"},
            confidence=1.0,
            raw_snippet="Ollama models run locally - no API costs",
        )

        return ModelPricing(
            input_per_1m_tokens=0.0,
            output_per_1m_tokens=0.0,
            currency="USD",
            citation=citation,
            effective_date=datetime.now(UTC),
        )

    async def fetch_limits(self, model_id: str) -> ModelLimits | None:
        """Ollama local limits depend on hardware."""
        return ModelLimits(rpm=1000, tpm=1000000, rpd=100000)

    async def verify_model(self, model_id: str) -> ModelSpec | None:
        """Verify a specific model against Ollama."""
        clean_id = model_id.replace("ollama/", "").replace("-", ":")
        client = await self._get_client()

        try:
            response = await client.post("/api/show", json={"name": clean_id})
            if response.status_code == 404:
                return None

            response.raise_for_status()
            model_data = response.json()

            # Convert show response to tags format
            tags_format = {"models": [{"name": clean_id, "details": model_data}]}
            return await self._parse_model_spec(tags_format["models"][0])

        except Exception as e:
            logger.error("Failed to verify Ollama model %s: %s", model_id, e)
            return None


def create_ollama_adapter(base_url: str = OLLAMA_API_BASE) -> OllamaProviderAdapter:
    """Create Ollama adapter."""
    return OllamaProviderAdapter(base_url=base_url)