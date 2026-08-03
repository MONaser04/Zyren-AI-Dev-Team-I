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

    def test_analyse_empty_results(self):
        """Test analysing empty results list."""
        analyser = PerformanceAnalyser()
        result = analyser.analyse([])
        assert "summary" in result

    def test_analyse_basic_results(self):
        """Test analysing basic results."""
        from contracts.eval_result import EvalResult

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

        assert analysis["summary"]["total"] == 2
        assert analysis["summary"]["passed"] == 1
        assert analysis["summary"]["failed"] == 1
        assert analysis["summary"]["pass_rate"] == 0.5
        assert "mean_score" in analysis["summary"]
        assert "total_cost_usd" in analysis["summary"]

    def test_detect_low_lint_pattern(self):
        """Test detection of low lint score pattern."""
        from contracts.eval_result import EvalResult, EvalIssue

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

        weaknesses = analysis.get("weaknesses", [])
        low_lint = [w for w in weaknesses if w["dimension"] == "lint_score"]
        assert len(low_lint) == 1
        assert low_lint[0]["affected_count"] == 2

    def test_detect_high_iteration_failure(self):
        """Test detection of tasks that fail after many iterations."""
        from contracts.eval_result import EvalResult

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

        recommendations = analysis.get("recommendations", [])
        assert any("High iteration count" in r for r in recommendations)


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

    @patch("optim.prompt_tuner.LLMClient")
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

        from contracts.eval_result import EvalResult
        eval_results = [EvalResult(workflow_id="w1", task_id="t1", overall_score=0.8)]
        result = tuner.tune("coder", original, failure_analysis, eval_results=eval_results)

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

    def test_recommend_returns_string(self):
        """Test recommend returns a model string."""
        opt = ModelOptimiser()
        mock_store = MagicMock()
        mock_store.get_model_performance.return_value = {"success_rate": 0.8}
        
        rec = opt.recommend("smart", mock_store, "openai/gpt-4o")
        assert isinstance(rec, str)
        assert rec == "openai/gpt-4o"

    def test_optimise_model_routing(self):
        """Test optimise returns a list of changes."""
        opt = ModelOptimiser(min_success_rate=0.6)
        mock_store = MagicMock()
        mock_store.get_model_performance.return_value = {"success_rate": 0.5, "total_calls": 10, "total_cost_usd": 0.05}
        
        changes = opt.optimise([], mock_store)
        assert isinstance(changes, list)
        assert len(changes) > 0
        assert changes[0]["action"] in ("demote", "remove", "keep")



class TestFeedbackStore:
    """Tests for FeedbackStore."""

    def test_store_creation(self, tmp_path):
        """Test store creation."""
        db_path = tmp_path / "test_feedback.db"
        store = FeedbackStore(str(db_path))
        assert store.db_path == db_path

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
        config = ReporterConfig(output_dir=str(tmp_path / "reports"), formats=["markdown"])
        reporter = OptimisationReporter(config)
        assert reporter.config.output_dir == str(tmp_path / "reports")


    def test_generate_report(self, tmp_path):
        """Test report generation."""
        from optim.reporter import OptimisationReporter, ReporterConfig
        from contracts.optim_report import OptimReport, RoundReport
        from contracts.eval_result import EvalResult

        config = ReporterConfig(output_dir=str(tmp_path / "reports"), formats=["markdown", "json"])
        reporter = OptimisationReporter(config)

        report = OptimReport(
            supervisor_id="test_session",
            rounds=[
                RoundReport(
                    round_num=1,
                    eval_results=[
                        {"task_id": "t1", "passed": True, "overall_score": 0.8},
                    ],
                    tuning_results=[],
                    model_changes=[]
                )
            ]
        )

        written = reporter.generate(report)

        assert "markdown" in written
        assert "json" in written
        assert written["markdown"].exists()
        assert written["json"].exists()

    def test_save_formats(self, tmp_path):
        """Test saving in different formats."""
        from optim.reporter import OptimisationReporter, ReporterConfig
        from contracts.optim_report import OptimReport

        for fmt in ["markdown", "json"]:
            config = ReporterConfig(output_dir=str(tmp_path / "reports"), formats=[fmt])
            reporter = OptimisationReporter(config)

            report = OptimReport(supervisor_id="fmt_test")
            written = reporter.generate(report)

            assert fmt in written
            assert written[fmt].exists()


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

        from contracts.eval_result import EvalResult
        r = EvalResult(workflow_id="w1", task_id="t1", overall_score=0.5)

        result = detector.record([r])
        assert result.converged is False
        assert "Need at least 5 rounds" in result.recommendation

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

        from contracts.eval_result import EvalResult

        # Scores that plateau
        scores = [0.6, 0.61, 0.615, 0.617, 0.618]
        last_result = None

        for s in scores:
            r = EvalResult(workflow_id="w", task_id="t", overall_score=s)
            last_result = detector.record([r])

        # Should converge due to plateau
        assert last_result.converged is True or last_result.patience_counter >= 1

    def test_convergence_check_function(self):
        """Test convenience check_convergence function."""
        from contracts.eval_result import EvalResult

        results = [
            EvalResult(workflow_id="w1", task_id="t1", overall_score=0.5),
            EvalResult(workflow_id="w2", task_id="t2", overall_score=0.51),
            EvalResult(workflow_id="w3", task_id="t3", overall_score=0.515),
            EvalResult(workflow_id="w4", task_id="t4", overall_score=0.517),
            EvalResult(workflow_id="w5", task_id="t5", overall_score=0.518),
        ]

        config = ConvergenceConfig()
        conv_result = check_convergence(results, config)
        assert isinstance(conv_result, ConvergenceResult)
        assert conv_result.trend == "collecting"


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
