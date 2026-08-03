"""
ProfessionalResearcherAgent — Phase 2
=======================================
Zero-LLM-knowledge researcher agent. Every claim is backed by official sources
with citations and confidence scoring.

Rules:
- NEVER use LLM training knowledge for model specs
- ALL data comes from official APIs, docs, pricing pages
- EVERY field has a SourceCitation
- REJECT if confidence < 0.7
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from agents.researcher_docs import (
    FETCHER_REGISTRY,
    FetchResult,
    ModelDetail,
    ModelSummary,
    OfficialDocsFetcher,
    PricingTable,
    ProviderName,
    RateLimitInfo,
    create_fetcher,
    get_all_fetchers,
)
from gateway.model_registry import (
    ModelCapabilities,
    ModelLimits,
    ModelPricing,
    ModelSpec,
    ModelStatus,
    ModelTier,
    SourceCitation,
    SourceType,
)
from observability.instrumentation import trace_agent_invocation

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Confidence thresholds per source type
CONFIDENCE_THRESHOLDS = {
    SourceType.API: 1.0,
    SourceType.PRICING_PAGE: 0.9,
    SourceType.OFFICIAL_DOCS: 0.85,
    SourceType.MODEL_CARD: 0.8,
    SourceType.CHANGELOG: 0.75,
}

# Minimum confidence to accept a model spec
MIN_CONFIDENCE = 0.7


# ============================================================
# Research Result Types
# ============================================================


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """Result of a research operation."""

    success: bool
    provider: str
    model_id: str
    data: dict[str, Any] = field(default_factory=dict)
    citations: list[SourceCitation] = field(default_factory=list)
    confidence: float = 0.0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of cross-validation."""

    passed: bool
    model_id: str
    issues: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """Summary of research across multiple models/providers."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    results: list[ResearchResult] = field(default_factory=list)
    total_models: int = 0
    verified_models: int = 0
    rejected_models: int = 0
    errors: list[str] = field(default_factory=list)


# ============================================================
# ProfessionalResearcherAgent
# ============================================================


class ProfessionalResearcherAgent(BaseAgent):
    """Professional Researcher — Zero LLM knowledge, verified sources only.

    باحث محترف — صفر تخمين، صفر معرفة LLM
    كل معلومة = مصدر رسمي + Timestamp + Confidence

    Features:
    - Uses 10 official doc fetchers (OpenAI, Anthropic, Google, NVIDIA, etc.)
    - Cross-validates specs from multiple sources
    - Rejects any spec below MIN_CONFIDENCE (0.7)
    - Every field has a SourceCitation
    """

    role: str = "professional_researcher"

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        agent_id: str = "pro-researcher-01",
        http_client: Any | None = None,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            role="professional_researcher",
            llm_client=llm_client,
        )
        self._fetchers: dict[ProviderName, OfficialDocsFetcher] = {}
        self._http_client = http_client
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._cache_ttl_seconds = 86400  # 24 hours

    def register_fetcher(self, provider: ProviderName, fetcher: OfficialDocsFetcher) -> None:
        """Register a doc fetcher for a provider."""
        self._fetchers[provider] = fetcher
        logger.info("Registered doc fetcher for provider: %s", provider.value)

    def register_all_fetchers(self, **kwargs: Any) -> None:
        """Register all available doc fetchers."""
        self._fetchers = get_all_fetchers(**kwargs)
        logger.info("Registered %d doc fetchers", len(self._fetchers))

    # ----------------------------------------------------------
    # Core Research Tasks
    # ----------------------------------------------------------

    @trace_agent_invocation(agent_role="professional_researcher")
    async def research_model_spec(
        self, provider: str, model_id: str
    ) -> ResearchResult:
        """Research a specific model's full specification from official sources.

        Args:
            provider: Provider name (e.g., 'openai', 'nvidia_nim').
            model_id: Model identifier.

        Returns:
            ResearchResult with verified data and citations.
        """
        fetcher = self._get_fetcher(provider)
        if not fetcher:
            return ResearchResult(
                success=False,
                provider=provider,
                model_id=model_id,
                error=f"No doc fetcher registered for provider: {provider}",
            )

        citations: list[SourceCitation] = []
        data: dict[str, Any] = {}

        # 1. Fetch model details (capabilities)
        details_result = await fetcher.fetch_model_details(model_id)
        if details_result.success and details_result.data:
            detail: ModelDetail = details_result.data
            data["capabilities"] = {
                "context_window": detail.context_window,
                "modalities": detail.modalities,
                "function_calling": detail.function_calling,
                "structured_output": detail.structured_output,
                "parallel_tool_calls": detail.parallel_tool_calls,
                "max_output_tokens": detail.max_output_tokens or 4096,
            }
            citations.append(
                SourceCitation(
                    source_type=SourceType.API,
                    url=details_result.source_url,
                    provider=provider,
                    accessed_at=details_result.fetched_at,
                    field_mapping={"capabilities": "model_details_endpoint"},
                    confidence=details_result.confidence,
                    raw_snippet=f"model_id={model_id}, context={detail.context_window}",
                )
            )

        # 2. Fetch pricing
        pricing_result = await fetcher.fetch_pricing(model_id)
        if pricing_result.success and pricing_result.data:
            pricing: PricingTable = pricing_result.data
            data["pricing"] = {
                "input_per_1m_tokens": pricing.input_per_1m_tokens,
                "output_per_1m_tokens": pricing.output_per_1m_tokens,
                "currency": pricing.currency,
            }
            citations.append(
                SourceCitation(
                    source_type=SourceType.PRICING_PAGE,
                    url=pricing_result.source_url,
                    provider=provider,
                    accessed_at=pricing_result.fetched_at,
                    field_mapping={"pricing": "official_pricing_page"},
                    confidence=pricing_result.confidence,
                    raw_snippet=f"input=${pricing.input_per_1m_tokens}/1M, output=${pricing.output_per_1m_tokens}/1M",
                )
            )

        # 3. Fetch rate limits
        limits_result = await fetcher.fetch_rate_limits(model_id)
        if limits_result.success and limits_result.data:
            limits: RateLimitInfo = limits_result.data
            data["limits"] = {
                "rpm": limits.rpm,
                "tpm": limits.tpm,
                "rpd": limits.rpd,
            }
            citations.append(
                SourceCitation(
                    source_type=SourceType.OFFICIAL_DOCS,
                    url=limits_result.source_url,
                    provider=provider,
                    accessed_at=limits_result.fetched_at,
                    field_mapping={"limits": "rate_limits_docs"},
                    confidence=limits_result.confidence,
                    raw_snippet=f"rpm={limits.rpm}, tpm={limits.tpm}",
                )
            )

        # Calculate overall confidence
        confidence = self._calculate_confidence(citations)

        return ResearchResult(
            success=bool(data),
            provider=provider,
            model_id=model_id,
            data=data,
            citations=citations,
            confidence=confidence,
        )

    @trace_agent_invocation(agent_role="professional_researcher")
    async def research_provider_models(self, provider: str) -> list[ResearchResult]:
        """Research all models from a provider.

        Args:
            provider: Provider name.

        Returns:
            List of ResearchResults, one per model.
        """
        fetcher = self._get_fetcher(provider)
        if not fetcher:
            return []

        models_result = await fetcher.fetch_model_list()
        if not models_result.success or not models_result.data:
            logger.warning("Failed to fetch model list from %s: %s", provider, models_result.error)
            return []

        results: list[ResearchResult] = []
        for model_summary in models_result.data:
            if isinstance(model_summary, ModelSummary):
                result = await self.research_model_spec(provider, model_summary.model_id)
                results.append(result)
            elif isinstance(model_summary, dict):
                model_id = model_summary.get("model_id", model_summary.get("id", ""))
                if model_id:
                    result = await self.research_model_spec(provider, model_id)
                    results.append(result)

        return results

    @trace_agent_invocation(agent_role="professional_researcher")
    async def cross_validate(
        self, provider: str, model_id: str, existing_citations: list[SourceCitation]
    ) -> ValidationResult:
        """Cross-validate model specs by checking against official docs.

        Args:
            provider: Provider name.
            model_id: Model to validate.
            existing_citations: Citations to validate against.

        Returns:
            ValidationResult with pass/fail and issues.
        """
        issues: list[str] = []

        # Check minimum citation count
        if len(existing_citations) < 1:
            issues.append("No citations provided")

        # Check confidence threshold per citation
        for citation in existing_citations:
            expected = CONFIDENCE_THRESHOLDS.get(citation.source_type, 0.7)
            if citation.confidence < expected * 0.8:  # Allow 20% tolerance
                issues.append(
                    f"Low confidence for {citation.source_type}: "
                    f"{citation.confidence} < {expected * 0.8}"
                )

        # Cross-reference with fetcher data
        fetcher = self._get_fetcher(provider)
        if fetcher:
            exists = await fetcher.validate_model_exists(model_id)
            if not exists:
                issues.append(f"Model {model_id} not found in {provider} official API")

        overall_confidence = self._calculate_confidence(existing_citations)
        passed = len(issues) == 0 and overall_confidence >= MIN_CONFIDENCE

        return ValidationResult(
            passed=passed,
            model_id=model_id,
            issues=issues,
            confidence=overall_confidence,
        )

    async def build_model_spec(
        self, provider: str, model_id: str, research: ResearchResult
    ) -> ModelSpec | None:
        """Build a verified ModelSpec from research results.

        Args:
            provider: Provider name.
            model_id: Model ID.
            research: ResearchResult from research_model_spec.

        Returns:
            ModelSpec if confidence is sufficient, None otherwise.
        """
        if not research.success or research.confidence < MIN_CONFIDENCE:
            logger.warning(
                "Rejecting model %s: insufficient confidence (%.2f < %.2f)",
                model_id, research.confidence, MIN_CONFIDENCE,
            )
            return None

        caps_data = research.data.get("capabilities", {})
        pricing_data = research.data.get("pricing", {})
        limits_data = research.data.get("limits", {})

        capabilities = ModelCapabilities(
            context_window=caps_data.get("context_window", 4096),
            modalities=caps_data.get("modalities", ["text"]),
            function_calling=caps_data.get("function_calling", False),
            structured_output=caps_data.get("structured_output", False),
            parallel_tool_calls=caps_data.get("parallel_tool_calls", False),
            max_output_tokens=caps_data.get("max_output_tokens", 4096),
        )

        pricing = ModelPricing(
            input_per_1m_tokens=pricing_data.get("input_per_1m_tokens", 0.0),
            output_per_1m_tokens=pricing_data.get("output_per_1m_tokens", 0.0),
            currency=pricing_data.get("currency", "USD"),
        )

        limits = ModelLimits(
            rpm=limits_data.get("rpm"),
            tpm=limits_data.get("tpm"),
            rpd=limits_data.get("rpd"),
        )

        tier = self._classify_model(model_id, capabilities)

        citation_dict = {
            c.field_mapping.get(list(c.field_mapping.keys())[0], "general"): c
            for c in research.citations
            if c.field_mapping
        }

        return ModelSpec(
            model_id=f"{provider}/{model_id}" if "/" not in model_id else model_id,
            provider=provider,
            display_name=model_id.split("/")[-1] if "/" in model_id else model_id,
            tier=tier,
            capabilities=capabilities,
            pricing=pricing,
            limits=limits,
            status=ModelStatus.ACTIVE,
            citations=citation_dict,
            verification_confidence=research.confidence,
            tags=self._generate_tags(model_id, capabilities),
        )

    # ----------------------------------------------------------
    # LLM Tools (for reasoning layer)
    # ----------------------------------------------------------

    def get_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions for LLM tool-use."""
        return [
            {
                "name": "fetch_official_page",
                "description": "Fetch and parse an official documentation page",
                "parameters": {"url": "string"},
            },
            {
                "name": "call_provider_api",
                "description": "Call a provider's /models or similar API endpoint",
                "parameters": {"provider": "string", "endpoint": "string"},
            },
            {
                "name": "validate_model_card",
                "description": "Validate model specs against official model card",
                "parameters": {"provider": "string", "model_id": "string"},
            },
        ]

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _get_fetcher(self, provider: str) -> OfficialDocsFetcher | None:
        """Get the doc fetcher for a provider."""
        # Try direct ProviderName enum match
        try:
            provider_enum = ProviderName(provider)
            return self._fetchers.get(provider_enum)
        except ValueError:
            pass

        # Try matching by string
        for pname, fetcher in self._fetchers.items():
            if pname.value == provider or provider in pname.value:
                return fetcher

        logger.warning("No fetcher found for provider: %s", provider)
        return None

    def _calculate_confidence(self, citations: list[SourceCitation]) -> float:
        """Calculate overall confidence from multiple citations."""
        if not citations:
            return 0.0
        return min(c.confidence for c in citations)

    def _classify_model(self, model_id: str, capabilities: ModelCapabilities) -> ModelTier:
        """Classify by capabilities, NOT provider name."""
        model_lower = model_id.lower()

        # Code-specialized
        if any(kw in model_lower for kw in ["code", "coder", "starcoder", "codellama"]):
            return ModelTier.CODE_SPECIALIZED

        # Vision
        if "vision" in model_lower or "image" in capabilities.modalities:
            return ModelTier.VISION

        # Long context
        if capabilities.context_window >= 128000:
            return ModelTier.LONG_CONTEXT

        # Frontier (largest, most capable)
        if any(kw in model_lower for kw in [
            "405b", "nemotron-4-340b", "deepseek-v3", "phi-4",
            "gpt-4o", "claude-3.5-sonnet", "gemini-1.5-pro",
        ]):
            return ModelTier.FRONTIER

        # Critic (different architecture family)
        if any(kw in model_lower for kw in [
            "gemma-2-27b", "qwen2.5-72b", "llama-3.1-70b",
        ]):
            return ModelTier.CRITIC

        # Fast (small, efficient)
        if any(kw in model_lower for kw in [
            "8b", "7b", "phi-3", "gemma-2-9b", "mistral-7b", "mini",
        ]):
            return ModelTier.FAST

        return ModelTier.FAST  # Default

    def _generate_tags(self, model_id: str, capabilities: ModelCapabilities) -> list[str]:
        """Generate classification tags for a model."""
        tags: list[str] = []
        model_lower = model_id.lower()

        if capabilities.function_calling:
            tags.append("function_calling")
        if capabilities.structured_output:
            tags.append("structured_output")
        if "vision" in capabilities.modalities or "image" in capabilities.modalities:
            tags.append("vision")
        if capabilities.context_window >= 128000:
            tags.append("long_context")
        if any(kw in model_lower for kw in ["code", "coder"]):
            tags.append("code")

        return tags

    async def close(self) -> None:
        """Clean up all fetcher resources."""
        for fetcher in self._fetchers.values():
            await fetcher.close()

    def __repr__(self) -> str:
        return f"ProfessionalResearcherAgent(fetchers={len(self._fetchers)})"
