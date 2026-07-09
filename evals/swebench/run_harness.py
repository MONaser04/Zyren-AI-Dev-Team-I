#!/usr/bin/env python3
"""
SWE-bench Lite — Evaluation Harness Runner
===========================================

Placeholder script for running the SWE-bench Lite evaluation harness.
This will be fully wired once the minimal viable loop is built in Phase 1.

Usage:
    uv run python evals/swebench/run_harness.py [--tasks N] [--verbose]

North-Star Metric:
    % Resolved = (tasks_passed / total_tasks) × 100
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the SWE-bench Lite evaluation harness",
    )
    parser.add_argument(
        "--tasks",
        type=int,
        default=0,
        help="Number of tasks to evaluate (0 = all)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--golden-only",
        action="store_true",
        help="Run only the golden task set (evals/golden/tasks.yaml)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to save results JSON",
    )
    return parser.parse_args()


def run_golden_tasks(verbose: bool = False) -> dict:
    """Run the golden task set and return results."""
    golden_path = Path(__file__).parent.parent / "golden" / "tasks.yaml"

    if not golden_path.exists():
        print(f"⚠ Golden tasks file not found: {golden_path}")
        return {"status": "error", "message": "tasks.yaml not found"}

    print(f"📂 Loading golden tasks from: {golden_path}")
    print("⚠ Eval harness not yet wired — this is a Phase 0 placeholder")
    print("   The minimal viable loop (Phase 1) must be built first.")

    return {
        "status": "placeholder",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "golden_tasks_path": str(golden_path),
        "message": "Harness scaffolding complete. Wire up in Phase 1.",
        "metrics": {
            "total_tasks": 0,
            "passed": 0,
            "failed": 0,
            "timeout": 0,
            "percent_resolved": 0.0,
        },
    }


def run_swebench_lite(num_tasks: int = 0, verbose: bool = False) -> dict:
    """Run SWE-bench Lite evaluation and return results."""
    print("📊 SWE-bench Lite Evaluation Harness")
    print("=" * 50)
    print("⚠ SWE-bench integration not yet wired — Phase 0 placeholder")
    print("   Install SWE-bench and configure before running.")
    print()
    print("   Setup steps:")
    print("   1. git clone https://github.com/princeton-nlp/SWE-bench.git")
    print("   2. cd SWE-bench && pip install -e .")
    print("   3. Re-run this harness")

    return {
        "status": "placeholder",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "benchmark": "swe-bench-lite",
        "message": "SWE-bench not yet installed. See evals/swebench/README.md.",
        "metrics": {
            "total_tasks": 300,
            "passed": 0,
            "failed": 0,
            "timeout": 0,
            "percent_resolved": 0.0,
        },
    }


def main() -> None:
    """Main entry point."""
    args = parse_args()

    if args.golden_only:
        results = run_golden_tasks(verbose=args.verbose)
    else:
        results = run_swebench_lite(
            num_tasks=args.tasks,
            verbose=args.verbose,
        )

    # Print results
    print()
    print("📋 Results:")
    print(json.dumps(results, indent=2))

    # Save results if output path specified
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2))
        print(f"\n💾 Results saved to: {output_path}")

    # Exit with appropriate code
    if results.get("status") == "placeholder":
        print("\n✅ Phase 0 scaffolding verified — harness is ready for Phase 1 wiring.")
        sys.exit(0)
    elif results["metrics"]["percent_resolved"] > 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
