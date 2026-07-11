"""
Golden Tasks Runner — Phase 6
==============================
Runs the curated golden task set through the full evaluation harness.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from evals.harness import run_evaluation, load_tasks_from_yaml, EvaluationSummary


@dataclass
class GoldenRunner:
    """Runner for golden task evaluation."""

    tasks_path: str = "evals/golden/tasks.yaml"
    max_iterations: int = 5
    timeout_seconds: int = 300
    cost_cap_usd: float = 1.0
    max_tasks: int | None = None
    output_dir: str = "reports/evaluations/golden"
    verbose: bool = False

    def run(self, **kwargs) -> EvaluationSummary:
        """Run golden task evaluation."""
        return run_evaluation(
            tasks_path=self.tasks_path,
            max_iterations=self.max_iterations,
            timeout_seconds=self.timeout_seconds,
            cost_cap_usd=self.cost_cap_usd,
            max_tasks=self.max_tasks,
            output_dir=self.output_dir,
            verbose=self.verbose,
            **kwargs
        )


def run_golden_eval(
    tasks_path: str = "evals/golden/tasks.yaml",
    max_iterations: int = 5,
    timeout_seconds: int = 300,
    cost_cap_usd: float = 1.0,
    max_tasks: int | None = None,
    output_dir: str = "reports/evaluations/golden",
    verbose: bool = False,
) -> EvaluationSummary:
    """Convenience function to run golden evaluation."""
    runner = GoldenRunner(
        tasks_path=tasks_path,
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
        cost_cap_usd=cost_cap_usd,
        max_tasks=max_tasks,
        output_dir=output_dir,
        verbose=verbose,
    )
    return runner.run()


def main():
    parser = argparse.ArgumentParser(description="Run golden task evaluation")
    parser.add_argument(
        "--tasks",
        type=str,
        default="evals/golden/tasks.yaml",
        help="Path to golden tasks YAML file",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of tasks to run (default: all)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Max workflow iterations per task",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout per task in seconds",
    )
    parser.add_argument(
        "--cost-cap",
        type=float,
        default=1.0,
        help="Cost cap per workflow in USD",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/evaluations/golden",
        help="Output directory for results",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List tasks without running",
    )

    args = parser.parse_args()

    # Load and validate tasks
    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"❌ Tasks file not found: {tasks_path}")
        sys.exit(1)

    tasks = load_tasks_from_yaml(tasks_path)
    print(f"📂 Loaded {len(tasks)} golden tasks from {tasks_path}")

    if args.dry_run:
        print("\nTasks:")
        for i, task in enumerate(tasks, 1):
            task_id = task.get("id", f"task-{i}")
            prompt = task.get("prompt", task.get("description", ""))[:80]
            print(f"  {i}. {task_id}: {prompt}...")
        return

    # Run evaluation
    print(f"\n🚀 Starting golden task evaluation...")
    print(f"   Max tasks: {args.max_tasks or 'all'}")
    print(f"   Max iterations: {args.max_iterations}")
    print(f"   Timeout: {args.timeout}s")
    print(f"   Cost cap: ${args.cost_cap:.2f}")

    summary = run_evaluation(
        tasks_path=tasks_path,
        max_iterations=args.max_iterations,
        timeout_seconds=args.timeout,
        cost_cap_usd=args.cost_cap,
        max_tasks=args.max_tasks,
        output_dir=args.output_dir,
        verbose=args.verbose,
    )

    # Print final summary
    print(f"\n{'='*60}")
    print(f"🏁 GOLDEN TASK EVALUATION COMPLETE")
    print(f"{'='*60}")
    print(f"   Tasks evaluated: {summary.total_tasks}")
    print(f"   Passed: {summary.passed_tasks} ({summary.percent_resolved:.1f}%)")
    print(f"   Failed: {summary.failed_tasks}")
    print(f"   Mean score: {summary.mean_score:.4f}")
    print(f"   Total cost: ${summary.total_cost_usd:.6f}")
    print(f"   Total time: {summary.total_duration_seconds:.1f}s")

    # Exit code based on results
    if summary.percent_resolved >= 50:
        print(f"\n✅ TARGET MET: ≥50% resolved")
        sys.exit(0)
    else:
        print(f"\n⚠️  BELOW TARGET: <50% resolved")
        sys.exit(1)


if __name__ == "__main__":
    main()