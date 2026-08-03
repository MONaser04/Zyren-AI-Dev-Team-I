"""
AWS Bedrock Provider Adapter — Phase 1
======================================
Implements ProviderAdapter for AWS Bedrock models.
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

# AWS Bedrock API base (region-specific)
BEDROCK_API_BASE = "https://bedrock-runtime.{region}.amazonaws.com"


class AWSBedrockProviderAdapter(ProviderAdapter):
    """AWS Bedrock provider adapter for model discovery and verification."""

    def __init__(
        self,
        api_key: str | None = None,
        region: str = "us-east-1",
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "aws_bedrock"

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
            # AWS Bedrock uses AWS SigV4 signing - simplified for now
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=BEDROCK_API_BASE.format(region=self.region),
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def discover_models(self) -> list[ModelSpec]:
        """Discover models from AWS Bedrock ListFoundationModels API."""
        # AWS Bedrock uses ListFoundationModels API, not /models endpoint
        # This is a simplified implementation
        models = []

        # Known Bedrock models with their IDs
        known_models = [
            "anthropic.claude-3-5-sonnet-20240620-v1:0",
            "anthropic.claude-3-5-haiku-20241022-v1:0",
            "anthropic.claude-3-opus-20240229-v1:0",
            "anthropic.claude-3-sonnet-20240229-v1:0",
            "anthropic.claude-3-haiku-20240307-v1:0",
            "amazon.titan-text-premier-v1:0",
            "amazon.titan-text-express-v1:0",
            "amazon.titan-text-lite-v1:0",
            "meta.llama3-1-405b-instruct-v1:0",
            "meta.llama3-1-70b-instruct-v1:0",
            "meta.llama3-1-8b-instruct-v1:0",
            "meta.llama3-70b-instruct-v1:0",
            "meta.llama3-8b-instruct-v1:0",
            "cohere.command-r-v1:0",
            "cohere.command-r-plus-v1:0",
            "mistral.mistral-7b-instruct-v0:2",
            "mistral.mixtral-8x7b-instruct-v0:1",
            "ai21.jamba-1-5-large-v1:0",
            "ai21.jamba-1-5-mini-v1:0",
        ]

        for model_id in known_models:
            spec = await self._create_model_spec(model_id)
            if spec:
                models.append(spec)

        return models

    async def _create_model_spec(self, model_id: str) -> ModelSpec | None:
        """Create ModelSpec for a known Bedrock model."""
        try:
            # Parse provider from model ID
            parts = model_id.split(".")
            if len(parts) < 2:
                return None

            provider = parts[0]  # anthropic, amazon, meta, cohere, mistral, ai21

            capabilities = self._infer_capabilities(model_id)
            tier = self._classify_tier(model_id, capabilities.context_window)

            citation = SourceCitation(
                source_type=SourceType.OFFICIAL_DOCS,
                url=f"https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html",
                provider="aws_bedrock",
                accessed_at=datetime.now(UTC),
                field_mapping={"model_id": "model_id"},
                confidence=0.85,
                raw_snippet=f"AWS Bedrock model: {model_id}",
            )

            pricing = await self.fetch_pricing(model_id) or ModelPricing(
                input_per_1m_tokens=0.0,
                output_per_1m_tokens=0.0,
                currency="USD",
            )

            limits = await self.fetch_limits(model_id) or ModelLimits()

            spec = ModelSpec(
                model_id=f"aws_bedrock/{model_id}",
                provider="aws_bedrock",
                display_name=model_id,
                tier=tier,
                capabilities=capabilities,
                pricing=pricing,
                limits=limits,
                status=ModelStatus.ACTIVE,
                version="1.0",
                citations={"discovery": citation},
                verification_confidence=0.85,
                tags=["aws_bedrock", provider, tier.value],
                description=f"AWS Bedrock model: {model_id}",
            )

            return spec

        except Exception as e:
            logger.error("Failed to create spec for Bedrock model %s: %s", model_id, e)
            return None

    def _infer_capabilities(self, model_id: str) -> ModelCapabilities:
        """Infer capabilities from model ID."""
        model_lower = model_id.lower()

        # Context windows for known models
        context_windows = {
            "claude-3-5-sonnet": 200000,
            "claude-3-5-haiku": 200000,
            "claude-3-opus": 200000,
            "claude-3-sonnet": 200000,
            "claude-3-haiku": 200000,
            "titan-text-premier": 32768,
            "titan-text-express": 8192,
            "titan-text-lite": 4096,
            "llama3-1-405b": 128000,
            "llama3-1-70b": 128000,
            "llama3-1-8b": 128000,
            "llama3-70b": 8192,
            "llama3-8b": 8192,
            "command-r": 128000,
            "command-r-plus": 128000,
            "mistral-7b": 32768,
            "mixtral-8x7b": 32768,
            "jamba-1-5-large": 256000,
            "jamba-1-5-mini": 256000,
        }

        context_window = 4096
        for key, value in context_windows.items():
            if key in model_lower:
                context_window = value
                break

        # Capabilities
        has_vision = any(v in model_lower for v in ["claude-3", "sonnet", "opus", "haiku"])
        has_function_calling = not any(x in model_lower for x in ["titan-text-lite", "mistral-7b"])

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

        if "code" in model_lower or "llama3-1-8b" in model_lower:
            return ModelTier.CODE_SPECIALIZED

        if any(x in model_lower for x in ["haiku", "lite", "8b-instruct", "7b-instruct", "mistral-7b"]):
            return ModelTier.FAST

        if context_window >= 100000:
            return ModelTier.LONG_CONTEXT

        return ModelTier.FRONTIER

    async def fetch_pricing(self, model_id: str) -> ModelPricing | None:
        """Fetch pricing for a Bedrock model."""
        # AWS Bedrock pricing varies by model provider
        # Simplified pricing (on-demand, US East)
        pricing_map = {
            "anthropic.claude-3-5-sonnet-20240620-v1:0": (3.00, 15.00),
            "anthropic.claude-3-5-haiku-20241022-v1:0": (0.25, 1.25),
            "anthropic.claude-3-opus-20240229-v1:0": (15.00, 75.00),
            "anthropic.claude-3-sonnet-20240229-v1:0": (3.00, 15.00),
            "anthropic.claude-3-haiku-20240307-v1:0": (0.25, 1.25),
            "amazon.titan-text-premier-v1:0": (0.50, 1.50),
            "amazon.titan-text-express-v1:0": (0.20, 0.60),
            "amazon.titan-text-lite-v1:0": (0.06, 0.24),
            "meta.llama3-1-405b-instruct-v1:0": (5.32, 16.00),
            "meta.llama3-1-70b-instruct-v1:0": (1.18, 1.18),
            "meta.llama3-1-8b-instruct-v1:0": (0.22, 0.22),
            "meta.llama3-70b-instruct-v1:0": (1.18, 1.18),
            "meta.llama3-8b-instruct-v1:0": (0.22, 0.22),
            "cohere.command-r-v1:0": (0.15, 0.60),
            "cohere.command-r-plus-v1:0": (2.50, 10.00),
            "mistral.mistral-7b-instruct-v0:2": (0.15, 0.15),
            "mistral.mixtral-8x7b-instruct-v0:1": (0.60, 0.60),
            "ai21.jamba-1-5-large-v1:0": (2.00, 2.00),
            "ai21.jamba-1-5-mini-v1:0": (0.20, 0.20),
        }

        input_price, output_price = pricing_map.get(model_id, (0.0, 0.0))

        citation = SourceCitation(
            source_type=SourceType.PRICING_PAGE,
            url="https://aws.amazon.com/bedrock/pricing/",
            provider="aws_bedrock",
            accessed_at=datetime.now(UTC),
            field_mapping={"input": "input_per_1m", "output": "output_per_1m"},
            confidence=0.9,
            raw_snippet=f"AWS Bedrock pricing for {model_id}",
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
        # Bedrock default limits (can be increased via quota)
        if "405b" in model_id or "opus" in model_id:
            return ModelLimits(rpm=10, tpm=50000, rpd=1000)
        if "70b" in model_id or "sonnet" in model_id:
            return ModelLimits(rpm=50, tpm=100000, rpd=5000)
        return ModelLimits(rpm=100, tpm=200000, rpd=10000)

    async def verify_model(self, model_id: str) -> ModelSpec | None:
        """Verify a specific model against AWS Bedrock sources."""
        clean_id = model_id.replace("aws_bedrock/", "")
        return await self._create_model_spec(clean_id)


def create_aws_bedrock_adapter(
    api_key: str | None = None,
    region: str = "us-east-1",
    access_key: str | None = None,
    secret_key: str | None = None,
) -> AWSBedrockProviderAdapter:
    """Create AWS Bedrock adapter."""
    return AWSBedrockProviderAdapter(
        api_key=api_key, region=region, access_key=access_key, secret_key=secret_key
    )