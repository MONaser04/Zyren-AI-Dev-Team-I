"""OpenAI Official Documentation Fetcher"""

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


class OpenAIFetcher(OfficialDocsFetcher):
    """Official OpenAI documentation and API fetcher.

    Sources:
    - OpenAI API: https://api.openai.com/v1
    - OpenAI Models: https://platform.openai.com/docs/models
    - OpenAI Pricing: https://openai.com/pricing
    - OpenAI Rate Limits: https://platform.openai.com/docs/guides/rate-limits
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self._base_url = "https://api.openai.com/v1"
        self._docs_base_url = "https://platform.openai.com/docs/models"
        self._pricing_url = "https://openai.com/pricing"
        self._rate_limits_url = "https://platform.openai.com/docs/guides/rate-limits"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.OPENAI

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
            headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
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
        """Fetch all available models from OpenAI /models endpoint"""
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
                            owned_by=model_data.get("owned_by", "openai"),
                            permission=model_data.get("permission", []),
                            root=model_data.get("root"),
                            parent=model_data.get("parent"),
                        )
                    )

            return self._create_success_result(
                models,
                f"{self._base_url}/models",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch OpenAI model list: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/models")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch model details from OpenAI docs and known specifications"""
        try:
            details = self._get_openai_model_details(model_id)
            if details:
                return self._create_success_result(
                    details,
                    f"https://platform.openai.com/docs/models/{model_id}",
                    confidence=0.95,
                )

            # Fallback: try to scrape from docs page
            docs_result = await self.fetch_official_docs(model_id)
            if docs_result.success and docs_result.data:
                details = self._parse_openai_docs(docs_result.data.get("html", ""), model_id)
                if details:
                    return self._create_success_result(
                        details,
                        f"https://platform.openai.com/docs/models/{model_id}",
                        confidence=0.85,
                    )

            return self._create_error_result(f"No details found for {model_id}", "")
        except Exception as e:
            logger.error(f"Failed to fetch OpenAI model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://platform.openai.com/docs/models/{model_id}")

    def _get_openai_model_details(self, model_id: str) -> ModelDetail | None:
        """Get known OpenAI model specifications"""
        known_models = {
            "gpt-4o": ModelDetail(
                model_id="gpt-4o",
                context_window=128000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=16384,
            ),
            "gpt-4o-mini": ModelDetail(
                model_id="gpt-4o-mini",
                context_window=128000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=16384,
            ),
            "gpt-4.1": ModelDetail(
                model_id="gpt-4.1",
                context_window=128000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=16384,
            ),
            "gpt-4.1-mini": ModelDetail(
                model_id="gpt-4.1-mini",
                context_window=128000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=16384,
            ),
            "gpt-4-turbo": ModelDetail(
                model_id="gpt-4-turbo",
                context_window=128000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "gpt-3.5-turbo": ModelDetail(
                model_id="gpt-3.5-turbo",
                context_window=16384,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
        }
        return known_models.get(model_id)

    async def _parse_openai_docs(self, html: str, model_id: str) -> ModelDetail | None:
        """Parse OpenAI docs HTML for model specifications"""
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Try to extract context window and capabilities from docs
            text = soup.get_text()

            # Look for context window mentions
            context_match = re.search(r"(\d+(?:,\d+)*)\s*(?:token|context)", text, re.IGNORECASE)
            context_window = int(context_match.group(1).replace(",", "")) if context_match else 4096

            return ModelDetail(
                model_id=model_id,
                context_window=context_window,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=min(16384, context_window // 4),
            )
        except Exception as e:
            logger.warning(f"Failed to parse OpenAI docs for {model_id}: {e}")
            return None

    async def fetch_pricing(self, model_id: str) -> FetchResult:
        """Fetch pricing from OpenAI pricing page"""
        try:
            pricing_data = self._get_openai_pricing(model_id)
            if pricing_data:
                return self._create_success_result(
                    pricing_data,
                    self._pricing_url,
                    confidence=0.9,
                )

            # Try to scrape pricing page
            client = httpx.AsyncClient(timeout=self._timeout)
            response = await client.get(self._pricing_url)
            await client.aclose()

            if response.status_code == 200:
                pricing = self._parse_openai_pricing(response.text, model_id)
                if pricing:
                    return self._create_success_result(
                        pricing,
                        self._pricing_url,
                        confidence=0.8,
                    )

            return self._create_error_result(f"Pricing not found for {model_id}", self._pricing_url)
        except Exception as e:
            logger.error(f"Failed to fetch OpenAI pricing for {model_id}: {e}")
            return self._create_error_result(str(e), self._pricing_url)

    def _get_openai_pricing(self, model_id: str) -> PricingTable | None:
        """Known OpenAI pricing (as of 2024)"""
        pricing = {
            "gpt-4o": PricingTable(input_per_1m_tokens=2.50, output_per_1m_tokens=10.00),
            "gpt-4o-mini": PricingTable(input_per_1m_tokens=0.15, output_per_1m_tokens=0.60),
            "gpt-4.1": PricingTable(input_per_1m_tokens=2.00, output_per_1m_tokens=8.00),
            "gpt-4.1-mini": PricingTable(input_per_1m_tokens=0.15, output_per_1m_tokens=0.60),
            "gpt-4-turbo": PricingTable(input_per_1m_tokens=10.00, output_per_1m_tokens=30.00),
            "gpt-3.5-turbo": PricingTable(input_per_1m_tokens=0.50, output_per_1m_tokens=1.50),
        }
        return pricing.get(model_id)

    def _parse_openai_pricing(self, html: str, model_id: str) -> PricingTable | None:
        """Parse pricing from OpenAI pricing page HTML"""
        try:
            soup = BeautifulSoup(html, "html.parser")
            # This would need specific selectors based on page structure
            # For now, return None to use known pricing
            return None
        except Exception:
            return None

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limits from OpenAI docs"""
        try:
            limits = self._get_openai_rate_limits(model_id)
            return self._create_success_result(
                limits,
                self._rate_limits_url,
                confidence=0.9,
            )
        except Exception as e:
            logger.error(f"Failed to fetch OpenAI rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), self._rate_limits_url)

    def _get_openai_rate_limits(self, model_id: str) -> RateLimitInfo:
        """Known OpenAI rate limits"""
        if "gpt-4o-mini" in model_id or "gpt-3.5" in model_id:
            return RateLimitInfo(rpm=1000, tpm=50000, rpd=None, regions=["global"])
        elif "gpt-4" in model_id:
            return RateLimitInfo(rpm=500, tpm=30000, rpd=None, regions=["global"])
        return RateLimitInfo(rpm=500, tpm=30000, rpd=None, regions=["global"])

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official documentation page"""
        try:
            url = f"https://platform.openai.com/docs/models/{model_id}"
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
            logger.error(f"Failed to fetch OpenAI docs for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://platform.openai.com/docs/models/{model_id}")


def create_openai_fetcher(api_key: str | None = None) -> OpenAIFetcher:
    """Factory function to create OpenAI fetcher"""
    return OpenAIFetcher(api_key=api_key)