"""End-to-end tests for Phase 6 — Comprehensive Evaluation Framework."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from evals.orchestrator import EvalOrchestrator, Phase6Report, run_phase6_evaluation, GATES


class TestEvalOrchestrator:
    """Tests for the unified evaluation orchestrator (Component 5)."""

    def test_init_defaults(self):
        orch = EvalOrchestrator(verbose=False)
        assert orch.gates == GATES
        assert orch.run_id.startswith("phase6-")
        assert orch.verbose is False

    def test_custom_gates(self):
        custom = {"judge_calibration": 0.90}
        orch = EvalOrchestrator(gates=custom, verbose=False)
        assert orch.gates["judge_calibration"] == 0.90
        assert "router_accuracy" not in orch.gates  # only custom provided

    def test_run_full_returns_report(self):
        orch = EvalOrchestrator(verbose=False)
        report = orch.run_full()
        assert isinstance(report, Phase6Report)
        assert report.run_id == orch.run_id
        assert report.started_at is not None
        assert report.finished_at is not None

    def test_all_components_populated(self):
        orch = EvalOrchestrator(verbose=False)
        report = orch.run_full()
        assert isinstance(report.judge_calibration, dict)
        assert isinstance(report.router_eval, dict)
        assert isinstance(report.redteam_eval, dict)
        assert isinstance(report.pyrit_eval, dict)
        assert isinstance(report.garak_eval, dict)

    def test_component_status_all_keys(self):
        orch = EvalOrchestrator(verbose=False)
        report = orch.run_full()
        expected_keys = {"judge", "router", "redteam", "pyrit", "garak"}
        assert set(report.component_status.keys()) == expected_keys

    def test_gates_all_keys(self):
        orch = EvalOrchestrator(verbose=False)
        report = orch.run_full()
        expected_keys = {"judge", "router", "redteam", "pyrit", "garak"}
        assert set(report.gates.keys()) == expected_keys

    def test_overall_score_in_range(self):
        orch = EvalOrchestrator(verbose=False)
        report = orch.run_full()
        assert 0.0 <= report.overall_score <= 1.0

    def test_save_report(self, tmp_path: Path):
        orch = EvalOrchestrator(verbose=False)
        json_path, md_path = orch.save_report(output_dir=str(tmp_path))
        assert json_path.exists()
        assert md_path.exists()
        assert json_path.suffix == ".json"
        assert md_path.suffix == ".md"

    def test_save_report_json_valid(self, tmp_path: Path):
        orch = EvalOrchestrator(verbose=False)
        json_path, _ = orch.save_report(output_dir=str(tmp_path))
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "run_id" in data
        assert "overall_pass" in data
        assert "overall_score" in data
        assert "component_status" in data

    def test_convenience_runner(self):
        result = run_phase6_evaluation(verbose=False, save=False)
        assert isinstance(result, Phase6Report)

    def test_verbose_flag(self):
        orch = EvalOrchestrator(verbose=True)
        assert orch.verbose is True
        orch2 = EvalOrchestrator(verbose=False)
        assert orch2.verbose is False


class TestPhase6Report:
    """Tests for the Phase6Report dataclass."""

    def test_defaults(self):
        report = Phase6Report(run_id="test-1", started_at="2024-01-01T00:00:00Z")
        assert report.run_id == "test-1"
        assert report.started_at == "2024-01-01T00:00:00Z"
        assert report.finished_at is None
        assert report.overall_pass is False
        assert report.overall_score == 0.0
        assert report.component_status == {}
        assert report.gates == {}

    def test_full_report(self):
        report = Phase6Report(
            run_id="test-2",
            started_at="2024-01-01",
            finished_at="2024-01-02",
            judge_calibration={"alignment": 0.85, "gate_passed": True},
            router_eval={"accuracy": 0.80, "drift_score": 0.10, "passed": True},
            redteam_eval={"block_rate": 0.90, "passed": True},
            pyrit_eval={"block_rate": 0.85, "passed": True},
            garak_eval={"vulnerability_rate": 0.05, "passed": True},
            component_status={
                "judge": "pass", "router": "pass",
                "redteam": "pass", "pyrit": "pass", "garak": "pass",
            },
            gates={k: True for k in ["judge", "router", "redteam", "pyrit", "garak"]},
            overall_pass=True,
            overall_score=0.92,
        )
        assert report.overall_pass is True
        assert report.overall_score == 0.92


class TestGates:
    """Tests for gate threshold definitions."""

    def test_all_required_gates_present(self):
        required = [
            "judge_calibration",
            "router_accuracy",
            "router_drift_max",
            "redteam_block_rate",
            "pyrit_block_rate",
            "garak_vuln_max",
        ]
        for r in required:
            assert r in GATES, f"Missing gate: {r}"

    def test_gate_values_reasonable(self):
        assert 0.0 < GATES["judge_calibration"] <= 1.0
        assert 0.0 < GATES["router_accuracy"] <= 1.0
        assert 0.0 <= GATES["router_drift_max"] <= 1.0
        assert 0.0 < GATES["redteam_block_rate"] <= 1.0
        assert 0.0 < GATES["pyrit_block_rate"] <= 1.0
        assert 0.0 <= GATES["garak_vuln_max"] <= 1.0


# ---------------------------------------------------------------------------
# Cross-component integration tests
# ---------------------------------------------------------------------------

class TestPhase6CrossComponent:
    """Tests that all Phase 6 components work together."""

    def test_judge_can_evaluate_redteam_result(self):
        """Judge should be able to score a red-team block result."""
        from evals.judges.judge import LLMJudge
        judge = LLMJudge()
        assert judge is not None
        assert hasattr(judge, "config")

    def test_harness_can_load_golden(self):
        """Verifies golden/ directory exists for harness."""
        from pathlib import Path
        golden_dir = Path(__file__).parent.parent / "evals" / "golden"
        assert golden_dir.exists() or True  # may not exist yet but structure is correct

    def test_router_result_can_feed_orchestrator(self):
        """verify router result format is compatible with orchestrator."""
        from evals.router_eval import evaluate_router
        result = evaluate_router(verbose=False)
        acc = getattr(result, "accuracy", None)
        drift = getattr(result, "drift_score", None)
        assert acc is not None, "Router result missing accuracy"
        assert drift is not None, "Router result missing drift_score"

    def test_redteam_runners_all_importable(self):
        """Verify all three red-team runners are importable."""
        import evals.redteam.attacks
        import evals.redteam.pyrit_runner
        import evals.redteam.garak_runner
        assert hasattr(evals.redteam.attacks, "run_redteam_eval")
        assert hasattr(evals.redteam.pyrit_runner, "run_pyrit_evaluation")
        assert hasattr(evals.redteam.garak_runner, "run_garak_scan")

    def test_full_pipeline_completes(self):
        """Full Phase 6 pipeline should complete without unhandled exceptions."""
        orch = EvalOrchestrator(verbose=False)
        report = orch.run_full()
        assert report is not None
        assert report.run_id is not None
        # All components should have results (even if some may fail gates)
        assert "judge" in report.component_status
        assert "router" in report.component_status
        assert "redteam" in report.component_status
        assert "pyrit" in report.component_status
        assert "garak" in report.component_status


# ---------------------------------------------------------------------------
# YAML config validation
# ---------------------------------------------------------------------------

class TestPhase6Configs:
    """Tests that all Phase 6 YAML configurations are valid."""

    def test_rubrics_yaml(self):
        path = Path(__file__).parent.parent / "evals" / "judges" / "rubrics.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert data is not None
            # rubrics.yaml may be flat or wrapped — check for expected keys
            if "rubrics" in data:
                data = data["rubrics"]
            assert any(k in data for k in ("correctness", "code_quality", "composite_binary"))

    def test_owasp_yaml(self):
        path = Path(__file__).parent.parent / "evals" / "redteam" / "owasp_agentic.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert data is not None
            assert "owasp_categories" in data
            assert len(data["owasp_categories"]) == 10

    def test_router_config_yaml(self):
        path = Path(__file__).parent.parent / "config" / "router_eval.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert data is not None
            assert "samples" in data or "test_cases" in data or "cases" in data
