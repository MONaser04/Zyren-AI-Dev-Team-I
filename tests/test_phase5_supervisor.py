"""
Phase 5 Supervisor Tests — Closed-Loop Self-Improvement
=========================================================
Tests the key Phase 5 components: contracts, optim modules,
and the Supervisor integration with mock data.
"""

from __future__ import annotations

import pytest

from contracts.eval_result import EvalResult
from contracts.optim_report import OptimReport, RoundReport
from optim.convergence import ConvergenceConfig, check_convergence
from optim.feedback_store import FeedbackStore, FeedbackRecord
from optim.analyser import analyse_round
from optim.model_optimiser import optimise_model_routing, recommend_best_model
from optim.prompt_tuner import TuningResult, tune_prompts
from optim.reporter import generate_json_report, generate_markdown_report
from evals.scorer import compute_round_score

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_eval_results() -> list[EvalResult]:
    """مجموعة نتائج تقييم وهمية للاختبار."""
    return [
        EvalResult(workflow_id="wf1", task_id="g0", passed=True, overall_score=0.92, test_pass_rate=1.0),
        EvalResult(workflow_id="wf2", task_id="g1", passed=True, overall_score=0.85, test_pass_rate=0.9),
        EvalResult(workflow_id="wf3", task_id="g2", passed=False, overall_score=0.55, test_pass_rate=0.5, issues=["stack overflow"]),
        EvalResult(workflow_id="wf4", task_id="g3", passed=True, overall_score=0.78, test_pass_rate=0.85),
        EvalResult(workflow_id="wf5", task_id="g4", passed=False, overall_score=0.40, test_pass_rate=0.3, issues=["timeout", "bad json"]),
    ]


@pytest.fixture
def empty_store(tmp_path) -> FeedbackStore:
    """FeedbackStore فارغ للاختبار."""
    db_path = tmp_path / "test_feedback.db"
    return FeedbackStore(str(db_path))


@pytest.fixture
def populated_store(tmp_path, sample_eval_results) -> FeedbackStore:
    """FeedbackStore محشو ببيانات وهمية."""
    db_path = str(tmp_path / "test_feedback_pop.db")
    store = FeedbackStore(db_path)
    for er in sample_eval_results:
        store.record_eval(er)
    return store


# ═══════════════════════════════════════════════════════════════════════════════
# Contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvalResult:
    """اختبارات EvalResult contract."""

    def test_to_dict_roundtrip(self):
        """التأكد من أن to_dict و from_dict يعملان بتناسق."""
        er = EvalResult(workflow_id="wf-1", task_id="g0", passed=True, overall_score=0.95,
                        test_pass_rate=1.0, lint_score=0.98, iterations_taken=2,
                        total_cost_usd=0.05, issues=["minor lint warning"])
        d = er.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["overall_score"] == 0.95
        assert d["passed"] is True

        er2 = EvalResult.from_dict(d)
        assert er2.workflow_id == er.workflow_id
        assert er2.overall_score == er.overall_score

    def test_defaults(self):
        """القيم الافتراضية صحيحة."""
        er = EvalResult()
        assert er.passed is False
        assert er.overall_score == 0.0
        assert er.test_pass_rate == 0.0
        assert er.lint_score == 1.0
        assert er.issues == []


class TestOptimReport:
    """اختبارات OptimReport."""

    def test_best_score_calculation(self):
        """حساب best_score يعمل بدقة."""
        report = OptimReport(supervisor_id="s1")
        r1 = RoundReport(round_num=1, mean_score=0.65)
        r2 = RoundReport(round_num=2, mean_score=0.82)
        r3 = RoundReport(round_num=3, mean_score=0.71)
        report.add_round(r1)
        report.add_round(r2)
        report.add_round(r3)

        assert report.best_score == 0.82
        assert report.best_round == 2
        assert report.total_evaluations == 0  # no eval results stored
        assert report.total_cost_usd == 0.0

    def test_to_dict(self):
        """to_dict للـ report الكامل يعمل."""
        report = OptimReport(supervisor_id="s1")
        report.finalize("completed")
        d = report.to_dict()
        assert d["status"] == "completed"
        assert "rounds" in d
        assert "finished_at" in d

    def test_all_statuses(self):
        """كل الحالات مقبولة."""
        for status in ("completed", "converged", "budget_exceeded", "error"):
            report = OptimReport(supervisor_id="s1")
            report.finalize(status)
            assert report.status == status


