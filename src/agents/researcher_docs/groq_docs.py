"""Groq Official Documentation Fetcher"""

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


class GroqFetcher(OfficialDocsFetcher):
    """Official Groq documentation and API fetcher.

    Sources:
    - Groq Models: https://console.groq.com/docs/models
    - Groq Pricing: https://groq.com/pricing/
    - Groq Rate Limits: https://console.groq.com/docs/rate-limits
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self._base_url = "https://api.groq.com/openai/v1"
        self._docs_base_url = "https://console.groq.com/docs"
        self._pricing_url = "https://groq.com/pricing/"
        self._rate_limits_url = "https://console.groq.com/docs/rate-limits"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.GROQ

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            "api": self._base_url,
            "models": f"{self._base_url}/models",
            "docs": self._docs_base_url,
            "pricing": "https://groq.com/pricing/",
            "rate_limits": "https://console.groq.com/docs/rate-limits",
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
        """Fetch available models from Groq /models endpoint"""
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
                            owned_by=model_data.get("owned_by", "groq"),
                            permission=model_data.get("permission", []),
                        )
                    )

            return self._create_success_result(
                models,
                f"{self._base_url}/models",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Groq model list: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/models")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch model details from Groq docs"""
        try:
            details = self._get_groq_model_details(model_id)
            if details:
                return self._create_success_result(
                    details,
                    f"https://console.groq.com/docs/models#{model_id}",
                    confidence=0.9,
                )

            docs_result = await self.fetch_official_docs(model_id)
            if docs_result.success and docs_result.data:
                details = await self._parse_groq_docs(docs_result.data.get("html", ""), model_id)
                if details:
                    return self._create_success_result(
                        details,
                        f"https://console.groq.com/docs/models#{model_id}",
                        confidence=0.85,
                    )

            return self._create_error_result(f"No details found for {model_id}", "")
        except Exception as e:
            logger.error(f"Failed to fetch Groq model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://console.groq.com/docs/models#{model_id}")

    def _get_groq_model_details(self, model_id: str) -> ModelDetail | None:
        """Known Groq model specifications"""
        known_models = {
            "llama-3.1-405b-reasoning": ModelDetail(
                model_id="llama-3.1-405b-reasoning",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "llama-3.1-70b-versatile": ModelDetail(
                model_id="llama-3.1-70b-versatile",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "llama-3.1-8b-instant": ModelDetail(
                model_id="llama-3.1-8b-instant",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
            "llama3-70b-8192": ModelDetail(
                model_id="llama3-70b-8192",
                context_window=8192,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "llama3-8b-8192": ModelDetail(
                model_id="llama3-8b-8192",
                context_window=8192,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
            "mixtral-8x7b-32768": ModelDetail(
                model_id="mixtral-8x7b-32768",
                context_window=32768,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "gemma2-9b-it": ModelDetail(
                model_id="gemma2-9b-it",
                context_window=8192,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
        }
        return known_models.get(model_id)

    async def fetch_pricing(self, model_id: str) -> FetchResult:
        """Groq models have free tier + paid plans"""
        try:
            pricing = self._get_groq_pricing(model_id)
            if pricing:
                return self._create_success_result(
                    pricing,
                    "https://groq.com/pricing/",
                    confidence=0.9,
                )

            client = httpx.AsyncClient(timeout=self._timeout)
            response = await client.get("https://groq.com/pricing/")
            await client.aclose()

            if response.status_code == 200:
                pricing = await self._parse_groq_pricing(response.text, model_id)
                if pricing:
                    return self._create_success_result(
                        pricing,
                        "https://groq.com/pricing/",
                        confidence=0.8,
                    )

            return self._create_error_result(f"Pricing not found for {model_id}", "https://groq.com/pricing/")
        except Exception as e:
            logger.error(f"Failed to fetch Groq pricing for {model_id}: {e}")
            return self._create_error_result(str(e), "https://groq.com/pricing/")

    def _get_groq_pricing(self, model_id: str) -> PricingTable | None:
        """Known Groq pricing (per 1M tokens, as of 2024)"""
        pricing = {
            "llama-3.1-405b-reasoning": PricingTable(input_per_1m_tokens=2.50, output_per_1m_tokens=2.50),
            "llama-3.1-70b-versatile": PricingTable(input_per_1m_tokens=0.89, output_per_1m_tokens=0.89),
            "llama-3.1-8b-instant": PricingTable(input_per_1m_tokens=0.05, output_per_1m_tokens=0.05),
            "llama3-70b-8192": PricingTable(input_per_1m_tokens=0.59, output_per_1m_tokens=0.79),
            "llama3-8b-8192": PricingTable(input_per_1m_tokens=0.05, output_per_1m_tokens=0.08),
            "mixtral-8x7b-32768": PricingTable(input_per_1m_tokens=0.27, output_per_1m_tokens=0.27),
            "gemma2-9b-it": PricingTable(input_per_1m_tokens=0.05, output_per_1m_tokens=0.08),
        }
        return pricing.get(model_id)

    async def _parse_groq_pricing(self, html: str, model_id: str) -> PricingTable | None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            return None
        except Exception:
            return None

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limits from Groq docs"""
        try:
            limits = self._get_groq_rate_limits(model_id)
            return self._create_success_result(
                limits,
                "https://console.groq.com/docs/rate-limits",
                confidence=0.9,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Groq rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), "https://console.groq.com/docs/rate-limits")

    def _get_groq_rate_limits(self, model_id: str) -> RateLimitInfo:
        """Known Groq rate limits"""
        if "405b" in model_id.lower():
            return RateLimitInfo(rpm=20, tpm=10000, rpd=500, regions=["global"])
        elif "70b" in model_id.lower():
            return RateLimitInfo(rpm=30, tpm=6000, rpd=1000, regions=["global"])
        elif "8b" in model_id.lower():
            return RateLimitInfo(rpm=30, tpm=6000, rpd=2000, regions=["global"])
        return RateLimitInfo(rpm=30, tpm=6000, rpd=1000, regions=["global"])

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official Groq documentation page"""
        try:
            url = f"https://console.groq.com/docs/models#{model_id}"
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
            logger.error(f"Failed to fetch Groq docs for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://console.groq.com/docs/models#{model_id}")

    async def _parse_groq_docs(self, html: str, model_id: str) -> ModelDetail | None:
        """Parse Groq docs HTML for model specifications"""
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text()

            context_match = re.search(r"(\d+(?:,\d+)*)\s*(?:token|context)", text, re.IGNORECASE)
            context_window = int(context_match.group(1).replace(",", "")) if context_match else 8192

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
            logger.warning(f"Failed to parse Groq docs for {model_id}: {e}")
            return None


def create_groq_fetcher(api_key: str | None = None) -> GroqFetcher:
    """Factory function to create Groq fetcher"""
    return GroqFetcher(api_key=api_key)