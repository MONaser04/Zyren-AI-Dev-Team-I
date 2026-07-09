"""
Semantic Router — Fast Complexity Classification (Phase 4)
===========================================================

A lightweight LLM call (on 'fast' model) that classifies incoming
task complexity with confidence-aware routing.

README §4.2: "confidence-aware routing — below threshold it falls
back to the safe full pipeline."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from contracts.schemas import RoutingDecision, TaskComplexity
from gateway.llm_client import LLMClient

if TYPE_CHECKING:
    from state.store import EventStore
    from state.events import EventType


@dataclass(frozen=True)
class SemanticRouterConfig:
    model: str = "fast"
    confidence_threshold: float = 0.7  # below → safe_fallback=True
    system_prompt_file: str = "config/agents/router.yaml"


class SemanticRouter:
    """Classify task complexity and emit a RoutingDecision."""

    def __init__(
        self,
        llm_client: LLMClient,
        config: SemanticRouterConfig | None = None,
    ) -> None:
        self._llm = llm_client
        self._config = config or SemanticRouterConfig()

    def classify(
        self,
        task_description: str,
        *,
        workflow_id: str = "",
    ) -> RoutingDecision:
        """Classify the task and return a routing decision."""
        prompt = self._build_prompt(task_description)
        decision = self._llm.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=RoutingDecision,
            model=self._config.model,
            temperature=0.0,
            workflow_id=workflow_id,
        )
        # Apply confidence-aware fallback
        safe_fallback = decision.confidence < self._config.confidence_threshold
        if safe_fallback and decision.complexity == TaskComplexity.SIMPLE:
            # Downgrade SIMPLE → MEDIUM when unsure
            decision = RoutingDecision(
                complexity=TaskComplexity.MEDIUM,
                confidence=decision.confidence,
                safe_fallback=True,
                reasoning=decision.reasoning + " (low confidence → safe fallback)",
                fast_lane=False,
            )
        return RoutingDecision(
            complexity=decision.complexity,
            confidence=decision.confidence,
            safe_fallback=safe_fallback,
            reasoning=decision.reasoning,
            fast_lane=(decision.complexity == TaskComplexity.SIMPLE and not safe_fallback),
        )

    def _build_prompt(self, task: str) -> str:
        return (
            f"Task: {task}\n\n"
            "Classify as SIMPLE / MEDIUM / COMPLEX with confidence (0-1).\n"
            "SIMPLE: single function, bug fix, small refactor, isolated change.\n"
            "MEDIUM: multi-file change, new module, moderate architecture impact.\n"
            "COMPLEX: greenfield project, cross-cutting concerns, major refactor,\n"
            "       security-critical, multi-system integration.\n\n"
            "Consider: lines of code affected, number of files, architectural scope,\n"
            "domain expertise needed, risk level.\n\n"
            "If uncertain, confidence < 0.7.\n"
            "Output JSON with keys: complexity, confidence, reasoning."
        )