"""
Fallback Chain — Phase 3 Resilience
====================================
Manages fallback chains for LLM models with cooldown support.

Fallback chains automatically switch to alternative models when the primary
model fails, with configurable cooldown periods to prevent retry storms.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FallbackConfig:
    """Configuration for fallback behavior."""

    cooldown_duration: float = 60.0  # Seconds to wait before retrying a model
    max_fallback_attempts: int = 3  # Max models to try in chain
    require_different_provider: bool = True  # Prefer different provider for fallback


@dataclass
class ModelFallback:
    """Represents a fallback entry in the chain."""

    model: str
    provider: str
    tier: str
    priority: int = 0  # Lower = higher priority


class FallbackChain:
    """Manages fallback chains for models with cooldown tracking."""

    def __init__(self, config: FallbackConfig | None = None):
        self.config = config or FallbackConfig()
        self._chains: dict[str, list[ModelFallback]] = {}
        self._cooldowns: dict[str, float] = {}  # model -> cooldown expiry time

    def register_chain(self, primary_model: str, fallbacks: list[ModelFallback | dict[str, Any]]) -> None:
        """Register a fallback chain for a primary model."""
        converted: list[ModelFallback] = []
        for item in fallbacks:
            if isinstance(item, dict):
                converted.append(ModelFallback(**item))
            elif isinstance(item, ModelFallback):
                converted.append(item)
        converted.sort(key=lambda f: f.priority)
        self._chains[primary_model] = converted
        logger.info(
            "Registered fallback chain for %s with %d fallbacks",
            primary_model,
            len(fallbacks),
        )

    def get_fallback(self, model: str) -> str | None:
        """Get the next available fallback for a model."""
        chain = self._chains.get(model)
        if not chain:
            return None

        for fallback in chain:
            if self._is_available(fallback.model):
                logger.info("Selected fallback %s for %s", fallback.model, model)
                return fallback.model

        return None

    def _is_available(self, model: str) -> bool:
        """Check if a model is available (not in cooldown)."""
        cooldown_expiry = self._cooldowns.get(model)
        if cooldown_expiry is None:
            return True
        return time.monotonic() >= cooldown_expiry

    def set_cooldown(self, model: str, duration: float | None = None) -> None:
        """Put a model into cooldown."""
        duration = duration or self.config.cooldown_duration
        self._cooldowns[model] = time.monotonic() + duration
        logger.info("Model %s in cooldown for %.0fs", model, duration)

    def clear_cooldown(self, model: str) -> None:
        """Manually clear cooldown for a model."""
        if model in self._cooldowns:
            del self._cooldowns[model]
            logger.info("Cleared cooldown for model %s", model)

    def is_in_cooldown(self, model: str) -> bool:
        """Check if a model is currently in cooldown."""
        return not self._is_available(model)

    def get_cooldown_remaining(self, model: str) -> float | None:
        """Get remaining cooldown time in seconds."""
        cooldown_expiry = self._cooldowns.get(model)
        if cooldown_expiry is None:
            return None
        remaining = cooldown_expiry - time.monotonic()
        return max(0.0, remaining)

    def get_chain_status(self, model: str) -> dict[str, Any]:
        """Get status of the fallback chain for a model."""
        chain = self._chains.get(model, [])
        return {
            "primary_model": model,
            "fallbacks": [
                {
                    "model": fb.model,
                    "provider": fb.provider,
                    "tier": fb.tier,
                    "priority": fb.priority,
                    "in_cooldown": self.is_in_cooldown(fb.model),
                    "cooldown_remaining": self.get_cooldown_remaining(fb.model),
                }
                for fb in chain
            ],
        }

    def reset_all_cooldowns(self) -> None:
        """Clear all cooldowns."""
        self._cooldowns.clear()
        logger.info("All cooldowns cleared")


# Default fallback chains based on tiers
def create_default_chains() -> FallbackChain:
    """Create default fallback chains for common model patterns."""
    chain = FallbackChain()

    # Frontier model fallbacks
    chain.register_chain(
        "frontier",
        [
            ModelFallback("nvidia_nim/nvidia/nemotron-4-340b", "nvidia_nim", "frontier", 0),
            ModelFallback("openai/gpt-4o", "openai", "frontier", 1),
            ModelFallback("anthropic/claude-3.5-sonnet", "anthropic", "frontier", 2),
            ModelFallback("google/gemini-1.5-pro", "google", "frontier", 3),
            ModelFallback("together/meta-llama/Meta-Llama-3.1-405B-Instruct", "together", "frontier", 4),
        ],
    )

    # Fast model fallbacks
    chain.register_chain(
        "fast",
        [
            ModelFallback("nvidia_nim/minimaxai/minimax-m3", "nvidia_nim", "fast", 0),
            ModelFallback("openai/gpt-4o-mini", "openai", "fast", 1),
            ModelFallback("groq/llama-3.1-8b-instant", "groq", "fast", 2),
            ModelFallback("ollama/llama3.1-8b", "ollama", "fast", 3),
        ],
    )

    # Critic model fallbacks
    chain.register_chain(
        "critic",
        [
            ModelFallback("nvidia_nim/google/gemma-4-31b-it", "nvidia_nim", "critic", 0),
            ModelFallback("openai/gpt-4o-mini", "openai", "critic", 1),
            ModelFallback("anthropic/claude-3-haiku", "anthropic", "critic", 2),
        ],
    )

    # Code specialized fallbacks
    chain.register_chain(
        "code",
        [
            ModelFallback("nvidia_nim/deepseek-ai/deepseek-coder-v2", "nvidia_nim", "code_specialized", 0),
            ModelFallback("together/deepseek-ai/DeepSeek-Coder-V2-Instruct", "together", "code_specialized", 1),
            ModelFallback("openai/gpt-4o", "openai", "code_specialized", 2),
        ],
    )

    return chain