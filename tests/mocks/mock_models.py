"""Mock model response dataclasses for testing."""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


@dataclass
class MockModelInfo:
    """Mock model info from /v1/models endpoint."""
    id: str
    object: str = "model"
    created: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    owned_by: str = "mock-provider"
    permission: list = field(default_factory=list)
    root: Optional[str] = None
    parent: Optional[str] = None


@dataclass
class MockModelListResponse:
    """Mock response for /v1/models endpoint."""
    object: str = "list"
    data: list = field(default_factory=list)


@dataclass
class MockPricingInfo:
    """Mock pricing information for a model."""
    input_per_1m_tokens: float
    output_per_1m_tokens: float
    currency: str = "USD"
    effective_date: Optional[str] = None


@dataclass
class MockLimitsInfo:
    """Mock rate limits for a model."""
    rpm: Optional[int] = None
    tpm: Optional[int] = None
    rpd: Optional[int] = None


# Pre-built model data for testing

MOCK_NVIDIA_MODELS = [
    MockModelInfo(id="nvidia_nim/deepseek-ai/deepseek-v4-pro", owned_by="nvidia"),
    MockModelInfo(id="nvidia_nim/minimaxai/minimax-m3", owned_by="nvidia"),
    MockModelInfo(id="nvidia_nim/google/gemma-4-31b-it", owned_by="nvidia"),
    MockModelInfo(id="nvidia_nim/nvidia/nemotron-3-ultra", owned_by="nvidia"),
]

MOCK_NVIDIA_MODEL_LIST = MockModelListResponse(data=MOCK_NVIDIA_MODELS)

MOCK_OPENAI_MODELS = [
    MockModelInfo(id="gpt-4o", owned_by="openai"),
    MockModelInfo(id="gpt-4o-mini", owned_by="openai"),
    MockModelInfo(id="gpt-4.1", owned_by="openai"),
    MockModelInfo(id="gpt-4.1-mini", owned_by="openai"),
]

MOCK_OPENAI_MODEL_LIST = MockModelListResponse(data=MOCK_OPENAI_MODELS)

MOCK_ANTHROPIC_MODELS = [
    MockModelInfo(id="claude-3-5-sonnet-20241022", owned_by="anthropic"),
    MockModelInfo(id="claude-3-5-haiku-20241022", owned_by="anthropic"),
    MockModelInfo(id="claude-3-opus-20240229", owned_by="anthropic"),
]

MOCK_ANTHROPIC_MODEL_LIST = MockModelListResponse(data=MOCK_ANTHROPIC_MODELS)

# Mock pricing for NVIDIA models (free tier)
MOCK_NVIDIA_PRICING = {
    "nvidia_nim/deepseek-ai/deepseek-v4-pro": MockPricingInfo(0.0, 0.0),
    "nvidia_nim/minimaxai/minimax-m3": MockPricingInfo(0.0, 0.0),
    "nvidia_nim/google/gemma-4-31b-it": MockPricingInfo(0.0, 0.0),
    "nvidia_nim/nvidia/nemotron-3-ultra": MockPricingInfo(0.0, 0.0),
}

# Mock pricing for OpenAI models
MOCK_OPENAI_PRICING = {
    "gpt-4o": MockPricingInfo(2.50, 10.00),
    "gpt-4o-mini": MockPricingInfo(0.15, 0.60),
    "gpt-4.1": MockPricingInfo(2.00, 8.00),
    "gpt-4.1-mini": MockPricingInfo(0.15, 0.60),
}

# Mock pricing for Anthropic models
MOCK_ANTHROPIC_PRICING = {
    "claude-3-5-sonnet-20241022": MockPricingInfo(3.00, 15.00),
    "claude-3-5-haiku-20241022": MockPricingInfo(0.25, 1.25),
    "claude-3-opus-20240229": MockPricingInfo(15.00, 75.00),
}

# Combined pricing
MOCK_ALL_PRICING = {
    **MOCK_NVIDIA_PRICING,
    **MOCK_OPENAI_PRICING,
    **MOCK_ANTHROPIC_PRICING,
}

# Mock limits
MOCK_NVIDIA_LIMITS = {
    "nvidia_nim/deepseek-ai/deepseek-v4-pro": MockLimitsInfo(rpm=60, tpm=100000),
    "nvidia_nim/minimaxai/minimax-m3": MockLimitsInfo(rpm=100, tpm=200000),
    "nvidia_nim/google/gemma-4-31b-it": MockLimitsInfo(rpm=120, tpm=150000),
}

MOCK_OPENAI_LIMITS = {
    "gpt-4o": MockLimitsInfo(rpm=500, tpm=30000),
    "gpt-4o-mini": MockLimitsInfo(rpm=1000, tpm=50000),
    "gpt-4.1": MockLimitsInfo(rpm=500, tpm=30000),
}

MOCK_ANTHROPIC_LIMITS = {
    "claude-3-5-sonnet-20241022": MockLimitsInfo(rpm=50, tpm=20000),
    "claude-3-5-haiku-20241022": MockLimitsInfo(rpm=100, tpm=50000),
    "claude-3-opus-20240229": MockLimitsInfo(rpm=50, tpm=20000),
}

MOCK_ALL_LIMITS = {
    **MOCK_NVIDIA_LIMITS,
    **MOCK_OPENAI_LIMITS,
    **MOCK_ANTHROPIC_LIMITS,
}


def get_mock_pricing(model: str) -> MockPricingInfo:
    """Get mock pricing for a model."""
    return MOCK_ALL_PRICING.get(model, MockPricingInfo(0.0, 0.0))


def get_mock_limits(model: str) -> MockLimitsInfo:
    """Get mock limits for a model."""
    return MOCK_ALL_LIMITS.get(model, MockLimitsInfo())