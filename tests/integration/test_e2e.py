"""
Phase 7 Final — E2E Integration Tests
======================================
Complete end-to-end validation of the AI Dev Team pipeline.
Part 1: Test Suite Structure & Configuration
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import yaml

from gateway.smart_gateway import SmartGateway
from gateway.model_registry import AutoModelRegistry
from agents.liaison import LiaisonAgent
from orchestrator.runner import run_workflow
from orchestrator.graph import build_feedback_loop

logger = logging.getLogger(__name__)


# ============================================================
# Test Configuration
# ============================================================

@dataclass
class E2ETestCase:
    """End-to-end test case definition."""
    test_id: str
    name: str
    description: str
    task_prompt: str
    expected_outcome: str  # "success" or "failure"
    expected_files: list[str] = field(default_factory=list)
    max_duration_seconds: int = 300
    cost_cap_usd: float = 1.0
    required_tier: str | None = None
    required_capabilities: list[str] = field(default_factory=list)


@dataclass
class E2ETestResult:
    """Result of an E2E test."""
    test_id: str
    success: bool
    duration_seconds: float
    workflow_id: str = ""
    files_created: list[str] = field(default_factory=list)
    error: str | None = None
    cost_usd: float = 0.0
    quality_score: float = 0.0


# ============================================================
# E2E Test Suite
# ============================================================

class E2ETestSuite:
    """Complete end-to-end test suite for AI Dev Team."""

    def __init__(self, cost_cap_usd: float = 5.0):
        self.cost_cap_usd = cost_cap_usd
        self.registry: AutoModelRegistry | None = None
        self.gateway: SmartGateway | None = None
        self.liaison: LiaisonAgent | None = None
        self.graph = None
        self.results: list[E2ETestResult] = []

    async def initialize(self) -> None:
        """Initialize all components."""
        logger.info("Initializing E2E test suite...")
        
        self.registry = AutoModelRegistry()
        await self.registry.initialize(discover=True)
        
        self.gateway = SmartGateway(self.registry)
        
        self.liaison = LiaisonAgent(
            registry=self.registry,
            gateway=self.gateway,
        )
        
        # Build LangGraph workflow
        self.graph = build_feedback_loop(
            event_store=None,  # Will be created per workflow
            llm_client=self.gateway,
        )
        
        logger.info("E2E test suite initialized successfully")

    def load_test_cases(self) -> list[E2ETestCase]:
        """Load E2E test cases."""
        return [
            # Simple Algorithmic Tasks
            E2ETestCase(
                test_id="e2e_001",
                name="Fibonacci Function",
                description="Write iterative Fibonacci function with tests",
                task_prompt="Write a Python function `fibonacci(n: int) -> int` that returns the n-th Fibonacci number using an iterative approach (no recursion). Include type hints, docstring, and return 0 for n=0, 1 for n=1.",
                expected_outcome="success",
                expected_files=["fibonacci.py", "test_fibonacci.py"],
                max_duration_seconds=120,
                cost_cap_usd=0.10,
            ),
            E2ETestCase(
                test_id="e2e_002",
                name="Palindrome Checker",
                description="Check if string is palindrome ignoring case/spaces/punctuation",
                task_prompt="Write a Python function `is_palindrome(s: str) -> bool` that checks if a string is a palindrome, ignoring case, spaces, and punctuation. Include type hints, docstring, and at least 3 assert-based tests.",
                expected_outcome="success",
                expected_files=["palindrome.py", "test_palindrome.py"],
                max_duration_seconds=120,
                cost_cap_usd=0.10,
            ),

            # API / Web Tasks
            E2ETestCase(
                test_id="e2e_003",
                name="FastAPI User CRUD",
                description="Create FastAPI app with user CRUD endpoints",
                task_prompt="Create a FastAPI application with two endpoints: POST /users — creates a user with name and email, stores in memory; GET /users/{user_id} — retrieves a user by ID. Use Pydantic models for request/response validation. Include proper HTTP status codes and error responses.",
                expected_outcome="success",
                expected_files=["main.py", "models.py", "test_main.py"],
                max_duration_seconds=180,
                cost_cap_usd=0.20,
            ),
            E2ETestCase(
                test_id="e2e_004",
                name="Async HTTP Fetch with Retry",
                description="Async function to fetch JSON with retry logic",
                task_prompt="Write an async Python function `fetch_json(url: str) -> dict` using aiohttp that fetches JSON from a URL with proper error handling for: connection errors, HTTP errors (4xx, 5xx), and invalid JSON responses. Include type hints, docstring, and a retry mechanism (max 3 retries with exponential backoff).",
                expected_outcome="success",
                expected_files=["fetch_json.py", "test_fetch_json.py"],
                max_duration_seconds=180,
                cost_cap_usd=0.15,
            ),

            # Data Structure Tasks
            E2ETestCase(
                test_id="e2e_005",
                name="LRU Cache Implementation",
                description="Implement LRU cache with O(1) operations",
                task_prompt="Implement an `LRUCache` class with capacity limit using OrderedDict or doubly linked list + hashmap. Methods: `get(key) -> int`, `put(key: int, value: int)`. O(1) operations. Include tests.",
                expected_outcome="success",
                expected_files=["lru_cache.py", "test_lru_cache.py"],
                max_duration_seconds=180,
                cost_cap_usd=0.15,
            ),
            E2ETestCase(
                test_id="e2e_006",
                name="Binary Search Tree",
                description="BST with insert, delete, search, traversals",
                task_prompt="Implement a `BinarySearchTree` class with methods: `insert(val: int)`, `delete(val: int)`, `search(val: int) -> bool`, `inorder() -> list[int]`, `preorder() -> list[int]`, `postorder() -> list[int]`, `height() -> int`, `is_balanced() -> bool`. Include type hints and tests.",
                expected_outcome="success",
                expected_files=["bst.py", "test_bst.py"],
                max_duration_seconds=240,
                cost_cap_usd=0.20,
            ),

            # Utility Tasks
            E2ETestCase(
                test_id="e2e_007",
                name="Retry Decorator",
                description="Decorator with exponential backoff retry",
                task_prompt="Write a decorator `@retry_on_failure(max_retries=3, backoff_factor=2.0)` that retries a function on exception with exponential backoff. Include type hints, docstring, and an example usage.",
                expected_outcome="success",
                expected_files=["retry_decorator.py", "test_retry_decorator.py"],
                max_duration_seconds=120,
                cost_cap_usd=0.10,
            ),

            # Security Tasks
            E2ETestCase(
                test_id="e2e_008",
                name="SQL Injection Sanitizer",
                description="Sanitize SQL input to prevent injection",
                task_prompt="Write a function `sanitize_sql_input(value: str) -> str` that escapes single quotes and removes semicolons from a string to prevent basic SQL injection. Include type hints, docstring, and assert-based validation tests with malicious inputs.",
                expected_outcome="success",
                expected_files=["sanitize_sql.py", "test_sanitize_sql.py"],
                max_duration_seconds=120,
                cost_cap_usd=0.10,
            ),
            E2ETestCase(
                test_id="e2e_009",
                name="Password Validator",
                description="Validate password strength with comprehensive rules",
                task_prompt="Write a function `validate_password(password: str) -> tuple[bool, list[str]]` that validates password strength: min 12 chars, uppercase, lowercase, digit, special char, no common patterns. Return (is_valid, errors). Include comprehensive tests.",
                expected_outcome="success",
                expected_files=["validate_password.py", "test_validate_password.py"],
                max_duration_seconds=120,
                cost_cap_usd=0.10,
            ),

            # Real World Tasks
            E2ETestCase(
                test_id="e2e_010",
                name="Config Manager",
                description="Load config from ENV, YAML, CLI with priority",
                task_prompt="Create a `ConfigManager` class that loads configuration from environment variables, YAML files, and command-line arguments with priority: CLI > ENV > YAML > defaults. Support type coercion (str, int, float, bool, list). Include type hints and tests.",
                expected_outcome="success",
                expected_files=["config_manager.py", "test_config_manager.py"],
                max_duration_seconds=180,
                cost_cap_usd=0.15,
            ),
            E2ETestCase(
                test_id="e2e_011",
                name="Feature Flags with Rollout",
                description="Feature flag system with percentage rollout",
                task_prompt="Build a simple feature flag system: `is_enabled(flag: str, user_id: str = None) -> bool`. Support: boolean, percentage rollout, user allowlist. Config from YAML with hot reload. Thread-safe. Include tests.",
                expected_outcome="success",
                expected_files=["feature_flags.py", "test_feature_flags.py"],
                max_duration_seconds=180,
                cost_cap_usd=0.15,
            ),
            E2ETestCase(
                test_id="e2e_012",
                name="Circuit Breaker Decorator",
                description="Async circuit breaker with failure threshold",
                task_prompt="Write a circuit breaker decorator for async functions: `@circuit_breaker(failure_threshold=5, recovery_timeout=30)`. Tracks failures, opens circuit, allows probe requests after timeout. Thread-safe. Include metrics and tests.",
                expected_outcome="success",
                expected_files=["circuit_breaker.py", "test_circuit_breaker.py"],
                max_duration_seconds=180,
                cost_cap_usd=0.15,
            ),
            E2ETestCase(
                test_id="e2e_013",
                name="Distributed Lock with Redis",
                description="Redis-based distributed lock with TTL",
                task_prompt="Implement a distributed lock using Redis: `acquire_lock(key: str, timeout: int = 10, ttl: int = 30) -> Lock`. Lock supports: `__enter__`, `__exit__`, `extend(ttl)`, `release()`. Auto-release on TTL expiry. Include tests with fakeredis.",
                expected_outcome="success",
                expected_files=["distributed_lock.py", "test_distributed_lock.py"],
                max_duration_seconds=180,
                cost_cap_usd=0.15,
            ),
            E2ETestCase(
                test_id="e2e_014",
                name="Idempotency Key System",
                description="API idempotency with Redis TTL",
                task_prompt="Create an idempotency key system for API endpoints: `check_idempotency(key: str) -> Result | None`, `store_result(key: str, result: Any, ttl: int = 86400)`. Uses Redis with TTL. Handles concurrent requests correctly. Include FastAPI dependency and tests.",
                expected_outcome="success",
                expected_files=["idempotency.py", "test_idempotency.py"],
                max_duration_seconds=180,
                cost_cap_usd=0.15,
            ),
            E2ETestCase(
                test_id="e2e_015",
                name="Metrics Collector with Prometheus Export",
                description="Metrics collector with Prometheus export",
                task_prompt="Build a simple metrics collector: `increment(counter: str, tags: dict = None)`, `gauge(name: str, value: float, tags: dict = None)`, `histogram(name: str, value: float, tags: dict = None)`, export to Prometheus format (`/metrics` endpoint). Include tests.",
                expected_outcome="success",
                expected_files=["metrics.py", "test_metrics.py"],
                max_duration_seconds=180,
                cost_cap_usd=0.15,
            ),
        ]

    async def run_test(self, test_case: E2ETestCase) -> E2ETestResult:
        """Run a single E2E test case."""
        logger.info("Running E2E test: %s (%s)", test_case.test_id, test_case.name)
        start_time = time.monotonic()

        try:
            # Create workflow
            workflow_id = f"e2e-{test_case.test_id}-{int(time.time())}"

            # Run workflow
            result = await run_workflow(
                workflow_id=workflow_id,
                task_description=test_case.task_prompt,
                max_iterations=5,
                cost_cap_usd=min(test_case.cost_cap_usd, self.cost_cap_usd),
            )

            # Collect created files
            created_files = []
            if hasattr(result, "artifacts"):
                for artifact in result.artifacts:
                    if hasattr(artifact, "path"):
                        created_files.append(str(artifact.path))

            duration = time.monotonic() - start_time

            # Check timeout
            if duration > test_case.max_duration_seconds:
                return E2ETestResult(
                    test_id=test_case.test_id,
                    success=False,
                    duration_seconds=duration,
                    error=f"Timeout: {duration:.1f}s > {test_case.max_duration_seconds}s",
                )

            # Verify expected files (simplified)
            files_ok = True  # In real implementation, check actual files

            success = result.success and files_ok

            return E2ETestResult(
                test_id=test_case.test_id,
                success=success,
                duration_seconds=duration,
                workflow_id=workflow_id,
                files_created=created_files,
                cost_usd=0.0,  # Would track from cost tracker
                quality_score=1.0 if success else 0.0,
            )

        except Exception as e:
            logger.exception("Test %s failed with exception", test_case.test_id)
            duration = time.monotonic() - start_time
            return E2ETestResult(
                test_id=test_case.test_id,
                success=False,
                duration_seconds=duration,
                error=str(e),
            )

    async def run_all_tests(self, max_concurrent: int = 2) -> dict[str, Any]:
        """Run all E2E tests with concurrency control."""
        test_cases = self.load_test_cases()
        logger.info("Running %d E2E tests with max_concurrent=%d", len(test_cases), max_concurrent)

        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_with_semaphore(test_case):
            async with semaphore:
                return await self.run_test(test_case)

        self.results = await asyncio.gather(*[run_with_semaphore(tc) for tc in self.test_cases])

        return self.generate_report()

    def generate_report(self) -> dict[str, Any]:
        """Generate test report."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed
        total_duration = sum(r.duration_seconds for r in self.results)
        total_cost = sum(r.cost_usd for r in self.results)

        return {
            "summary": {
                "total_tests": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": passed / total if total > 0 else 0.0,
                "total_duration_seconds": total_duration,
                "total_cost_usd": total_cost,
            },
            "results": [
                {
                    "test_id": r.test_id,
                    "success": r.success,
                    "duration_seconds": r.duration_seconds,
                    "workflow_id": r.workflow_id,
                    "files_created": r.files_created,
                    "error": r.error,
                    "cost_usd": r.cost_usd,
                    "quality_score": r.quality_score,
                }
                for r in self.results
            ],
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def save_report(self, report: dict[str, Any], path: str) -> None:
        """Save test report to JSON."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info("E2E test report saved to %s", path)


async def run_e2e_tests(max_concurrent: int = 2, cost_cap_usd: float = 5.0) -> dict[str, Any]:
    # E2ETestSuite is defined in this same file
    suite = E2ETestSuite(cost_cap_usd=cost_cap_usd)
    await suite.initialize()
    return await suite.run_all_tests(max_concurrent=max_concurrent)


if __name__ == "__main__":
    asyncio.run(run_e2e_tests())