# ═══════════════════════════════════════════════════════════════════════════════
# Feedback Store & Analyser
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeedbackStore:
    """اختبارات FeedbackStore."""

    def test_record_eval(self, empty_store, sample_eval_results):
        """تسجيل EvalResult ينجح ولا يرمي خطأ."""
        for er in sample_eval_results:
            empty_store.record_eval(er)

    def test_get_model_performance(self, populated_store):
        """get_model_performance يرجع dict."""
        perf = populated_store.get_model_performance("openai/gpt-4o-mini")
        assert "total_calls" in perf

    def test_stats(self, populated_store):
        """get_stats يرجع ملخص."""
        stats = populated_store.get_stats()
        assert "total_evals" in stats

    def test_insert_raw(self, empty_store):
        """إدخال FeedbackRecord يدويًا."""
        empty_store.insert(FeedbackRecord(workflow_id="wf-0", source="test", severity="info", message="hello"))
        stats = empty_store.get_stats()
        assert stats["total_evals"] >= 0


class TestAnalyser:
    """اختبارات analyser."""

    def test_analyse_round(self, sample_eval_results, empty_store):
        """تحليل نتائج جولة يُنتج ملخص صحيح."""
        for er in sample_eval_results:
            empty_store.record_eval(er)
        result = analyse_round(sample_eval_results, feedback_store=empty_store)
        assert "summary" in result
        assert "pass_rate" in result["summary"]
        assert "weaknesses" in result
        assert "recommendations" in result

    def test_analyse_empty(self, empty_store):
        """analyse جولة فارغة لا ترمي خطأ."""
        result = analyse_round([], feedback_store=empty_store)
        assert "summary" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Convergence
# ═══════════════════════════════════════════════════════════════════════════════


class TestConvergence:
    """اختبارات convergence detection."""

    def test_not_enough_samples(self, sample_eval_results):
        """عينة أقل من min_samples → not converged."""
        cfg = ConvergenceConfig(min_samples=10)
        result = check_convergence(sample_eval_results[:2], cfg, previous_best_score=0.8, patience_counter=0)
        assert result.converged is False
        assert result.trend == "collecting"  # actual value from implementation

    def test_converged_high_score(self, sample_eval_results):
        """Score عالي + patience exceeded → converged."""
        high_results = [
            EvalResult(workflow_id="w1", task_id="g0", passed=True, overall_score=0.92),
            EvalResult(workflow_id="w2", task_id="g1", passed=True, overall_score=0.90),
            EvalResult(workflow_id="w3", task_id="g2", passed=True, overall_score=0.88),
        ]
        cfg = ConvergenceConfig(min_samples=3, patience=2, improvement_threshold=0.02, min_score=0.85)
        result = check_convergence(high_results, cfg, previous_best_score=0.91, patience_counter=2, current_round=5)
        assert result.converged is True

    def test_min_score_not_met(self, sample_eval_results):
        """Score أقل من min_score → not converged."""
        cfg = ConvergenceConfig(min_samples=3, min_score=0.95)
        # sample_eval_results have mediocre scores
        result = check_convergence(sample_eval_results, cfg, previous_best_score=0.5, patience_counter=0, current_round=3)
        assert result.converged is False


