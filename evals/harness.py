"""
Evaluation Harness — Phase 6
============================
Trajectory-first evaluation: runs full workflows end-to-end
and measures % Resolved (SWE-bench style) + golden tasks.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.orchestrator.runner import run_workflow
from src.contracts.schemas import TaskAssignment, CodePatch, VerificationReport, ReviewDecision


@dataclass
class EvaluationResult:
    """Result of evaluating a single task."""
    task_id: str
    workflow_id: str
    passed: bool
    overall_score: float
    iterations_taken: int
    total_cost_usd: float
    total_duration_seconds: float
    issues: list[str] = field(default_factory=list)
    # Detailed metrics
    test_pass_rate: float = 1.0
    lint_score: float = 1.0
    type_check_passed: bool = True
    security_issues_count: int = 0
    coverage_percent: float | None = None
    # Trajectory data
    trajectory: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvaluationSummary:
    """Summary of an evaluation run."""
    run_id: str
    started_at: str
    finished_at: str | None = None
    total_tasks: int = 0
    passed_tasks: int = 0
    failed_tasks: int = 0
    timeout_tasks: int = 0
    percent_resolved: float = 0.0
    mean_score: float = 0.0
    median_score: float = 0.0
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    avg_iterations: float = 0.0
    results: list[EvaluationResult] = field(default_factory=list)


class EvaluationHarness:
    """
    Trajectory-first evaluation harness.
    
    Runs tasks through the complete AI Dev Team pipeline and
    evaluates outcomes based on verified execution results.
    """
    
    def __init__(
        self,
        max_iterations: int = 5,
        timeout_seconds: int = 300,
        cost_cap_usd: float = 1.0,
        verbose: bool = False,
    ):
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        self.cost_cap_usd = cost_cap_usd
        self.verbose = verbose
        
        self.run_id = f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        self.results: list[EvaluationResult] = []
        self.started_at = datetime.now(timezone.utc).isoformat()
    
    def evaluate_task(
        self,
        task_id: str,
        task_prompt: str,
        expected_outcome: dict | None = None,
    ) -> EvaluationResult:
        """
        Evaluate a single task through the full pipeline.
        
        Args:
            task_id: Unique identifier for the task
            task_prompt: The task description/prompt
            expected_outcome: Optional expected output for validation
            
        Returns:
            EvaluationResult with all metrics
        """
        workflow_id = f"{self.run_id}-{task_id}"
        start_time = time.time()
        
        if self.verbose:
            print(f"\n📋 Evaluating task: {task_id}")
            print(f"   Prompt: {task_prompt[:80]}...")
        
        try:
            # Run the full workflow
            result = run_workflow(
                task_description=task_prompt,
                workflow_id=workflow_id,
                max_iterations=self.max_iterations,
                cost_cap_usd=self.cost_cap_usd,
            )
            
            duration = time.time() - start_time
            
            # Extract metrics from result
            passed = getattr(result, "verdict", "fail") == "pass"
            score = getattr(result, "score", 0.0)
            iterations = getattr(result, "iterations_taken", 1)
            cost = getattr(result, "total_cost_usd", 0.0)
            issues = getattr(result, "issues", [])
            
            # Get detailed verification data
            test_pass_rate = getattr(result, "test_pass_rate", 1.0)
            lint_score = getattr(result, "lint_score", 1.0)
            type_check_passed = getattr(result, "type_check_passed", True)
            security_issues = getattr(result, "security_issues_count", 0)
            coverage = getattr(result, "coverage_percent", None)
            
            # Build trajectory from events (if available)
            trajectory = getattr(result, "trajectory", [])
            
            eval_result = EvaluationResult(
                task_id=task_id,
                workflow_id=workflow_id,
                passed=passed,
                overall_score=score,
                iterations_taken=iterations,
                total_cost_usd=cost,
                total_duration_seconds=duration,
                issues=issues,
                test_pass_rate=test_pass_rate,
                lint_score=lint_score,
                type_check_passed=type_check_passed,
                security_issues_count=security_issues,
                coverage_percent=coverage,
                trajectory=trajectory,
            )
            
        except Exception as e:
            duration = time.time() - start_time
            eval_result = EvaluationResult(
                task_id=task_id,
                workflow_id=workflow_id,
                passed=False,
                overall_score=0.0,
                iterations_taken=0,
                total_cost_usd=0.0,
                total_duration_seconds=duration,
                issues=[f"Evaluation error: {str(e)}"],
            )
            
            if self.verbose:
                print(f"   ❌ Error: {e}")
        
        self.results.append(eval_result)
        
        if self.verbose:
            status = "✅ PASS" if eval_result.passed else "❌ FAIL"
            print(f"   {status} | Score: {eval_result.overall_score:.2f} | "
                  f"Cost: ${eval_result.total_cost_usd:.4f} | "
                  f"Time: {eval_result.total_duration_seconds:.1f}s")
        
        return eval_result
    
    def evaluate_batch(
        self,
        tasks: list[dict[str, Any]],
        max_tasks: int | None = None,
    ) -> EvaluationSummary:
        """
        Evaluate a batch of tasks.
        
        Args:
            tasks: List of task dicts with 'id', 'prompt', optional 'expected'
            max_tasks: Optional limit on number of tasks to evaluate
            
        Returns:
            EvaluationSummary with aggregate metrics
        """
        tasks_to_run = tasks[:max_tasks] if max_tasks else tasks
        
        print(f"\n{'='*60}")
        print(f"🚀 Evaluation Run: {self.run_id}")
        print(f"   Tasks: {len(tasks_to_run)}")
        print(f"   Max iterations: {self.max_iterations}")
        print(f"   Timeout: {self.timeout_seconds}s")
        print(f"   Cost cap: ${self.cost_cap_usd:.2f}")
        print(f"{'='*60}")
        
        for i, task in enumerate(tasks_to_run, 1):
            task_id = task.get("id", f"task-{i}")
            prompt = task.get("prompt", task.get("description", ""))
            expected = task.get("expected", task.get("expected_outcome"))
            
            if self.verbose:
                print(f"\n[{i}/{len(tasks_to_run)}] {task_id}")
            
            self.evaluate_task(task_id, prompt, expected)
        
        return self.summarize()
    
    def summarize(self) -> EvaluationSummary:
        """Generate evaluation summary."""
        finished_at = datetime.now(timezone.utc).isoformat()
        
        if not self.results:
            return EvaluationSummary(
                run_id=self.run_id,
                started_at=self.started_at,
                finished_at=finished_at,
            )
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        
        scores = [r.overall_score for r in self.results]
        scores_sorted = sorted(scores)
        median_score = scores_sorted[len(scores_sorted) // 2] if scores_sorted else 0.0
        
        total_cost = sum(r.total_cost_usd for r in self.results)
        total_duration = sum(r.total_duration_seconds for r in self.results)
        avg_iterations = sum(r.iterations_taken for r in self.results) / total
        
        summary = EvaluationSummary(
            run_id=self.run_id,
            started_at=self.started_at,
            finished_at=finished_at,
            total_tasks=total,
            passed_tasks=passed,
            failed_tasks=failed,
            timeout_tasks=0,  # Could track separately
            percent_resolved=(passed / total * 100) if total > 0 else 0.0,
            mean_score=sum(scores) / total if total > 0 else 0.0,
            median_score=median_score,
            total_cost_usd=total_cost,
            total_duration_seconds=total_duration,
            avg_iterations=avg_iterations,
            results=self.results,
        )
        
        print(f"\n{'='*60}")
        print(f"📊 EVALUATION SUMMARY: {self.run_id}")
        print(f"{'='*60}")
        print(f"   Total Tasks:     {total}")
        print(f"   Passed:          {passed} ({summary.percent_resolved:.1f}%)")
        print(f"   Failed:          {failed}")
        print(f"   Mean Score:      {summary.mean_score:.4f}")
        print(f"   Median Score:    {summary.median_score:.4f}")
        print(f"   Total Cost:      ${total_cost:.6f}")
        print(f"   Total Duration:  {total_duration:.1f}s")
        print(f"   Avg Iterations:  {avg_iterations:.1f}")
        print(f"{'='*60}")
        
        return summary
    
    def save_results(self, output_dir: str | Path = "reports/evaluations") -> Path:
        """Save evaluation results to disk."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        summary = self.summarize()
        
        # Save as JSON
        json_file = output_path / f"evaluation_{self.run_id}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "run_id": summary.run_id,
                "started_at": summary.started_at,
                "finished_at": summary.finished_at,
                "total_tasks": summary.total_tasks,
                "passed_tasks": summary.passed_tasks,
                "failed_tasks": summary.failed_tasks,
                "percent_resolved": summary.percent_resolved,
                "mean_score": summary.mean_score,
                "median_score": summary.median_score,
                "total_cost_usd": summary.total_cost_usd,
                "total_duration_seconds": summary.total_duration_seconds,
                "avg_iterations": summary.avg_iterations,
                "results": [
                    {
                        "task_id": r.task_id,
                        "workflow_id": r.workflow_id,
                        "passed": r.passed,
                        "overall_score": r.overall_score,
                        "iterations_taken": r.iterations_taken,
                        "total_cost_usd": r.total_cost_usd,
                        "total_duration_seconds": r.total_duration_seconds,
                        "issues": r.issues,
                        "test_pass_rate": r.test_pass_rate,
                        "lint_score": r.lint_score,
                        "type_check_passed": r.type_check_passed,
                        "security_issues_count": r.security_issues_count,
                        "coverage_percent": r.coverage_percent,
                    }
                    for r in summary.results
                ],
            }, f, indent=2, ensure_ascii=False)
        
        # Save as Markdown
        md_file = output_path / f"evaluation_{self.run_id}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(self._generate_markdown(summary))
        
        print(f"\n💾 Results saved:")
        print(f"   JSON: {json_file}")
        print(f"   Markdown: {md_file}")
        
        return json_file
    
    def _generate_markdown(self, summary: EvaluationSummary) -> str:
        """Generate markdown report."""
        lines = [
            f"# Evaluation Report: {summary.run_id}",
            f"\n**Started:** {summary.started_at}",
            f"**Finished:** {summary.finished_at or 'In progress'}",
            f"\n## Summary",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Tasks | {summary.total_tasks} |",
            f"| Passed | {summary.passed_tasks} ({summary.percent_resolved:.1f}%) |",
            f"| Failed | {summary.failed_tasks} |",
            f"| Mean Score | {summary.mean_score:.4f} |",
            f"| Median Score | {summary.median_score:.4f} |",
            f"| Total Cost | ${summary.total_cost_usd:.6f} |",
            f"| Total Duration | {summary.total_duration_seconds:.1f}s |",
            f"| Avg Iterations | {summary.avg_iterations:.1f} |",
            f"\n## Task Results",
            f"| Task ID | Status | Score | Iterations | Cost | Duration |",
            f"|---------|--------|-------|------------|------|----------|",
        ]
        
        for r in summary.results:
            status = "✅ PASS" if r.passed else "❌ FAIL"
            lines.append(
                f"| {r.task_id} | {status} | {r.overall_score:.3f} | "
                f"{r.iterations_taken} | ${r.total_cost_usd:.4f} | {r.total_duration_seconds:.1f}s |"
            )
        
        lines.append(f"\n---\n*Generated by AI Dev Team Phase 6 Evaluation Harness*")
        return "\n".join(lines)


