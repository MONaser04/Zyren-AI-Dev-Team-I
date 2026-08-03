"""Ollama Official Documentation Fetcher"""

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


class OllamaFetcher(OfficialDocsFetcher):
    """Official Ollama documentation and API fetcher.

    Sources:
    - Ollama Models: https://ollama.com/library
    - Ollama API: http://localhost:11434/api
    - Ollama Docs: https://github.com/ollama/ollama/blob/main/docs
    """

    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 30.0):
        self._base_url = base_url
        self._docs_base_url = "https://github.com/ollama/ollama/blob/main/docs"
        self._library_url = "https://ollama.com/library"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.OLLAMA

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            "api": self._base_url,
            "models": f"{self._base_url}/api/tags",
            "docs": self._docs_base_url,
            "library": self._library_url,
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_model_list(self) -> FetchResult:
        """Fetch available models from Ollama /api/tags endpoint"""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("models", []):
                model_id = model_data.get("name", "")
                if model_id:
                    models.append(
                        ModelSummary(
                            model_id=model_id,
                            owned_by="ollama",
                            permission=[],
                        )
                    )

            return self._create_success_result(
                models,
                f"{self._base_url}/api/tags",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Ollama model list: {e}")
            return self._create_error_result(str(e), f"{self._base_url}/api/tags")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch model details from Ollama library page"""
        try:
            details = self._get_ollama_model_details(model_id)
            if details:
                return self._create_success_result(
                    details,
                    f"https://ollama.com/library/{model_id}",
                    confidence=0.9,
                )

            docs_result = await self.fetch_official_docs(model_id)
            if docs_result.success and docs_result.data:
                details = await self._parse_ollama_docs(docs_result.data.get("html", ""), model_id)
                if details:
                    return self._create_success_result(
                        details,
                        f"https://ollama.com/library/{model_id}",
                        confidence=0.85,
                    )

            return self._create_error_result(f"No details found for {model_id}", "")
        except Exception as e:
            logger.error(f"Failed to fetch Ollama model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://ollama.com/library/{model_id}")

    def _get_ollama_model_details(self, model_id: str) -> ModelDetail | None:
        """Known Ollama model specifications from library"""
        known_models = {
            "llama3.1:8b": ModelDetail(
                model_id="llama3.1:8b",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
            "llama3.1:70b": ModelDetail(
                model_id="llama3.1:70b",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "llama3.1:405b": ModelDetail(
                model_id="llama3.1:405b",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "codellama:34b": ModelDetail(
                model_id="codellama:34b",
                context_window=16384,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "mistral:7b": ModelDetail(
                model_id="mistral:7b",
                context_window=32768,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
            "phi3:mini": ModelDetail(
                model_id="phi3:mini",
                context_window=4096,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
            "gemma2:9b": ModelDetail(
                model_id="gemma2:9b",
                context_window=8192,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
            "gemma2:27b": ModelDetail(
                model_id="gemma2:27b",
                context_window=8192,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "qwen2:7b": ModelDetail(
                model_id="qwen2:7b",
                context_window=32768,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
            "qwen2:72b": ModelDetail(
                model_id="qwen2:72b",
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
        """Ollama models are free (local execution)"""
        try:
            pricing = PricingTable(
                input_per_1m_tokens=0.0,
                output_per_1m_tokens=0.0,
                currency="USD",
                notes="Free - runs locally on your hardware",
            )

            return self._create_success_result(
                pricing,
                "https://ollama.com",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Ollama pricing for {model_id}: {e}")
            return self._create_error_result(str(e), "https://ollama.com")

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Ollama rate limits depend on local hardware"""
        try:
            limits = RateLimitInfo(
                rpm=None,  # No API rate limits - local execution
                tpm=None,
                rpd=None,
                regions=["local"],
            )

            return self._create_success_result(
                limits,
                "https://ollama.com",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch Ollama rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), "https://ollama.com")

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official Ollama library page"""
        try:
            url = f"https://ollama.com/library/{model_id}"
            client = httpx.AsyncClient(timeout=self._timeout)
            response = await client.get(url)
            await client.aclose()

            if response.status_code == 200:
                return self._create_success_result(
                    {"html": response.text, "model_id": model_id, "url": url},
                    url,
                    confidence=0.9,
                )
            return self._create_error_result(f"Library page not found: {response.status_code}", url)
        except Exception as e:
            logger.error(f"Failed to fetch Ollama library page for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://ollama.com/library/{model_id}")

    async def _parse_ollama_docs(self, html: str, model_id: str) -> ModelDetail | None:
        """Parse Ollama library page for model specifications"""
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text()

            context_match = re.search(r"(\d+(?:,\d+)*)\s*(?:token|context)", text, re.IGNORECASE)
            context_window = int(context_match.group(1).replace(",", "")) if context_match else 4096

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
            logger.warning(f"Failed to parse Ollama docs for {model_id}: {e}")
            return None


def create_ollama_fetcher(base_url: str = "http://localhost:11434") -> OllamaFetcher:
    """Factory function to create Ollama fetcher"""
    return OllamaFetcher(base_url=base_url)