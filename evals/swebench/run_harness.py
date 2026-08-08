#!/usr/bin/env python3
"""
SWE-bench Lite — Evaluation Harness Runner
===========================================
Runs the SWE-bench Lite evaluation harness against the Zyren AI Dev-Team.

This integrates with the official SWE-bench evaluation framework
to measure % Resolved on real GitHub issues.

Usage:
    python evals/swebench/run_harness.py [--tasks N] [--verbose]

Requirements:
    - SWE-bench installed: pip install swebench
    - Docker available for test execution
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.harness import EvaluationHarness, load_tasks_from_yaml


def check_swebench_installed() -> bool:
    """Check if SWE-bench is installed."""
    try:
        import swebench
        return True
    except ImportError:
        return False


def check_docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def load_swebench_tasks(
    dataset: str = "lite",
    max_tasks: int | None = None,
    split: str = "test",
) -> list[dict[str, Any]]:
    """
    Load tasks from SWE-bench dataset.
    
    Args:
        dataset: "lite" or "verified"
        max_tasks: Maximum number of tasks to load
        split: Dataset split ("test", "dev")
        
    Returns:
        List of task dicts compatible with EvaluationHarness
    """
    if not check_swebench_installed():
        raise RuntimeError("SWE-bench not installed. Run: pip install swebench")
    
    try:
        from swebench import load_dataset
    except ImportError:
        # Alternative import path
        from datasets import load_dataset as hf_load_dataset
        ds = hf_load_dataset("princeton-nlp/SWE-bench_Lite" if dataset == "lite" else "princeton-nlp/SWE-bench_Verified", split=split)
        return _convert_hf_dataset(ds, max_tasks)
    
    # Try swebench loader
    try:
        ds = load_dataset(dataset, split=split)
        return _convert_swebench_dataset(ds, max_tasks)
    except Exception:
        # Fallback to HF datasets
        from datasets import load_dataset as hf_load_dataset
        ds = hf_load_dataset("princeton-nlp/SWE-bench_Lite" if dataset == "lite" else "princeton-nlp/SWE-bench_Verified", split=split)
        return _convert_hf_dataset(ds, max_tasks)


def _convert_swebench_dataset(dataset, max_tasks: int | None) -> list[dict[str, Any]]:
    """Convert SWE-bench dataset format to our task format."""
    tasks = []
    for i, item in enumerate(dataset):
        if max_tasks and i >= max_tasks:
            break
        
        # SWE-bench item has: instance_id, repo, base_commit, problem_statement, etc.
        task_id = item.get("instance_id", f"swebench-{i}")
        problem = item.get("problem_statement", "")
        
        # Create a prompt for our system
        prompt = f"""Solve the following GitHub issue:

Repository: {item.get('repo', 'unknown')}
Base Commit: {item.get('base_commit', 'unknown')}

Issue Description:
{problem}

Please implement a fix that resolves this issue. Write the necessary code changes."""
        
        tasks.append({
            "id": task_id,
            "prompt": prompt,
            "metadata": {
                "repo": item.get("repo"),
                "base_commit": item.get("base_commit"),
                "problem_statement": problem,
                "version": item.get("version"),
                "hints": item.get("hints_text", ""),
            }
        })
    
    return tasks


def _convert_hf_dataset(dataset, max_tasks: int | None) -> list[dict[str, Any]]:
    """Convert HuggingFace dataset format to our task format."""
    tasks = []
    for i, item in enumerate(dataset):
        if max_tasks and i >= max_tasks:
            break
        
        task_id = item.get("instance_id", f"swebench-{i}")
        problem = item.get("problem_statement", "")
        
        prompt = f"""Solve the following GitHub issue:

Repository: {item.get('repo', 'unknown')}
Base Commit: {item.get('base_commit', 'unknown')}

Issue Description:
{problem}