def load_tasks_from_yaml(path: str | Path) -> list[dict[str, Any]]:
    """Load tasks from YAML file (golden tasks format)."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("tasks", [])


def run_evaluation(
    tasks_path: str | Path = "evals/golden/tasks.yaml",
    max_iterations: int = 5,
    timeout_seconds: int = 300,
    cost_cap_usd: float = 1.0,
    max_tasks: int | None = None,
    output_dir: str | Path = "reports/evaluations",
    verbose: bool = False,
) -> EvaluationSummary:
    """
    Convenience function to run a full evaluation.
    
    Args:
        tasks_path: Path to tasks YAML file
        max_iterations: Max workflow iterations per task
        timeout_seconds: Timeout per task
        cost_cap_usd: Cost cap per workflow
        max_tasks: Optional limit on number of tasks
        output_dir: Directory to save results
        verbose: Print detailed progress
        
    Returns:
        EvaluationSummary
    """
    tasks = load_tasks_from_yaml(tasks_path)
    
    harness = EvaluationHarness(
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
        cost_cap_usd=cost_cap_usd,
        verbose=verbose,
    )
    
    summary = harness.evaluate_batch(tasks, max_tasks=max_tasks)
    harness.save_results(output_dir)
    
    return summary


if __name__ == "__main__":
    import sys
    
    # Allow CLI usage
    tasks_file = sys.argv[1] if len(sys.argv) > 1 else "evals/golden/tasks.yaml"
    max_tasks = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    summary = run_evaluation(
        tasks_path=tasks_file,
        max_tasks=max_tasks,
        verbose=True,
    )
    
    print(f"\n✅ Evaluation complete: {summary.percent_resolved:.1f}% resolved")
    sys.exit(0 if summary.percent_resolved > 0 else 1)