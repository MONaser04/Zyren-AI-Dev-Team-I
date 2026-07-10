"""
LLM Client — Thin Wrapper Around LiteLLM (Phase 3 Upgraded + Phase 4 Instrumented)
==================================================================================

Provides a consistent interface for calling LLMs with:
- Model alias resolution (frontier, fast, critic)
- Structured output via Pydantic models
- Exponential backoff retry with jitter
- Cost tracking per workflow with hard caps
- Circuit breaker pattern (fail-fast on budget exceeded)
- Fallback chains on repeated failures
- Complexity-based routing (cheap for simple, frontier for hard)
- OpenTelemetry instrumentation (Phase 4): chat spans + token metrics

READ Phase 3 deliverable:
  'Route every model call through a self-hosted LiteLLM proxy.'
  'Hard per-workflow cost caps.'
  'Fallback chains + cooldowns on 429/5xx.'
  'Complexity-based routing.'
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel

from gateway.cost_tracker import BudgetExceededError, CostTracker, UsageSnapshot
from observability import trace_chat

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ============================================================
# Default Model Aliases
# ============================================================

DEFAULT_MODEL_MAP: dict[str, str] = {
    "frontier": "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b",
    "fast": "nvidia_nim/minimaxai/minimax-m3",
    "critic": "nvidia_nim/google/gemma-4-31b-it",
    "fallback": "nvidia_nim/google/gemma-4-31b-it",
}


# ============================================================
# Circuit Breaker Error
# ============================================================


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open — LLM calls are blocked."""


# ============================================================
# LLM Client (Phase 3 Upgraded + Phase 4 Instrumented)
# ============================================================


