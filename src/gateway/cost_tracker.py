"""
Cost Tracker — Per-Workflow Token & Cost Tracking
====================================================

Tracks per-workflow token usage and enforces hard cost caps.

READ Phase 3 deliverable:
  'Global budget + iteration ceilings per workflow.
   On breach → halt, block further calls, alert the human.'
  'Combined with LiteLLM caps, cost becomes fully predictable.'
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# Budget Error
# ============================================================


class BudgetExceededError(Exception):
    """Raised when a workflow exceeds its cost or iteration budget."""


# ============================================================
# Usage Data
# ============================================================


@dataclass
class UsageSnapshot:
    """A snapshot of token usage for a single LLM call."""

    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


# ============================================================
# Per-Model Pricing ($/1M tokens) — approximate, configurable
# ============================================================

# These are approximate prices. Override via config/litellm.yaml.
_DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "gpt-4.1": {"prompt": 2.00, "completion": 8.00},
    "gpt-4.1-mini": {"prompt": 0.40, "completion": 1.60},
    "gpt-4.1-nano": {"prompt": 0.10, "completion": 0.40},
    "claude-sonnet-4-20250514": {"prompt": 3.00, "completion": 15.00},
    "claude-haiku-3.5": {"prompt": 0.80, "completion": 4.00},
    "claude-opus-4-20250514": {"prompt": 15.00, "completion": 75.00},
    "gemini-2.5-flash": {"prompt": 0.15, "completion": 0.60},
    "gemini-2.5-pro": {"prompt": 1.25, "completion": 10.00},
    "deepseek-chat": {"prompt": 0.27, "completion": 1.10},
    "deepseek-reasoner": {"prompt": 0.55, "completion": 2.19},
    "o4-mini": {"prompt": 1.10, "completion": 4.40},
    "o3": {"prompt": 10.00, "completion": 40.00},
    "local-model": {"prompt": 0.00, "completion": 0.00},
}


# ============================================================
# Cost Tracker
# ============================================================


class CostTracker:
    """Tracks per-workflow token usage and enforces cost caps."""

    def __init__(
        self,
        max_cost_per_workflow_usd: float = 5.00,
        max_iterations_per_workflow: int = 15,
    ) -> None:
        """Initialize the cost tracker.

        Args:
            max_cost_per_workflow_usd: Hard cost cap per workflow.
            max_iterations_per_workflow: Max agent loop iterations.
        """
        self._max_cost = max_cost_per_workflow_usd
        self._max_iterations = max_iterations_per_workflow
        # Per-workflow tracking
        self._workflows: dict[str, dict[str, Any]] = {}
        # Pricing (can be overridden)
        self._pricing: dict[str, dict[str, float]] = dict(_DEFAULT_PRICING)

    # ----------------------------------------------------------
    # Workflow Budget Management
    # ----------------------------------------------------------

    def init_workflow(self, workflow_id: str) -> None:
        """Initialize tracking for a new workflow."""
        self._workflows[workflow_id] = {
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "iterations": 0,
            "calls": [],
        }
        logger.info(
            "Workflow %s initialized — budget: $%.2f, max iterations: %d",
            workflow_id,
            self._max_cost,
            self._max_iterations,
        )

    def close_workflow(
        self, workflow_id: str, status: str = "completed"
    ) -> dict[str, Any]:
        """Close tracking and return summary."""
        wf = self._workflows.pop(workflow_id, None)
        if wf is None:
            return {}
        return {
            "workflow_id": workflow_id,
            "status": status,
            "total_tokens": wf["total_tokens"],
            "total_cost_usd": round(wf["total_cost_usd"], 4),
            "iterations": wf["iterations"],
            "num_calls": len(wf["calls"]),
        }

    # ----------------------------------------------------------
    # Recording Usage
    # ----------------------------------------------------------

    def record_usage(
        self,
        workflow_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> UsageSnapshot:
        """Record token usage for a single LLM call.

        Args:
            workflow_id: The workflow making the call.
            model: Model name.
            prompt_tokens: Input tokens consumed.
            completion_tokens: Output tokens generated.

        Returns:
            UsageSnapshot with cost estimate.

        Raises:
            BudgetExceededError: If cumulative cost exceeds cap.
        """
        total = prompt_tokens + completion_tokens
        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)

        wf = self._workflows.get(workflow_id)
        if wf is None:
            self.init_workflow(workflow_id)
            wf = self._workflows[workflow_id]

        # Update cumulative
        new_total_cost = wf["total_cost_usd"] + cost
        new_iters = wf["iterations"] + 1

        # Check budget caps
        if new_total_cost > self._max_cost:
            msg = (
                f"Workflow '{workflow_id}' exceeded cost cap: "
                f"${new_total_cost:.4f} > ${self._max_cost:.2f}"
            )
            logger.error(msg)
            raise BudgetExceededError(msg)

        if new_iters > self._max_iterations:
            msg = (
                f"Workflow '{workflow_id}' exceeded iteration cap: "
                f"{new_iters} > {self._max_iterations}"
            )
            logger.error(msg)
            raise BudgetExceededError(msg)

        # Record
        snapshot = UsageSnapshot(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            estimated_cost_usd=cost,
        )
        wf["total_tokens"] += total
        wf["total_cost_usd"] = new_total_cost
        wf["iterations"] = new_iters
        wf["calls"].append(snapshot)

        logger.debug(
            "Workflow %s: +%d tokens ($%.4f) → cumulative %d tokens ($%.4f) [iter %d/%d]",
            workflow_id,
            total,
            cost,
            wf["total_tokens"],
            wf["total_cost_usd"],
            new_iters,
            self._max_iterations,
        )

        return snapshot

    # ----------------------------------------------------------
    # Budget Status
    # ----------------------------------------------------------

    def remaining_budget(self, workflow_id: str) -> float:
        """Return remaining USD budget for a workflow."""
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return self._max_cost
        return max(0.0, self._max_cost - wf["total_cost_usd"])

    def remaining_iterations(self, workflow_id: str) -> int:
        """Return remaining iterations for a workflow."""
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return self._max_iterations
        return max(0, self._max_iterations - wf["iterations"])

    def check_budget(self, workflow_id: str) -> bool:
        """Check if workflow has remaining budget. Returns False if exceeded."""
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return True
        return (
            wf["total_cost_usd"] < self._max_cost
            and wf["iterations"] < self._max_iterations
        )

    def workflow_summary(self, workflow_id: str) -> dict[str, Any]:
        """Return current status for a workflow."""
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return {"workflow_id": workflow_id, "status": "not_tracked"}
        return {
            "workflow_id": workflow_id,
            "total_tokens": wf["total_tokens"],
            "total_cost_usd": round(wf["total_cost_usd"], 4),
            "iterations": wf["iterations"],
            "remaining_budget": self.remaining_budget(workflow_id),
            "remaining_iterations": self.remaining_iterations(workflow_id),
            "max_cost": self._max_cost,
            "max_iterations": self._max_iterations,
            "budget_exceeded": wf["total_cost_usd"] >= self._max_cost
            or wf["iterations"] >= self._max_iterations,
        }

    # ----------------------------------------------------------
    # Cost Calculation
    # ----------------------------------------------------------

    def _estimate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Estimate USD cost from token counts using per-model pricing."""
        # Find pricing (case-insensitive match)
        pricing = None
        model_lower = model.lower()
        for key, rates in self._pricing.items():
            if key in model_lower or model_lower in key:
                pricing = rates
                break

        if pricing is None:
            # Unknown model — use a conservative default
            pricing = {"prompt": 2.50, "completion": 10.00}

        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
        return prompt_cost + completion_cost

    def set_pricing(self, pricing: dict[str, dict[str, float]]) -> None:
        """Override default pricing with custom rates."""
        self._pricing.update(pricing)

    # ----------------------------------------------------------
    # Global Stats
    # ----------------------------------------------------------

    def global_stats(self) -> dict[str, Any]:
        """Return aggregate stats across all tracked workflows."""
        total_tokens = sum(w["total_tokens"] for w in self._workflows.values())
        total_cost = sum(w["total_cost_usd"] for w in self._workflows.values())
        total_calls = sum(len(w["calls"]) for w in self._workflows.values())
        return {
            "active_workflows": len(self._workflows),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "total_llm_calls": total_calls,
        }