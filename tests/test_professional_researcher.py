"""
Tests for ProfessionalResearcherAgent and CommandExecutor — Phase 2
====================================================================
All tests use mocks — NO real API calls.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agents.professional_researcher import (
    MIN_CONFIDENCE,
    ProfessionalResearcherAgent,
    ResearchResult,
    ValidationResult,
)
from agents.researcher_docs.base import FetchResult, ModelDetail, PricingTable, RateLimitInfo
from gateway.model_registry import (
    ModelCapabilities,
    ModelSpec,
    ModelStatus,
    ModelTier,
    SourceCitation,
    SourceType,
)
from orchestrator.command_executor import CommandExecutor, CommandResult, ParsedCommand


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_fetcher():
    """Create a mock OfficialDocsFetcher."""
    fetcher = MagicMock()
    fetcher.provider_name = MagicMock(return_value="openai")

    # Mock model details
    fetcher.fetch_model_details = AsyncMock(return_value=FetchResult(
        success=True,
        data=ModelDetail(
            model_id="gpt-4o",
            context_window=128000,
            modalities=["text"],
            function_calling=True,
            structured_output=True,
            parallel_tool_calls=True,
            max_output_tokens=4096,
        ),
        source_url="https://platform.openai.com/docs/models/gpt-4o",
        confidence=1.0,
    ))

    # Mock pricing
    fetcher.fetch_pricing = AsyncMock(return_value=FetchResult(
        success=True,
        data=PricingTable(
            input_per_1m_tokens=2.50,
            output_per_1m_tokens=10.00,
            currency="USD",
        ),
        source_url="https://openai.com/pricing",
        confidence=0.95,
    ))

    # Mock rate limits
    fetcher.fetch_rate_limits = AsyncMock(return_value=FetchResult(
        success=True,
        data=RateLimitInfo(rpm=500, tpm=30000, rpd=10000),
        source_url="https://platform.openai.com/docs/guides/rate-limits",
        confidence=0.9,
    ))

    fetcher.validate_model_exists = AsyncMock(return_value=True)
    fetcher.close = AsyncMock()

    return fetcher


@pytest.fixture
def researcher(mock_fetcher):
    """Create researcher with mock fetcher."""
    from agents.researcher_docs.base import ProviderName
    agent = ProfessionalResearcherAgent(agent_id="test-researcher")
    agent.register_fetcher(ProviderName.OPENAI, mock_fetcher)
    return agent


@pytest.fixture
def mock_registry():
    """Create a mock AutoModelRegistry."""
    registry = MagicMock()
    registry.manual_add_model = MagicMock()
    registry.manual_disable_model = MagicMock(return_value=True)
    registry.manual_enable_model = MagicMock(return_value=True)
    registry.disable_provider_models = MagicMock(return_value=3)
    registry.get_by_provider = MagicMock(return_value=[])
    registry.list_models = MagicMock(return_value=[])
    registry.discover_all = AsyncMock(return_value=10)
    registry.get_stats = MagicMock(return_value={"total": 10})
    registry.list_all = MagicMock(return_value=[])
    return registry


@pytest.fixture
def mock_gateway():
    """Create a mock SmartGateway."""
    gw = MagicMock()
    gw.handle_manual_model_change = AsyncMock(return_value={"status": "ok", "message": "done"})
    gw.get_routing_stats = MagicMock(return_value={"models": 10})
    return gw


# ============================================================
# ProfessionalResearcherAgent Tests
# ============================================================


class TestProfessionalResearcherAgent:
    """Tests for ProfessionalResearcherAgent."""

    @pytest.mark.asyncio
    async def test_research_model_spec_success(self, researcher):
        """Should return successful ResearchResult with citations."""
        result = await researcher.research_model_spec("openai", "gpt-4o")

        assert result.success is True
        assert result.provider == "openai"
        assert result.model_id == "gpt-4o"
        assert len(result.citations) == 3  # details + pricing + rate_limits
        assert result.confidence > 0
        assert "capabilities" in result.data
        assert "pricing" in result.data
        assert "limits" in result.data

    @pytest.mark.asyncio
    async def test_research_model_spec_no_fetcher(self, researcher):
        """Should fail gracefully if no fetcher for provider."""
        result = await researcher.research_model_spec("nonexistent_provider", "model-x")

        assert result.success is False
        assert "No doc fetcher" in (result.error or "")

    @pytest.mark.asyncio
    async def test_cross_validate_passes(self, researcher):
        """Cross-validation should pass with good citations."""
        citations = [
            SourceCitation(
                source_type=SourceType.API,
                url="https://api.openai.com/v1/models",
                provider="openai",
                accessed_at=datetime.now(UTC),
                confidence=1.0,
            )
        ]
        result = await researcher.cross_validate("openai", "gpt-4o", citations)

        assert result.passed is True
        assert len(result.issues) == 0

    @pytest.mark.asyncio
    async def test_cross_validate_fails_no_citations(self, researcher):
        """Cross-validation should fail with no citations."""
        result = await researcher.cross_validate("openai", "gpt-4o", [])

        assert result.passed is False
        assert any("No citations" in i for i in result.issues)

    @pytest.mark.asyncio
    async def test_build_model_spec_success(self, researcher):
        """Should build a valid ModelSpec from research results."""
        research = await researcher.research_model_spec("openai", "gpt-4o")
        spec = await researcher.build_model_spec("openai", "gpt-4o", research)

        assert spec is not None
        assert spec.model_id == "openai/gpt-4o"
        assert spec.provider == "openai"
        assert spec.status == ModelStatus.ACTIVE
        assert spec.capabilities.context_window == 128000
        assert spec.capabilities.function_calling is True

    @pytest.mark.asyncio
    async def test_build_model_spec_rejected_low_confidence(self, researcher):
        """Should reject spec if confidence is below threshold."""
        research = ResearchResult(
            success=True,
            provider="openai",
            model_id="gpt-4o",
            confidence=0.3,  # Below MIN_CONFIDENCE
            data={"capabilities": {}},
        )
        spec = await researcher.build_model_spec("openai", "gpt-4o", research)

        assert spec is None

    def test_classify_model_tiers(self, researcher):
        """Model tier classification should work by keyword/capability."""
        caps = ModelCapabilities(context_window=4096)
        assert researcher._classify_model("codellama-34b", caps) == ModelTier.CODE_SPECIALIZED

        long_caps = ModelCapabilities(context_window=200000)
        assert researcher._classify_model("some-model", long_caps) == ModelTier.LONG_CONTEXT

        assert researcher._classify_model("gpt-4o", caps) == ModelTier.FRONTIER

    def test_generate_tags(self, researcher):
        """Should generate correct tags for capabilities."""
        caps = ModelCapabilities(
            context_window=128000,
            modalities=["text", "vision"],
            function_calling=True,
            structured_output=True,
        )
        tags = researcher._generate_tags("gpt-4o", caps)

        assert "function_calling" in tags
        assert "structured_output" in tags
        assert "vision" in tags
        assert "long_context" in tags


# ============================================================
# CommandExecutor Tests
# ============================================================


class TestCommandExecutor:
    """Tests for CommandExecutor."""

    @pytest.mark.asyncio
    async def test_disable_model(self, mock_registry, mock_gateway):
        """Should disable a model via gateway."""
        executor = CommandExecutor(mock_registry, mock_gateway)
        cmd = ParsedCommand(action="disable_model", params={"model_id": "gpt-4o", "reason": "testing"})

        result = await executor.execute_command(cmd)
        assert result.success is True
        mock_gateway.handle_manual_model_change.assert_called_once()

    @pytest.mark.asyncio
    async def test_enable_model(self, mock_registry, mock_gateway):
        """Should enable a model via gateway."""
        executor = CommandExecutor(mock_registry, mock_gateway)
        cmd = ParsedCommand(action="enable_model", params={"model_id": "gpt-4o"})

        result = await executor.execute_command(cmd)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_disable_provider(self, mock_registry, mock_gateway):
        """Should disable all models from a provider."""
        executor = CommandExecutor(mock_registry, mock_gateway)
        cmd = ParsedCommand(action="disable_provider", params={"provider": "openai", "reason": "outage"})

        result = await executor.execute_command(cmd)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_query_status(self, mock_registry, mock_gateway):
        """Should return system status."""
        executor = CommandExecutor(mock_registry, mock_gateway)
        cmd = ParsedCommand(action="query_status")

        result = await executor.execute_command(cmd)
        assert result.success is True
        assert "models" in result.data

    @pytest.mark.asyncio
    async def test_unknown_command(self, mock_registry, mock_gateway):
        """Should fail gracefully for unknown commands."""
        executor = CommandExecutor(mock_registry, mock_gateway)
        cmd = ParsedCommand(action="unknown_action")

        result = await executor.execute_command(cmd)
        assert result.success is False
        assert "Unknown" in result.message

    @pytest.mark.asyncio
    async def test_add_model_with_researcher(self, mock_registry, mock_gateway, researcher):
        """Should research then register a model."""
        executor = CommandExecutor(mock_registry, mock_gateway, researcher=researcher)
        cmd = ParsedCommand(
            action="add_model",
            params={"provider": "openai", "model_id": "gpt-4o"},
        )

        result = await executor.execute_command(cmd)
        assert result.success is True
        mock_registry.manual_add_model.assert_called_once()