class LLMClient:
    """Wrapper around litellm with cost tracking, fallback, and circuit breaker.

    Phase 3 additions:
    - CostTracker integration (per-workflow caps)
    - Complexity-based routing
    - Fallback chains with cooldown on 429/5xx
    - Circuit breaker (fail-fast on budget exceeded)
    - Jitter added to exponential backoff

    Phase 4 additions:
    - OpenTelemetry instrumentation via trace_chat decorator
    """

    def __init__(
        self,
        model_map: dict[str, str] | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        """Initialize the LLM client.

        Args:
            model_map: Map of alias → litellm model string.
            max_retries: Maximum number of retries on transient errors.
            base_delay: Base delay for exponential backoff (seconds).
            cost_tracker: Optional CostTracker for per-workflow budget enforcement.
        """
        self.model_map = model_map or dict(DEFAULT_MODEL_MAP)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._cost_tracker = cost_tracker

        # Fallback chain: model → fallback_model
        self._fallback_chain: dict[str, str] = {
            "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b": "nvidia_nim/google/gemma-4-31b-it",
            "nvidia_nim/minimaxai/minimax-m3": "nvidia_nim/google/gemma-4-31b-it",
        }

        # Cooldown state for models that return 429
        self._cooldowns: dict[str, float] = {}
        self._cooldown_duration = 30.0  # seconds

        # Circuit breaker state
        self._breaker_open: dict[str, bool] = {}  # workflow_id → open?

        # Suppress litellm noise
        litellm.suppress_debug_info = True

    # ----------------------------------------------------------
    # Model Resolution / Routing
    # ----------------------------------------------------------

    def resolve_model(self, model_or_alias: str) -> str:
        """Resolve a model alias to its full litellm model string."""
        return self.model_map.get(model_or_alias, model_or_alias)

    def route_by_complexity(self, complexity: str) -> str:
        """Route tasks by complexity to appropriate model tier.

        Args:
            complexity: "simple", "medium", "hard", or "critical".

        Returns:
            Resolved model string for the complexity tier.
        """
        _COMPLEXITY_MAP = {
            "simple": self.resolve_model("fast"),
            "medium": self.resolve_model("frontier"),
            "hard": self.resolve_model("frontier"),
            "critical": self.resolve_model("critic"),
        }
        return _COMPLEXITY_MAP.get(complexity, self.resolve_model("fast"))

    # ----------------------------------------------------------
    # Public API — complete_text / complete_structured
    # ----------------------------------------------------------

    @trace_chat("frontier")
    def complete_text(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        workflow_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Call an LLM and return plain text.

        Args:
            model: Model name or alias.
            messages: Chat messages.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            workflow_id: Optional workflow ID for cost tracking.

        Returns:
            The generated text content.
        """
        resolved = self.resolve_model(model)

        # Circuit breaker check
        if workflow_id:
            self._check_circuit_breaker(workflow_id)

        response = self._call_with_retry(
            model=resolved,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            workflow_id=workflow_id,
            **kwargs,
        )
        content: str = response.choices[0].message.content or ""
        return content

    @trace_chat("frontier")
    def complete_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        workflow_id: str = "",
        **kwargs: Any,
    ) -> T:
        """Call an LLM and parse the response into a Pydantic model.

        Args:
            model: Model name or alias.
            messages: Chat messages.
            response_model: Pydantic model class for the response.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            workflow_id: Optional workflow ID for cost tracking.

        Returns:
            An instance of response_model.
        """
        resolved = self.resolve_model(model)

        # Circuit breaker check
        if workflow_id:
            self._check_circuit_breaker(workflow_id)

        # Build JSON schema instruction
        schema_json = response_model.model_json_schema()
        schema_instruction = (
            "\n\nYou MUST respond with valid JSON matching this schema:\n"
            f"```json\n{schema_json}\n```\n"
            "Respond ONLY with the JSON object, no other text."
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
            workflow_id=workflow_id,
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

        import json
        try:
            parsed = json.loads(cleaned, strict=False)
            return response_model.model_validate(parsed)
        except Exception:
            return response_model.model_validate_json(cleaned)

    # ----------------------------------------------------------
    # Core — Retry + Fallback + Cost Tracking
    # ----------------------------------------------------------

    def _call_with_retry(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        workflow_id: str = "",
        **kwargs: Any,
    ) -> Any:
        """Call litellm.completion with exponential backoff + jitter + fallback.

        Phase 3 features:
        - Jitter: random delay (±25%) added to backoff to prevent retry storms.
        - Cooldown: models returning 429 are temporarily bypassed.
        - Fallback: after max_retries/2 failures, switch to fallback model.
        - Cost tracking: if cost_tracker is set, records usage and enforces cap.
        """
        current_model = model
        last_error: Exception | None = None
        fallback_attempted = False

        for attempt in range(self.max_retries):
            try:
                # Check model cooldown (429 handling)
                if current_model in self._cooldowns:
                    if time.monotonic() < self._cooldowns[current_model]:
                        # Model is in cooldown — use fallback
                        fb = self._get_fallback(current_model)
                        logger.info(
                            "Model %s in cooldown, switching to fallback: %s",
                            current_model,
                            fb,
                        )
                        current_model = fb

                response = litellm.completion(
                    model=current_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )

                # Record cost
                if self._cost_tracker and workflow_id:
                    usage = getattr(response, "usage", None)
                    if usage:
                        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                        try:
                            self._cost_tracker.record_usage(
                                workflow_id=workflow_id,
                                model=current_model,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                            )
                        except BudgetExceededError:
                            logger.error(
                                "Budget exceeded for workflow %s — opening circuit breaker.",
                                workflow_id,
                            )
                            self._breaker_open[workflow_id] = True
                            raise

                return response

            except BudgetExceededError:
                raise  # Re-raise immediately — no retry on budget

            except Exception as e:
                last_error = e
                error_str = str(e)

                # Detect 429 → put model in cooldown
                if "429" in error_str:
                    self._cooldowns[current_model] = (
                        time.monotonic() + self._cooldown_duration
                    )
                    logger.warning(
                        "Model %s rate-limited (429), cooldown for %.0fs.",
                        current_model,
                        self._cooldown_duration,
                    )

                # Determine if retryable
                is_retryable = any(
                    code in error_str
                    for code in ["429", "500", "502", "503", "529", "timeout"]
                )

                if not is_retryable or attempt == self.max_retries - 1:
                    logger.error(
                        "LLM call failed (attempt %d/%d, model=%s): %s",
                        attempt + 1,
                        self.max_retries,
                        current_model,
                        e,
                    )
                    raise

                # Fallback at halfway point
                if attempt >= self.max_retries // 2 and not fallback_attempted:
                    fb = self._get_fallback(current_model)
                    if fb != current_model:
                        logger.info(
                            "Attempt %d/%d — switching from %s to fallback %s.",
                            attempt + 1,
                            self.max_retries,
                            current_model,
                            fb,
                        )
                        current_model = fb
                        fallback_attempted = True

                # Exponential backoff with jitter
                base = self.base_delay * (2**attempt)
                jitter = base * random.uniform(-0.25, 0.25)  # ±25%
                delay = max(0.1, base + jitter)

                logger.warning(
                    "LLM call failed (attempt %d/%d, model=%s), retrying in %.1fs: %s",
                    attempt + 1,
                    self.max_retries,
                    current_model,
                    delay,
                    e,
                )
                time.sleep(delay)

        # Should not reach here, but satisfy type checker
        if last_error:
            raise last_error
        msg = "Retry loop exhausted unexpectedly."
        raise RuntimeError(msg)

    def _get_fallback(self, model: str) -> str:
        """Get the next model in the fallback chain."""
        return self._fallback_chain.get(
            model,
            self.resolve_model("fallback"),
        )

    # ----------------------------------------------------------
    # Circuit Breaker
    # ----------------------------------------------------------

    def _check_circuit_breaker(self, workflow_id: str) -> None:
        """Check if the circuit breaker is open for this workflow.

        Opens when:
        - BudgetExceededError was raised (cost cap hit).
        - Manually opened via open_circuit().

        Raises:
            CircuitBreakerOpenError: If the circuit is open.
        """
        if self._breaker_open.get(workflow_id, False):
            msg = (
                f"Circuit breaker OPEN for workflow '{workflow_id}'. "
                f"All LLM calls are blocked. Human intervention required."
            )
            logger.error(msg)
            raise CircuitBreakerOpenError(msg)

    def open_circuit(self, workflow_id: str) -> None:
        """Manually open the circuit breaker for a workflow."""
        self._breaker_open[workflow_id] = True
        logger.warning("Circuit breaker manually opened for workflow %s.", workflow_id)

    def close_circuit(self, workflow_id: str) -> None:
        """Close the circuit breaker (human resolved the issue)."""
        self._breaker_open[workflow_id] = False
        logger.info("Circuit breaker closed for workflow %s.", workflow_id)

    def is_circuit_open(self, workflow_id: str) -> bool:
        """Check circuit breaker status."""
        return self._breaker_open.get(workflow_id, False)

    # ----------------------------------------------------------
    # Introspection
    # ----------------------------------------------------------

    @property
    def cost_tracker(self) -> CostTracker | None:
        """Return the cost tracker if set."""
        return self._cost_tracker