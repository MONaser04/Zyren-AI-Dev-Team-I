"""
LLM Client — Thin Wrapper Around LiteLLM
==========================================

Provides a consistent interface for calling LLMs with:
- Model alias resolution (frontier, fast, critic)
- Structured output via Pydantic models
- Retry with exponential backoff
- Consistent error handling
"""

from __future__ import annotations

import logging
import time
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ============================================================
# Default Model Aliases
# ============================================================

DEFAULT_MODEL_MAP: dict[str, str] = {
    "frontier": "openai/gpt-4o",
    "fast": "openai/gpt-4o-mini",
    "critic": "anthropic/claude-sonnet-4-20250514",
    "fallback": "gemini/gemini-2.5-flash",
}


# ============================================================
# LLM Client
# ============================================================


class LLMClient:
    """Thin wrapper around litellm for consistent LLM access.

    Supports model alias resolution, retries, and structured output.
    """

    def __init__(
        self,
        model_map: dict[str, str] | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        """Initialize the LLM client.

        Args:
            model_map: Map of alias → litellm model string.
            max_retries: Maximum number of retries on transient errors.
            base_delay: Base delay for exponential backoff (seconds).
        """
        self.model_map = model_map or DEFAULT_MODEL_MAP
        self.max_retries = max_retries
        self.base_delay = base_delay

        # Suppress litellm noise
        litellm.suppress_debug_info = True

    def resolve_model(self, model_or_alias: str) -> str:
        """Resolve a model alias to its full litellm model string."""
        return self.model_map.get(model_or_alias, model_or_alias)

    def complete_text(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Call an LLM and return plain text.

        Args:
            model: Model name or alias.
            messages: Chat messages.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Returns:
            The generated text content.
        """
        resolved = self.resolve_model(model)
        response = self._call_with_retry(
            model=resolved,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        content: str = response.choices[0].message.content or ""
        return content

    def complete_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> T:
        """Call an LLM and parse the response into a Pydantic model.

        Uses litellm's response_format with json_schema for structured output,
        then parses the JSON response into the given Pydantic model.

        Args:
            model: Model name or alias.
            messages: Chat messages.
            response_model: Pydantic model class for the response.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Returns:
            An instance of response_model.
        """
        resolved = self.resolve_model(model)

        # Build JSON schema instruction
        schema_json = response_model.model_json_schema()
        schema_instruction = (
            f"\n\nYou MUST respond with valid JSON matching this schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Respond ONLY with the JSON object, no other text."
        )

        # Append schema instruction to the last user message
        augmented_messages = list(messages)
        if augmented_messages and augmented_messages[-1]["role"] == "user":
            augmented_messages[-1] = {
                "role": "user",
                "content": augmented_messages[-1]["content"] + schema_instruction,
            }
        else:
            augmented_messages.append({"role": "user", "content": schema_instruction})

        response = self._call_with_retry(
            model=resolved,
            messages=augmented_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        raw_content = response.choices[0].message.content or "{}"

        # Strip markdown code fences if present
        cleaned = raw_content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        return response_model.model_validate_json(cleaned)

    def _call_with_retry(
        self,
        **kwargs: Any,
    ) -> Any:
        """Call litellm.completion with exponential backoff retry."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                return litellm.completion(**kwargs)
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_retryable = any(
                    code in error_str
                    for code in ["429", "500", "502", "503", "529", "timeout"]
                )

                if not is_retryable or attempt == self.max_retries - 1:
                    logger.error(
                        "LLM call failed (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries,
                        e,
                    )
                    raise

                delay = self.base_delay * (2**attempt)
                logger.warning(
                    "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    self.max_retries,
                    delay,
                    e,
                )
                time.sleep(delay)

        # Should not reach here, but satisfy type checker
        if last_error:
            raise last_error
        msg = "Retry loop exhausted unexpectedly."
        raise RuntimeError(msg)
