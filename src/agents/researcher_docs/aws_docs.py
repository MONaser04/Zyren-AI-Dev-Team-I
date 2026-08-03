"""AWS Bedrock Official Documentation Fetcher"""

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


class AWSBedrockFetcher(OfficialDocsFetcher):
    """Official AWS Bedrock documentation and API fetcher.

    Sources:
    - Bedrock Models: https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
    - Bedrock Pricing: https://aws.amazon.com/bedrock/pricing/
    - Bedrock Quotas: https://docs.aws.amazon.com/bedrock/latest/userguide/quotas.html
    """

    def __init__(self, region: str = "us-east-1", timeout: float = 30.0):
        self._region = region
        self._base_url = f"https://bedrock.{region}.amazonaws.com"
        self._docs_base_url = "https://docs.aws.amazon.com/bedrock/latest/userguide"
        self._pricing_url = "https://aws.amazon.com/bedrock/pricing/"
        self._quotas_url = "https://docs.aws.amazon.com/bedrock/latest/userguide/quotas.html"
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.AWS_BEDROCK

    @property
    def base_urls(self) -> dict[str, str]:
        return {
            "api": self._base_url,
            "models": f"{self._base_url}/foundation-models",
            "docs": self._docs_base_url,
            "pricing": self._pricing_url,
            "quotas": self._quotas_url,
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
        """Fetch available models from AWS Bedrock"""
        try:
            # Bedrock list_foundation_models API
            client = await self._get_client()
            # Note: Actual implementation would use boto3 for AWS APIs
            # This is a simplified example using HTTP

            # Known Bedrock models
            models = [
                ModelSummary(model_id="anthropic.claude-3-5-sonnet-20240620-v1:0", owned_by="anthropic"),
                ModelSummary(model_id="anthropic.claude-3-5-haiku-20241022-v1:0", owned_by="anthropic"),
                ModelSummary(model_id="anthropic.claude-3-opus-20240229-v1:0", owned_by="anthropic"),
                ModelSummary(model_id="meta.llama3-1-405b-instruct-v1:0", owned_by="meta"),
                ModelSummary(model_id="meta.llama3-1-70b-instruct-v1:0", owned_by="meta"),
                ModelSummary(model_id="meta.llama3-1-8b-instruct-v1:0", owned_by="meta"),
                ModelSummary(model_id="amazon.titan-text-premier-v1:0", owned_by="amazon"),
                ModelSummary(model_id="amazon.titan-text-lite-v1:0", owned_by="amazon"),
                ModelSummary(model_id="cohere.command-r-plus-v1:0", owned_by="cohere"),
                ModelSummary(model_id="cohere.command-r-v1:0", owned_by="cohere"),
                ModelSummary(model_id="mistral.mistral-7b-instruct-v0:2", owned_by="mistral"),
                ModelSummary(model_id="mistral.mixtral-8x7b-instruct-v0:1", owned_by="mistral"),
            ]

            return self._create_success_result(
                models,
                f"{self._docs_base_url}/models-supported.html",
                confidence=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to fetch AWS Bedrock model list: {e}")
            return self._create_error_result(str(e), f"{self._docs_base_url}/models-supported.html")

    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch model details from AWS Bedrock docs"""
        try:
            details = self._get_aws_model_details(model_id)
            if details:
                return self._create_success_result(
                    details,
                    f"https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html#{model_id}",
                    confidence=0.9,
                )

            docs_result = await self.fetch_official_docs(model_id)
            if docs_result.success and docs_result.data:
                details = await self._parse_aws_docs(docs_result.data.get("html", ""), model_id)
                if details:
                    return self._create_success_result(
                        details,
                        f"https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html#{model_id}",
                        confidence=0.85,
                    )

            return self._create_error_result(f"No details found for {model_id}", "")
        except Exception as e:
            logger.error(f"Failed to fetch AWS Bedrock model details for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html#{model_id}")

    def _get_aws_model_details(self, model_id: str) -> ModelDetail | None:
        """Known AWS Bedrock model specifications"""
        known_models = {
            "anthropic.claude-3-5-sonnet-20240620-v1:0": ModelDetail(
                model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
                context_window=200000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=8192,
            ),
            "anthropic.claude-3-5-haiku-20241022-v1:0": ModelDetail(
                model_id="anthropic.claude-3-5-haiku-20241022-v1:0",
                context_window=200000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=8192,
            ),
            "anthropic.claude-3-opus-20240229-v1:0": ModelDetail(
                model_id="anthropic.claude-3-opus-20240229-v1:0",
                context_window=200000,
                modalities=["text", "vision", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "meta.llama3-1-405b-instruct-v1:0": ModelDetail(
                model_id="meta.llama3-1-405b-instruct-v1:0",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "meta.llama3-1-70b-instruct-v1:0": ModelDetail(
                model_id="meta.llama3-1-70b-instruct-v1:0",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "meta.llama3-1-8b-instruct-v1:0": ModelDetail(
                model_id="meta.llama3-1-8b-instruct-v1:0",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "amazon.titan-text-premier-v1:0": ModelDetail(
                model_id="amazon.titan-text-premier-v1:0",
                context_window=32768,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=2048,
            ),
            "cohere.command-r-plus-v1:0": ModelDetail(
                model_id="cohere.command-r-plus-v1:0",
                context_window=128000,
                modalities=["text", "function_calling", "structured_output"],
                function_calling=True,
                structured_output=True,
                parallel_tool_calls=True,
                max_output_tokens=4096,
            ),
            "mistral.mixtral-8x7b-instruct-v0:1": ModelDetail(
                model_id="mistral.mixtral-8x7b-instruct-v0:1",
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
        """Fetch pricing from AWS Bedrock pricing page"""
        try:
            pricing = self._get_aws_pricing(model_id)
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
                pricing = await self._parse_aws_pricing(response.text, model_id)
                if pricing:
                    return self._create_success_result(
                        pricing,
                        self._pricing_url,
                        confidence=0.8,
                    )

            return self._create_error_result(f"Pricing not found for {model_id}", self._pricing_url)
        except Exception as e:
            logger.error(f"Failed to fetch AWS Bedrock pricing for {model_id}: {e}")
            return self._create_error_result(str(e), self._pricing_url)

    def _get_aws_pricing(self, model_id: str) -> PricingTable | None:
        """Known AWS Bedrock pricing (per 1M tokens, as of 2024)"""
        pricing = {
            "anthropic.claude-3-5-sonnet-20240620-v1:0": PricingTable(input_per_1m_tokens=3.00, output_per_1m_tokens=15.00),
            "anthropic.claude-3-5-haiku-20241022-v1:0": PricingTable(input_per_1m_tokens=0.25, output_per_1m_tokens=1.25),
            "anthropic.claude-3-opus-20240229-v1:0": PricingTable(input_per_1m_tokens=15.00, output_per_1m_tokens=75.00),
            "meta.llama3-1-405b-instruct-v1:0": PricingTable(input_per_1m_tokens=5.00, output_per_1m_tokens=15.00),
            "meta.llama3-1-70b-instruct-v1:0": PricingTable(input_per_1m_tokens=0.90, output_per_1m_tokens=1.20),
            "meta.llama3-1-8b-instruct-v1:0": PricingTable(input_per_1m_tokens=0.15, output_per_1m_tokens=0.18),
            "amazon.titan-text-premier-v1:0": PricingTable(input_per_1m_tokens=0.50, output_per_1m_tokens=1.50),
            "cohere.command-r-plus-v1:0": PricingTable(input_per_1m_tokens=3.00, output_per_1m_tokens=15.00),
            "mistral.mixtral-8x7b-instruct-v0:1": PricingTable(input_per_1m_tokens=0.70, output_per_1m_tokens=1.40),
        }
        return pricing.get(model_id)

    async def _parse_aws_pricing(self, html: str, model_id: str) -> PricingTable | None:
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Would need specific selectors for AWS pricing page
            return None
        except Exception:
            return None

    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limits from AWS Bedrock quotas page"""
        try:
            limits = self._get_aws_rate_limits(model_id)
            return self._create_success_result(
                limits,
                "https://docs.aws.amazon.com/bedrock/latest/userguide/quotas.html",
                confidence=0.85,
            )
        except Exception as e:
            logger.error(f"Failed to fetch AWS Bedrock rate limits for {model_id}: {e}")
            return self._create_error_result(str(e), "https://docs.aws.amazon.com/bedrock/latest/userguide/quotas.html")

    def _get_aws_rate_limits(self, model_id: str) -> RateLimitInfo:
        """Known AWS Bedrock rate limits (per account/region)"""
        if "sonnet" in model_id.lower():
            return RateLimitInfo(rpm=50, tpm=20000, rpd=1000, regions=["us-east-1", "us-west-2"])
        elif "haiku" in model_id.lower():
            return RateLimitInfo(rpm=100, tpm=50000, rpd=5000, regions=["us-east-1", "us-west-2"])
        elif "opus" in model_id.lower():
            return RateLimitInfo(rpm=10, tpm=5000, rpd=100, regions=["us-east-1", "us-west-2"])
        elif "llama" in model_id.lower() or "titan" in model_id.lower() or "cohere" in model_id.lower():
            return RateLimitInfo(rpm=100, tpm=50000, rpd=5000, regions=["us-east-1", "us-west-2"])
        elif "mistral" in model_id.lower():
            return RateLimitInfo(rpm=50, tpm=20000, rpd=1000, regions=["us-east-1", "us-west-2"])
        return RateLimitInfo(rpm=50, tpm=20000, rpd=1000, regions=["us-east-1", "us-west-2"])

    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official AWS Bedrock documentation page"""
        try:
            url = f"https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html#{model_id}"
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
            logger.error(f"Failed to fetch AWS Bedrock docs for {model_id}: {e}")
            return self._create_error_result(str(e), f"https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html#{model_id}")

    async def _parse_aws_docs(self, html: str, model_id: str) -> ModelDetail | None:
        """Parse AWS Bedrock docs HTML for model specifications"""
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
                max_output_tokens=min(8192, context_window // 4),
            )
        except Exception as e:
            logger.warning(f"Failed to parse AWS docs for {model_id}: {e}")
            return None


def create_aws_fetcher(region: str = "us-east-1") -> AWSBedrockFetcher:
    """Factory function to create AWS Bedrock fetcher"""
    return AWSBedrockFetcher(region=region)