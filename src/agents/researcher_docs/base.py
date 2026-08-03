"""Base classes for Official Documentation Fetchers"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ProviderName(StrEnum):
    """Supported provider names"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    NVIDIA_NIM = "nvidia_nim"
    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"
    OLLAMA = "ollama"
    TOGETHER = "together"
    FIREWORKS = "fireworks"
    GROQ = "groq"


@dataclass(frozen=True, slots=True)
class ModelSummary:
    """Summary of a model from provider's /models endpoint"""

    model_id: str
    owned_by: str = ""
    permission: list = field(default_factory=list)
    root: str | None = None
    parent: str | None = None


@dataclass(frozen=True, slots=True)
class ModelDetail:
    """Detailed model capabilities from provider docs/API"""

    model_id: str
    context_window: int
    modalities: list[str]  # ["text", "vision", "audio", "function_calling"]
    function_calling: bool
    structured_output: bool
    parallel_tool_calls: bool
    max_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class PricingTable:
    """Pricing information for a model"""

    input_per_1m_tokens: float
    output_per_1m_tokens: float
    currency: str = "USD"
    effective_date: datetime | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class RateLimitInfo:
    """Rate limit information for a model"""

    rpm: int | None = None  # requests per minute
    tpm: int | None = None  # tokens per minute
    rpd: int | None = None  # requests per day
    regions: list[str] = field(default_factory=list)


class FetchResult(BaseModel):
    """Result of a fetch operation with metadata"""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    success: bool
    data: Any | None = None
    error: str | None = None
    source_url: str = ""
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence: float = 1.0  # 0.0 - 1.0


class OfficialDocsFetcher(ABC):
    """Abstract base class for provider-specific documentation fetchers.

    Each provider (OpenAI, Anthropic, etc.) implements this interface
    to fetch official model specifications, pricing, and rate limits.
    """

    @property
    @abstractmethod
    def provider_name(self) -> ProviderName:
        """Return the provider name this fetcher handles"""
        pass

    @property
    @abstractmethod
    def base_urls(self) -> dict[str, str]:
        """Return base URLs for this provider's documentation/API"""
        pass

    @abstractmethod
    async def fetch_model_list(self) -> FetchResult:
        """Fetch the complete list of available models from the provider"""
        pass

    @abstractmethod
    async def fetch_model_details(self, model_id: str) -> FetchResult:
        """Fetch detailed capabilities for a specific model"""
        pass

    @abstractmethod
    async def fetch_pricing(self, model_id: str) -> FetchResult:
        """Fetch pricing information for a specific model"""
        pass

    @abstractmethod
    async def fetch_rate_limits(self, model_id: str) -> FetchResult:
        """Fetch rate limit information for a specific model"""
        pass

    @abstractmethod
    async def fetch_official_docs(self, model_id: str) -> FetchResult:
        """Fetch official documentation page for a model"""
        pass

    async def validate_model_exists(self, model_id: str) -> bool:
        """Check if a model exists and is accessible"""
        try:
            result = await self.fetch_model_details(model_id)
            return result.success
        except Exception:
            return False

    async def close(self) -> None:
        """Clean up resources (HTTP clients, etc.)"""
        pass

    def _create_error_result(self, error: str, source_url: str = "") -> FetchResult:
        """Helper to create error result"""
        return FetchResult(
            success=False,
            error=error,
            source_url=source_url,
            confidence=0.0,
        )

    def _create_success_result(
        self, data: Any, source_url: str, confidence: float = 1.0
    ) -> FetchResult:
        """Helper to create success result"""
        return FetchResult(
            success=True,
            data=data,
            source_url=source_url,
            confidence=confidence,
        )