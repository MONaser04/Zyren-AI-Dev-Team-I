"""
Tests for Phase 6: Trajectory-First Evaluation Harness
======================================================
Tests the evaluation harness, metrics, and golden/SWE-bench runners.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from evals.harness import EvaluationHarness, EvaluationResult, load_tasks_from_yaml
from evals.metrics import (
    TrajectoryMetrics,
    EvaluationAggregate,
    compute_aggregate,
    format_metrics_table,
    SWEBenchMetrics,
    compute_swebench_metrics,
)


class TestEvaluationHarness:
    """Test the EvaluationHarness class."""

    def test_harness_initialization(self):
        """Test harness initializes with correct defaults."""
        harness = EvaluationHarness(
            max_iterations=5,
            timeout_seconds=300,
            cost_cap_usd=1.0,
            verbose=False,
        )
        assert harness.max_iterations == 5
        assert harness.timeout_seconds == 300
        assert harness.cost_cap_usd == 1.0
        assert harness.verbose is False
        assert harness.run_id.startswith("eval-")
        assert harness.results == []

    def test_evaluation_result_dataclass(self):
        """Test EvaluationResult dataclass."""
        result = EvaluationResult(
            task_id="test-1",
            workflow_id="wf-1",
            passed=True,
            overall_score=0.85,
            iterations_taken=2,
            total_cost_usd=0.05,
            total_duration_seconds=30.0,
        )
        assert result.task_id == "test-1"
        assert result.passed is True
        assert result.overall_score == 0.85
        assert result.test_pass_rate == 1.0  # default
        assert result.lint_score == 1.0  # default

    def test_load_tasks_from_yaml(self):
        """Test loading tasks from YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
tasks:
  - id: "task-1"
    prompt: "Write a hello world function"
  - id: "task-2"
    prompt: "Write a fibonacci function"
    expected:
      output: "fib(5) = 5"
