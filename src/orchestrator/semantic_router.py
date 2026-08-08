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
from pydantic import BaseModel, Field

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

class RoutingLLMResponse(BaseModel):
    """LLM response schema without nested Pydantic models to avoid $defs validation errors."""
    domain: TargetDomain
    confidence: float
    safe_fallback: bool
    reasoning: str
    fast_lane: bool


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
        decision_llm = self._llm.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=RoutingLLMResponse,
            model=self._config.model,
            temperature=0.0,
            max_tokens=1024,
            workflow_id=workflow_id,
        )

        safe_fallback = decision_llm.confidence < self._config.confidence_threshold

        # ── Domain-level fallback ──
        # Low-confidence domain classification defaults to Software Engineering
        # to guarantee the safest, most structured pipeline.
        resolved_domain = decision_llm.domain
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
            
            # HARDCODE OVERRIDE: Prevent write tasks from being classified as exploration
            write_keywords = ["create", "write", "make", "upgrade", "update", "modify", "delete", "remove", "add", "change", "build", "generate", "انشاء", "اضافة", "تعديل", "امسح", "اكتب", "اعمل", "بناء", "صمم"]
            if swe_sub.complexity == TaskComplexity.EXPLORATION and any(kw in task_description.lower() for kw in write_keywords):
                swe_sub = swe_sub.model_copy(update={
                    "complexity": TaskComplexity.MEDIUM,
                    "reasoning": "Overridden from exploration to medium due to write/modify keywords in task."
                })
                
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
            confidence=decision_llm.confidence,
            safe_fallback=safe_fallback,
            reasoning=decision_llm.reasoning,
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
            "You are a multi-department intent classifier. Evaluate the task below and classify it into EXACTLY ONE domain.\n\n"
            f"Task: {task}\n\n"
            "DOMAINS:\n"
            "  conversational — General chat, greetings, or follow-up questions. DO NOT use this if the user asks to modify files, write code, or perform tasks.\n"
            "  system_command — System commands to configure the AI model registry, e.g., 'add model', 'disable model', 'enable model', 'what is the status of gpt-4o', 'list models', 'حالة gpt-4o', 'أوقف موديل'. (Do not write code for these).\n"
            "  os_command — Requests to delete files, move files, create directories, or execute operating system level commands (like rm, del, mkdir). (Do not use software_engineering for deleting files).\n"
            "  software_engineering — coding, debugging, architecture, DevOps, infrastructure, API design, database queries, any technical software task. (e.g. 'replace 2026 with 2025 in a file', 'make a file that prints hello', 'fix typo').\n"
            "  deep_research — open web research, market analysis, competitive intelligence, social statistics, non-technical data gathering, literature review, fact-finding.\n"
            "  media_production — generating or processing audio, images, video, 3D assets, music composition, voice synthesis, graphic design, video editing.\n\n"
            "CRITICAL: If the user requests ANY modification to files, code, or data (EXCEPT deleting files), you MUST classify it as 'software_engineering'. If they want to delete files, classify as 'os_command'. Never use 'conversational' for task delegation.\n\n"
            "Respond ONLY with a JSON object, no other text:\n"
            '{"domain": "software_engineering"|"deep_research"|"media_production"|"conversational"|"system_command"|"os_command", '
            '"confidence": 0.0-1.0, '
            '"safe_fallback": false, '
            '"reasoning": "brief reason", '
            '"fast_lane": false}'
        )

    @staticmethod
    def _build_complexity_prompt(task: str) -> str:
        return (
            "Classify this software engineering task's complexity or type.\n\n"
            f"Task: {task}\n\n"
            "EXPLORATION: Purely informational queries to read/search the codebase, without writing code.\n"
            "SIMPLE: single function, bug fix, small refactor.\n"
            "MEDIUM: multi-file change, new module.\n"
            "COMPLEX: greenfield project, major refactor, multi-system.\n\n"
            "CRITICAL: If the user requests ANY modification, upgrading, writing, or deleting of code/files, you MUST NOT use 'exploration'. 'exploration' is ONLY for read-only questions like 'how does X work?'.\n\n"
            "Respond ONLY with a JSON object, no other text:\n"
            '{"complexity": "exploration"|"simple"|"medium"|"complex", "confidence": 0.0-1.0, '
            '"safe_fallback": false, "reasoning": "brief reason", "fast_lane": true|false}'
        )