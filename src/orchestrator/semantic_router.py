"""
Semantic Router — Multi-Department Intent Classifier
======================================================

Evaluates incoming payloads and routes to one of three primary domains:

    1. Software Engineering — technical tasks, coding, architecture.
       Includes a complexity sub-route (Fast Lane vs. Full SDLC).
    2. Deep Research — open web research, non-technical data gathering,
       social statistics.
    3. Media Production — audio, image, and video generation/processing.

Confidence-aware routing is preserved: below threshold the decision falls
back to the safe full pipeline (Software Engineering domain only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from contracts.schemas import (
    RoutingDecision,
    SWEComplexityDecision,
    TargetDomain,
    TaskComplexity,
)
from gateway.llm_client import LLMClient

if TYPE_CHECKING:
    from state.store import EventStore
    from state.events import EventType


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True)
class SemanticRouterConfig:
    model: str = "fast"
    confidence_threshold: float = 0.7  # below → safe_fallback=True
    system_prompt_file: str = "config/agents/router.yaml"
    domain_keywords: dict[str, list[str]] = field(default_factory=dict)


# ============================================================
# Semantic Router
# ============================================================


class SemanticRouter:
    """Multi-department intent classifier with SE complexity sub-routing."""

    def __init__(
        self,
        llm_client: LLMClient,
        config: SemanticRouterConfig | None = None,
    ) -> None:
        self._llm = llm_client
        self._config = config or SemanticRouterConfig()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def classify(
        self,
        task_description: str,
        *,
        workflow_id: str = "",
    ) -> RoutingDecision:
        """Classify the task into a target domain and return a routing decision.

        For the Software Engineering domain, an additional complexity
        sub-classification determines Fast Lane vs. Full SDLC routing.
        """
        prompt = self._build_domain_prompt(task_description)
        decision = self._llm.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=RoutingDecision,
            model=self._config.model,
            temperature=0.0,
            max_tokens=1024,
            workflow_id=workflow_id,
        )

        safe_fallback = decision.confidence < self._config.confidence_threshold

        # ── Domain-level fallback ──
        # Low-confidence domain classification defaults to Software Engineering
        # to guarantee the safest, most structured pipeline.
        resolved_domain = decision.domain
        if safe_fallback and resolved_domain != TargetDomain.SOFTWARE_ENGINEERING:
            resolved_domain = TargetDomain.SOFTWARE_ENGINEERING

        # ── Sub-routing for Software Engineering ──
        swe_sub: SWEComplexityDecision | None = None
        fast_lane = False
        if resolved_domain == TargetDomain.SOFTWARE_ENGINEERING:
            swe_sub = self._classify_swe_complexity(
                task_description,
                workflow_id=workflow_id,
            )
            # Apply confidence-aware fallback within SE
            swe_safe = swe_sub.confidence < self._config.confidence_threshold
            if swe_safe and swe_sub.complexity == TaskComplexity.SIMPLE:
                swe_sub = SWEComplexityDecision(
                    complexity=TaskComplexity.MEDIUM,
                    confidence=swe_sub.confidence,
                    safe_fallback=True,
                    reasoning=swe_sub.reasoning + " (low confidence → safe fallback)",
                    fast_lane=False,
                )
            else:
                swe_sub = SWEComplexityDecision(
                    complexity=swe_sub.complexity,
                    confidence=swe_sub.confidence,
                    safe_fallback=swe_safe,
                    reasoning=swe_sub.reasoning,
                    fast_lane=(
                        swe_sub.complexity == TaskComplexity.SIMPLE and not swe_safe
                    ),
                )
            fast_lane = swe_sub.fast_lane

        return RoutingDecision(
            domain=resolved_domain,
            confidence=decision.confidence,
            safe_fallback=safe_fallback,
            reasoning=decision.reasoning,
            fast_lane=fast_lane,
            swe_sub=swe_sub,
        )

    # ----------------------------------------------------------
    # Internal: SE Complexity Sub-classification
    # ----------------------------------------------------------

    def _classify_swe_complexity(
        self,
        task_description: str,
        *,
        workflow_id: str = "",
    ) -> SWEComplexityDecision:
        """Run the legacy complexity classification for SE tasks."""
        prompt = self._build_complexity_prompt(task_description)
        return self._llm.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=SWEComplexityDecision,
            model=self._config.model,
            temperature=0.0,
            max_tokens=1024,
            workflow_id=workflow_id,
        )

    # ----------------------------------------------------------
    # Prompt Builders
    # ----------------------------------------------------------

    @staticmethod
    def _build_domain_prompt(task: str) -> str:
        return (
            "You are a multi-department intent classifier.\n\n"
            "Evaluate the task below and classify it into EXACTLY ONE domain.\n\n"
            f"Task: {task}\n\n"
            "DOMAINS:\n"
            "  software_engineering — coding, debugging, architecture, DevOps, "
            "infrastructure, API design, database queries, any technical "
            "software task.\n"
            "  deep_research — open web research, market analysis, competitive "
            "intelligence, social statistics, non-technical data gathering, "
            "literature review, fact-finding.\n"
            "  media_production — generating or processing audio, images, video, "
            "3D assets, music composition, voice synthesis, graphic design, "
            "video editing.\n\n"
            "Respond ONLY with a JSON object, no other text:\n"
            '{"domain": "software_engineering"|"deep_research"|"media_production", '
            '"confidence": 0.0-1.0, '
            '"safe_fallback": false, '
            '"reasoning": "brief reason", '
            '"fast_lane": false, '
            '"swe_sub": null}'
        )

    @staticmethod
    def _build_complexity_prompt(task: str) -> str:
        return (
            "Classify this software engineering task's complexity.\n\n"
            f"Task: {task}\n\n"
            "SIMPLE: single function, bug fix, small refactor.\n"
            "MEDIUM: multi-file change, new module.\n"
            "COMPLEX: greenfield project, major refactor, multi-system.\n\n"
            "Respond ONLY with a JSON object, no other text:\n"
            '{"complexity": "simple"|"medium"|"complex", "confidence": 0.0-1.0, '
            '"safe_fallback": false, "reasoning": "brief reason", "fast_lane": true|false}'
        )