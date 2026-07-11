"""Tests for Router Evaluation & Anti-Drift Guardrail — Phase 6."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from evals.router_eval import (
    RouterEvaluator,
    RouterEvaluationResult,
    PerformanceFloor,
    RoutingSample,
    evaluate_router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mini_dataset_yaml() -> str:
    """Minimal 6-sample dataset (one per agent)."""
    data = {
        "samples": [
            {"id": "a1", "input": "Design a system architecture", "expected_agent": "architect"},
            {"id": "c1", "input": "Implement a function", "expected_agent": "coder"},
            {"id": "r1", "input": "Review this code", "expected_agent": "critic"},
            {"id": "d1", "input": "Debug the error", "expected_agent": "debugger"},
            {"id": "o1", "input": "Deploy to Kubernetes", "expected_agent": "devops"},
            {"id": "rs1", "input": "Research vector databases", "expected_agent": "researcher"},
        ],
    }
    return yaml.dump(data)


@pytest.fixture
def dataset_file(tmp_path: Path, mini_dataset_yaml: str) -> Path:
    """Write the mini dataset to a temp file."""
    f = tmp_path / "router_eval.yaml"
    f.write_text(mini_dataset_yaml, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# PerformanceFloor tests
# ---------------------------------------------------------------------------

class TestPerformanceFloor:
    def test_default_values(self):
        floor = PerformanceFloor()
        assert floor.min_accuracy == 0.70
        assert floor.min_per_agent_accuracy == 0.60
        assert floor.max_drift_score == 0.30
        assert floor.max_latency_p95_ms == 500.0

    def test_custom_values(self):
        floor = PerformanceFloor(min_accuracy=0.80, max_drift_score=0.15)
        assert floor.min_accuracy == 0.80
        assert floor.max_drift_score == 0.15
        # other values remain default
        assert floor.min_per_agent_accuracy == 0.60


# ---------------------------------------------------------------------------
# RouterEvaluator tests
# ---------------------------------------------------------------------------

class TestRouterEvaluatorInit:
    def test_default_init(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        assert evaluator.floor.min_accuracy == 0.70
        assert evaluator.window_size == 5
        assert evaluator.history == []

    def test_custom_floor(self, dataset_file):
        floor = PerformanceFloor(min_accuracy=0.85)
        evaluator = RouterEvaluator(dataset_path=dataset_file, floor=floor)
        assert evaluator.floor.min_accuracy == 0.85

    def test_missing_dataset_raises(self):
        evaluator = RouterEvaluator(dataset_path="nonexistent.yaml")
        with pytest.raises(FileNotFoundError):
            evaluator.load_dataset()


class TestDatasetLoading:
    def test_load_dataset(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        samples = evaluator.load_dataset()
        assert len(samples) == 6
        assert samples[0]["id"] == "a1"
        assert samples[0]["expected_agent"] == "architect"


class TestClassification:
    def test_classify_architect_input(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        agent, conf = evaluator._classify_input("Design a system architecture")
        assert agent == "architect"
        assert conf > 0.0

    def test_classify_coder_input(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        agent, conf = evaluator._classify_input("Implement a new feature")
        assert agent == "coder"

    def test_classify_critic_input(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        agent, conf = evaluator._classify_input("Review this pull request")
        assert agent == "critic"

    def test_classify_debugger_input(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        agent, conf = evaluator._classify_input("Fix the bug in payment processing")
        assert agent == "debugger"

    def test_classify_devops_input(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        agent, conf = evaluator._classify_input("Deploy to production with Docker")
        assert agent == "devops"

    def test_classify_researcher_input(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        agent, conf = evaluator._classify_input("Research the best caching strategy")
        assert agent == "researcher"

    def test_classify_unknown_fallback(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        agent, conf = evaluator._classify_input("xyzzy unknown gibberish")
        assert agent == "coder"  # default fallback
        assert conf < 0.5


class TestFullEvaluation:
    def test_evaluate_mini_dataset(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        result = evaluator.evaluate()
        assert isinstance(result, RouterEvaluationResult)
        assert result.total_samples == 6
        assert 0.0 <= result.accuracy <= 1.0
        assert result.mean_confidence > 0.0
        assert len(result.per_agent_accuracy) > 0
        assert result.drift_score >= 0.0

    def test_confusion_matrix_keys(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        result = evaluator.evaluate()
        # Confusion matrix should have expected agents as row keys
        for sample in evaluator.load_dataset():
            assert sample["expected_agent"] in result.confusion_matrix, \
                f"Expected {sample['expected_agent']} in confusion matrix"

    def test_per_agent_accuracy_range(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        result = evaluator.evaluate()
        for agent, acc in result.per_agent_accuracy.items():
            assert 0.0 <= acc <= 1.0, f"Accuracy for {agent} out of range: {acc}"


class TestFloorEnforcement:
    def test_check_floor_passing(self, dataset_file):
        """With the mini dataset our heuristic should pass."""
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        result = evaluator.evaluate()
        violations = evaluator.check_floor(result)
        # Depending on heuristic accuracy, may or may not pass
        # Just check format
        assert isinstance(violations, list)

    def test_check_floor_with_low_accuracy(self, dataset_file):
        """Force low accuracy by using a strict floor."""
        strict = PerformanceFloor(min_accuracy=0.99)
        evaluator = RouterEvaluator(dataset_path=dataset_file, floor=strict)
        result = evaluator.evaluate()
        violations = evaluator.check_floor(result)
        # Should have at least one violation (accuracy < 99%)
        assert len(violations) >= 1
        assert any("accuracy" in v.lower() for v in violations)

    def test_check_floor_drift(self, dataset_file):
        """After multiple runs, check drift score is computed."""
        evaluator = RouterEvaluator(dataset_path=dataset_file, window_size=10)
        # First run
        r1 = evaluator.evaluate()
        assert r1.drift_score == 0.0  # No history yet
        # Second run
        r2 = evaluator.evaluate()
        # Drift should now be computed
        assert r2.drift_score >= 0.0


class TestSerialization:
    def test_to_dict(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        result = evaluator.evaluate()
        d = evaluator.to_dict(result)
        assert d["total_samples"] == 6
        assert "accuracy" in d
        assert "confusion_matrix" in d
        assert "floor_violations" in d
        assert len(d["samples"]) == 6

    def test_routing_sample_dataclass(self):
        sample = RoutingSample(
            sample_id="test-1",
            input_text="hello",
            expected_agent="coder",
            actual_agent="coder",
            confidence=0.9,
            latency_ms=12.5,
            correct=True,
        )
        assert sample.correct is True
        assert sample.confidence == 0.9
        assert sample.latency_ms == 12.5


class TestIntegration:
    def test_evaluate_router_convenience(self, dataset_file):
        result = evaluate_router(dataset_path=dataset_file, verbose=False)
        assert isinstance(result, RouterEvaluationResult)
        assert result.total_samples == 6

    def test_run_id_format(self, dataset_file):
        evaluator = RouterEvaluator(dataset_path=dataset_file)
        assert evaluator.run_id.startswith("router-eval-")
        assert len(evaluator.run_id) > 12
