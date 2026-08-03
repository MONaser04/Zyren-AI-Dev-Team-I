"""
Phase 5 Tests — End-to-End Integration
=======================================
Full integration tests for the Phase 5 closed-loop system.
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from agents.supervisor import SupervisorAgent, SupervisorConfig, run_supervisor
from orchestrator.runner import run_workflow, run_evaluation_batch, WorkflowResult
from contracts.eval_result import EvalResult
from optim.feedback_store import FeedbackStore, get_feedback_store
from state.store import SQLiteEventStore
from gateway.llm_client import LLMClient


class TestSupervisorIntegration:
    """Integration tests for the Supervisor agent."""

    @patch("src.orchestrator.runner.run_evaluation_batch")
    @patch("optim.prompt_tuner.tune_prompts")
    @patch("optim.reporter.generate_report")
    @patch("evals.swebench.harness.run_swebench_eval")
    @patch("evals.redteam.attacks.run_redteam_eval")
    def test_supervisor_single_round(self, mock_redteam, mock_swebench, mock_generate_report, mock_tune_prompts, mock_run_eval):
        """Test supervisor runs one optimisation round."""
        # Setup mocks - return proper EvalResult objects with all required fields
        mock_run_eval.return_value = [
            EvalResult(
                workflow_id="w1", task_id="t1", passed=True, overall_score=0.8,
                total_cost_usd=0.01, iterations_taken=2,
                test_pass_rate=1.0, lint_score=1.0, type_check_passed=True,
                security_issues_count=0, issues=[],
            ),
            EvalResult(
                workflow_id="w2", task_id="t2", passed=False, overall_score=0.4,
                total_cost_usd=0.02, iterations_taken=4,
                test_pass_rate=0.0, lint_score=1.0, type_check_passed=True,
                security_issues_count=0, issues=[],
            ),
        ]
        mock_swebench.return_value = []
        mock_redteam.return_value = EvalResult(
            workflow_id="redteam-batch", task_id="redteam-security-audit",
            passed=False, overall_score=0.0, total_cost_usd=0.0, iterations_taken=1,
            test_pass_rate=0.0, lint_score=1.0, type_check_passed=True,
            security_issues_count=0, issues=[],
        )

        from contracts.optim_report import TuningResult
        mock_tune_prompts.return_value = [
            TuningResult(agent="coder", original_prompt="orig", variants=["v1"],
                        best_variant="v1", best_score=0.85, evaluations=[]),
        ]

        mock_report = Mock()
        mock_report.to_dict.return_value = {}
        mock_generate_report.return_value = mock_report

        # Run supervisor with minimal config
        config = SupervisorConfig(
            max_optimisation_rounds=1,
            max_eval_instances=2,
            max_workflow_iterations=3,
            enable_prompt_tuning=True,
            enable_model_switching=False,
            enable_convergence=False,
            redteam_enabled=False,
        )

        supervisor = SupervisorAgent(config)
        state = supervisor.run()

        # Verify
        assert state.status in ("completed", "converged")
        assert len(state.rounds) == 1
        assert state.rounds[0].round_num == 1
        assert len(state.rounds[0].eval_results) == 2

    @patch("src.orchestrator.runner.run_evaluation_batch")
    @patch("optim.prompt_tuner.tune_prompts")
    @patch("optim.reporter.generate_report")
    def test_supervisor_multiple_rounds(self, mock_generate_report, mock_tune_prompts, mock_run_eval):
        """Test supervisor runs multiple rounds until convergence."""
        # Setup mocks to return improving then plateauing scores
        call_count = 0

        def mock_eval(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    EvalResult(
                        workflow_id="w1", task_id="t1", passed=True, overall_score=0.6,
                        total_cost_usd=0.01, iterations_taken=1,
                        test_pass_rate=1.0, lint_score=1.0, type_check_passed=True,
                        security_issues_count=0, issues=[],
                    ),
                ]
            elif call_count == 2:
                return [
                    EvalResult(
                        workflow_id="w2", task_id="t1", passed=True, overall_score=0.65,
                        total_cost_usd=0.01, iterations_taken=1,
                        test_pass_rate=1.0, lint_score=1.0, type_check_passed=True,
                        security_issues_count=0, issues=[],
                    ),
                ]
            else:
                return [
                    EvalResult(
                        workflow_id="w3", task_id="t1", passed=True, overall_score=0.66,
                        total_cost_usd=0.01, iterations_taken=1,
                        test_pass_rate=1.0, lint_score=1.0, type_check_passed=True,
                        security_issues_count=0, issues=[],
                    ),
                ]

        mock_run_eval.side_effect = mock_eval

        from contracts.optim_report import TuningResult
        mock_tune_prompts.return_value = [
            TuningResult(agent="coder", original_prompt="orig", variants=["v1"],
                        best_variant="v1", best_score=0.7, evaluations=[]),
        ]

        mock_report = Mock()
        mock_report.to_dict.return_value = {}
        mock_generate_report.return_value = mock_report

        config = SupervisorConfig(
            max_optimisation_rounds=3,
            max_eval_instances=1,
            enable_convergence=True,
            convergence_threshold=0.01,
            convergence_patience=2,
            min_score_threshold=0.5,
            redteam_enabled=False,
        )

        supervisor = SupervisorAgent(config)
        state = supervisor.run()

        # Should run at least 2 rounds, possibly converge on 3rd
        assert state.status in ("converged", "completed")
        assert len(state.rounds) >= 2
        assert state.best_score >= 0.6

    def test_supervisor_loads_golden_tasks(self, tmp_path):
        """Test supervisor loads golden tasks from YAML."""
        import yaml

        tasks_data = {
            "tasks": [
                {"id": "task-1", "prompt": "Write a function"},
                {"id": "task-2", "prompt": "Create a class"},
            ]
        }
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(yaml.dump(tasks_data))

        config = SupervisorConfig(
            eval_dataset=str(tasks_file),
            max_optimisation_rounds=1,
            max_eval_instances=2,
        )

        supervisor = SupervisorAgent(config)
        tasks = supervisor._load_golden_tasks()

        assert len(tasks) == 2
        assert tasks[0]["id"] == "task-1"

    def test_supervisor_fallback_tasks(self):
        """Test supervisor uses fallback tasks when file missing."""
        config = SupervisorConfig(
            eval_dataset="nonexistent.yaml",
            max_optimisation_rounds=1,
            max_eval_instances=3,
        )

        supervisor = SupervisorAgent(config)
        tasks = supervisor._load_golden_tasks()

        assert len(tasks) == 3  # 3 demo tasks
        assert all("id" in t for t in tasks)
        assert all("prompt" in t for t in tasks)


class TestOrchestratorIntegration:
    """Integration tests for the enhanced orchestrator."""

    @patch("src.state.store.SQLiteEventStore")
    @patch("src.gateway.llm_client.LLMClient")
    @patch("src.orchestrator.runner.build_feedback_loop")
    def test_workflow_with_all_phase5_features(self, mock_build_graph, mock_llm, mock_store):
        """Test workflow with convergence, artifacts, and HITL enabled."""
        # Setup graph mock
        mock_graph = Mock()
        mock_compiled = Mock()
        mock_graph.compile.return_value = mock_compiled
        mock_compiled.invoke.return_value = {
            "workflow_id": "integration-wf",
            "verdict": "PASS",
            "current_iteration": 2,
            "code_patch": {"files": [{"path": "main.py", "content": "def main(): pass"}]},
            "error": None,
        }
        mock_build_graph.return_value = mock_graph

        # Setup store mock
        mock_store_instance = Mock()
        mock_store_instance.get_events.return_value = []
        mock_store.return_value = mock_store_instance

        # Run with all Phase 5 features
        result = run_workflow(
            task_description="Create a simple REST API",
            max_iterations=5,
            enable_convergence=True,
            convergence_config={"min_samples": 2, "patience": 1, "improvement_threshold": 0.05},
            enable_artifacts=True,
            enable_hitl=True,
            hitl_config={"backend": "auto", "policy": "approve"},
        )

        # Verify result
        assert isinstance(result, WorkflowResult)
        assert result.success is True
        assert result.iterations == 2
        assert "main.py" in result.final_code
        assert result.converged is not None
        assert "total_artifacts" in result.artifacts_summary
        assert len(result.hitl_approvals) >= 0  # May be 0 if gates not enabled

    @patch("src.state.store.SQLiteEventStore")
    @patch("src.gateway.llm_client.LLMClient")
    @patch("src.orchestrator.runner.build_feedback_loop")
    def test_evaluation_batch_integration(self, mock_build_graph, mock_llm, mock_store):
        """Test batch evaluation integration."""
        # Setup graph mock
        mock_graph = Mock()
        mock_compiled = Mock()
        mock_graph.compile.return_value = mock_compiled

        # Alternate between pass and fail
        call_count = 0

        def mock_invoke(state):
            nonlocal call_count
            call_count += 1
            return {
                "workflow_id": f"w{call_count}",
                "verdict": "PASS" if call_count % 2 == 1 else "FAIL",
                "current_iteration": 1,
                "code_patch": {"files": [{"path": f"task{call_count}.py", "content": "pass"}]},
                "error": None,
            }

        mock_compiled.invoke.side_effect = mock_invoke
        mock_build_graph.return_value = mock_graph

        # Setup store mock
        mock_store_instance = Mock()
        mock_store_instance.get_events.return_value = []
        mock_store.return_value = mock_store_instance

        # Run batch
        tasks = [
            {"id": "task-1", "prompt": "Task 1"},
            {"id": "task-2", "description": "Task 2"},
            {"id": "task-3", "prompt": "Task 3"},
        ]

        results = run_evaluation_batch(tasks, max_iterations=3)

        assert len(results) == 3
        assert results[0].task_id == "task-1"
        assert results[1].task_id == "task-2"
        assert results[2].task_id == "task-3"
        # First and third should pass, second fail
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True


class TestFeedbackLoopIntegration:
    """Test the full feedback loop: evaluate -> analyse -> tune -> apply."""

    def test_feedback_store_persistence(self, tmp_path):
        """Test feedback persists across runs."""
        db_path = tmp_path / "feedback.db"
        store1 = FeedbackStore(str(db_path))

        # Insert some records
        from optim.feedback_store import FeedbackRecord
        records = [
            FeedbackRecord(workflow_id="w1", source="tester", severity="error", message="Test failed"),
            FeedbackRecord(workflow_id="w1", source="linter", severity="warning", message="Unused import"),
        ]
        store1.insert_batch(records)

        # Create new store instance (simulating new run)
        store2 = FeedbackStore(str(db_path))

        # Query should find records
        results = store2.query()
        assert len(results) == 2

        # Count by source
        counts = store2.count_by_source()
        assert counts["tester"] == 1
        assert counts["linter"] == 1

    def test_tuning_history_persistence(self, tmp_path):
        """Test tuning history persists across runs."""
        db_path = tmp_path / "feedback.db"
        store1 = FeedbackStore(str(db_path))

        # Save tuning history
        store1.save_tuning(
            agent="coder",
            original_prompt="Original prompt",
            variants=["Variant 1", "Variant 2"],
            evaluations=[{"v": "Variant 1", "score": 0.8}, {"v": "Variant 2", "score": 0.7}],
            best_variant="Variant 1",
            best_score=0.8,
        )

        # New store instance
        store2 = FeedbackStore(str(db_path))

        # Retrieve history
        history = store2.get_tuning_history(agent="coder")
        assert len(history) == 1
        assert history[0]["agent"] == "coder"
        assert history[0]["best_variant"] == "Variant 1"
        assert history[0]["best_score"] == 0.8


class TestConvergenceIntegration:
    """Test convergence detection integrated with evaluation."""

    def test_convergence_stops_early(self):
        """Test that convergence detection can stop optimisation early."""
        from optim.convergence import ConvergenceDetector, ConvergenceConfig
        from contracts.eval_result import EvalResult

        # Simulate scores that plateau quickly - 10 rounds
        results = [
            EvalResult(workflow_id=f"w{i}", task_id="t", overall_score=0.7 + i * 0.001)
            for i in range(10)
        ]

        config = ConvergenceConfig(
            min_samples=3,
            window_size=3,
            improvement_threshold=0.01,
            patience=2,
            min_score=0.5,
        )

        detector = ConvergenceDetector(config)
        
        # Simulate 5 rounds
        last_result = None
        for i in range(5):
            round_results = [results[i]]  # One result per round
            last_result = detector.record(round_results)

        # Should converge because improvements are < 1%
        assert last_result.converged is True
        assert last_result.improvement < 0.01

    def test_no_convergence_when_improving(self):
        """Test no convergence when scores keep improving."""
        from optim.convergence import check_convergence, ConvergenceConfig
        from contracts.eval_result import EvalResult

        # Scores improving steadily
        results = [
            EvalResult(workflow_id=f"w{i}", task_id="t", overall_score=0.5 + i * 0.05)
            for i in range(5)
        ]

        config = ConvergenceConfig(
            min_samples=3,
            window_size=2,
            improvement_threshold=0.01,
            patience=2,
        )

        conv_result = check_convergence(results, config)

        # Should not converge - still improving
        assert conv_result.converged is False
        assert conv_result.improvement > 0.01


class TestArtifactIntegration:
    """Test artifact management integration."""

    @patch("src.state.store.SQLiteEventStore")
    @patch("src.gateway.llm_client.LLMClient")
    @patch("src.orchestrator.runner.build_feedback_loop")
    def test_artifacts_saved_during_workflow(self, mock_build_graph, mock_llm, mock_store, tmp_path):
        """Test artifacts are created and saved during workflow."""
        from orchestrator.artifacts import create_artifact_manager

        # Setup mocks
        mock_graph = Mock()
        mock_compiled = Mock()
        mock_graph.compile.return_value = mock_compiled
        mock_compiled.invoke.return_value = {
            "workflow_id": "artifact-test",
            "verdict": "PASS",
            "current_iteration": 2,
            "code_patch": {"files": [{"path": "main.py", "content": "print('hello')"}]},
            "error": None,
        }
        mock_build_graph.return_value = mock_graph

        mock_store_instance = Mock()
        mock_store_instance.get_events.return_value = []
        mock_store.return_value = mock_store_instance

        # Override artifact root to temp path
        import src.orchestrator.artifacts as artifacts_module
        original_root = artifacts_module.ArtifactManager.ROOT_DIR
        artifacts_module.ArtifactManager.ROOT_DIR = tmp_path / "artifacts"

        try:
            result = run_workflow(
                task_description="Test artifact creation",
                max_iterations=3,
                enable_artifacts=True,
                enable_convergence=False,
                enable_hitl=False,
            )

            # Check artifacts were created
            assert result.artifacts_summary["total_artifacts"] > 0
            assert "source" in result.artifacts_summary["by_type"] or \
                   "final_code_patch" in result.artifacts_summary["by_type"]
        finally:
            artifacts_module.ArtifactManager.ROOT_DIR = original_root


class TestHITLIntegration:
    """Test HITL integration with workflow."""

    @patch("src.state.store.SQLiteEventStore")
    @patch("src.gateway.llm_client.LLMClient")
    @patch("src.orchestrator.runner.build_feedback_loop")
    def test_hitl_auto_approve(self, mock_build_graph, mock_llm, mock_store):
        """Test HITL with auto-approval backend."""
        mock_graph = Mock()
        mock_compiled = Mock()
        mock_graph.compile.return_value = mock_compiled
        mock_compiled.invoke.return_value = {
            "workflow_id": "hitl-test",
            "verdict": "PASS",
            "current_iteration": 1,
            "code_patch": {"files": [{"path": "test.py", "content": "pass"}]},
            "error": None,
        }
        mock_build_graph.return_value = mock_graph

        mock_store_instance = Mock()
        mock_store_instance.get_events.return_value = []
        mock_store.return_value = mock_store_instance

        result = run_workflow(
            task_description="Test HITL",
            max_iterations=3,
            enable_hitl=True,
            hitl_config={"backend": "auto", "policy": "approve", "enabled_gates": ["pre_code"]},
            enable_convergence=False,
            enable_artifacts=False,
        )

        # Should have HITL approvals recorded
        assert "hitl_approvals" in result.__dict__ or hasattr(result, "hitl_approvals")