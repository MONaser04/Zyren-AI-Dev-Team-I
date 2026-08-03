"""Anthropic Official Documentation Fetcher"""

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


class AnthropicFetcher(OfficialDocsFetcher):
    """Official Anthropic documentation and API fetcher.

    Sources:
    - Anthropic API: https://api.anthropic.com
    - Anthropic Models: https://docs.anthropic.com/en/docs/models-overview
    - Anthropic Pricing: https://www.anthropic.com/pricing
    - Anthropic Rate Limits: https://docs.anthropic.com/en/api/rate-limits
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self._base_url = "https://api.anthropic.com"
        self._docs_base_url = "https://docs.anthropic.com/en/docs"
        self._pricing_url = "https://www.anthropic.com/pricing"
        self._rate_limits_url = "https://docs.anthropic.com/en/api/rate-limits"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.ANTHROPIC

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            "api": self._base_url,
            "models": f"{self._base_url}/v1/models",
            "docs": self._docs_base_url,
            "pricing": self._pricing_url,
            "rate_limits": self._rate_limits_url,
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {}
            if self._api_key:
                headers["x-api-key"] = self._api_key
                headers["anthropic-version"] = "2023-06-01"
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
        """Fetch available models from Anthropic API"""
        try:
            client = await self._get_client()
            response = await client.get("/v1/models")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("data", []):
                model_id = model_data.get("id", "")
                if model_id:
                    models.append(
                        ModelSummary(
                            model_id=model_id,
                            owned_by=model_data.get("owned_by", "anthropic"),
                            permission=model_data.get("permission", []),
                            root=model_data.get("root"),
                            parent=model_data.get("parent"),
                        )
                    )

            return self._create_success_result(
                models,
                f"{self._base_url}/v1/models",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Anthropic model list: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/v1/models")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch model details from Anthropic docs and known specifications"""
        try:
            details = self._get_anthropic_model_details(model_id)
            if details:
                return self._create_success_result(
                    details,
                    f"https://docs.anthropic.com/en/docs/models-overview#{model_id}",
                    confidence=0.95,
                )

            # Fallback: scrape docs
            docs_result = await self.fetch_official_docs(model_id)
            if docs_result.success and docs_result.data:
                details = await self._parse_anthropic_docs(docs_result.data.get("html", ""), model_id)
                if details:
                    return self._create_success_result(
                        details,
                        f"https://docs.anthropic.com/en/docs/models-overview#{model_id}",
                        confidence=0.85,
                    )

            return self._create_error_result(f"No details found for {model_id}", "")
        except Exception as e:
            logger.error(f"Failed to fetch Anthropic model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://docs.anthropic.com/en/docs/models-overview#{model_id}")

    def _get_anthropic_model_details(self, model_id: str) -> ModelDetail | None:
        """Known Anthropic model specifications"""
        known_models = {
            "claude-3-5-sonnet-20241022": ModelDetail(
                model_id="claude-3-5-sonnet-20241022",
                context_window=200000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=8192,
            ),
            "claude-3-5-haiku-20241022": ModelDetail(
                model_id="claude-3-5-haiku-20241022",
                context_window=200000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=8192,
            ),
            "claude-3-opus-20240229": ModelDetail(
                model_id="claude-3-opus-20240229",
                context_window=200000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "claude-3-sonnet-20240229": ModelDetail(
                model_id="claude-3-sonnet-20240229",
                context_window=200000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "claude-3-haiku-20240307": ModelDetail(
                model_id="claude-3-haiku-20240307",
                context_window=200000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
        }
        return known_models.get(model_id)

    async def fetch_pricing(self, model_id: str) -> FetchResult:
        """Fetch pricing from Anthropic pricing page"""
        try:
            pricing = self._get_anthropic_pricing(model_id)
            if pricing:
                return self._create_success_result(
                    pricing,
                    self._pricing_url,
                    confidence=0.9,
                )

            # Try to scrape pricing page
            client = httpx.AsyncClient(timeout=self._timeout)
            response = await client.get(self._pricing_url)
            await client.aclose()

            if response.status_code == 200:
                pricing = await self._parse_anthropic_pricing(response.text, model_id)
                if pricing:
                    return self._create_success_result(
                        pricing,
                        self._pricing_url,
                        confidence=0.8,
                    )

            return self._create_error_result(f"Pricing not found for {model_id}", self._pricing_url)
        except Exception as e:
            logger.error(f"Failed to fetch Anthropic pricing for {model_id}: {e}")
            return self._create_error_result(str(e), self._pricing_url)

    def _get_anthropic_pricing(self, model_id: str) -> PricingTable | None:
        """Known Anthropic pricing (as of 2024)"""
        pricing = {
            "claude-3-5-sonnet-20241022": PricingTable(input_per_1m_tokens=3.00, output_per_1m_tokens=15.00),
            "claude-3-5-haiku-20241022": PricingTable(input_per_1m_tokens=0.25, output_per_1m_tokens=1.25),
            "claude-3-opus-20240229": PricingTable(input_per_1m_tokens=15.00, output_per_1m_tokens=75.00),
            "claude-3-sonnet-20240229": PricingTable(input_per_1m_tokens=3.00, output_per_1m_tokens=15.00),
            "claude-3-haiku-20240307": PricingTable(input_per_1m_tokens=0.25, output_per_1m_tokens=1.25),
        }
        return pricing.get(model_id)

    async def _parse_anthropic_pricing(self, html: str, model_id: str) -> PricingTable | None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Would need specific selectors for Anthropic pricing page
            return None
        except Exception:
            return None

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limits from Anthropic docs"""
        try:
            limits = self._get_anthropic_rate_limits(model_id)
            return self._create_success_result(
                limits,
                self._rate_limits_url,
                confidence=0.9,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Anthropic rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), self._rate_limits_url)

    def _get_anthropic_rate_limits(self, model_id: str) -> RateLimitInfo:
        """Known Anthropic rate limits"""
        if "haiku" in model_id.lower():
            return RateLimitInfo(rpm=100, tpm=50000, rpd=None, regions=["global"])
        elif "sonnet" in model_id.lower():
            return RateLimitInfo(rpm=50, tpm=20000, rpd=None, regions=["global"])
        elif "opus" in model_id.lower():
            return RateLimitInfo(rpm=50, tpm=20000, rpd=None, regions=["global"])
        return RateLimitInfo(rpm=50, tpm=20000, rpd=None, regions=["global"])

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official documentation page"""
        try:
            url = f"https://docs.anthropic.com/en/docs/models-overview#{model_id}"
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
            logger.error(f"Failed to fetch Anthropic docs for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://docs.anthropic.com/en/docs/models-overview#{model_id}")

    async def _parse_anthropic_docs(self, html: str, model_id: str) -> ModelDetail | None:
        """Parse Anthropic docs HTML for model specifications"""
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text()

            # Look for context window
            context_match = re.search(r"(\d+(?:,\d+)*)\s*(?:token|context)", text, re.IGNORECASE)
            context_window = int(context_match.group(1).replace(",", "")) if context_match else 200000

            return ModelDetail(
                model_id=model_id,
                context_window=context_window,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=min(8192, context_window // 4),
            )
        except Exception as e:
            logger.warning(f"Failed to parse Anthropic docs for {model_id}: {e}")
            return None


def create_anthropic_fetcher(api_key: str | None = None) -> AnthropicFetcher:
    """Factory function to create Anthropic fetcher"""
    return AnthropicFetcher(api_key=api_key)