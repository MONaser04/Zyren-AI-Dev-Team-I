"""Smoke tests for Phase 3 — CostTracker."""

import pytest

from gateway.cost_tracker import BudgetExceededError, CostTracker, UsageSnapshot


class TestCostTracker:
    """Verify cost tracking, budget enforcement, and introspection."""

    def test_init_workflow_sets_budget(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=3.00, max_iterations_per_workflow=10)
        ct.init_workflow("wf-1")
        assert ct.remaining_budget("wf-1") == 3.00
        assert ct.remaining_iterations("wf-1") == 10

    def test_record_usage_updates_totals(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=5.00)
        ct.init_workflow("wf-2")

        snap = ct.record_usage("wf-2", "gpt-4o", prompt_tokens=5000, completion_tokens=2000)
        assert snap.total_tokens == 7000
        assert snap.model == "gpt-4o"
        assert ct.remaining_budget("wf-2") < 5.00  # cost consumed

    def test_budget_exceeded_raises(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=0.01)  # tiny cap
        ct.init_workflow("wf-3")

        # 1M tokens of gpt-4o exceeds $0.01
        with pytest.raises(BudgetExceededError, match="exceeded cost cap"):
            ct.record_usage("wf-3", "gpt-4o", prompt_tokens=500_000, completion_tokens=500_000)

    def test_iteration_cap_raises(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=100.00, max_iterations_per_workflow=2)
        ct.init_workflow("wf-4")

        ct.record_usage("wf-4", "gpt-4o-mini", 10, 10)
        ct.record_usage("wf-4", "gpt-4o-mini", 10, 10)

        with pytest.raises(BudgetExceededError, match="exceeded iteration cap"):
            ct.record_usage("wf-4", "gpt-4o-mini", 10, 10)

    def test_check_budget_false_after_exceed(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=5.00, max_iterations_per_workflow=3)
        ct.init_workflow("wf-5")
        assert ct.check_budget("wf-5") is True

        # Exhaust iterations
        for _ in range(3):
            ct.record_usage("wf-5", "gpt-4o-mini", 10, 10)
        assert ct.check_budget("wf-5") is False

    def test_close_workflow_returns_summary(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=5.00)
        ct.init_workflow("wf-6")
        ct.record_usage("wf-6", "gpt-4o", 1000, 500)

        summary = ct.close_workflow("wf-6")
        assert summary["workflow_id"] == "wf-6"
        assert summary["total_tokens"] == 1500
        assert summary["status"] == "completed"

    def test_workflow_summary_live(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=5.00)
        ct.init_workflow("wf-7")
        ct.record_usage("wf-7", "gpt-4o-mini", 1000, 500)

        summary = ct.workflow_summary("wf-7")
        assert summary["budget_exceeded"] is False
        assert summary["remaining_iterations"] == 14  # 15 - 1

    def test_global_stats_aggregates(self) -> None:
        ct = CostTracker()
        ct.init_workflow("wf-a")
        ct.init_workflow("wf-b")
        ct.record_usage("wf-a", "gpt-4o-mini", 100, 50)
        ct.record_usage("wf-b", "gpt-4o-mini", 200, 100)

        stats = ct.global_stats()
        assert stats["active_workflows"] == 2
        assert stats["total_llm_calls"] == 2

    def test_pricing_override(self) -> None:
        ct = CostTracker()
        ct.set_pricing({"my-model": {"prompt": 0.01, "completion": 0.02}})
        snap = ct.record_usage("wf-x", "my-model", 1_000_000, 500_000)
        # ~ $0.01 + $0.01 = $0.02
        assert snap.estimated_cost_usd == pytest.approx(0.02, rel=0.01)

    def test_not_tracked_workflow_returns_default(self) -> None:
        ct = CostTracker(max_cost_per_workflow_usd=10.0, max_iterations_per_workflow=15)
        assert ct.remaining_budget("unknown") == 10.0
        assert ct.remaining_iterations("unknown") == 15
