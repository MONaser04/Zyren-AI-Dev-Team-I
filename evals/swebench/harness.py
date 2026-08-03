"""
SWE-bench Verified Harness — Phase 7
=====================================
Runs AI Dev Team on SWE-bench Verified instances.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gateway.smart_gateway import SmartGateway
from gateway.model_registry import AutoModelRegistry
from orchestrator.runner import run_workflow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SWEBenchInstance:
    """A single SWE-bench instance."""
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    hints_text: str = ""
    created_at: str = ""
    version: str = ""
    FAIL_TO_PASS: list[str] = field(default_factory=list)
    PASS_TO_PASS: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SWEBenchResult:
    """Result of evaluating a SWE-bench instance."""
    instance_id: str
    success: bool
    duration_seconds: float
    patch_generated: str = ""
    tests_passed: int = 0
    tests_failed: int = 0
    error: str | None = None
    workflow_id: str = ""


class SWEBenchHarness:
    """Evaluates SWE-bench Verified instances through the AI Dev Team."""

    def __init__(
        self,
        max_iterations: int = 10,
        timeout_seconds: int = 600,
        cost_cap_usd: float = 5.0,
        dataset_path: str = "evals/swebench/verified.jsonl",
    ):
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        self.cost_cap_usd = cost_cap_usd
        self.dataset_path = dataset_path

        # Initialize core components
        self.registry = AutoModelRegistry()
        self.gateway = SmartGateway(self.registry)

    async def initialize(self) -> None:
        """Initialize registry and gateway."""
        await self.registry.initialize(discover=True)

    async def load_dataset(self, max_instances: int | None = None) -> list[SWEBenchInstance]:
        """Load SWE-bench Verified dataset."""
        instances = []
        with open(self.dataset_path) as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                instances.append(SWEBenchInstance(**data))
                if max_instances and len(instances) >= max_instances:
                    break
        return instances

    async def setup_repo(self, instance: SWEBenchInstance, workdir: Path) -> None:
        """Clone and checkout repository at base commit."""
        repo_name = instance.repo.split("/")[-1].replace(".git", "")
        repo_path = workdir / repo_name

        # Clone if needed
        if not repo_path.exists():
            logger.info("Cloning %s...", instance.repo)
            subprocess.run(
                ["git", "clone", f"https://github.com/{instance.repo}.git", str(repo_path)],
                check=True,
                capture_output=True,
            )

        # Checkout base commit
        subprocess.run(
            ["git", "checkout", instance.base_commit],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Install dependencies
        if (repo_path / "requirements.txt").exists():
            subprocess.run(
                ["pip", "install", "-q", "-r", "requirements.txt"],
                cwd=repo_path,
                check=False,
                capture_output=True,
            )
        if (repo_path / "setup.py").exists():
            subprocess.run(
                ["pip", "install", "-q", "-e", "."],
                cwd=repo_path,
                check=False,
                capture_output=True,
            )
        if (repo_path / "pyproject.toml").exists():
            subprocess.run(
                ["pip", "install", "-q", "-e", "."],
                cwd=repo_path,
                check=False,
                capture_output=True,
            )

    async def run_instance(self, instance: SWEBenchInstance) -> SWEBenchResult:
        """Run a single SWE-bench instance through the pipeline."""
        instance_id = instance.instance_id
        start_time = time.monotonic()

        with tempfile.TemporaryDirectory(prefix=f"swebench_{instance_id}_") as tmpdir:
            workdir = Path(tmpdir)

            try:
                # Setup repository
                await self.setup_repo(instance, workdir)

                # Create workflow
                workflow_id = f"swebench-{instance_id}-{int(time.time())}"

                # Build task description
                task_description = self._build_task_description(instance)

                # Run workflow
                result = await run_workflow(
                    workflow_id=workflow_id,
                    task_description=task_description,
                    max_iterations=self.max_iterations,
                    cost_cap_usd=self.cost_cap_usd,
                )

                # Extract generated patch
                patch = self._extract_patch(result, workdir)

                # Apply patch and run tests
                test_results = await self._run_tests(instance, workdir, patch)

                duration = time.monotonic() - start_time

                success = test_results.get("passed", False)

                return SWEBenchResult(
                    instance_id=instance_id,
                    success=success,
                    duration_seconds=duration,
                    patch_generated=patch,
                    tests_passed=test_results.get("passed_count", 0),
                    tests_failed=test_results.get("failed_count", 0),
                    workflow_id=workflow_id,
                )

            except Exception as e:
                logger.exception("Instance %s failed", instance_id)
                duration = time.monotonic() - start_time
                return SWEBenchResult(
                    instance_id=instance_id,
                    success=False,
                    duration_seconds=duration,
                    error=str(e),
                )

    def _build_task_description(self, instance: SWEBenchInstance) -> str:
        """Build task description for the AI Dev Team."""
        parts = [
            f"Repository: {instance.repo}",
            f"Base Commit: {instance.base_commit}",
            f"Problem: {instance.problem_statement}",
        ]

        if instance.hints_text:
            parts.append(f"Hints: {instance.hints_text}")

        if instance.FAIL_TO_PASS:
            parts.append("Tests that should pass after fix:")
            for test in instance.FAIL_TO_PASS:
                parts.append(f"  - {test}")

        if instance.PASS_TO_PASS:
            parts.append("Tests that must continue to pass:")
            for test in instance.PASS_TO_PASS:
                parts.append(f"  - {test}")

        parts.append("""
