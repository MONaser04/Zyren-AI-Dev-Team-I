"""NVIDIA NIM Official Documentation Fetcher"""

from __future__ import annotations

import logging
from typing import Any

import httpx

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


class NvidiaNimFetcher(OfficialDocsFetcher):
    """Official NVIDIA NIM documentation and API fetcher.

    Sources:
    - NVIDIA NIM API: https://integrate.api.nvidia.com/v1
    - NVIDIA NIM Models: https://build.nvidia.com
    - NVIDIA AI Enterprise: https://www.nvidia.com/en-us/ai-data-science/products/nim/
    """

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self._api_key = api_key
        self._base_url = "https://integrate.api.nvidia.com/v1"
        self._docs_base_url = "https://build.nvidia.com"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.NVIDIA_NIM

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            "api": self._base_url,
            "models": "https://integrate.api.nvidia.com/v1/models",
            "docs": self._docs_base_url,
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
        """Fetch all available models from NVIDIA NIM /models endpoint"""
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
                            owned_by=model_data.get("owned_by", "nvidia"),
                            permission=model_data.get("permission", []),
                            root=model_data.get("root"),
                            parent=model_data.get("parent"),
                        )
                    )

            return self._create_success_result(
                models,
                f"{self._base_url}/models",
                confidence=1.0,  # Direct API response
            )
        except Exception as e:
            logger.error(f"Failed to fetch NVIDIA NIM model list: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/models")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch detailed model capabilities from NVIDIA NIM API"""
        try:
            # NVIDIA NIM doesn't have per-model detail endpoint
            # Infer from model_id and general NVIDIA NIM capabilities
            details = self._infer_model_details(model_id)

            return self._create_success_result(
                details,
                f"{self._base_url}/models/{model_id}",
                confidence=0.85,  # Inferred, not directly from API
            )
        except Exception as e:
            logger.error(f"Failed to fetch NVIDIA NIM model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/models/{model_id}")

    async def fetch_pricing(self, model_id: str) -> FetchResult:
        """Fetch pricing for a model - NVIDIA NIM is typically free with NVIDIA AI Enterprise"""
        try:
            # NVIDIA NIM models are included with NVIDIA AI Enterprise license
            # Free for development/evaluation
            pricing = PricingTable(
                input_per_1m_tokens=0.0,
                output_per_1m_tokens=0.0,
                currency="USD",
                effective_date=None,
                notes="NVIDIA NIM models included with NVIDIA AI Enterprise license. Free for development.",
            )

            return self._create_success_result(
                pricing,
                "https://www.nvidia.com/en-us/ai-data-science/products/nim/",
                confidence=0.9,
            )
        except Exception as e:
            logger.error(f"Failed to fetch NVIDIA NIM pricing for {model_id}: {e}")
            return self._create_error_result(str(e), "https://www.nvidia.com/en-us/ai-data-science/products/nim/")

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limits - defaults based on NVIDIA NIM deployment"""
        try:
            limits = RateLimitInfo(
                rpm=60,
                tpm=100000,
                rpd=10000,
                regions=["global"],
            )

            return self._create_success_result(
                limits,
                "https://docs.nvidia.com/nim/",
                confidence=0.75,  # Estimated defaults
            )
        except Exception as e:
            logger.error(f"Failed to fetch NVIDIA NIM rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), "https://docs.nvidia.com/nim/")

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official documentation for a model"""
        try:
            docs_url = f"https://build.nvidia.com/{model_id}"
            return self._create_success_result(
                {"url": docs_url, "model_id": model_id},
                docs_url,
                confidence=0.8,
            )
        except Exception as e:
            logger.error(f"Failed to fetch NVIDIA NIM docs for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://build.nvidia.com/{model_id}")

    def _infer_model_details(self, model_id: str) -> ModelDetail:
        """Infer model capabilities from model_id patterns"""
        model_lower = model_id.lower()

        # Context window inference
        if "128k" in model_lower or "405b" in model_lower:
            context_window = 128000
        elif "32k" in model_lower or "70b" in model_lower:
            context_window = 32768
        elif "16k" in model_lower:
            context_window = 16384
        elif "phi" in model_lower or "mistral-7b" in model_lower:
            context_window = 4096
        else:
            context_window = 4096  # Default for most NVIDIA NIM models

        # Modality inference
        modalities = ["text"]
        if "vision" in model_lower or "fuyu" in model_lower or "llava" in model_lower:
            modalities.append("image")

        # Function calling - most modern NVIDIA NIM models support it
        function_calling = True
        excluded_from_fc = ["phi-3", "gemma-2-2b", "gemma-2-9b"]
        if any(ex in model_lower for ex in excluded_from_fc):
            function_calling = False

        return ModelDetail(
            model_id=model_id,
            context_window=context_window,
            modalities=modalities,
            function_calling=function_calling,
            structured_output=True,  # Most NVIDIA NIM models support structured output
            parallel_tool_calls=True,
            max_output_tokens=min(8192, context_window // 4),
        )


def create_nvidia_nim_fetcher(api_key: str | None = None) -> NvidiaNimFetcher:
    """Factory function to create NVIDIA NIM fetcher"""
    return NvidiaNimFetcher(api_key=api_key)