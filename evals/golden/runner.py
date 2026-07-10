"""
Golden Task Runner — Phase 5
=============================
Runs golden evaluation tasks through the full autonomous loop
and collects EvalResults for scoring and optimisation.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore

from src.contracts.eval_result import EvalIssue, EvalResult
from src.contracts.run import AgentInvocation, WorkflowRun
from src.orchestrator.runner import run_workflow


class GoldenTask:
    """A single golden task loaded from tasks.yaml."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.id: str = raw["id"]
        self.name: str = raw["name"]
        self.description: str = raw["description"]
        self.language: str = raw.get("language", "python")
        self.difficulty: str = raw.get("difficulty", "medium")
        self.expected_files: list[str] = raw.get("expected_files", [])
        self.golden_solution: str | None = raw.get("golden_solution")
        self.test_cases: list[dict[str, str]] = raw.get("test_cases", [])
        self.verification: list[dict[str, str]] = raw.get("verification", [])

    @property
    def task_prompt(self) -> str:
        """The prompt to send to the orchestrator."""
        return self.description


class GoldenRunner:
    """Runs golden tasks through the orchestrator and evaluates results."""

    def __init__(
        self,
        tasks_file: str | None = None,
        max_iterations: int = 5,
        timeout_per_task: int = 600,
    ) -> None:
        self.tasks_file = tasks_file or "evals/golden/tasks.yaml"
        self.max_iterations = max_iterations
        self.timeout_per_task = timeout_per_task

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def load_tasks(self) -> list[GoldenTask]:
        """Load golden tasks from YAML file."""
        path = Path(self.tasks_file)
        if not path.exists():
            raise FileNotFoundError(f"Golden tasks file not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        raw_tasks: list[dict[str, Any]] = data.get("tasks", [])
        print(f"[GoldenRunner] Loaded {len(raw_tasks)} tasks from {path}")
        return [GoldenTask(t) for t in raw_tasks]

    # ------------------------------------------------------------------
    # Run All
    # ------------------------------------------------------------------
    def run_all(self) -> list[EvalResult]:
        """Run all golden tasks and return evaluation results."""
        tasks = self.load_tasks()
        results: list[EvalResult] = []

        for i, task in enumerate(tasks, 1):
            print(f"\n{'='*60}")
            print(f"[GoldenRunner] Task {i}/{len(tasks)}: {task.id} — {task.name}")
            print(f"  Difficulty: {task.difficulty} | Language: {task.language}")
            print(f"{'='*60}")
            result = self.run_task(task)
            results.append(result)

        self._print_summary(results)
        return results

    # ------------------------------------------------------------------
    # Run Single Task
    # ------------------------------------------------------------------
    def run_task(self, task: GoldenTask) -> EvalResult:
        """Run a single golden task through the autonomous loop."""
        workflow_id = str(uuid.uuid4())
        start_time = time.monotonic()

        # Step 1: Orchestrate the task
        try:
            workflow_run = run_workflow(
                task_description=task.task_prompt,
                language=task.language,
                max_iterations=self.max_iterations,
                workflow_id=workflow_id,
            )
        except Exception as exc:
            # If orchestration crashes, return a failed result
            return self._failure_result(
                workflow_id=workflow_id,
                task_id=task.id,
                error=str(exc),
                start_time=start_time,
            )

        # Step 2: Evaluate the output
        result = self._evaluate(task, workflow_run, start_time)
        return result

    # ------------------------------------------------------------------
    # Evaluation Logic
    # ------------------------------------------------------------------
    def _evaluate(
        self, task: GoldenTask, run: WorkflowRun, start_time: float
    ) -> EvalResult:
        """Score a completed workflow run against the golden task."""
        duration = time.monotonic() - start_time
        result = EvalResult(
            workflow_id=run.workflow_id,
            task_id=task.id,
            iterations_taken=run.iterations,
            total_cost_usd=run.total_cost_usd,
            total_duration_seconds=duration,
        )

        # 1. Check file existence
        missing_files = [
            f for f in task.expected_files if f not in run.final_code
        ]
        if missing_files:
            result.issues.append(
                EvalIssue(
                    source="golden_check",
                    severity="error",
                    message=f"Missing expected files: {', '.join(missing_files)}",
                )
            )

        # 2. Test pass rate (from the orchestrated run — we trust the tester agent)
        # In a real SWE-bench setup we'd actually run tests here.
        # For golden tasks, we check if the run was successful.
        if run.success:
            result.test_pass_rate = 1.0
        else:
            result.test_pass_rate = 0.0
            result.issues.append(
                EvalIssue(
                    source="orchestrator",
                    severity="error",
                    message=f"Workflow did not succeed: {run.error or 'unknown reason'}",
                )
            )

        # 3. Lint score (inferred from the workflow — democratically 0.95 if no lint issues)
        # A real implementation would run ruff/mypy on the generated code.
        # For now, we set defaults based on workflow success signals.
        lint_issues = [
            i for i in (run.error or "").split("\n") if "lint" in i.lower()
        ]
        if lint_issues:
            result.lint_score = max(0.0, 1.0 - 0.1 * len(lint_issues))
            for li in lint_issues:
                result.issues.append(
                    EvalIssue(source="lint", severity="warning", message=li)
                )
        else:
            result.lint_score = 0.95  # Assume clean unless told otherwise

        # 4. Type check
        result.type_check_passed = "type_error" not in (run.error or "").lower()

        # 5. Security
        result.security_issues_count = 0  # Filled by red-team separately

        # 6. Compute overall score
        result.overall_score = self._compute_score(result)

        # 7. Pass/fail
        result.passed = result.overall_score >= 0.60 and result.test_pass_rate >= 0.5

        # 8. Store artifact reference
        result.artifact_path = getattr(run, 'artifact_path', None)

        print(
            f"[GoldenRunner] {task.id}: "
            f"passed={result.passed}, "
            f"score={result.overall_score:.2f}, "
            f"iterations={result.iterations_taken}, "
            f"cost=${result.total_cost_usd:.4f}"
        )
        return result

    # ------------------------------------------------------------------
    # Scoring Algorithm
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_score(result: EvalResult) -> float:
        """Compute composite score from weighted signals."""
        weights = {
            "test_pass": 0.40,
            "lint": 0.10,
            "type_check": 0.15,
            "security": 0.10,
        }
        # Judge weight is distributed to others if no judge yet
        if result.judge_score is None:
            weights["test_pass"] += 0.25  # Add judge weight to test pass

        score = (
            weights["test_pass"] * result.test_pass_rate
            + weights["lint"] * result.lint_score
            + weights["type_check"] * (1.0 if result.type_check_passed else 0.3)
            + weights["security"]
            * max(0.0, 1.0 - result.security_issues_count * 0.1)
        )
        return min(1.0, max(0.0, score))

    # ------------------------------------------------------------------
    # Failure Fallback
    # ------------------------------------------------------------------
    def _failure_result(
        self, workflow_id: str, task_id: str, error: str, start_time: float
    ) -> EvalResult:
        """Create an EvalResult for a crashed orchestration."""
        duration = time.monotonic() - start_time
        result = EvalResult(
            workflow_id=workflow_id,
            task_id=task_id,
            passed=False,
            overall_score=0.0,
            total_duration_seconds=duration,
        )
        result.issues.append(
            EvalIssue(
                source="orchestrator",
                severity="critical",
                message=f"Orchestration crashed: {error}",
            )
        )
        return result

    # ------------------------------------------------------------------
    # Summary Report
    # ------------------------------------------------------------------
    @staticmethod
    def _print_summary(results: list[EvalResult]) -> None:
        """Print a summary of all task results."""
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        avg_score = sum(r.overall_score for r in results) / max(total, 1)
        avg_iterations = sum(r.iterations_taken for r in results) / max(total, 1)
        total_cost = sum(r.total_cost_usd for r in results)

        print(f"\n{'='*60}")
        print("GOLDEN TASK EVALUATION — SUMMARY")
        print(f"{'='*60}")
        print(f"  Total tasks:   {total}")
        print(f"  Passed:        {passed}")
        print(f"  Failed:        {total - passed}")
        print(f"  Pass rate:     {passed / max(total, 1):.1%}")
        print(f"  Avg score:     {avg_score:.2f}")
        print(f"  Avg iterations:{avg_iterations:.1f}")
        print(f"  Total cost:    ${total_cost:.4f}")
        print(f"{'='*60}")

        if total - passed > 0:
            print("\n  Failed tasks:")
            for r in results:
                if not r.passed:
                    print(f"    - {r.task_id}: score={r.overall_score:.2f}")


def run_golden_eval(
    tasks_file: str = "evals/golden/tasks.yaml",
    max_iterations: int = 5,
) -> list[EvalResult]:
    """Convenience entry-point: run all golden tasks."""
    runner = GoldenRunner(
        tasks_file=tasks_file,
        max_iterations=max_iterations,
    )
    return runner.run_all()


if __name__ == "__main__":
    run_golden_eval()