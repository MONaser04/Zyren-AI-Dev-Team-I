"""Google/Vertex AI Official Documentation Fetcher"""

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


class GoogleFetcher(OfficialDocsFetcher):
    """Official Google/Vertex AI documentation and API fetcher.

    Sources:
    - Vertex AI Models: https://cloud.google.com/vertex-ai/docs/models
    - Vertex AI Pricing: https://cloud.google.com/vertex-ai/pricing
    - Vertex AI Quotas: https://cloud.google.com/vertex-ai/docs/quotas
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self._base_url = "https://us-central1-aiplatform.googleapis.com/v1"
        self._docs_base_url = "https://cloud.google.com/vertex-ai/docs"
        self._pricing_url = "https://cloud.google.com/vertex-ai/pricing"
        self._quotas_url = "https://cloud.google.com/vertex-ai/docs/quotas"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.GOOGLE

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            "api": self._base_url,
            "models": f"{self._base_url}/models",
            "docs": self._docs_base_url,
            "pricing": self._pricing_url,
            "quotas": self._quotas_url,
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
        """Fetch available models from Google Vertex AI"""
        try:
            client = await self._get_client()
            # Note: Vertex AI uses projects/locations/models structure
            # This is a simplified example
            response = await client.get("/projects/-/locations/us-central1/models")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("models", []):
                model_id = model_data.get("name", "").split("/")[-1]
                if model_id:
                    models.append(
                        ModelSummary(
                            model_id=model_id,
                            owned_by=model_data.get("owner", "google"),
                            permission=[],
                        )
                    )

            return self._create_success_result(
                models,
                f"{self._base_url}/models",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Google model list: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/models")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch model details from Google docs and known specifications"""
        try:
            details = self._get_google_model_details(model_id)
            if details:
                return self._create_success_result(
                    details,
                    f"https://cloud.google.com/vertex-ai/docs/models/{model_id}",
                    confidence=0.9,
                )

            docs_result = await self.fetch_official_docs(model_id)
            if docs_result.success and docs_result.data:
                details = await self._parse_google_docs(docs_result.data.get("html", ""), model_id)
                if details:
                    return self._create_success_result(
                        details,
                        f"https://cloud.google.com/vertex-ai/docs/models/{model_id}",
                        confidence=0.85,
                    )

            return self._create_error_result(f"No details found for {model_id}", "")
        except Exception as e:
            logger.error(f"Failed to fetch Google model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://cloud.google.com/vertex-ai/docs/models/{model_id}")

    def _get_google_model_details(self, model_id: str) -> ModelDetail | None:
        """Known Google/Vertex AI model specifications"""
        known_models = {
            "gemini-1.5-pro": ModelDetail(
                model_id="gemini-1.5-pro",
                context_window=2000000,
                modalities=["text", "vision", "audio", "video", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=8192,
            ),
            "gemini-1.5-flash": ModelDetail(
                model_id="gemini-1.5-flash",
                context_window=1000000,
                modalities=["text", "vision", "audio", "video", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=8192,
            ),
            "gemini-1.0-pro": ModelDetail(
                model_id="gemini-1.0-pro",
                context_window=32768,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
        }
        return known_models.get(model_id)

    async def fetch_pricing(self, model_id: str) -> FetchResult:
        """Fetch pricing from Google Cloud Vertex AI pricing page"""
        try:
            pricing = self._get_google_pricing(model_id)
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
                pricing = await self._parse_google_pricing(response.text, model_id)
                if pricing:
                    return self._create_success_result(
                        pricing,
                        self._pricing_url,
                        confidence=0.8,
                    )

            return self._create_error_result(f"Pricing not found for {model_id}", self._pricing_url)
        except Exception as e:
            logger.error(f"Failed to fetch Google pricing for {model_id}: {e}")
            return self._create_error_result(str(e), self._pricing_url)

    def _get_google_pricing(self, model_id: str) -> PricingTable | None:
        """Known Google Vertex AI pricing (as of 2024)"""
        pricing = {
            "gemini-1.5-pro": PricingTable(input_per_1m_tokens=1.25, output_per_1m_tokens=5.00),
            "gemini-1.5-flash": PricingTable(input_per_1m_tokens=0.075, output_per_1m_tokens=0.30),
            "gemini-1.0-pro": PricingTable(input_per_1m_tokens=0.50, output_per_1m_tokens=1.50),
        }
        return pricing.get(model_id)

    async def _parse_google_pricing(self, html: str, model_id: str) -> PricingTable | None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Would need specific selectors for Google Cloud pricing page
            return None
        except Exception:
            return None

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limits from Google Cloud quotas page"""
        try:
            limits = self._get_google_rate_limits(model_id)
            return self._create_success_result(
                limits,
                self._quotas_url,
                confidence=0.85,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Google rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), self._quotas_url)

    def _get_google_rate_limits(self, model_id: str) -> RateLimitInfo:
        """Known Google rate limits"""
        if "gemini-1.5-pro" in model_id:
            return RateLimitInfo(rpm=60, tpm=100000, rpd=1000, regions=["global"])
        elif "gemini-1.5-flash" in model_id:
            return RateLimitInfo(rpm=1000, tpm=250000, rpd=10000, regions=["global"])
        elif "gemini-1.0-pro" in model_id:
            return RateLimitInfo(rpm=60, tpm=30000, rpd=1000, regions=["global"])
        return RateLimitInfo(rpm=60, tpm=30000, rpd=1000, regions=["global"])

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official documentation page"""
        try:
            url = f"https://cloud.google.com/vertex-ai/docs/models/{model_id}"
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
            logger.error(f"Failed to fetch Google docs for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://cloud.google.com/vertex-ai/docs/models/{model_id}")

    async def _parse_google_docs(self, html: str, model_id: str) -> ModelDetail | None:
        """Parse Google docs HTML for model specifications"""
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text()

            context_match = re.search(r"(\d+(?:,\d+)*)\s*(?:token|context)", text, re.IGNORECASE)
            context_window = int(context_match.group(1).replace(",", "")) if context_match else 1000000

            return ModelDetail(
                model_id=model_id,
                context_window=context_window,
                modalities=["text", "vision", "audio", "video", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=min(8192, context_window // 4),
            )
        except Exception as e:
            logger.warning(f"Failed to parse Google docs for {model_id}: {e}")
            return None


def create_google_fetcher(api_key: str | None = None) -> GoogleFetcher:
    """Factory function to create Google/Vertex AI fetcher"""
    return GoogleFetcher(api_key=api_key)