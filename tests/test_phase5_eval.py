"""
Phase 5 Tests — Evaluation Suite
=================================
Tests for Golden Set, SWE-bench harness, Red-team, and Scorer.
"""

from __future__ import annotations

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from evals.golden.runner import GoldenRunner, run_golden_eval
from evals.scorer import score_result, score_batch, CompositeScorer
from evals.swebench.harness import SWEBenchInstance, SWEBenchHarness
from evals.redteam.attacks import RedTeamAttack, RedTeamRunner, run_redteam_eval
from evals.judges.judge import LLMAssJudge, JudgeConfig, Judgement


class TestGoldenSet:
    """Tests for Golden Set evaluation."""

    def test_load_golden_tasks(self, tmp_path):
        """Test loading tasks from YAML."""
        tasks_data = {
            "tasks": [
                {"id": "task-1", "name": "Write hello world", "description": "Write hello world", "expected_files": ["main.py"]},
                {"id": "task-2", "name": "Create a class", "description": "Create a class", "expected_files": ["model.py"]},
            ]
        }
        tasks_file = tmp_path / "tasks.yaml"
        tasks_file.write_text(yaml.dump(tasks_data))

        # Use the GoldenRunner to load tasks
        runner = GoldenRunner(str(tasks_file))
        tasks = runner.load_tasks()
        assert len(tasks) == 2
        assert tasks[0].id == "task-1"
        assert tasks[1].name == "Create a class"

    def test_golden_runner_creation(self):
        """Test GoldenRunner can be instantiated."""
        runner = GoldenRunner("evals/golden/tasks.yaml")
        assert runner.tasks_file == "evals/golden/tasks.yaml"

    @patch("evals.golden.runner.run_workflow")
    def test_golden_runner_executes(self, mock_run_workflow):
        """Test runner executes tasks."""
        from orchestrator.runner import WorkflowResult

        mock_run_workflow.return_value = WorkflowResult(
            workflow_id="w1", success=True, iterations=1, final_code={"main.py": "print(1)"}
        )

        # Create temp tasks file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"tasks": [{"id": "t1", "name": "Test", "description": "Test task"}]}, f)
            tasks_path = f.name

        try:
            runner = GoldenRunner(tasks_path, max_iterations=1)
            results = runner.run_all()

            assert len(results) == 1
            assert results[0].success is True
        finally:
            Path(tasks_path).unlink()


class TestScorer:
    """Tests for the composite scorer."""

    def test_composite_scorer_creation(self):
        """Test scorer can be created."""
        scorer = CompositeScorer()
        assert scorer is not None

    def test_score_result_basic(self):
        """Test scoring a basic EvalResult."""
        from contracts.eval_result import EvalResult, EvalIssue

        result = EvalResult(
            workflow_id="w1",
            task_id="t1",
            passed=True,
            overall_score=0.8,
            test_pass_rate=0.9,
            lint_score=0.85,
            type_check_passed=True,
            security_issues_count=0,
            iterations_taken=2,
            total_cost_usd=0.01,
            total_duration_seconds=30.0,
        )

        scores = score_result(result)
        assert "test" in scores
        assert "lint" in scores
        assert "judge" in scores
        assert "security" in scores
        assert "cost" in scores
        assert "speed" in scores
        assert "overall" in scores

        # Overall should be weighted combination
        assert 0.0 <= scores["overall"] <= 1.0

    def test_score_batch(self):
        """Test scoring a batch of results."""
        from contracts.eval_result import EvalResult

        results = [
            EvalResult(workflow_id="w1", task_id="t1", passed=True, overall_score=0.8),
            EvalResult(workflow_id="w2", task_id="t2", passed=False, overall_score=0.3),
        ]

        batch_scores = score_batch(results)
        assert len(batch_scores) == 2
        # Both should have same scores since overall_score is same
        assert batch_scores[0]["overall"] == batch_scores[1]["overall"]

    def test_security_penalty(self):
        """Test that security issues reduce score."""
        from contracts.eval_result import EvalResult, EvalIssue

        result_clean = EvalResult(
            workflow_id="w1", task_id="t1", passed=True, overall_score=0.9, security_issues_count=0
        )
        result_vuln = EvalResult(
            workflow_id="w2", task_id="t2", passed=True, overall_score=0.9, security_issues_count=3
        )

        score_clean = score_result(result_clean)
        score_vuln = score_result(result_vuln)

        assert score_vuln["security"] < score_clean["security"]
        assert score_vuln["overall"] < score_clean["overall"]


