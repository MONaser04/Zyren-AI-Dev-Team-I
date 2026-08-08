"""
SmartGateway — The ONLY Gateway for LLM Calls
==============================================
All LLM calls go through SmartGateway. No direct litellm calls anywhere else.

Architecture:
- SmartRouter: 6-factor routing (capabilities, availability, cost, quality, manual overrides, fallback chains)
- ResilienceLayer: Circuit breakers, fallback chains, rate limits, health monitoring
- CostTracker: Budget enforcement with per-workflow tracking
- AutoModelRegistry: Provider-agnostic model registry with auto-discovery
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeVar

import litellm
litellm.telemetry = False

from pydantic import BaseModel

from gateway.cost_tracker import CostTracker
from gateway.model_registry import AutoModelRegistry, BenchmarkRegistry, ModelSpec, ModelTier, ModelStatus
from observability import trace_chat
from resilience import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    FallbackChain,
    HealthMonitor,
    RateLimiter,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ============================================================
# Request/Response Types
# ============================================================


class CompletionType(StrEnum):
    TEXT = "text"
    STRUCTURED = "structured"


@dataclass(frozen=True)
class CompletionRequest:
    """Request for LLM completion."""
    model: str
    messages: list[dict[str, str]]
    temperature: float = 0.0
    max_tokens: int = 4096
    workflow_id: str = ""
    complexity: str = "simple"
    required_capabilities: list[str] = field(default_factory=list)
    response_model: type[T] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompletionResponse:
    """Response from LLM completion."""
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingDecision:
    """Result of routing decision."""
    primary_model: ModelSpec
    fallback_chain: list[ModelSpec]
    reasoning: str
    complexity: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class RoutingCriteria:
    """Criteria for routing decisions."""
    complexity: str = "simple"
    required_capabilities: list[str] = field(default_factory=list)
    cost_budget_usd: float | None = None
    preferred_tier: ModelTier | None = None
    workflow_id: str = ""
    exclude_family: str | None = None  # For Critic diversity: exclude this model family


# ============================================================
# SmartRouter (6-Factor Routing)
# ============================================================


class SmartRouter:
    """6-factor model router: capabilities, availability, cost, quality, manual overrides, fallback chains."""

    def __init__(self, registry: AutoModelRegistry):
        self._registry = registry
        self._manual_overrides: dict[str, str] = {}  # tier -> model_id
        
        from gateway.bayesian_tracker import BayesianTracker
        from gateway.routing.calibration_engine import CalibrationEngine
        self.bayesian_tracker = BayesianTracker()
        self.calibration_engine = CalibrationEngine.get_instance(self._registry, self.bayesian_tracker)
        if self.calibration_engine:
            self.calibration_engine.start()

    def set_manual_override(self, tier: ModelTier, model_id: str) -> None:
        """Set manual model override for a tier."""
        self._manual_overrides[tier.value] = model_id
        logger.info("Manual override: %s -> %s", tier.value, model_id)

    def clear_manual_override(self, tier: ModelTier) -> None:
        """Clear manual model override for a tier."""
        self._manual_overrides.pop(tier.value, None)

    def find_optimal_model(self, criteria: RoutingCriteria) -> RoutingDecision:
        """Find optimal model based on 6-factor routing."""
        # Check manual override first
        if criteria.complexity in self._manual_overrides:
            model_id = self._manual_overrides[criteria.complexity]
            model = self._registry.get_model(model_id)
            if model:
                return RoutingDecision(
                    primary_model=model,
                    fallback_chain=[],
                    reasoning=f"Manual override for {criteria.complexity}",
                    complexity=criteria.complexity,
                )

        # Get models matching required capabilities
        candidates = self._filter_by_capabilities(criteria.required_capabilities)

        # Tier filtering removed to enable dynamic capabilities-based routing
        
        if not candidates:
            # Fallback to any available model
            candidates = self._registry.get_active_models()

        if not candidates:
            raise RuntimeError("No models available")

        # Filter by availability
        candidates = self._filter_by_availability(candidates)
        if not candidates:
            raise RuntimeError("No available models after availability filtering")

        # Filter by family exclusion (for Critic diversity)
        if criteria.exclude_family:
            bench_reg = BenchmarkRegistry()
            family_filtered = [
                m for m in candidates
                if bench_reg.get_family(m.model_id) != criteria.exclude_family
            ]
            if family_filtered:
                candidates = family_filtered
                logger.info(
                    "Excluded family '%s' for diversity, %d candidates remain",
                    criteria.exclude_family, len(candidates),
                )
            else:
                logger.warning(
                    "Cannot exclude family '%s' — no alternatives, keeping all",
                    criteria.exclude_family,
                )

        # Filter by cost budget
        if criteria.cost_budget_usd:
            candidates = self._filter_by_cost(candidates, criteria.cost_budget_usd)
            if not candidates:
                logger.warning("No models within cost budget, ignoring budget constraint")
                candidates = self._filter_by_capabilities(criteria.required_capabilities)
                candidates = self._filter_by_availability(candidates)

        # Score models
        scored = self._score_models(candidates, criteria)

        # Apply manual overrides
        scored = self._apply_manual_overrides(scored)

        # Select best + build fallback chain
        best = scored[0]
        fallbacks = self._build_fallback_chain(best, scored[1:], criteria)

        return RoutingDecision(
            primary_model=best,
            fallback_chain=fallbacks,
            reasoning=f"Selected {best.model_id} (tier={best.tier.value}, cost={best.pricing.input_per_1m_tokens if best.pricing else 'N/A'})",
            complexity=criteria.complexity,
        )

    def _filter_by_capabilities(self, required: list[str]) -> list[ModelSpec]:
        if not required:
            return list(self._registry._models.values())

        candidates = []
        for model in self._registry._models.values():
            if all(cap in model.capabilities.modalities for cap in required):
                candidates.append(model)
        return candidates

    def _filter_by_availability(self, candidates: list[ModelSpec]) -> list[ModelSpec]:
        available = []
        for model in candidates:
            if model.status == ModelStatus.ACTIVE:
                available.append(model)
        return available

    def _filter_by_cost(self, candidates: list[ModelSpec], budget: float) -> list[ModelSpec]:
        return [m for m in candidates if m.pricing and m.pricing.input_per_1m_tokens <= budget]

    def _score_models(self, candidates: list[ModelSpec], criteria: RoutingCriteria) -> list[ModelSpec]:
        """Score models predictively based on capability vs cost (RouteLLM style)."""
        complexity = criteria.complexity or "simple"

        def get_score(model: ModelSpec) -> float:
            # 1. Graph-Informed Priors
            from gateway.routing.route_profile import RouteProfile
            prior_alpha, prior_beta = RouteProfile.extract_profile_priors(model.model_id)
            
            # 2. Check if we already have strong official benchmarks to initialize the posterior
            bs = model.benchmark_scores
                    
            # 3. Use Bayesian Thompson Sampling for expected quality
            state = self.bayesian_tracker.get_state(model.model_id, prior_alpha, prior_beta)
            expected_quality = self.bayesian_tracker.sample(model.model_id, prior_alpha, prior_beta)

            # 5. Cost-Quality Utility Maximization
            # Utility = P(Quality|Query) - (w * Cost)
            cost = model.pricing.input_per_1m_tokens if model.pricing else 0.0
            w = 0.05 # Economic weight parameter (can be scaled by user budget)
            utility = expected_quality - (w * cost)
            
            return utility

        scored_candidates = sorted(candidates, key=get_score, reverse=True)
        return scored_candidates

    def _apply_manual_overrides(self, scored: list[ModelSpec]) -> list[ModelSpec]:
        for tier_name, model_id in self._manual_overrides.items():
            for i, model in enumerate(scored):
                if model.model_id == model_id:
                    scored.insert(0, scored.pop(i))
                    break
        return scored

    def _build_fallback_chain(
        self,
        primary: ModelSpec,
        alternatives: list[ModelSpec],
        criteria: RoutingCriteria,
    ) -> list[ModelSpec]:
        fallbacks = []
        primary_provider = primary.provider

        for alt in alternatives:
            if len(fallbacks) >= 3:
                break
            # Because alternatives are already sorted by Utility = Quality - w*Cost,
            # we just take the top next models that aren't the primary model.
            if alt.model_id != primary.model_id:
                fallbacks.append(alt)

        return fallbacks

    def _get_model_family(self, model_id: str) -> str:
        """Get model family using BenchmarkRegistry."""
        bench_reg = BenchmarkRegistry()
        return bench_reg.get_family(model_id)




# ============================================================
# SmartGateway
# ============================================================


class SmartGateway:
    """The ONLY gateway for LLM calls. All resilience, routing, and cost tracking here."""

    def __init__(
        self,
        registry: AutoModelRegistry | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        if registry is None:
            from gateway.model_registry import get_registry
            registry = get_registry()
        self._registry = registry
        self._router = SmartRouter(registry)
        self._cost_tracker = cost_tracker
        
        if getattr(self._router, 'calibration_engine', None):
            self._router.calibration_engine.set_gateway(self)

        # Resilience components
        self._circuit_breakers = CircuitBreakerRegistry()
        self._fallback_chain = FallbackChain()
        self._rate_limiter = RateLimiter()
        self._health_monitor = HealthMonitor()

        # Enforce hard limits per provider
        self._provider_semaphores: dict[str, asyncio.Semaphore] = {}
        # Set RPM limit for NVIDIA NIM to 40
        self._rate_limiter.set_limits("nvidia_nim_provider", RateLimitConfig(rpm=40))
        # Set RPM limit for Gemini to 15 (Free tier)
        self._rate_limiter.set_limits("gemini_provider", RateLimitConfig(rpm=15))

        # Suppress litellm noise
        litellm.suppress_debug_info = True

    @trace_chat
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Execute completion with full resilience (circuit breakers, fallbacks, rate limits)."""
        start_time = time.monotonic()

        # Find optimal model
        criteria = RoutingCriteria(
            complexity=request.complexity,
            required_capabilities=request.required_capabilities,
            cost_budget_usd=request.metadata.get("cost_budget"),
            workflow_id=request.workflow_id,
            exclude_family=request.metadata.get("exclude_family"),
        )
        decision = self._router.find_optimal_model(criteria)

        if request.model:
            requested_model = self._registry.get_model(request.model) or self._registry.resolve_alias(request.model)
            if requested_model:
                # Rebuild fallback chain around the explicitly requested model
                # Remove the requested model from the list of ALL active models to form alternatives
                all_models = self._registry.get_active_models()
                alternatives = [m for m in all_models if m.model_id != requested_model.model_id]
                # Re-score alternatives using the original criteria
                scored_alts = self._router._score_models(alternatives, criteria)
                fallbacks = self._router._build_fallback_chain(requested_model, scored_alts, criteria)
                
                decision = RoutingDecision(
                    primary_model=requested_model,
                    fallback_chain=fallbacks,
                    reasoning=f"Explicitly requested model {requested_model.model_id}",
                    complexity=decision.complexity
                )

        # Try primary model
        try:
            return await self._execute_with_resilience(
                decision.primary_model,
                request,
                start_time,
            )
        except Exception as e:
            logger.warning("Primary model %s failed: %s", decision.primary_model.model_id, e)

        # Try fallback chain
        for fallback in decision.fallback_chain:
            try:
                logger.info("Trying fallback: %s", fallback.model_id)
                return await self._execute_with_resilience(fallback, request, start_time)
            except Exception as e:
                logger.warning("Fallback %s failed: %s", fallback.model_id, e)

        # All failed
        raise RuntimeError(f"All models failed for request {request.workflow_id}")

    async def complete_structured(
        self,
        request: CompletionRequest,
        response_model: type[BaseModel] | None = None,
    ) -> BaseModel:
        """Execute structured completion with schema validation."""
        target_model = response_model or request.response_model
        if not target_model:
            raise ValueError("response_model required for structured completion")

        # Add schema to messages
        schema_json = target_model.model_json_schema()
        schema_instruction = (
            "\n\nCRITICAL INSTRUCTION: You MUST format your response as a valid JSON object that conforms to the following JSON schema:\n"
            f"```json\n{json.dumps(schema_json, indent=2)}\n```\n"
            "Do NOT return the schema itself. You must return a concrete JSON instance containing the actual data! Respond ONLY with the JSON object."
        )

        augmented_messages = list(request.messages)
        if augmented_messages and augmented_messages[-1]["role"] == "user":
            augmented_messages[-1] = {
                "role": "user",
                "content": augmented_messages[-1]["content"] + schema_instruction,
            }
        else:
            augmented_messages.append({"role": "user", "content": schema_instruction})

        new_request = CompletionRequest(
            model=request.model,
            messages=augmented_messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            workflow_id=request.workflow_id,
            complexity=request.complexity,
            required_capabilities=request.required_capabilities + ["structured_output"],
            metadata=request.metadata,
        )

        last_error = None
        for attempt in range(3):
            try:
                response = await self.complete(new_request)
                
                cleaned = response.content.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
                parsed = {}
                
                # Try direct parse first
                try:
                    parsed = json.loads(cleaned)
                except json.JSONDecodeError:
                    # Extract first JSON object from response
                    start = cleaned.find("{")
                    if start == -1:
                        logger.warning(f"No JSON found. Raw LLM output: {response.content}")
                        raise ValueError(f"No JSON object found in response: {cleaned[:100]}")
                    stack = []
                    end = start
                    in_string = False
                    escape = False
                    for i, ch in enumerate(cleaned[start:], start):
                        if not in_string:
                            if ch == "{":
                                stack.append("}")
                            elif ch == "[":
                                stack.append("]")
                            elif ch == "}" or ch == "]":
                                if stack and stack[-1] == ch:
                                    stack.pop()
                                if not stack:
                                    end = i + 1
                                    break
                            elif ch == '"':
                                in_string = True
                        else:
                            if escape:
                                escape = False
                            elif ch == '\\':
                                escape = True
                            elif ch == '"':
                                in_string = False

                    if stack:
                        suffix = ""
                        if in_string:
                            suffix += '"'
                        while stack:
                            suffix += stack.pop()
                        cleaned_obj = cleaned[start:] + suffix
                    else:
                        cleaned_obj = cleaned[start:end]
                    
                    try:
                        parsed = json.loads(cleaned_obj)
                    except json.JSONDecodeError as err:
                        if "}" not in suffix:
                            # If we added closing braces and it still failed, it's definitely invalid
                            raise ValueError(f"JSONDecodeError: {str(err)} for extracted string: {cleaned_obj[:100]}...")
                        else:
                            raise err
                
                try:
                    return target_model.model_validate(parsed, strict=False)
                except Exception as val_err:
                    logger.warning("Pydantic validation failed for %s: %s. Attempting fallback...", target_model.__name__, val_err)
                    raise val_err

            except Exception as e:
                last_error = e
                logger.warning("Structured parse/execution failed attempt %d: %s", attempt + 1, e)
                
                # If we got a response but it failed parsing, add it to history and ask for a fix
                if 'response' in locals() and response:
                    new_messages = list(new_request.messages)
                    new_messages.append({"role": "assistant", "content": response.content})
                    new_messages.append({
                        "role": "user", 
                        "content": f"Your previous response failed validation: {str(e)}\nCRITICAL: You must fix this and return ONLY a valid JSON object matching the schema."
                    })
                    new_request = CompletionRequest(
                        model=new_request.model,
                        messages=new_messages,
                        temperature=new_request.temperature,
                        max_tokens=new_request.max_tokens,
                        workflow_id=new_request.workflow_id,
                        complexity=new_request.complexity,
                        required_capabilities=new_request.required_capabilities,
                        metadata=new_request.metadata,
                    )
        
        # If we exhausted retries, try safe fallback if it's RoutingDecision
        logger.error("Failed to parse structured response after 3 attempts: %s", last_error)
        if target_model.__name__ == "RoutingDecision":
            from contracts.schemas import TaskComplexity, RoutingDecision, TargetDomain, SWEComplexityDecision
            return RoutingDecision(
                domain=TargetDomain.SOFTWARE_ENGINEERING,
                confidence=0.5,
                safe_fallback=True,
                reasoning="Safe fallback routing due to model parsing error",
                fast_lane=False,
                swe_sub=SWEComplexityDecision(
                    complexity=TaskComplexity.MEDIUM,
                    confidence=0.5,
                    safe_fallback=True,
                    reasoning="Fallback SE sub-route",
                    fast_lane=False,
                ),
            )
        
        raise last_error

    # ----------------------------------------------------------
    # Resilience Execution
    # ----------------------------------------------------------

    async def _execute_with_resilience(
        self,
        model: ModelSpec,
        request: CompletionRequest,
        start_time: float,
    ) -> CompletionResponse:
        model_id = model.model_id
        provider = model_id.split("/")[0] if "/" in model_id else "unknown"

        # Check circuit breaker
        breaker = self._circuit_breakers.get_or_create(model_id)
        if not breaker.is_available():
            retry_after = breaker.config.timeout - (time.monotonic() - breaker._last_failure_time)
            raise RuntimeError(f"Circuit breaker OPEN for {model_id}. Retry after {retry_after:.0f}s")

        # Acquire rate limit per model and provider
        await self._rate_limiter.acquire(model_id, tokens=request.max_tokens)
        if provider == "nvidia_nim":
            # NVIDIA NIM allows max 40 requests per minute across the provider
            await self._rate_limiter.acquire("nvidia_nim_provider", tokens=1)
            
            # Enforce max 3 concurrent requests
            if provider not in self._provider_semaphores:
                self._provider_semaphores[provider] = asyncio.Semaphore(3)
            sema = self._provider_semaphores[provider]
        elif provider in ("gemini", "google"):
            # Gemini Free Tier allows 15 RPM
            await self._rate_limiter.acquire("gemini_provider", tokens=1)
            if provider not in self._provider_semaphores:
                self._provider_semaphores[provider] = asyncio.Semaphore(2)
            sema = self._provider_semaphores[provider]
        else:
            sema = None

        # Execute with circuit breaker protection and concurrency control
        try:
            if sema:
                await sema.acquire()
            try:
                response_fmt = {"type": "json_object"} if "structured_output" in request.required_capabilities else None
                response = await breaker.call(
                    self._call_litellm,
                    model_id,
                    request.messages,
                    request.temperature,
                    request.max_tokens,
                    response_fmt,
                )
            finally:
                if sema:
                    sema.release()
        except Exception as e:
            # Record failure in health monitor
            self._health_monitor.record_failure(model_id, e)
            # Set cooldown in fallback chain
            self._fallback_chain.set_cooldown(model_id)
            raise

        # Record success
        latency_ms = (time.monotonic() - start_time) * 1000
        self._health_monitor.record_success(model_id, latency_ms)

        # Track cost
        usage = getattr(response, "usage", None)
        if self._cost_tracker and request.workflow_id:
            if usage:
                self._cost_tracker.record_usage(
                    workflow_id=request.workflow_id,
                    model=model_id,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0),
                    completion_tokens=getattr(usage, "completion_tokens", 0),
                )

        return CompletionResponse(
            content=response.choices[0].message.content or "",
            model=model_id,
            provider=model.provider,
            usage={
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
            },
            latency_ms=latency_ms,
            finish_reason=getattr(response.choices[0], "finish_reason", "stop"),
        )

    async def _call_litellm(
        self,
        model_id: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        response_format: dict | None = None,
    ):
        # Extract provider prefix if present
        if "/" in model_id:
            provider_prefix, model_name = model_id.split("/", 1)
            if provider_prefix == "google":
                provider_prefix = "gemini"
            litellm_model = f"{provider_prefix}/{model_name}"
        else:
            litellm_model = model_id

        kwargs = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": 300.0, # 5 full minutes for large contexts or queued cloud API tiers
            "num_retries": 0, # Disable internal retries to fail fast if it hits the timeout
        }
        if response_format:
            kwargs["response_format"] = response_format
        return await litellm.acompletion(**kwargs)

    # ----------------------------------------------------------
    # Manual Override Handlers (from Liaison)
    # ----------------------------------------------------------

    async def handle_manual_model_change(self, command: dict) -> dict:
        """Handle manual model changes from Liaison agent.

        Supports: add_model, set_default, disable_model, enable_model, disable_provider.
        """
        action = command.get("action")
        model_id = command.get("model_id")
        tier = command.get("tier")
        provider = command.get("provider")
        reason = command.get("reason", "")

        if action == "add_model":
            # Build spec from command data and register
            spec_data = command.get("spec")
            if spec_data:
                from gateway.model_registry import ModelSpec
                spec = ModelSpec(**spec_data)
                self._registry.manual_add_model(spec, added_by="liaison")
                return {"status": "ok", "message": f"Added model {spec.model_id}"}
            return {"status": "error", "message": "Missing spec data for add_model"}

        elif action == "set_default":
            if tier and model_id:
                self._router.set_manual_override(ModelTier(tier), model_id)
                return {"status": "ok", "message": f"Set {model_id} as default for {tier}"}
            return {"status": "error", "message": "Missing tier or model_id for set_default"}

        elif action == "disable_model":
            if model_id:
                success = self._registry.manual_disable_model(model_id, reason, disabled_by="liaison")
                if success:
                    # Also open the circuit breaker for this model
                    breaker = self._circuit_breakers.get_or_create(model_id)
                    breaker.force_open()
                    return {"status": "ok", "message": f"Disabled model {model_id}: {reason}"}
                return {"status": "error", "message": f"Model {model_id} not found"}
            return {"status": "error", "message": "Missing model_id for disable_model"}

        elif action == "enable_model":
            if model_id:
                success = self._registry.manual_enable_model(model_id, enabled_by="liaison")
                if success:
                    # Close the circuit breaker
                    breaker = self._circuit_breakers.get(model_id)
                    if breaker:
                        breaker.force_close()
                    return {"status": "ok", "message": f"Enabled model {model_id}"}
                return {"status": "error", "message": f"Model {model_id} not found"}
            return {"status": "error", "message": "Missing model_id for enable_model"}

        elif action == "disable_provider":
            if provider:
                count = self._registry.disable_provider_models(provider, reason, disabled_by="liaison")
                # Open circuit breakers for all models from this provider
                for model in self._registry.get_by_provider(provider):
                    breaker = self._circuit_breakers.get_or_create(model.model_id)
                    breaker.force_open()
                return {"status": "ok", "message": f"Disabled {count} models from provider {provider}"}
            return {"status": "error", "message": "Missing provider for disable_provider"}

        logger.warning("Unknown action: %s", action)
        return {"status": "error", "message": f"Unknown action: {action}"}

    # ----------------------------------------------------------
    # Introspection
    # ----------------------------------------------------------

    def get_routing_stats(self) -> dict[str, Any]:
        return {
            "registry": self._registry.get_stats(),
            "circuit_breakers": self._circuit_breakers.get_all_status(),
            "fallback_chains": {
                k: v.get_chain_status(k) for k in self._fallback_chain._chains
            },
            "rate_limits": self._rate_limiter.get_all_status(),
            "health": self._health_monitor.get_status_summary(),
            "manual_overrides": self._router._manual_overrides,
        }