Please implement a fix that resolves this issue. Write the necessary code changes."""
        
        tasks.append({
            "id": task_id,
            "prompt": prompt,
            "metadata": {
                "repo": item.get("repo"),
                "base_commit": item.get("base_commit"),
                "problem_statement": problem,
                "version": item.get("version"),
                "hints": item.get("hints_text", ""),
            }
        })
    
    return tasks


def run_swebench_evaluation(
    dataset: str = "lite",
    max_tasks: int | None = None,
    max_iterations: int = 5,
    timeout_seconds: int = 600,
    cost_cap_usd: float = 2.0,
    output_dir: str | Path = "reports/evaluations/swebench",
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Run SWE-bench evaluation using our harness.
    
    Args:
        dataset: "lite" (300 tasks) or "verified" (500 tasks)
        max_tasks: Limit number of tasks (for testing)
        max_iterations: Max workflow iterations per task
        timeout_seconds: Timeout per task
        cost_cap_usd: Cost cap per workflow
        output_dir: Directory for results
        verbose: Print progress
        
    Returns:
        Evaluation summary dict
    """
    print(f"\n{'='*60}")
    print(f"🔬 SWE-bench {dataset.upper()} Evaluation")
    print(f"{'='*60}")
    print(f"Dataset: {dataset}")
    print(f"Max tasks: {max_tasks or 'all'}")
    print(f"Max iterations: {max_iterations}")
    print(f"Timeout: {timeout_seconds}s")
    print(f"Cost cap: ${cost_cap_usd:.2f}")
    
    # Check prerequisites
    if not check_swebench_installed():
        print("❌ SWE-bench not installed. Run: pip install swebench")
        return {"status": "error", "message": "SWE-bench not installed"}
    
    if not check_docker_available():
        print("⚠️  Docker not available. Some tests may fail.")
    
    # Load tasks
    print(f"\n📂 Loading SWE-bench {dataset} tasks...")
    try:
        tasks = load_swebench_tasks(dataset=dataset, max_tasks=max_tasks)
        print(f"   Loaded {len(tasks)} tasks")
    except Exception as e:
        print(f"❌ Failed to load tasks: {e}")
        return {"status": "error", "message": str(e)}
    
    if not tasks:
        return {"status": "error", "message": "No tasks loaded"}
    
    # Run evaluation
    harness = EvaluationHarness(
        max_iterations=max_iterations,
        timeout_seconds=timeout_seconds,
        cost_cap_usd=cost_cap_usd,
        verbose=verbose,
    )
    
    start_time = time.time()
    summary = harness.evaluate_batch(tasks)
    total_duration = time.time() - start_time
    
    # Save results
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    run_id = f"swebench_{dataset}_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    
    # JSON results
    json_file = output_path / f"{run_id}.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump({
            "run_id": run_id,
            "dataset": dataset,
            "started_at": summary.started_at,
            "finished_at": summary.finished_at,
            "total_tasks": summary.total_tasks,
            "passed_tasks": summary.passed_tasks,
            "failed_tasks": summary.failed_tasks,
            "percent_resolved": summary.percent_resolved,
            "mean_score": summary.mean_score,
            "median_score": summary.median_score,
            "total_cost_usd": summary.total_cost_usd,
            "total_duration_seconds": total_duration,
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
    
    # Markdown report
    md_file = output_path / f"{run_id}.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(f"# SWE-bench {dataset.upper()} Evaluation: {run_id}\n\n")
        f.write(f"**Started:** {summary.started_at}\n")
        f.write(f"**Finished:** {summary.finished_at or 'In progress'}\n\n")
        f.write(f"## Summary\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Dataset | {dataset} |\n")
        f.write(f"| Total Tasks | {summary.total_tasks} |\n")
        f.write(f"| Passed | {summary.passed_tasks} ({summary.percent_resolved:.1f}%) |\n")
        f.write(f"| Failed | {summary.failed_tasks} |\n")
        f.write(f"| Mean Score | {summary.mean_score:.4f} |\n")
        f.write(f"| Median Score | {summary.median_score:.4f} |\n")
        f.write(f"| Total Cost | ${summary.total_cost_usd:.6f} |\n")
        f.write(f"| Total Duration | {total_duration:.1f}s |\n")
        f.write(f"| Avg Iterations | {summary.avg_iterations:.1f} |\n\n")
        f.write(f"## Task Results\n")
        f.write(f"| Task ID | Status | Score | Iterations | Cost | Duration |\n")
        f.write(f"|---------|--------|-------|------------|------|----------|\n")
        for r in summary.results:
            status = "✅ PASS" if r.passed else "❌ FAIL"
            f.write(f"| {r.task_id} | {status} | {r.overall_score:.3f} | {r.iterations_taken} | ${r.total_cost_usd:.4f} | {r.total_duration_seconds:.1f}s |\n")
    
    print(f"\n💾 Results saved:")
    print(f"   JSON: {json_file}")
    print(f"   Markdown: {md_file}")
    
    return {
        "status": "success",
        "run_id": run_id,
        "percent_resolved": summary.percent_resolved,
        "total_tasks": summary.total_tasks,
        "passed_tasks": summary.passed_tasks,
        "failed_tasks": summary.failed_tasks,
        "mean_score": summary.mean_score,
        "total_cost_usd": summary.total_cost_usd,
        "total_duration_seconds": total_duration,
        "json_file": str(json_file),
        "md_file": str(md_file),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run SWE-bench evaluation harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test with 5 tasks
  python evals/swebench/run_harness.py --max-tasks 5 --verbose
  
  # Full SWE-bench Lite run
  python evals/swebench/run_harness.py --dataset lite
  
  # SWE-bench Verified (500 tasks)
  python evals/swebench/run_harness.py --dataset verified --max-tasks 50
        """
    )
    parser.add_argument(
        "--dataset",
        choices=["lite", "verified"],
        default="lite",
        help="SWE-bench dataset to use (default: lite)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of tasks to evaluate",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Max workflow iterations per task (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout per task in seconds (default: 600)",
    )
    parser.add_argument(
        "--cost-cap",
        type=float,
        default=2.0,
        help="Cost cap per workflow in USD (default: 2.0)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/evaluations/swebench",
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
    
    if args.dry_run:
        print("🔍 Dry run - loading tasks only...")
        try:
            tasks = load_swebench_tasks(dataset=args.dataset, max_tasks=args.max_tasks)
            print(f"Loaded {len(tasks)} tasks:")
            for i, task in enumerate(tasks[:10], 1):
                print(f"  {i}. {task['id']}: {task['prompt'][:80]}...")
            if len(tasks) > 10:
                print(f"  ... and {len(tasks) - 10} more")
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
        return
    
    # Run evaluation
    result = run_swebench_evaluation(
        dataset=args.dataset,
        max_tasks=args.max_tasks,
        max_iterations=args.max_iterations,
        timeout_seconds=args.timeout,
        cost_cap_usd=args.cost_cap,
        output_dir=args.output_dir,
        verbose=args.verbose,
    )
    
    if result.get("status") == "error":
        print(f"\n❌ Evaluation failed: {result.get('message')}")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"🏁 SWE-bench {args.dataset.upper()} EVALUATION COMPLETE")
    print(f"{'='*60}")
    print(f"   Tasks evaluated: {result['total_tasks']}")
    print(f"   Resolved: {result['passed_tasks']} ({result['percent_resolved']:.1f}%)")
    print(f"   Failed: {result['failed_tasks']}")
    print(f"   Mean score: {result['mean_score']:.4f}")
    print(f"   Total cost: ${result['total_cost_usd']:.6f}")
    print(f"   Total time: {result['total_duration_seconds']:.1f}s")
    
    # Exit code based on resolved rate
    if result['percent_resolved'] >= 10:
        print(f"\n✅ Minimum threshold met (≥10% resolved)")
        sys.exit(0)
    else:
        print(f"\n⚠️  Below minimum threshold (<10% resolved)")
        sys.exit(1)


if __name__ == "__main__":
    main()