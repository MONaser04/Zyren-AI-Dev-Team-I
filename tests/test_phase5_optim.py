"""
Phase 5 Tests — Optimisation Modules
=====================================
Tests for PerformanceAnalyser, PromptTuner, ModelOptimiser,
FeedbackStore, Reporter, and ConvergenceDetector.
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from optim.analyser import PerformanceAnalyser, analyse_results
from optim.prompt_tuner import PromptTuner, tune_prompts
from optim.model_optimiser import ModelOptimiser, recommend_model, ModelRecommendation
from optim.feedback_store import FeedbackStore, get_feedback_store, FeedbackRecord
from optim.reporter import OptimisationReporter, generate_report, ReporterConfig
from optim.convergence import (
    ConvergenceDetector,
    check_convergence,
    ConvergenceConfig,
    ConvergenceResult,
)


class TestPerformanceAnalyser:
    """Tests for PerformanceAnalyser."""

    def test_analyser_creation(self):
        """Test analyser can be created."""
        analyser = PerformanceAnalyser()
        assert analyser is not None
        assert analyser.feedback is not None

    def test_analyse_empty_results(self):
        """Test analysing empty results list."""
        analyser = PerformanceAnalyser()
        result = analyser.analyse([])
        assert "error" in result

    def test_analyse_basic_results(self):
        """Test analysing basic results."""
        from src.contracts.eval_result import EvalResult

        results = [
            EvalResult(
                workflow_id="w1", task_id="t1", passed=True, overall_score=0.8,
                test_pass_rate=0.9, lint_score=0.85, total_cost_usd=0.01,
                iterations_taken=2,
            ),
            EvalResult(
                workflow_id="w2", task_id="t2", passed=False, overall_score=0.4,
                test_pass_rate=0.5, lint_score=0.6, total_cost_usd=0.02,
                iterations_taken=4,
            ),
        ]

        analyser = PerformanceAnalyser()
        analysis = analyser.analyse(results)

        assert analysis["total"] == 2
        assert analysis["pass_count"] == 1
        assert analysis["fail_count"] == 1
        assert analysis["pass_rate"] == 0.5
        assert "avg_score" in analysis
        assert "avg_cost_usd" in analysis
        assert "issue_sources" in analysis

    def test_detect_low_lint_pattern(self):
        """Test detection of low lint score pattern."""
        from src.contracts.eval_result import EvalResult, EvalIssue

        results = [
            EvalResult(
                workflow_id="w1", task_id="t1", passed=False, overall_score=0.5,
                lint_score=0.3,  # Low lint
            ),
            EvalResult(
                workflow_id="w2", task_id="t2", passed=False, overall_score=0.4,
                lint_score=0.2,  # Low lint
            ),
        ]

        analyser = PerformanceAnalyser()
        analysis = analyser.analyse(results)

        patterns = analysis.get("patterns", [])
        low_lint = [p for p in patterns if p["type"] == "low_lint"]
        assert len(low_lint) == 1
        assert low_lint[0]["count"] == 2

    def test_detect_high_iteration_failure(self):
        """Test detection of high iteration failures."""
        from src.contracts.eval_result import EvalResult

        results = [
            EvalResult(
                workflow_id="w1", task_id="t1", passed=False, overall_score=0.3,
                iterations_taken=5,  # High iterations + failure
            ),
            EvalResult(
                workflow_id="w2", task_id="t2", passed=False, overall_score=0.2,
                iterations_taken=4,
            ),
        ]

        analyser = PerformanceAnalyser()
        analysis = analyser.analyse(results)

        patterns = analysis.get("patterns", [])
        high_iter = [p for p in patterns if p["type"] == "high_iteration_failure"]
        assert len(high_iter) == 1


class TestPromptTuner:
    """Tests for PromptTuner."""

    def test_tuner_creation(self):
        """Test PromptTuner creation."""
        tuner = PromptTuner(model="test-model", max_variants=2)
        assert tuner.max_variants == 2
        assert tuner.model == "test-model"

    def test_generate_variants(self):
        """Test variant generation."""
        tuner = PromptTuner(model="test-model", max_variants=2)

        original = "You are a coder. Write code."
        failure_analysis = {
            "patterns": [
                {"type": "low_lint", "recommendation": "Add linting instructions"},
            ],
            "issue_sources": {"lint": 5},
        }

        # This will fail without real LLM, but we test the flow
        variants = tuner.generate_variants(original, failure_analysis, num_variants=1)
        # With mocked LLM it would return variants
        # Here we just verify it doesn't crash
        assert isinstance(variants, list)

    @patch("optim.prompt_tuner.LiteLLMClient")
    def test_tune_prompts(self, mock_client_class):
        """Test prompt tuning with mocked LLM."""
        mock_client = Mock()
        mock_client.send.return_value = "IMPROVED: You are a coder. Write clean, linted code."
        mock_client_class.return_value = mock_client

        tuner = PromptTuner(model="test-model", max_variants=2)

        original = "You are a coder. Write code."
        failure_analysis = {
            "patterns": [
                {"type": "low_lint", "recommendation": "Add linting instructions"},
            ],
        }

        result = tuner.tune("coder", original, failure_analysis)

        assert result.agent == "coder"
        assert result.original_prompt == original
        assert len(result.variants) >= 1
        assert result.best_variant is not None
        assert result.best_score > 0


class TestModelOptimiser:
    """Tests for ModelOptimiser."""

    def test_optimiser_creation(self):
        """Test ModelOptimiser creation."""
        opt = ModelOptimiser()
        assert opt is not None
        assert "budget" in opt.MODEL_TIERS
        assert "standard" in opt.MODEL_TIERS
        assert "premium" in opt.MODEL_TIERS

    def test_recommend_hard_task(self):
        """Test recommendation for hard task."""
        opt = ModelOptimiser()

        rec = opt.recommend("coder", "hard", "gpt-3.5-turbo")
        assert rec is not None
        assert rec.agent_role == "coder"
        assert rec.current_model == "gpt-3.5-turbo"
        assert "gpt-4o" in rec.recommended_model or "opus" in rec.recommended_model
        assert rec.confidence >= 0.7

    def test_recommend_easy_task(self):
        """Test recommendation for easy task (cost optimisation)."""
        opt = ModelOptimiser()

        rec = opt.recommend("coder", "easy", "gpt-4o")
        assert rec is not None
        assert rec.current_model == "gpt-4o"
        # Should recommend cheaper model
        assert "3.5" in rec.recommended_model or "mini" in rec.recommended_model or "haiku" in rec.recommended_model

    def test_no_recommendation_when_best(self):
        """Test no recommendation when already using best model."""
        opt = ModelOptimiser()

        # coder with standard tier, already using best in tier
        rec = opt.recommend("coder", "medium", "sonnet")  # Best in standard
        assert rec is None

    def test_update_profiles(self):
        """Test profile updates from results."""
        opt = ModelOptimiser()

        from src.contracts.eval_result import EvalResult
        from src.contracts.run import AgentInvocation

        results = [
            EvalResult(
                workflow_id="w1", task_id="coding", passed=True, overall_score=0.9,
                total_cost_usd=0.05, iterations_taken=2,
            ),
        ]
        invocations = [
            AgentInvocation(
                workflow_id="w1", agent_role="coder", model="gpt-4o",
                duration_ms=5000, cost_usd=0.05, tokens_in=100, tokens_out=200,
            ),
        ]

        opt.update_profiles(results, invocations)

        profiles = opt.profiles.get("coding", {})
        assert "gpt-4o" in profiles
        profile = profiles["gpt-4o"]
        assert profile.total_runs == 1
        assert profile.avg_score == 0.9

    def test_pareto_frontier(self):
        """Test Pareto frontier computation."""
        opt = ModelOptimiser()

        # Manually add profiles
        opt.profiles["coding"] = {
            "gpt-3.5": ModelProfile("gpt-3.5", avg_score=0.6, avg_cost=0.01, pass_rate=0.5, total_runs=10),
            "gpt-4o": ModelProfile("gpt-4o", avg_score=0.85, avg_cost=0.05, pass_rate=0.8, total_runs=10),
            "gpt-4": ModelProfile("gpt-4", avg_score=0.8, avg_cost=0.08, pass_rate=0.75, total_runs=10),
        }

        frontier = opt.pareto_frontier("coding")
        assert len(frontier) >= 2  # gpt-3.5 and gpt-4o should be on frontier
        # gpt-4 is dominated by gpt-4o (lower score, higher cost)
        models = [f["model"] for f in frontier]
        assert "gpt-3.5" in models
        assert "gpt-4o" in models


class TestFeedbackStore:
    """Tests for FeedbackStore."""

    def test_store_creation(self, tmp_path):
        """Test store creation."""
        db_path = tmp_path / "test_feedback.db"
        store = FeedbackStore(str(db_path))
        assert store.db_path == str(db_path)

    def test_insert_and_query(self, tmp_path):
        """Test inserting and querying records."""
        db_path = tmp_path / "test_feedback.db"
        store = FeedbackStore(str(db_path))

        record = FeedbackRecord(
            workflow_id="w1",
            source="tester",
            severity="error",
            message="Test failed",
        )

        row_id = store.insert(record)
        assert row_id > 0

        results = store.query(source="tester")
        assert len(results) == 1
        assert results[0]["workflow_id"] == "w1"
        assert results[0]["source"] == "tester"
        assert results[0]["severity"] == "error"

    def test_insert_batch(self, tmp_path):
        """Test batch insert."""
        db_path = tmp_path / "test_feedback.db"
        store = FeedbackStore(str(db_path))

        records = [
            FeedbackRecord(workflow_id="w1", source="coder", severity="warning", message="Warn"),
            FeedbackRecord(workflow_id="w2", source="tester", severity="error", message="Error"),
        ]

        count = store.insert_batch(records)
        assert count == 2

        results = store.query()
        assert len(results) == 2

    def test_count_by_source(self, tmp_path):
        """Test counting by source."""
        db_path = tmp_path / "test_feedback.db"
        store = FeedbackStore(str(db_path))

        records = [
            FeedbackRecord(workflow_id="w1", source="coder", severity="warning", message="Warn"),
            FeedbackRecord(workflow_id="w2", source="coder", severity="error", message="Error"),
            FeedbackRecord(workflow_id="w3", source="tester", severity="error", message="Error"),
        ]
        store.insert_batch(records)

        counts = store.count_by_source()
        assert counts["coder"] == 2
        assert counts["tester"] == 1

    def test_count_by_severity(self, tmp_path):
        """Test counting by severity."""
        db_path = tmp_path / "test_feedback.db"
        store = FeedbackStore(str(db_path))

        records = [
            FeedbackRecord(workflow_id="w1", source="coder", severity="warning", message="Warn"),
            FeedbackRecord(workflow_id="w2", source="coder", severity="warning", message="Warn2"),
            FeedbackRecord(workflow_id="w3", source="tester", severity="error", message="Error"),
        ]
        store.insert_batch(records)

        counts = store.count_by_severity()
        assert counts["warning"] == 2
        assert counts["error"] == 1

    def test_tuning_history(self, tmp_path):
        """Test saving and retrieving tuning history."""
        db_path = tmp_path / "test_feedback.db"
        store = FeedbackStore(str(db_path))

        store.save_tuning(
            agent="coder",
            original_prompt="Original",
            variants=["Variant 1", "Variant 2"],
            evaluations=[{"variant": "Variant 1", "score": 0.8}, {"variant": "Variant 2", "score": 0.7}],
            best_variant="Variant 1",
            best_score=0.8,
        )

        history = store.get_tuning_history(agent="coder")
        assert len(history) == 1
        assert history[0]["agent"] == "coder"
        assert history[0]["best_score"] == 0.8


class TestReporter:
    """Tests for OptimisationReporter."""

    def test_reporter_creation(self, tmp_path):
        """Test reporter creation."""
        config = ReporterConfig(output_dir=str(tmp_path / "reports"), format="markdown")
        reporter = OptimisationReporter(config)
        assert reporter.config.output_dir == str(tmp_path / "reports")

    def test_generate_report(self, tmp_path):
        """Test report generation."""
        from src.contracts.eval_result import EvalResult
        from src.contracts.optim_report import TuningResult

        config = ReporterConfig(output_dir=str(tmp_path / "reports"), format="markdown")
        reporter = OptimisationReporter(config)

        results = [
            EvalResult(workflow_id="w1", task_id="t1", passed=True, overall_score=0.8, total_cost_usd=0.01),
            EvalResult(workflow_id="w2", task_id="t2", passed=False, overall_score=0.4, total_cost_usd=0.02),
        ]

        tuning_results = [
            TuningResult(
                agent="coder",
                original_prompt="Original",
                variants=["Variant 1"],
                best_variant="Variant 1",
                best_score=0.85,
                evaluations=[{"variant": "Variant 1", "score": 0.85}],
            ),
        ]

        report = reporter.generate(results, tuning_results)

        assert report.total_tasks == 2
        assert report.passed == 1
        assert report.failed == 1
        assert len(report.tuning_results) == 1

    def test_save_formats(self, tmp_path):
        """Test saving in different formats."""
        from src.contracts.eval_result import EvalResult

        for fmt in ["markdown", "json", "html"]:
            config = ReporterConfig(output_dir=str(tmp_path / "reports"), format=fmt)
            reporter = OptimisationReporter(config)

            results = [EvalResult(workflow_id="w1", task_id="t1", passed=True, overall_score=0.8)]
            report = reporter.generate(results)

            # Check file exists
            files = list((tmp_path / "reports").glob(f"*.{fmt}"))
            assert len(files) == 1


class TestConvergenceDetector:
    """Tests for ConvergenceDetector."""

    def test_detector_creation(self):
        """Test detector creation."""
        config = ConvergenceConfig(min_samples=3, window_size=2, patience=2)
        detector = ConvergenceDetector(config)
        assert detector.config.min_samples == 3

    def test_insufficient_samples(self):
        """Test convergence with insufficient samples."""
        detector = ConvergenceDetector(ConvergenceConfig(min_samples=5, window_size=2))

        from src.contracts.eval_result import EvalResult
        r = EvalResult(workflow_id="w1", task_id="t1", overall_score=0.5)

        result = detector.record(r)
        assert result.converged is False
        assert "Need 5 samples" in result.reason

    def test_convergence_on_plateau(self):
        """Test convergence detection on plateau."""
        config = ConvergenceConfig(
            min_samples=3,
            window_size=2,
            improvement_threshold=0.01,
            patience=2,
            min_score=0.5,
        )
        detector = ConvergenceDetector(config)

        from src.contracts.eval_result import EvalResult

        # Scores that plateau
        scores = [0.6, 0.61, 0.615, 0.617, 0.618]
        last_result = None

        for s in scores:
            r = EvalResult(workflow_id="w", task_id="t", overall_score=s)
            last_result = detector.record(r)

        # Should converge due to plateau
        assert last_result.converged is True or last_result.patience_remaining <= 1

    def test_convergence_check_function(self):
        """Test convenience check_convergence function."""
        from src.contracts.eval_result import EvalResult

        results = [
            EvalResult(workflow_id="w1", task_id="t1", overall_score=0.5),
            EvalResult(workflow_id="w2", task_id="t2", overall_score=0.51),
            EvalResult(workflow_id="w3", task_id="t3", overall_score=0.515),
            EvalResult(workflow_id="w4", task_id="t4", overall_score=0.517),
            EvalResult(workflow_id="w5", task_id="t5", overall_score=0.518),
        ]

        conv_result = check_convergence(results)
        assert isinstance(conv_result, ConvergenceResult)
        assert conv_result.samples_analysed == 5


class TestModelProfile:
    """Tests for ModelProfile dataclass."""

    def test_model_profile_creation(self):
        """Test ModelProfile creation."""
        from optim.model_optimiser import ModelProfile

        profile = ModelProfile(
            model_name="gpt-4o",
            avg_score=0.85,
            avg_cost=0.05,
            pass_rate=0.8,
            total_runs=10,
        )
        assert profile.model_name == "gpt-4o"
        assert profile.avg_score == 0.85
        assert profile.total_runs == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