""")
            temp_path = f.name
        
        try:
            tasks = load_tasks_from_yaml(temp_path)
            assert len(tasks) == 2
            assert tasks[0]["id"] == "task-1"
            assert tasks[1]["id"] == "task-2"
            assert "expected" in tasks[1]
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_tasks_missing_file(self):
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_tasks_from_yaml("/nonexistent/path.yaml")


class TestTrajectoryMetrics:
    """Test TrajectoryMetrics and aggregation."""

    def test_trajectory_metrics_creation(self):
        """Test creating TrajectoryMetrics."""
        metrics = TrajectoryMetrics(
            task_id="test-1",
            workflow_id="wf-1",
            resolved=True,
            test_pass_rate=0.9,
            lint_score=0.8,
            iterations_taken=3,
            total_cost_usd=0.10,
            total_duration_seconds=45.0,
        )
        assert metrics.task_id == "test-1"
        assert metrics.resolved is True
        assert metrics.agent_invocations == {}
        assert metrics.tool_calls == {}

    def test_compute_aggregate_empty(self):
        """Test aggregate with empty list."""
        agg = compute_aggregate([])
        assert agg.total_tasks == 0
        assert agg.resolved_tasks == 0

    def test_compute_aggregate_single(self):
        """Test aggregate with single metric."""
        metrics = [
            TrajectoryMetrics(
                task_id="t1", workflow_id="w1", resolved=True,
                test_pass_rate=0.8, lint_score=0.9, type_check_passed=True,
                iterations_taken=2, total_cost_usd=0.05, total_duration_seconds=30.0,
            ),
        ]
        agg = compute_aggregate(metrics)
        assert agg.total_tasks == 1
        assert agg.resolved_tasks == 1
        assert agg.percent_resolved == 100.0
        assert agg.mean_score == 0.8  # uses test_pass_rate as proxy
        assert agg.mean_iterations == 2.0

    def test_compute_aggregate_multiple(self):
        """Test aggregate with multiple metrics."""
        metrics = [
            TrajectoryMetrics(
                task_id="t1", workflow_id="w1", resolved=True,
                test_pass_rate=1.0, lint_score=1.0, type_check_passed=True,
                iterations_taken=1, total_cost_usd=0.02, total_duration_seconds=10.0,
            ),
            TrajectoryMetrics(
                task_id="t2", workflow_id="w2", resolved=False,
                test_pass_rate=0.5, lint_score=0.7, type_check_passed=True,
                iterations_taken=3, total_cost_usd=0.08, total_duration_seconds=45.0,
            ),
            TrajectoryMetrics(
                task_id="t3", workflow_id="w3", resolved=True,
                test_pass_rate=0.9, lint_score=0.8, type_check_passed=False,
                iterations_taken=2, total_cost_usd=0.05, total_duration_seconds=25.0,
            ),
        ]
        agg = compute_aggregate(metrics)
        assert agg.total_tasks == 3
        assert agg.resolved_tasks == 2
        assert agg.percent_resolved == pytest.approx(66.67, rel=0.01)
        assert agg.mean_score == pytest.approx(0.8, rel=0.01)
        assert agg.mean_iterations == 2.0
        assert agg.total_cost_usd == 0.15

    def test_format_metrics_table(self):
        """Test markdown table formatting."""
        agg = EvaluationAggregate(
            total_tasks=10,
            resolved_tasks=7,
            percent_resolved=70.0,
            mean_score=0.75,
            median_score=0.8,
            score_std=0.1,
            min_score=0.5,
            max_score=0.95,
            mean_iterations=2.5,
            mean_cost_usd=0.05,
            mean_duration_seconds=30.0,
            total_cost_usd=0.50,
            total_duration_seconds=300.0,
            mean_test_pass_rate=0.85,
            mean_lint_score=0.90,
            type_check_pass_rate=0.80,
            mean_security_issues=0.2,
            mean_coverage=75.5,
            agent_utilization={"coder": 1.0, "tester": 1.0, "critic": 0.8},
            tool_usage={"file_read": 50, "file_write": 30, "exec_test": 20},
            error_rate=0.1,
            timeout_rate=0.05,
            human_intervention_rate=0.0,
        )
        table = format_metrics_table(agg)
        assert "% Resolved" in table
        assert "70.0%" in table
        assert "Mean Score" in table
        assert "0.7500" in table
        assert "Agent Utilization" in table
        assert "coder" in table
        assert "Tool Usage" in table
        assert "file_read" in table


class TestSWEBenchMetrics:
    """Test SWE-bench specific metrics."""

    def test_swebench_metrics_creation(self):
        """Test creating SWEBenchMetrics."""
        m = SWEBenchMetrics(
            instance_id="test-123",
            repo="owner/repo",
            resolved=True,
            patch_generated=True,
            patch_applies=True,
            tests_pass=True,
            patch_similarity=0.85,
            files_modified=3,
            lines_changed=50,
            cost_usd=0.15,
            duration_seconds=120.0,
        )
        assert m.instance_id == "test-123"
        assert m.resolved is True
        assert m.patch_similarity == 0.85

    def test_compute_swebench_metrics(self):
        """Test SWE-bench aggregate computation."""
        results = [
            SWEBenchMetrics(
                instance_id="i1", repo="r1", resolved=True,
                patch_generated=True, patch_applies=True, tests_pass=True,
                patch_similarity=0.9, files_modified=2, lines_changed=30,
                cost_usd=0.10, duration_seconds=60.0,
            ),
            SWEBenchMetrics(
                instance_id="i2", repo="r2", resolved=False,
                patch_generated=True, patch_applies=False, tests_pass=False,
                patch_similarity=0.3, files_modified=1, lines_changed=10,
                cost_usd=0.05, duration_seconds=45.0,
            ),
            SWEBenchMetrics(
                instance_id="i3", repo="r3", resolved=True,
                patch_generated=True, patch_applies=True, tests_pass=True,
                patch_similarity=0.8, files_modified=3, lines_changed=40,
                cost_usd=0.12, duration_seconds=90.0,
            ),
        ]
        agg = compute_swebench_metrics(results)
        assert agg["total_instances"] == 3
        assert agg["resolved"] == 2
        assert agg["percent_resolved"] == pytest.approx(66.67, rel=0.01)
        assert agg["patch_generated_rate"] == 1.0
        assert agg["patch_applies_rate"] == pytest.approx(0.67, rel=0.01)
        assert agg["tests_pass_rate"] == pytest.approx(0.67, rel=0.01)
        assert agg["avg_patch_similarity"] == pytest.approx(0.67, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])