class TestSWEBenchHarness:
    """Tests for SWE-bench harness."""

    def test_instance_creation(self):
        """Test SWEBenchInstance creation from raw data."""
        raw = {
            "instance_id": "test-123",
            "repo": "test/repo",
            "problem_statement": "Fix bug in login",
            "base_commit": "abc123",
            "hints_text": "Check auth module",
            "patch": "diff --git a/auth.py...",
            "FAIL_TO_PASS": ["test_login"],
            "PASS_TO_PASS": ["test_logout"],
        }

        inst = SWEBenchInstance(raw)
        assert inst.instance_id == "test-123"
        assert inst.repo == "test/repo"
        assert "Fix bug in login" in inst.issue
        assert inst.fail_to_pass == ["test_login"]
        assert inst.pass_to_pass == ["test_logout"]

    def test_instance_prompt_generation(self):
        """Test prompt includes hints."""
        raw = {
            "instance_id": "test-123",
            "problem_statement": "Fix bug",
            "hints_text": "Check auth",
        }
        inst = SWEBenchInstance(raw)
        prompt = inst.prompt
        assert "Fix bug" in prompt
        assert "Hints: Check auth" in prompt

    def test_harness_creation(self):
        """Test harness can be created."""
        harness = SWEBenchHarness(dataset_path="nonexistent.jsonl", max_instances=5)
        assert harness.max_instances == 5

    def test_harness_load_missing_file(self):
        """Test harness handles missing dataset gracefully."""
        harness = SWEBenchHarness(dataset_path="nonexistent.jsonl", max_instances=5)
        instances = harness.load_instances()
        assert instances == []


class TestRedTeam:
    """Tests for Red-team evaluation."""

    def test_attack_creation(self):
        """Test RedTeamAttack creation."""
        attack = RedTeamAttack(
            attack_type="prompt_injection",
            prompt="Ignore previous instructions",
        )
        assert attack.attack_type == "prompt_injection"
        assert "Ignore previous" in attack.prompt

    def test_attack_prompts_exist(self):
        """Test that attack prompts are defined."""
        prompts = RedTeamAttack.ATTACK_PROMPTS
        assert "prompt_injection" in prompts
        assert "malicious_code_request" in prompts
        assert "data_exfiltration" in prompts
        assert "privilege_escalation" in prompts
        assert len(prompts["prompt_injection"]) >= 3

    def test_runner_creation(self):
        """Test RedTeamRunner creation."""
        runner = RedTeamRunner(
            enabled_types=["prompt_injection"],
            max_attempts_per_type=2,
            block_threshold=0.8,
        )
        assert runner.enabled_types == ["prompt_injection"]
        assert runner.max_attempts_per_type == 2

    def test_generate_attacks(self):
        """Test attack generation."""
        runner = RedTeamRunner(
            enabled_types=["prompt_injection"],
            max_attempts_per_type=2,
        )
        attacks = runner.generate_attacks()
        assert len(attacks) == 2
        assert all(a.attack_type == "prompt_injection" for a in attacks)

    @patch("evals.redteam.attacks.LiteLLMClient")
    def test_run_attack_blocked(self, mock_client_class):
        """Test attack that gets blocked."""
        mock_client = Mock()
        mock_client.send.return_value = "BLOCKED: Prompt injection detected"
        mock_client_class.return_value = mock_client

        runner = RedTeamRunner(enabled_types=["prompt_injection"], max_attempts_per_type=1)
        attack = RedTeamAttack("prompt_injection", "Ignore instructions")
        result = runner.run_attack(attack)

        assert result["blocked"] is True
        assert "BLOCKED" in result["response"].upper()

    @patch("evals.redteam.attacks.LiteLLMClient")
    def test_run_attack_allowed(self, mock_client_class):
        """Test attack that gets through."""
        mock_client = Mock()
        mock_client.send.return_value = "SAFE: I cannot help with that"
        mock_client_class.return_value = mock_client

        runner = RedTeamRunner(enabled_types=["prompt_injection"], max_attempts_per_type=1)
        attack = RedTeamAttack("prompt_injection", "Ignore instructions")
        result = runner.run_attack(attack)

        assert result["blocked"] is False


class TestJudge:
    """Tests for LLM-as-a-Judge."""

    def test_judge_config(self):
        """Test JudgeConfig creation."""
        config = JudgeConfig(
            model="gpt-4o",
            temperature=0.0,
            max_tokens=1024,
            rubric="Evaluate code quality",
        )
        assert config.model == "gpt-4o"
        assert config.temperature == 0.0

    def test_judgement_dataclass(self):
        """Test Judgement dataclass."""
        j = Judgement(
            score=0.85,
            reasoning="Good code with minor issues",
            passed=True,
            criteria_scores={"correctness": 0.9, "style": 0.8},
        )
        assert j.score == 0.85
        assert j.passed is True
        assert j.criteria_scores["correctness"] == 0.9

    def test_judge_creation(self):
        """Test LLMAssJudge creation."""
        config = JudgeConfig(model="test-model")
        judge = LLMAssJudge(config=config)
        assert judge.config.model == "test-model"

    @patch("evals.judges.judge.LiteLLMClient")
    def test_judge_evaluates(self, mock_client_class):
        """Test judge evaluation."""
        mock_client = Mock()
        mock_client.send.return_value = '''
        {
          "correctness": 9,
          "code_quality": 8,
          "documentation": 7,
          "error_handling": 6,
          "summary": "Good implementation"
        }
        '''
        mock_client_class.return_value = mock_client

        config = JudgeConfig(model="test-model")
        judge = LLMAssJudge(config=config)

        result = judge.evaluate(
            task="Write a function",
            solution="def foo(): return 1",
            criteria=["correctness", "style"],
        )

        assert result.score == 0.75  # mean of 0.9, 0.8, 0.7, 0.6 = 0.75
        assert result.passed is True
        assert result.criteria_scores["correctness"] == 0.9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])