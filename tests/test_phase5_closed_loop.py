"""
Phase 5 Tests — Closed-Loop Orchestration
==========================================
Tests for the enhanced orchestrator with convergence, artifacts, HITL.
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock

from orchestrator.runner import run_workflow, WorkflowResult
from orchestrator.convergence import create_convergence_manager, OrchestratorConvergence
from orchestrator.artifacts import create_artifact_manager, ArtifactManager
from orchestrator.hitl import (
    create_hitl_manager,
    HITLManager,
    ApprovalStatus,
    AutoApprovalBackend,
    CLIApprovalBackend,
)


class TestConvergenceManager:
    """Tests for convergence detection."""

    def test_convergence_detector_creation(self):
        """Test convergence manager can be created."""
        mgr = create_convergence_manager(
            min_samples=3,
            window_size=3,
            improvement_threshold=0.02,
            patience=2,
            min_score=0.7,
        )
        assert isinstance(mgr, OrchestratorConvergence)

    def test_convergence_records_scores(self):
        """Test that scores are recorded."""
        mgr = create_convergence_manager(min_samples=2, window_size=2)

        # Mock EvalResult
        from contracts.eval_result import EvalResult
        r1 = EvalResult(workflow_id="w1", task_id="t1", overall_score=0.5, passed=False)
        r2 = EvalResult(workflow_id="w2", task_id="t2", overall_score=0.52, passed=False)
        r3 = EvalResult(workflow_id="w3", task_id="t3", overall_score=0.53, passed=False)

        res1 = mgr.check(r1)
        assert res1.converged is False
        assert res1.samples_analysed == 1

        res2 = mgr.check(r2)
        assert res2.samples_analysed == 2

        res3 = mgr.check(r3)
        assert res3.samples_analysed == 3

    def test_convergence_detects_plateau(self):
        """Test convergence detects score plateau."""
        mgr = create_convergence_manager(
            min_samples=3,
            window_size=2,
            improvement_threshold=0.01,
            patience=2,
            min_score=0.5,
        )

        from contracts.eval_result import EvalResult
        # Scores that plateau
        scores = [0.6, 0.61, 0.615, 0.617, 0.618]
        for s in scores:
            r = EvalResult(workflow_id="w", task_id="t", overall_score=s, passed=True)
            res = mgr.check(r)

        # Should converge due to plateau
        assert res.converged is True or res.patience_remaining <= 1


class TestArtifactManager:
    """Tests for artifact management."""

    def test_artifact_manager_creation(self):
        """Test artifact manager can be created."""
        mgr = create_artifact_manager("test-wf-123")
        assert isinstance(mgr, ArtifactManager)
        assert mgr.workflow_id == "test-wf-123"

    def test_save_and_retrieve_artifact(self, tmp_path):
        """Test saving and retrieving artifacts."""
        mgr = create_artifact_manager("test-wf-456")
        # Override root to temp path
        mgr.ROOT_DIR = tmp_path / "artifacts"
        mgr.run_dir = mgr.ROOT_DIR / mgr.workflow_id
        mgr.run_dir.mkdir(parents=True, exist_ok=True)
        mgr._index_path = mgr.run_dir / "index.json"

        artifact = mgr.save(
            content="print('hello')",
            artifact_type="source",
            iteration=1,
            filename="test.py",
        )

        assert artifact.workflow_id == "test-wf-456"
        assert artifact.iteration == 1
        assert artifact.artifact_type == "source"
        assert artifact.size_bytes > 0

        # Retrieve
        latest = mgr.get_latest("source")
        assert latest is not None
        content = mgr.read_text(latest)
        assert content == "print('hello')"

    def test_artifact_summary(self, tmp_path):
        """Test artifact summary."""
        mgr = create_artifact_manager("test-wf-789")
        mgr.ROOT_DIR = tmp_path / "artifacts"
        mgr.run_dir = mgr.ROOT_DIR / mgr.workflow_id
        mgr.run_dir.mkdir(parents=True, exist_ok=True)
        mgr._index_path = mgr.run_dir / "index.json"

        mgr.save("code1", "source", 1, "a.py")
        mgr.save("code2", "source", 2, "b.py")
        mgr.save("test output", "test", 1, "test.log")

        summary = mgr.summary()
        assert summary["total_artifacts"] == 3
        assert summary["by_type"]["source"] == 2
        assert summary["by_type"]["test"] == 1


class TestHITLManager:
    """Tests for Human-in-the-Loop."""

    def test_auto_approval_backend(self):
        """Test auto-approval backend."""
        backend = AutoApprovalBackend(policy="approve")
        from orchestrator.hitl import ApprovalRequest
        req = ApprovalRequest(
            workflow_id="w1",
            iteration=1,
            gate="pre_code",
            title="Test",
            description="Test approval",
        )
        status = backend.request_approval(req)
        assert status == ApprovalStatus.APPROVED

    def test_auto_reject_backend(self):
        """Test auto-reject backend."""
        backend = AutoApprovalBackend(policy="reject")
        from orchestrator.hitl import ApprovalRequest
        req = ApprovalRequest(
            workflow_id="w1",
            iteration=1,
            gate="pre_code",
            title="Test",
            description="Test approval",
        )
        status = backend.request_approval(req)
        assert status == ApprovalStatus.REJECTED

    def test_hitl_manager_creation(self):
        """Test HITL manager creation."""
        mgr = create_hitl_manager(
            backend="auto",
            enabled_gates=["pre_code", "post_test"],
            policy="approve",
        )
        assert isinstance(mgr, HITLManager)
        assert "pre_code" in mgr.enabled_gates
        assert "post_test" in mgr.enabled_gates

    def test_hitl_skips_disabled_gates(self):
        """Test that disabled gates are skipped."""
        mgr = create_hitl_manager(
            backend="auto",
            enabled_gates=["pre_code"],
            policy="approve",
        )
        # post_test is not enabled
        status = mgr.request(
            workflow_id="w1",
            iteration=1,
            gate="post_test",
            title="Test",
            description="Test",
        )
        assert status == ApprovalStatus.SKIPPED


class TestEnhancedRunner:
    """Tests for the enhanced workflow runner."""

    @patch("src.state.store.SQLiteEventStore")
    @patch("src.gateway.llm_client.LLMClient")
    @patch("src.orchestrator.runner.build_feedback_loop")
    def test_run_workflow_basic(self, mock_build_graph, mock_llm, mock_store):
        """Test basic workflow run."""
        # Setup mocks
        mock_graph = Mock()
        mock_compiled = Mock()
        mock_graph.compile.return_value = mock_compiled
        mock_compiled.invoke.return_value = {
            "workflow_id": "test-wf",
            "verdict": "PASS",
            "current_iteration": 1,
            "code_patch": {"files": [{"path": "test.py", "content": "print(1)"}]},
            "error": None,
        }
        mock_build_graph.return_value = mock_graph

        mock_store_instance = Mock()
        mock_store_instance.get_events.return_value = []
        mock_store.return_value = mock_store_instance

        result = run_workflow(
            task_description="Write a hello world function",
            max_iterations=3,
            enable_convergence=False,
            enable_artifacts=False,
            enable_hitl=False,
        )

        assert isinstance(result, WorkflowResult)
        assert result.success is True
        assert result.iterations == 1
        assert "test.py" in result.final_code

    @patch("src.state.store.SQLiteEventStore")
    @patch("src.gateway.llm_client.LLMClient")
    @patch("src.orchestrator.runner.build_feedback_loop")
    def test_run_workflow_with_phase5_features(self, mock_build_graph, mock_llm, mock_store):
        """Test workflow with Phase 5 features enabled."""
        mock_graph = Mock()
        mock_compiled = Mock()
        mock_graph.compile.return_value = mock_compiled
        mock_compiled.invoke.return_value = {
            "workflow_id": "test-wf-2",
            "verdict": "PASS",
            "current_iteration": 2,
            "code_patch": {"files": [{"path": "main.py", "content": "def main(): pass"}]},
            "error": None,
        }
        mock_build_graph.return_value = mock_graph

        mock_store_instance = Mock()
        mock_store_instance.get_events.return_value = []
        mock_store.return_value = mock_store_instance

        result = run_workflow(
            task_description="Create a simple API",
            max_iterations=5,
            enable_convergence=True,
            convergence_config={"min_samples": 2, "patience": 1},
            enable_artifacts=True,
            enable_hitl=True,
            hitl_config={"backend": "auto", "policy": "approve"},
        )

        assert isinstance(result, WorkflowResult)
        assert result.converged is not None  # Should have convergence info
        assert "total_artifacts" in result.artifacts_summary


class TestEvaluationBatch:
    """Tests for evaluation batch runner."""

    @patch("src.orchestrator.runner.run_workflow")
    def test_run_evaluation_batch(self, mock_run_workflow):
        """Test batch evaluation runner."""
        from orchestrator.runner import WorkflowResult, run_evaluation_batch

        mock_run_workflow.side_effect = [
            WorkflowResult(workflow_id="w1", success=True, iterations=1, final_code={}),
            WorkflowResult(workflow_id="w2", success=False, iterations=3, final_code={}, error="Failed"),
        ]

        tasks = [
            {"id": "task-1", "prompt": "Task 1"},
            {"id": "task-2", "description": "Task 2"},
        ]

        results = run_evaluation_batch(tasks, max_iterations=3)

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False
        assert results[0].task_id == "task-1"
        assert results[1].task_id == "task-2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])