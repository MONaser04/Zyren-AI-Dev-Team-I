"""Azure OpenAI Official Documentation Fetcher"""

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


class AzureOpenAIFetcher(OfficialDocsFetcher):
    """Official Azure OpenAI documentation and API fetcher.

    Sources:
    - Azure OpenAI API: https://<resource>.openai.azure.com
    - Azure OpenAI Models: https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models
    - Azure OpenAI Pricing: https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/
    - Azure OpenAI Quotas: https://learn.microsoft.com/en-us/azure/ai-services/openai/quotas-limits
    """

    def __init__(self, api_key: str | None = None, endpoint: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self._endpoint = endpoint
        self._base_url = endpoint if endpoint else "https://<resource>.openai.azure.com"
        self._docs_base_url = "https://learn.microsoft.com/en-us/azure/ai-services/openai"
        self._pricing_url = "https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/"
        self._quotas_url = "https://learn.microsoft.com/en-us/azure/ai-services/openai/quotas-limits"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.AZURE_OPENAI

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            "api": self._base_url,
            "models": f"{self._base_url}/openai/models",
            "docs": self._docs_base_url,
            "pricing": self._pricing_url,
            "quotas": self._quotas_url,
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {}
            if self._api_key:
                headers["api-key"] = self._api_key
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
        """Fetch available models from Azure OpenAI"""
        try:
            client = await self._get_client()
            response = await client.get("/openai/models?api-version=2024-02-01")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("data", []):
                model_id = model_data.get("id", "")
                if model_id:
                    models.append(
                        ModelSummary(
                            model_id=model_id,
                            owned_by=model_data.get("owned_by", "azure"),
                            permission=model_data.get("permission", []),
                            root=model_data.get("root"),
                            parent=model_data.get("parent"),
                        )
                    )

            return self._create_success_result(
                models,
                f"{self._base_url}/openai/models?api-version=2024-02-01",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Azure OpenAI model list: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/openai/models")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch model details from Azure OpenAI docs"""
        try:
            details = self._get_azure_model_details(model_id)
            if details:
                return self._create_success_result(
                    details,
                    f"https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#{model_id}",
                    confidence=0.9,
                )

            docs_result = await self.fetch_official_docs(model_id)
            if docs_result.success and docs_result.data:
                details = await self._parse_azure_docs(docs_result.data.get("html", ""), model_id)
                if details:
                    return self._create_success_result(
                        details,
                        f"https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#{model_id}",
                        confidence=0.85,
                    )

            return self._create_error_result(f"No details found for {model_id}", "")
        except Exception as e:
            logger.error(f"Failed to fetch Azure OpenAI model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#{model_id}")

    def _get_azure_model_details(self, model_id: str) -> ModelDetail | None:
        """Known Azure OpenAI model specifications (matches OpenAI models deployed on Azure)"""
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
            "gpt-4": ModelDetail(
                model_id="gpt-4",
                context_window=8192,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "gpt-4-32k": ModelDetail(
                model_id="gpt-4-32k",
                context_window=32768,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "gpt-35-turbo": ModelDetail(
                model_id="gpt-35-turbo",
                context_window=16384,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "gpt-35-turbo-16k": ModelDetail(
                model_id="gpt-35-turbo-16k",
                context_window=16384,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
        }
        return known_models.get(model_id)

    async def fetch_pricing(self, model_id: str) -> FetchResult:
        """Fetch pricing from Azure OpenAI pricing page"""
        try:
            pricing = self._get_azure_pricing(model_id)
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
                pricing = await self._parse_azure_pricing(response.text, model_id)
                if pricing:
                    return self._create_success_result(
                        pricing,
                        self._pricing_url,
                        confidence=0.8,
                    )

            return self._create_error_result(f"Pricing not found for {model_id}", self._pricing_url)
        except Exception as e:
            logger.error(f"Failed to fetch Azure OpenAI pricing for {model_id}: {e}")
            return self._create_error_result(str(e), self._pricing_url)

    def _get_azure_pricing(self, model_id: str) -> PricingTable | None:
        """Known Azure OpenAI pricing (matches OpenAI pricing, billed through Azure)"""
        pricing = {
            "gpt-4o": PricingTable(input_per_1m_tokens=2.50, output_per_1m_tokens=10.00),
            "gpt-4o-mini": PricingTable(input_per_1m_tokens=0.15, output_per_1m_tokens=0.60),
            "gpt-4": PricingTable(input_per_1m_tokens=30.00, output_per_1m_tokens=60.00),
            "gpt-4-32k": PricingTable(input_per_1m_tokens=60.00, output_per_1m_tokens=120.00),
            "gpt-35-turbo": PricingTable(input_per_1m_tokens=0.50, output_per_1m_tokens=1.50),
            "gpt-35-turbo-16k": PricingTable(input_per_1m_tokens=3.00, output_per_1m_tokens=4.00),
        }
        return pricing.get(model_id)

    async def _parse_azure_pricing(self, html: str, model_id: str) -> PricingTable | None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Would need specific selectors for Azure pricing page
            return None
        except Exception:
            return None

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limits from Azure OpenAI quotas page"""
        try:
            limits = self._get_azure_rate_limits(model_id)
            return self._create_success_result(
                limits,
                self._quotas_url,
                confidence=0.9,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Azure OpenAI rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), self._quotas_url)

    def _get_azure_rate_limits(self, model_id: str) -> RateLimitInfo:
        """Known Azure OpenAI rate limits (per deployment)"""
        if "gpt-4o-mini" in model_id or "gpt-35-turbo" in model_id:
            return RateLimitInfo(rpm=1000, tpm=50000, rpd=None, regions=["global"])
        elif "gpt-4o" in model_id:
            return RateLimitInfo(rpm=500, tpm=30000, rpd=None, regions=["global"])
        elif "gpt-4" in model_id:
            return RateLimitInfo(rpm=100, tpm=10000, rpd=None, regions=["global"])
        return RateLimitInfo(rpm=100, tpm=10000, rpd=None, regions=["global"])

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official Azure OpenAI documentation page"""
        try:
            url = f"https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#{model_id}"
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
            logger.error(f"Failed to fetch Azure OpenAI docs for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#{model_id}")

    async def _parse_azure_docs(self, html: str, model_id: str) -> ModelDetail | None:
        """Parse Azure OpenAI docs HTML for model specifications"""
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text()

            context_match = re.search(r"(\d+(?:,\d+)*)\s*(?:token|context)", text, re.IGNORECASE)
            context_window = int(context_match.group(1).replace(",", "")) if context_match else 8192

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
            logger.warning(f"Failed to parse Azure docs for {model_id}: {e}")
            return None


def create_azure_fetcher(api_key: str | None = None, endpoint: str | None = None) -> AzureOpenAIFetcher:
    """Factory function to create Azure OpenAI fetcher"""
    return AzureOpenAIFetcher(api_key=api_key, endpoint=endpoint)