Generate a patch file that fixes the issue. The patch should:
1. Make minimal changes to fix the problem
2. Pass all FAIL_TO_PASS tests
3. Not break any PASS_TO_PASS tests
4. Follow the repository's coding style

Output the patch as a unified diff.
""")

        return "\n".join(parts)

    def _extract_patch(self, result: Any, workdir: Path) -> str:
        """Extract generated patch from workflow result."""
        # Check result artifacts
        if hasattr(result, "artifacts"):
            for artifact in result.artifacts:
                if hasattr(artifact, "path") and artifact.path.endswith(".patch"):
                    return Path(artifact.path).read_text()

        # Check for patch in workdir
        for patch_file in workdir.rglob("*.patch"):
            return patch_file.read_text()

        # Check for git diff
        for repo_dir in workdir.iterdir():
            if repo_dir.is_dir() and (repo_dir / ".git").exists():
                try:
                    diff = subprocess.run(
                        ["git", "diff", "HEAD"],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if diff.stdout.strip():
                        return diff.stdout
                except Exception:
                    pass

        return ""

    async def _run_tests(
        self,
        instance: SWEBenchInstance,
        workdir: Path,
        patch: str,
    ) -> dict[str, Any]:
        """Apply patch and run tests."""
        # Find repo directory
        repo_dirs = [d for d in workdir.iterdir() if d.is_dir() and (d / ".git").exists()]
        if not repo_dirs:
            return {"passed": False, "error": "No repo found"}

        repo_dir = repo_dirs[0]

        # Apply patch
        if patch:
            patch_file = workdir / "fix.patch"
            patch_file.write_text(patch)

            try:
                subprocess.run(
                    ["git", "apply", "--check", str(patch_file)],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "apply", str(patch_file)],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                return {"passed": False, "error": f"Patch apply failed: {e.stderr}"}

        # Run FAIL_TO_PASS tests
        passed = 0
        failed = 0

        for test in instance.FAIL_TO_PASS:
            try:
                result = subprocess.run(
                    ["python", "-m", "pytest", test, "-v", "--tb=short"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    passed += 1
                else:
                    failed += 1
            except subprocess.TimeoutExpired:
                failed += 1

        # Run PASS_TO_PASS tests
        for test in instance.PASS_TO_PASS:
            try:
                result = subprocess.run(
                    ["python", "-m", "pytest", test, "-v", "--tb=short"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    passed += 1
                else:
                    failed += 1
            except subprocess.TimeoutExpired:
                failed += 1

        return {
            "passed": failed == 0 and passed > 0,
            "passed_count": passed,
            "failed_count": failed,
        }

    async def evaluate_batch(
        self,
        instances: list[SWEBenchInstance],
        max_concurrent: int = 2,
    ) -> list[SWEBenchResult]:
        """Evaluate multiple instances with concurrency control."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def eval_with_semaphore(instance):
            async with semaphore:
                return await self.run_instance(instance)

        results = await asyncio.gather(*[eval_with_semaphore(i) for i in instances])
        return list(results)

    async def generate_report(self, results: list[SWEBenchResult]) -> dict[str, Any]:
        """Generate evaluation report."""
        total = len(results)
        resolved = sum(1 for r in results if r.success)
        total_duration = sum(r.duration_seconds for r in results)

        # Group by repo
        by_repo: dict[str, dict[str, int]] = {}
        for r in results:
            # Instance ID format: repo__issue_number
            repo = r.instance_id.split("__")[0] if "__" in r.instance_id else "unknown"
            if repo not in by_repo:
                by_repo[repo] = {"resolved": 0, "total": 0}
            by_repo[repo]["total"] += 1
            if r.success:
                by_repo[repo]["resolved"] += 1

        return {
            "summary": {
                "total_instances": total,
                "resolved": resolved,
                "resolve_rate": resolved / total if total > 0 else 0.0,
                "total_duration_seconds": total_duration,
                "avg_duration_seconds": total_duration / total if total > 0 else 0,
            },
            "by_repository": by_repo,
            "results": [
                {
                    "instance_id": r.instance_id,
                    "success": r.success,
                    "duration": r.duration_seconds,
                    "tests_passed": r.tests_passed,
                    "tests_failed": r.tests_failed,
                    "error": r.error,
                }
                for r in results
            ],
        }


async def main():
    """Main entry point."""
    harness = SWEBenchHarness(max_iterations=10, timeout_seconds=600, cost_cap_usd=5.0)
    await harness.initialize()

    # Load dataset
    instances = await harness.load_dataset(max_instances=50)  # Start with 50
    print(f"Loaded {len(instances)} SWE-bench Verified instances")

    # Run evaluation
    results = await harness.evaluate_batch(instances, max_concurrent=2)

    # Generate report
    report = await harness.generate_report(results)

    # Save report
    report_path = Path("reports/swebench_evaluation.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n=== SWE-bench Verified Evaluation ===")
    print(f"Total: {report['summary']['total_instances']}")
    print(f"Resolved: {report['summary']['resolved']}")
    print(f"Resolve Rate: {report['summary']['resolve_rate']:.1%}")
    print(f"Total Duration: {report['summary']['total_duration_seconds']:.1f}s")
    print(f"Report saved to: {report_path}")

    return report


if __name__ == "__main__":
    import json
    asyncio.run(main())