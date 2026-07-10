"""
Prompt Tuner — Phase 5 (DSPy-inspired)
=======================================
Generates and evaluates prompt variants for agents, selecting the
best-performing prompt for each agent role.

Strategy (DSPy-style compile):
  1. For each agent, generate N variants of its system prompt
  2. Evaluate each variant against the Golden Set
  3. Select the variant with the highest weighted score
  4. Record results in FeedbackStore for longitudinal tracking
"""

from __future__ import annotations

import logging
from typing import Any

from src.contracts.eval_result import EvalResult
from src.contracts.optim_report import TuningResult
from src.gateway.llm_client import LLMClient
from optim.feedback_store import FeedbackStore

logger = logging.getLogger(__name__)

# ── Known agent roles and their default system prompts ─────────────────────────
# These are the prompts that will be tuned.

AGENT_DEFAULTS: dict[str, str] = {
    "coder": (
        "You are an expert software engineer. Write clean, well-documented, "
        "production-quality code. Include type annotations where applicable. "
        "Handle edge cases. Follow the language's best practices and idioms."
    ),
    "tester": (
        "You are a QA engineer. Write thorough unit tests covering happy paths, "
        "edge cases, and error conditions. Use the testing framework appropriate "
        "for the language. Aim for >90% code coverage."
    ),
    "critic": (
        "You are a code reviewer. Analyse the code for bugs, security issues, "
        "performance problems, and style violations. Provide actionable feedback "
        "with specific line references. Be constructive."
    ),
    "architect": (
        "You are a software architect. Design clean, scalable system architectures. "
        "Consider separation of concerns, dependency management, and deployment "
        "patterns. Output structured design documents."
    ),
    "planner": (
        "You are a technical project planner. Break down complex coding tasks into "
        "clear, ordered steps. Estimate effort and identify dependencies. "
        "Output a structured implementation plan."
    ),
}


# ── Variant Generator ──────────────────────────────────────────────────────────


def generate_variants(
    original_prompt: str,
    n_variants: int = 5,
    *,
    llm_client: LLMClient | None = None,
) -> list[str]:
    """Generate N prompt variants based on an original prompt.

    Uses the LLM to rephrase, expand, or specialize the original prompt.
    If no LLM client is provided, falls back to simple template-based variants.

    Args:
        original_prompt: The prompt to generate variants from.
        n_variants: Number of variants to produce.
        llm_client: Optional LLM client for smart generation.

    Returns:
        List of variant strings (including the original as first).
    """
    variants: list[str] = [original_prompt]

    if llm_client:
        for i in range(n_variants - 1):
            try:
                meta_prompt = f"""You are a prompt engineer. Given this system prompt for an AI agent:

---
{original_prompt}
---

Generate a variant that might improve performance. The variant should:
1. Be more specific and detailed
2. Include explicit quality criteria
3. Add output format requirements

Respond with ONLY the new prompt text. No introduction, no explanation."""
                variant = llm_client.complete_text("fast", [{"role": "user", "content": meta_prompt}], temperature=0.7, max_tokens=2048)
                if variant and len(variant) > 20:
                    variants.append(variant.strip())
            except Exception:
                logger.warning("LLM variant generation failed for variant %d — using template fallback.", i + 2)

    # Fill remaining variants with template-based ones if needed
    templates = [
        f"[EXPERT MODE] {original_prompt}\n\nYou MUST follow these additional rules:\n1. Provide thorough documentation\n2. Include test cases inline\n3. Use best-practice design patterns.",
        f"[TURBO MODE] {original_prompt}\n\nPrioritise clarity and correctness. Include:\n- Type annotations\n- Docstrings\n- Error handling",
        f"[SAFETY FIRST] {original_prompt}\n\nCritical rules:\n1. Validate all inputs\n2. Handle all error states\n3. Log important operations\n4. Never expose sensitive data",
        f"[EFFICIENCY FOCUS] {original_prompt}\n\nOptimise for:\n- Time and space complexity\n- Minimal dependencies\n- Clean readable code",
    ]

    for tmpl in templates:
        if len(variants) >= n_variants:
            break
        if tmpl not in variants:
            variants.append(tmpl)

    # Ensure we have exactly n_variants
    while len(variants) < n_variants:
        variants.append(f"[VARIANT {len(variants)+1}] {original_prompt}")

    return variants[:n_variants]


# ── Evaluator ──────────────────────────────────────────────────────────────────


def evaluate_variants(
    variants: list[str],
    eval_results: list[EvalResult],
    agent: str,
) -> list[dict[str, Any]]:
    """Score each variant based on evaluation results.

    This is a simplified scoring model. In production, each variant would
    actually be deployed and evaluated independently. Here we simulate
    scoring with slight variations to demonstrate the loop.
    """
    evaluations: list[dict[str, Any]] = []
    base_score = sum(r.overall_score for r in eval_results) / max(1, len(eval_results))

    for i, variant in enumerate(variants):
        # Simulate slight variation per variant (in real DSPy, each would be tested)
        jitter = 0.02 * (i % 3 - 1)  # small variation for demo
        eval_score = round(min(1.0, max(0.0, base_score + jitter)), 4)
        evaluations.append({"variant": variant[:80] + "...", "variant_index": i, "score": eval_score})

    return evaluations


# ── Main Tuning Entry Point ────────────────────────────────────────────────────


def tune_prompts(
    *,
    eval_results: list[EvalResult],
    agents: list[str] | None = None,
    n_variants: int = 5,
    llm_client: LLMClient | None = None,
    feedback_store: FeedbackStore | None = None,
) -> list[TuningResult]:
    """Run prompt tuning for the specified agents.

    Args:
        eval_results: Current round's evaluation results (for scoring).
        agents: List of agent roles to tune (default: all known agents).
        n_variants: Number of prompt variants per agent.
        llm_client: Optional LLM client for generating variants.
        feedback_store: Optional store for persisting tuning history.

    Returns:
        List of TuningResult objects — one per agent.
    """
    agent_list = agents or list(AGENT_DEFAULTS.keys())
    results: list[TuningResult] = []

    for agent in agent_list:
        original = AGENT_DEFAULTS.get(agent, f"You are a {agent} agent.")
        logger.info("Tuning prompt for agent '%s' (%d variants)...", agent, n_variants)

        variants = generate_variants(original, n_variants, llm_client=llm_client)
        evaluations = evaluate_variants(variants, eval_results, agent)

        # Select best variant
        best = max(evaluations, key=lambda e: e["score"], default={"variant": original, "score": 0.0})
        best_variant_text = variants[best["variant_index"]] if "variant_index" in best else original
        best_score = best["score"]

        result = TuningResult(
            agent=agent,
            original_prompt=original,
            variants=variants,
            evaluations=evaluations,
            best_variant=best_variant_text,
            best_score=best_score,
        )

        results.append(result)

        # Persist
        if feedback_store:
            try:
                feedback_store.save_tuning(
                    agent=agent,
                    original_prompt=original,
                    variants=variants,
                    evaluations=evaluations,
                    best_variant=best_variant_text,
                    best_score=best_score,
                )
            except Exception as e:
                logger.warning("Failed to persist tuning for '%s': %s", agent, e)

    return results