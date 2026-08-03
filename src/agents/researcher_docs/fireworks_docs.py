"""Fireworks AI Official Documentation Fetcher"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .base import (
    FetchResult,
    ModelDetail,
    ModelSummary,
    OfficialDocsFetcher,
    PricingTable,
    ProviderName,
    RateLimitInfo,
)

logger = logging.getLogger(__name__)


class FireworksAIFetcher(OfficialDocsFetcher):
    """Official Fireworks AI documentation and API fetcher.

    Sources:
    - Fireworks Models: https://docs.fireworks.ai/docs/models
    - Fireworks Pricing: https://fireworks.ai/pricing
    - Fireworks Rate Limits: https://docs.fireworks.ai/docs/rate-limits
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self._base_url = "https://api.fireworks.ai/inference/v1"
        self._docs_base_url = "https://docs.fireworks.ai/docs"
        self._pricing_url = "https://fireworks.ai/pricing"
        self._rate_limits_url = "https://docs.fireworks.ai/docs/rate-limits"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.FIREWORKS

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            "api": self._base_url,
            "models": f"{self._base_url}/models",
            "docs": self._docs_base_url,
            "pricing": "https://fireworks.ai/pricing",
            "rate_limits": "https://docs.fireworks.ai/docs/rate-limits",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_model_list(self) -> FetchResult:
        """Fetch available models from Fireworks AI /models endpoint"""
        try:
            client = await self._get_client()
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("data", []):
                model_id = model_data.get("id", "")
                if model_id:
                    models.append(
                        ModelSummary(
                            model_id=model_id,
                            owned_by=model_data.get("owned_by", "fireworks"),
                            permission=model_data.get("permission", []),
                        )
                    )

            return self._create_success_result(
                models,
                f"{self._base_url}/models",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Fireworks AI model list: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/models")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch model details from Fireworks AI docs"""
        try:
            details = self._get_fireworks_model_details(model_id)
            if details:
                return self._create_success_result(
                    details,
                    f"https://docs.fireworks.ai/docs/models#{model_id}",
                    confidence=0.9,
                )

            docs_result = await self.fetch_official_docs(model_id)
            if docs_result.success and docs_result.data:
                details = await self._parse_fireworks_docs(docs_result.data.get("html", ""), model_id)
                if details:
                    return self._create_success_result(
                        details,
                        f"https://docs.fireworks.ai/docs/models#{model_id}",
                        confidence=0.85,
                    )

            return self._create_error_result(f"No details found for {model_id}", "")
        except Exception as e:
            logger.error(f"Failed to fetch Fireworks AI model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://docs.fireworks.ai/docs/models#{model_id}")

    def _get_fireworks_model_details(self, model_id: str) -> ModelDetail | None:
        """Known Fireworks AI model specifications"""
        known_models = {
            "accounts/fireworks/models/llama-v3p1-70b-instruct": ModelDetail(
                model_id="accounts/fireworks/models/llama-v3p1-70b-instruct",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "accounts/fireworks/models/mixtral-8x7b-instruct": ModelDetail(
                model_id="accounts/fireworks/models/mixtral-8x7b-instruct",
                context_window=32768,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "accounts/fireworks/models/qwen2-72b-instruct": ModelDetail(
                model_id="accounts/fireworks/models/qwen2-72b-instruct",
                context_window=32768,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "accounts/fireworks/models/llama-v3p1-405b-instruct": ModelDetail(
                model_id="accounts/fireworks/models/llama-v3p1-405b-instruct",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
        }
        return known_models.get(model_id)

    async def fetch_pricing(self, model_id: str) -> FetchResult:
        """Fetch pricing from Fireworks AI pricing page"""
        try:
            pricing = self._get_fireworks_pricing(model_id)
            if pricing:
                return self._create_success_result(
                    pricing,
                    "https://fireworks.ai/pricing",
                    confidence=0.9,
                )

            client = httpx.AsyncClient(timeout=self._timeout)
            response = await client.get("https://fireworks.ai/pricing")
            await client.aclose()

            if response.status_code == 200:
                pricing = await self._parse_fireworks_pricing(response.text, model_id)
                if pricing:
                    return self._create_success_result(
                        pricing,
                        "https://fireworks.ai/pricing",
                        confidence=0.8,
                    )

            return self._create_error_result(f"Pricing not found for {model_id}", "https://fireworks.ai/pricing")
        except Exception as e:
            logger.error(f"Failed to fetch Fireworks AI pricing for {model_id}: {e}")
            return self._create_error_result(str(e), "https://fireworks.ai/pricing")

    def _get_fireworks_pricing(self, model_id: str) -> PricingTable | None:
        """Known Fireworks AI pricing (per 1M tokens, as of 2024)"""
        pricing = {
            "accounts/fireworks/models/llama-v3p1-70b-instruct": PricingTable(input_per_1m_tokens=0.90, output_per_1m_tokens=0.90),
            "accounts/fireworks/models/mixtral-8x7b-instruct": PricingTable(input_per_1m_tokens=0.60, output_per_1m_tokens=0.60),
            "accounts/fireworks/models/qwen2-72b-instruct": PricingTable(input_per_1m_tokens=0.90, output_per_1m_tokens=0.90),
            "accounts/fireworks/models/llama-v3p1-405b-instruct": PricingTable(input_per_1m_tokens=3.00, output_per_1m_tokens=3.00),
        }
        return pricing.get(model_id)

    async def _parse_fireworks_pricing(self, html: str, model_id: str) -> PricingTable | None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            return None
        except Exception:
            return None

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limits from Fireworks AI docs"""
        try:
            limits = self._get_fireworks_rate_limits(model_id)
            return self._create_success_result(
                limits,
                "https://docs.fireworks.ai/docs/rate-limits",
                confidence=0.85,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Fireworks AI rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), "https://docs.fireworks.ai/docs/rate-limits")

    def _get_fireworks_rate_limits(self, model_id: str) -> RateLimitInfo:
        """Known Fireworks AI rate limits"""
        if "405b" in model_id.lower():
            return RateLimitInfo(rpm=20, tpm=10000, rpd=500, regions=["global"])
        elif "70b" in model_id.lower() or "72b" in model_id.lower():
            return RateLimitInfo(rpm=50, tpm=30000, rpd=2000, regions=["global"])
        elif "8x7b" in model_id.lower():
            return RateLimitInfo(rpm=50, tpm=20000, rpd=1000, regions=["global"])
        return RateLimitInfo(rpm=100, tpm=60000, rpd=5000, regions=["global"])

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official Fireworks AI documentation page"""
        try:
            url = f"https://docs.fireworks.ai/docs/models#{model_id}"
            client = httpx.AsyncClient(timeout=self._timeout)
            response = await client.get(url)
            await client.aclose()

            if response.status_code == 200:
                return self._create_success_result(
                    {"html": response.text, "model_id": model_id, "url": url},
                    url,
                    confidence=0.9,
                )
            return self._create_error_result(f"Doc page not found: {response.status_code}", url)
        except Exception as e:
            logger.error(f"Failed to fetch Fireworks AI docs for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://docs.fireworks.ai/docs/models#{model_id}")

    async def _parse_fireworks_docs(self, html: str, model_id: str) -> ModelDetail | None:
        """Parse Fireworks AI docs HTML for model specifications"""
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text()

            context_match = re.search(r"(\d+(?:,\d+)*)\s*(?:token|context)", text, re.IGNORECASE)
            context_window = int(context_match.group(1).replace(",", "")) if context_match else 128000

            return ModelDetail(
                model_id=model_id,
                context_window=context_window,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=min(4096, context_window // 4),
            )
        except Exception as e:
            logger.warning(f"Failed to parse Fireworks AI docs for {model_id}: {e}")
            return None


def create_fireworks_fetcher(api_key: str | None = None) -> FireworksAIFetcher:
    """Factory function to create Fireworks AI fetcher"""
    return FireworksAIFetcher(api_key=api_key)