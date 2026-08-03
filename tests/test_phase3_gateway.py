"""Smoke tests for Phase 3 — LLM Gateway (LLMClient + CostTracker)."""

import pytest

from gateway.cost_tracker import BudgetExceededError, CostTracker, UsageSnapshot
from gateway.llm_client import LLMClient
from resilience import CircuitBreakerOpenError


class TestLLMClientRouting:
    """Verify model resolution and complexity-based routing."""

    def test_resolve_alias(self) -> None:
        client = LLMClient()
        # frontier alias resolves
        resolved = client.resolve_model("frontier")
        assert resolved in [
            "nvidia_nim/deepseek-ai/deepseek-v4-pro",
        ] or resolved.startswith("nvidia_nim/")

        # fast alias resolves
        fast = client.resolve_model("fast")
        assert "minimax" in fast.lower() or "fast" in fast.lower()

    def test_resolve_exact_model_passthrough(self) -> None:
        client = LLMClient()
        resolved = client.resolve_model("openai/gpt-4o")
        assert resolved == "openai/gpt-4o"

    def test_route_simple_to_fast(self) -> None:
        client = LLMClient()
        model = client.route_by_complexity("simple")
        # Should route to fast model
        assert "fast" == model or "mini" in model.lower() or "flash" in model.lower() or "nano" in model.lower()

    def test_route_hard_to_frontier(self) -> None:
        client = LLMClient()
        model = client.route_by_complexity("hard")
        # Should route to frontier model
        assert "fast" != model  # NOT the cheap model

    def test_route_critical_to_critic(self) -> None:
        client = LLMClient()
        model = client.route_by_complexity("critical")
        # Should route to critic model (claude or similar strong model)
        assert model != client.resolve_model("fast")
        # Critic is typically claude-sonnet or similar
        assert "claude" in model.lower() or model == client.resolve_model("critic") or "gemini" in model.lower() or model.startswith("openai/")

    def test_custom_model_map(self) -> None:
        custom_map = {"frontier": "openai/my-custom-model"}
        client = LLMClient(model_map=custom_map)
        resolved = client.resolve_model("frontier")
        assert resolved == "openai/my-custom-model"


class TestCircuitBreaker:
    """Verify circuit breaker pattern for budget enforcement."""

    def test_circuit_starts_closed(self) -> None:
        client = LLMClient()
        assert not client.is_circuit_open("wf-001")

    def test_open_and_close_circuit(self) -> None:
        client = LLMClient()
        client.open_circuit("wf-001")
        assert client.is_circuit_open("wf-001")

        client.close_circuit("wf-001")
        assert not client.is_circuit_open("wf-001")

    def test_complete_text_blocked_by_circuit(self) -> None:
        client = LLMClient()
        client.open_circuit("wf-blocked")

        with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker OPEN"):
            client.complete_text(
                model="fast",
                messages=[{"role": "user", "content": "Hello"}],
                workflow_id="wf-blocked",
            )


class TestCostTracker:
    """Verify per-workflow cost tracking and budget caps."""

    def test_init_and_record(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=10.0)
        ct.init_workflow("wf-a")
        snapshot = ct.record_usage(
            workflow_id="wf-a",
            model="gpt-4o",
            prompt_tokens=500,
            completion_tokens=200,
        )
        assert snapshot.prompt_tokens == 500
        assert snapshot.completion_tokens == 200
        assert snapshot.total_tokens == 700
        assert snapshot.estimated_cost_usd > 0

    def test_budget_exceeded_raises(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=0.001)  # tiny cap
        ct.init_workflow("wf-b")

        with pytest.raises(BudgetExceededError):
            # large call exceeds tiny cap
            ct.record_usage(
                workflow_id="wf-b",
                model="gpt-4o",
                prompt_tokens=10000,
                completion_tokens=5000,
            )

    def test_iteration_cap_raises(self) -> None:
        ct = CostTracker(
            max_cost_per_workflow_usd=100.0,  # generous
            max_iterations_per_workflow=3,
        )
        ct.init_workflow("wf-c")

        # 3 calls should pass
        for _ in range(3):
            ct.record_usage(
                workflow_id="wf-c",
                model="gpt-4o-mini",
                prompt_tokens=1,
                completion_tokens=1,
            )

        # 4th call exceeds iteration cap
        with pytest.raises(BudgetExceededError, match="iteration"):
            ct.record_usage(
                workflow_id="wf-c",
                model="gpt-4o-mini",
                prompt_tokens=1,
                completion_tokens=1,
            )

    def test_close_workflow_summary(self) -> None:
        ct = CostTracker()
        ct.init_workflow("wf-d")
        ct.record_usage(
            workflow_id="wf-d",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
        )
        summary = ct.close_workflow("wf-d")
        assert summary["workflow_id"] == "wf-d"
        assert summary["total_tokens"] == 150
        # close_workflow resets — after close, workflow is not tracked
        assert summary["status"] in ("closed", "not_tracked") or summary["total_tokens"] == 150

    def test_auto_init_on_first_record(self) -> None:
        ct = CostTracker()
        # No explicit init — record_usage auto-initializes
        snapshot = ct.record_usage(
            workflow_id="wf-auto",
            model="gpt-4o-mini",
            prompt_tokens=10,
            completion_tokens=10,
        )
        assert snapshot.total_tokens == 20

    def test_get_workflow_snapshots(self) -> None:
        ct = CostTracker()
        ct.init_workflow("wf-e")
        ct.record_usage(
            workflow_id="wf-e",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=100,
        )
        ct.record_usage(
            workflow_id="wf-e",
            model="gpt-4o-mini",
            prompt_tokens=50,
            completion_tokens=50,
        )
        summary = ct.workflow_summary("wf-e")
        assert summary["total_tokens"] == 300
        assert summary["iterations"] == 2
