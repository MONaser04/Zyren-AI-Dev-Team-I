"""
LLM Client — Thin Wrapper Delegating to SmartGateway
======================================================

Phase 3 Refactored: Now delegates ALL calls to SmartGateway.
SmartGateway is THE ONLY gateway — no direct litellm calls here.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from gateway.cost_tracker import BudgetExceededError, CostTracker
from gateway.model_registry import ModelSpec
from gateway.smart_gateway import CompletionRequest, SmartGateway
from observability import trace_chat

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


import threading

_shared_loop = asyncio.new_event_loop()
def _run_shared_loop():
    asyncio.set_event_loop(_shared_loop)
    _shared_loop.run_forever()

_shared_thread = threading.Thread(target=_run_shared_loop, daemon=True)
_shared_thread.start()

def _run_sync(coro):
    """
    Safely runs an async coroutine synchronously.
    Uses a dedicated background event loop to prevent LiteLLM global queue crashes.
    """
    future = asyncio.run_coroutine_threadsafe(coro, _shared_loop)
    return future.result()


class LLMClient:
    """
    Thin wrapper that delegates to SmartGateway.

    All resilience (circuit breakers, fallbacks, rate limits, health monitoring),
    routing (6-factor decision), and cost tracking are handled by SmartGateway.

    This class provides a simple, stable interface for agents.
    """

    def __init__(
        self,
        smart_gateway: SmartGateway | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        """
        Initialize the LLM client.

        Args:
            smart_gateway: Optional SmartGateway instance. Creates default if None.
            cost_tracker: Optional CostTracker for per-workflow budget enforcement.
        """
        if smart_gateway is None:
            from gateway.smart_gateway import SmartGateway
            smart_gateway = SmartGateway(cost_tracker=cost_tracker)
        self._gateway = smart_gateway
        self._cost_tracker = cost_tracker

    # ----------------------------------------------------------
    # Model Resolution / Routing (delegated to gateway)
    # ----------------------------------------------------------

    def resolve_model(self, model_or_alias: str) -> str:
        """Resolve a model alias via the gateway's registry."""
        spec = self._gateway._registry.resolve_alias(model_or_alias)
        if spec:
            return spec.model_id
        return model_or_alias

    def route_by_complexity(self, complexity: str) -> str:
        """Route dynamically based on capabilities and cost using SmartRouter."""
        from gateway.smart_gateway import RoutingCriteria
        
        criteria = RoutingCriteria(complexity=complexity)
        try:
            decision = self._gateway._router.find_optimal_model(criteria)
            return decision.primary_model.model_id
        except Exception as e:
            logger.warning("Routing failed for complexity %s: %s", complexity, e)
            return "openai/gpt-4o-mini"

    # ----------------------------------------------------------
    # Public API — complete_text / complete_structured
    # ----------------------------------------------------------

    async def async_complete_text(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        workflow_id: str = "",
        **kwargs: Any,
    ) -> str:
        request = CompletionRequest(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            workflow_id=workflow_id,
            **kwargs,
        )
        response = await self._gateway.complete(request)
        return response.content

    @trace_chat("frontier")
    def complete_text(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        workflow_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Call an LLM and return plain text (synchronous)."""
        return _run_sync(
            self.async_complete_text(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                workflow_id=workflow_id,
                **kwargs,
            )
        )

    async def async_complete_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        workflow_id: str = "",
        **kwargs: Any,
    ) -> T:
        request = CompletionRequest(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            workflow_id=workflow_id,
            response_model=response_model,
            **kwargs,
        )
        return await self._gateway.complete_structured(request)

    @trace_chat("frontier")
    def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        workflow_id: str = "",
        **kwargs: Any,
    ) -> T:
        """Call an LLM and parse the response into a Pydantic model (synchronous)."""
        return _run_sync(
            self.async_complete_structured(
                model=model,
                messages=messages,
                response_model=response_model,
                temperature=temperature,
                max_tokens=max_tokens,
                workflow_id=workflow_id,
                **kwargs,
            )
        )

    # ----------------------------------------------------------
    # Circuit Breaker (delegated to gateway)
    # ----------------------------------------------------------

    def open_circuit(self, workflow_id: str) -> None:
        """Manually open the circuit breaker for a workflow."""
        self._gateway._circuit_breakers.get_or_create(workflow_id).force_open()
        logger.warning("Circuit breaker manually opened for workflow %s.", workflow_id)

    def close_circuit(self, workflow_id: str) -> None:
        """Close the circuit breaker (human resolved the issue)."""
        breaker = self._gateway._circuit_breakers.get(workflow_id)
        if breaker:
            breaker.force_close()
        logger.info("Circuit breaker closed for workflow %s.", workflow_id)

    def is_circuit_open(self, workflow_id: str) -> bool:
        """Check circuit breaker status."""
        breaker = self._gateway._circuit_breakers.get(workflow_id)
        return breaker is not None and not breaker.is_available()

    # ----------------------------------------------------------
    # Introspection
    # ----------------------------------------------------------

    @property
    def cost_tracker(self) -> CostTracker | None:
        """Return the cost tracker if set."""
        return self._cost_tracker

    def get_routing_stats(self) -> dict[str, Any]:
        """Get routing and resilience statistics from gateway."""
        return self._gateway.get_routing_stats()