# ═══════════════════════════════════════════════════════════════════════════════
# Model Optimiser
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelOptimiser:
    """اختبارات model optimiser."""

    def test_optimise(self, sample_eval_results, populated_store):
        """optimise_model_routing يرجع قائمة تغييرات."""
        changes = optimise_model_routing(eval_results=sample_eval_results, feedback_store=populated_store)
        assert isinstance(changes, list)
        for c in changes:
            assert "model" in c
            assert "action" in c

    def test_recommend(self, populated_store):
        """recommend_best_model يرجع string صحيح."""
        model = recommend_best_model("fast", feedback_store=populated_store)
        assert "fast" in model.lower() or "mini" in model.lower() or "haiku" in model.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt Tuner
# ═══════════════════════════════════════════════════════════════════════════════


class TestPromptTuner:
    """اختبارات prompt tuner."""

    def test_tune_prompts_returns_list(self, sample_eval_results, populated_store):
        """tune_prompts يرجع list[TuningResult]."""
        results = tune_prompts(eval_results=sample_eval_results, n_variants=3, feedback_store=populated_store)
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, TuningResult)
            assert r.agent in ("planner", "coder", "critic", "tester", "architect")

    def test_tuning_result_to_dict(self):
        """TuningResult.to_dict يعمل."""
        tr = TuningResult(
            agent="coder",
            original_prompt="You are a coder.",
            variants=["You are a coder v1.", "You are a coder v2."],
            evaluations=[{"variant": "v1", "score": 0.72}, {"variant": "v2", "score": 0.85}],
            best_variant="You are a coder v2.",
            best_score=0.85,
            best_variant_idx=1,
            baseline_score=0.72,
            improvement=0.13,
            tuning_cost_usd=0.01,
        )
        d = tr.to_dict()
        assert d["agent"] == "coder"
        assert d["best_score"] == 0.85
        assert d["best_variant"] == "You are a coder v2."
        assert d["improvement"] == 0.13


# ═══════════════════════════════════════════════════════════════════════════════
# Scorer
# ═══════════════════════════════════════════════════════════════════════════════


class TestScorer:
    """اختبارات scorer."""

    def test_compute_round_score(self, sample_eval_results):
        """compute_round_score يرجع (mean, median, pass_rate)."""
        mean, median, pass_rate = compute_round_score(sample_eval_results)
        assert 0.0 <= mean <= 1.0
        assert 0.0 <= median <= 1.0
        assert 0.0 <= pass_rate <= 1.0

    def test_all_passed(self):
        """كل النتائج passed → pass_rate=1.0."""
        results = [EvalResult(workflow_id=f"wf{i}", task_id=f"g{i}", passed=True, overall_score=0.9) for i in range(3)]
        _mean, _median, pass_rate = compute_round_score(results)
        assert pass_rate == 1.0

    def test_all_failed(self):
        """كل النتائج failed → pass_rate=0.0."""
        results = [EvalResult(workflow_id=f"wf{i}", task_id=f"g{i}", passed=False, overall_score=0.3) for i in range(3)]
        _mean, _median, pass_rate = compute_round_score(results)
        assert pass_rate == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Reporter
# ═══════════════════════════════════════════════════════════════════════════════


class TestReporter:
    """اختبارات reporter."""

    def test_json_output(self):
        """generate_json_report ينتج JSON صالح."""
        report = OptimReport(supervisor_id="test-s1")
        report.finalize("completed")
        json_str = generate_json_report(report)
        assert '"supervisor_id"' in json_str
        assert '"status"' in json_str

    def test_markdown_output(self):
        """generate_markdown_report ينتج Markdown يحوي معلومات."""
        report = OptimReport(supervisor_id="test-s1")
        rnd = RoundReport(round_num=1, mean_score=0.75, median_score=0.73,
                          total_cost_usd=0.15, converged=False)
        report.add_round(rnd)
        report.finalize("completed")
        md = generate_markdown_report(report)
        assert "# 🔄 AI Dev Team" in md
        assert "test-s1" in md
        assert "0.75" in md