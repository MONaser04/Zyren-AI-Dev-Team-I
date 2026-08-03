"""Together AI Official Documentation Fetcher"""

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


class TogetherAIFetcher(OfficialDocsFetcher):
    """Official Together AI documentation and API fetcher.

    Sources:
    - Together Models: https://docs.together.ai/docs/inference-models
    - Together Pricing: https://www.together.ai/pricing
    - Together Rate Limits: https://docs.together.ai/docs/rate-limits
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self._base_url = "https://api.together.xyz/v1"
        self._docs_base_url = "https://docs.together.ai/docs"
        self._pricing_url = "https://www.together.ai/pricing"
        self._rate_limits_url = "https://docs.together.ai/docs/rate-limits"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.TOGETHER

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            "api": self._base_url,
            "models": f"{self._base_url}/models",
            "docs": self._docs_base_url,
            "pricing": self._pricing_url,
            "rate_limits": self._rate_limits_url,
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
        """Fetch available models from Together AI /models endpoint"""
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
                            owned_by=model_data.get("owned_by", "together"),
                            permission=model_data.get("permission", []),
                        )
                    )

            return self._create_success_result(
                models,
                f"{self._base_url}/models",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Together AI model list: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/models")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch model details from Together AI docs"""
        try:
            details = self._get_together_model_details(model_id)
            if details:
                return self._create_success_result(
                    details,
                    f"https://docs.together.ai/docs/inference-models#{model_id}",
                    confidence=0.9,
                )

            docs_result = await self.fetch_official_docs(model_id)
            if docs_result.success and docs_result.data:
                details = await self._parse_together_docs(docs_result.data.get("html", ""), model_id)
                if details:
                    return self._create_success_result(
                        details,
                        f"https://docs.together.ai/docs/inference-models#{model_id}",
                        confidence=0.85,
                    )

            return self._create_error_result(f"No details found for {model_id}", "")
        except Exception as e:
            logger.error(f"Failed to fetch Together AI model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://docs.together.ai/docs/inference-models#{model_id}")

    def _get_together_model_details(self, model_id: str) -> ModelDetail | None:
        """Known Together AI model specifications"""
        known_models = {
            "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo": ModelDetail(
                model_id="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": ModelDetail(
                model_id="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": ModelDetail(
                model_id="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
            "mistralai/Mixtral-8x7B-Instruct-v0.1": ModelDetail(
                model_id="mistralai/Mixtral-8x7B-Instruct-v0.1",
                context_window=32768,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "Qwen/Qwen2-72B-Instruct": ModelDetail(
                model_id="Qwen/Qwen2-72B-Instruct",
                context_window=32768,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
        }
        return known_models.get(model_id)

    async def fetch_pricing(self, model_id: str) -> FetchResult:
        """Fetch pricing from Together AI pricing page"""
        try:
            pricing = self._get_together_pricing(model_id)
            if pricing:
                return self._create_success_result(
                    pricing,
                    self._pricing_url,
                    confidence=0.9,
                )

            client = httpx.AsyncClient(timeout=self._timeout)
            response = await client.get(self._pricing_url)
            await client.aclose()

            if response.status_code == 200:
                pricing = await self._parse_together_pricing(response.text, model_id)
                if pricing:
                    return self._create_success_result(
                        pricing,
                        self._pricing_url,
                        confidence=0.8,
                    )

            return self._create_error_result(f"Pricing not found for {model_id}", self._pricing_url)
        except Exception as e:
            logger.error(f"Failed to fetch Together AI pricing for {model_id}: {e}")
            return self._create_error_result(str(e), self._pricing_url)

    def _get_together_pricing(self, model_id: str) -> PricingTable | None:
        """Known Together AI pricing (per 1M tokens, as of 2024)"""
        pricing = {
            "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo": PricingTable(input_per_1m_tokens=1.80, output_per_1m_tokens=1.80),
            "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": PricingTable(input_per_1m_tokens=0.90, output_per_1m_tokens=0.90),
            "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": PricingTable(input_per_1m_tokens=0.18, output_per_1m_tokens=0.18),
            "mistralai/Mixtral-8x7B-Instruct-v0.1": PricingTable(input_per_1m_tokens=0.60, output_per_1m_tokens=0.60),
            "Qwen/Qwen2-72B-Instruct": PricingTable(input_per_1m_tokens=0.90, output_per_1m_tokens=0.90),
        }
        return pricing.get(model_id)

    async def _parse_together_pricing(self, html: str, model_id: str) -> PricingTable | None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            return None
        except Exception:
            return None

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limits from Together AI docs"""
        try:
            limits = self._get_together_rate_limits(model_id)
            return self._create_success_result(
                limits,
                self._rate_limits_url,
                confidence=0.85,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Together AI rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), self._rate_limits_url)

    def _get_together_rate_limits(self, model_id: str) -> RateLimitInfo:
        """Known Together AI rate limits"""
        if "405B" in model_id:
            return RateLimitInfo(rpm=20, tpm=10000, rpd=500, regions=["global"])
        elif "70B" in model_id or "72B" in model_id:
            return RateLimitInfo(rpm=50, tpm=30000, rpd=2000, regions=["global"])
        elif "8B" in model_id or "8x7B" in model_id:
            return RateLimitInfo(rpm=100, tpm=60000, rpd=5000, regions=["global"])
        return RateLimitInfo(rpm=100, tpm=60000, rpd=5000, regions=["global"])

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official Together AI documentation page"""
        try:
            url = f"https://docs.together.ai/docs/inference-models#{model_id}"
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
            logger.error(f"Failed to fetch Together AI docs for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://docs.together.ai/docs/inference-models#{model_id}")

    async def _parse_together_docs(self, html: str, model_id: str) -> ModelDetail | None:
        """Parse Together AI docs HTML for model specifications"""
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
            logger.warning(f"Failed to parse Together AI docs for {model_id}: {e}")
            return None


def create_together_fetcher(api_key: str | None = None) -> TogetherAIFetcher:
    """Factory function to create Together AI fetcher"""
    return TogetherAIFetcher(api_key=api_key)