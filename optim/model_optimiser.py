"""
Model Optimiser — Phase 5
==========================
Analyses per-model performance data to optimise the model routing map.
Drops under-performing models and recommends cost-efficient alternatives.
"""

from __future__ import annotations

import logging
from typing import Any

from src.contracts.eval_result import EvalResult
from optim.feedback_store import FeedbackStore

logger = logging.getLogger(__name__)

# ── KB: known Litellm model tiers ──────────────────────────────────────────────

MODEL_TIERS: dict[str, dict[str, Any]] = {
    # Format: "model_id": {"tier": str, "roles": [...], "cost_per_1k_tok": float}}
    "openai/gpt-4o-mini":       {"tier": "fast",   "roles": ["coder", "tester", "planner"], "cost_per_1k": 0.00015},
    "openai/gpt-4o":            {"tier": "smart",  "roles": ["coder", "tester", "critic", "architect"], "cost_per_1k": 0.0025},
    "anthropic/claude-3-haiku": {"tier": "fast",   "roles": ["coder", "tester", "planner"], "cost_per_1k": 0.00025},
    "anthropic/claude-3-sonnet":{"tier": "smart",  "roles": ["coder", "tester", "critic", "architect"], "cost_per_1k": 0.003},
    "openai/o3-mini":           {"tier": "fast",   "roles": ["coder", "tester", "planner"], "cost_per_1k": 0.00020},
    "openai/gpt-4.1":           {"tier": "smart",  "roles": ["coder", "tester", "critic", "architect"], "cost_per_1k": 0.004},
}


# ── Optimiser Logic ────────────────────────────────────────────────────────────


def optimise_model_routing(
    *,
    eval_results: list[EvalResult],
    feedback_store: FeedbackStore,
    min_success_rate: float = 0.6,
) -> list[dict[str, Any]]:
    """Review model performance and suggest routing changes.

    Returns a list of recommended changes:
    [
      {
        "model": "openai/gpt-4o-mini",
        "success_rate": 0.65,
        "avg_cost_usd": 0.03,
        "action": "keep" | "demote" | "remove" | "promote",
        "reason": "..."
      },
      ...
    ]
    """
    changes: list[dict[str, Any]] = []

    for model_id in MODEL_TIERS:
        perf = feedback_store.get_model_performance(model_id)
        total = perf.get("total_calls", 0)

        if total < 3:
            # Not enough data to decide
            changes.append(
                {
                    "model": model_id,
                    "success_rate": perf.get("success_rate", 0),
                    "avg_cost_usd": perf.get("total_cost_usd", 0),
                    "action": "keep",
                    "reason": f"Insufficient data ({total} calls); keeping model.",
                }
            )
            continue

        success_rate = perf.get("success_rate", 0)

        if success_rate < min_success_rate:
            info = MODEL_TIERS[model_id]
            tier = info["tier"]
            # Try to find a replacement in the same tier
            replacements = [
                m for m, d in MODEL_TIERS.items()
                if d["tier"] == tier and m != model_id
            ]
            reason = f"Success rate {success_rate:.2f} below threshold {min_success_rate}."
            if replacements:
                reason += f" Consider switching to: {', '.join(replacements[:2])}."
            changes.append(
                {
                    "model": model_id,
                    "success_rate": success_rate,
                    "avg_cost_usd": perf.get("total_cost_usd", 0),
                    "total_calls": total,
                    "tier": tier,
                    "action": "demote" if tier == "smart" else "remove",
                    "reason": reason,
                    "suggested_replacements": replacements,
                }
            )
        else:
            changes.append(
                {
                    "model": model_id,
                    "success_rate": success_rate,
                    "avg_cost_usd": perf.get("total_cost_usd", 0),
                    "total_calls": total,
                    "tier": MODEL_TIERS[model_id]["tier"],
                    "action": "keep",
                    "reason": f"Performance is acceptable (success_rate={success_rate:.2f}).",
                }
            )

    return changes


def recommend_best_model(
    tier: str,
    *,
    feedback_store: FeedbackStore,
    preferred_model: str | None = None,
) -> str:
    """Recommend the best-performing model in a given tier.

    Args:
        tier: "fast" or "smart"
        feedback_store: Store with performance history
        preferred_model: Optional specific model to evaluate

    Returns:
        Model ID string of the recommended model.
    """
    candidates = [
        (m, info) for m, info in MODEL_TIERS.items() if info["tier"] == tier
    ]

    if not candidates:
        return preferred_model or "openai/gpt-4o-mini"  # default fallback

    best_model = preferred_model or candidates[0][0]
    best_score = 0.0

    for model_id, _info in candidates:
        perf = feedback_store.get_model_performance(model_id)
        sr = perf.get("success_rate", 0)
        # Composite: success_rate weighted HIGHER than cost (which is already tracked)
        score = sr

        if score > best_score:
            best_score = score
            best_model = model_id

    return best_model