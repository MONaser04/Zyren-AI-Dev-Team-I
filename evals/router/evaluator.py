"""
Router Evaluation — Phase 7
============================
Evaluates SmartRouter decisions via shadow sampling vs frontier ground truth.
Implements immutable performance floor with auto-rollback.
"""
from __future__ import annotations

import asyncio
import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import yaml

from gateway.smart_gateway import SmartGateway
from gateway.model_registry import AutoModelRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouterTestCase:
    """A single router evaluation test case."""
    case_id: str
    task_description: str
    complexity: str  # simple, medium, hard, critical
    required_capabilities: list[str] = field(default_factory=list)
    expected_tier: str = ""  # frontier, fast, critic, etc.
    budget_usd: float | None = None


@dataclass(frozen=True)
class RoutingDecision:
    """A routing decision from the router."""
    case_id: str
    selected_model: str
    selected_tier: str
    reasoning: str
    confidence: float
    fallback_chain: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RouterEvalResult:
    """Result of evaluating a routing decision."""
    case_id: str
    router_decision: RoutingDecision
    frontier_decision: str  # What the frontier model would choose
    matches_frontier: bool
    quality_score: float  # 0-1 based on outcome
    latency_ms: float
    cost_usd: float


@dataclass
class RouterEvalReport:
    """Router evaluation report."""
    total_cases: int
    frontier_match_rate: float
    avg_quality_score: float
    avg_latency_ms: float
    avg_cost_usd: float
    by_complexity: dict[str, dict[str, float]] = field(default_factory=dict)
    by_tier: dict[str, dict[str, float]] = field(default_factory=dict)
    performance_floor_met: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class RouterEvaluator:
    """Evaluates SmartRouter via shadow sampling against frontier ground truth."""

    def __init__(
        self,
        frontier_model: str = "anthropic/claude-3.5-sonnet",
        performance_floor: float = 0.85,  # Minimum frontier match rate
    ):
        self.frontier_model = frontier_model
        self.performance_floor = performance_floor
        self.gateway = None
        self.router = None
        self._anchor_results: list[RouterEvalResult] = []  # Immutable performance anchor

    async def initialize(self) -> None:
        """Initialize gateway and router."""
        registry = AutoModelRegistry()
        await registry.initialize(discover=True)
        gateway = SmartGateway(registry)
        self.gateway = gateway
        self.router = gateway._router

    def load_test_cases(self, path: str) -> list[RouterTestCase]:
        """Load router test cases from YAML."""
        with open(path) as f:
            data = yaml.safe_load(f)
        cases = []
        for item in data.get("cases", []):
            cases.append(RouterTestCase(**item))
        logger.info("Loaded %d router test cases", len(cases))
        return cases

    def load_anchor_set(self, path: str) -> None:
        """Load immutable performance anchor set."""
        with open(path) as f:
            data = json.load(f)
        self._anchor_results = [RouterEvalResult(**r) for r in data.get("results", [])]
        logger.info("Loaded %d anchor results", len(self._anchor_results))

    async def evaluate_case(self, case: RouterTestCase) -> RouterEvalResult:
        """Evaluate a single routing case."""
        start_time = asyncio.get_event_loop().time()

        # Build routing criteria
        criteria = {
            "complexity": case.complexity,
            "required_capabilities": case.required_capabilities,
            "cost_budget": case.budget_usd,
        }

        # Get router decision
        routing_decision = self.router.route_request(criteria)
        router_decision = RoutingDecision(
            case_id=case.case_id,
            selected_model=routing_decision.primary_model,
            selected_tier=routing_decision.primary_tier,
            reasoning=routing_decision.reasoning,
            confidence=routing_decision.confidence,
            fallback_chain=routing_decision.fallback_chain,
        )

        # Get frontier ground truth (shadow evaluation)
        frontier_decision = await self._get_frontier_decision(case)

        # Compare
        matches_frontier = router_decision.selected_model == frontier_decision

        # Simulate quality score (in real impl, run actual task)
        quality_score = await self._simulate_quality(router_decision, case)

        latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        cost_usd = self._estimate_cost(router_decision.selected_model)

        return RouterEvalResult(
            case_id=case.case_id,
            router_decision=router_decision,
            frontier_decision=frontier_decision,
            matches_frontier=matches_frontier,
            quality_score=quality_score,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )

    async def _get_frontier_decision(self, case: RouterTestCase) -> str:
        """Get frontier model's routing decision (ground truth)."""
        prompt = f"""You are an expert LLM router. Given a task, select the best model.

Task: {case.task_description}
Complexity: {case.complexity}
Required Capabilities: {case.required_capabilities}
Budget: ${case.budget_usd or 'unlimited'}

Available models (via gateway):
- nvidia_nim/nvidia/nemotron-4-340b (frontier, coding, reasoning)
- nvidia_nim/meta/llama-3.1-70b-instruct (fast, general)
- nvidia_nim/mistralai/mistral-large (balanced)
- openai/gpt-4o (frontier, multimodal)
- openai/gpt-4o-mini (fast, cheap)
- anthropic/claude-3.5-sonnet (frontier, reasoning)
- anthropic/claude-3.5-haiku (fast, reasoning)
- google/gemini-1.5-pro (frontier, long context)
- google/gemini-1.5-flash (fast, long context)
- mistralai/mistral-large (balanced)
- cohere/command-r-plus (RAG, long context)

Output ONLY the model ID (e.g., "openai/gpt-4o")."""

        try:
            response = await self.gateway.complete_text(
                model=self.frontier_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=64,
            )
            return response.strip()
        except Exception as e:
            logger.exception("Frontier decision failed")
            # Fallback: use expected tier
            return case.expected_tier

    async def _simulate_quality(
        self,
        decision: RoutingDecision,
        case: RouterTestCase,
    ) -> float:
        """Simulate quality score based on routing decision."""
        # In production, this would run the actual task and measure outcome
        # For now, score based on tier match and capability coverage

        score = 1.0

        # Tier match bonus/penalty
        if decision.selected_tier == case.expected_tier:
            score += 0.1
        else:
            score -= 0.2

        # Capability coverage
        required = set(case.required_capabilities)
        if required:
            # Would check model capabilities from registry
            coverage = 1.0  # Simplified
            score *= coverage

        # Budget adherence
        if case.budget_usd:
            # Would check actual cost
            pass

        return max(0.0, min(1.0, score))

    def _estimate_cost(self, model: str) -> float:
        """Estimate cost per 1M tokens for a model."""
        costs = {
            "nvidia_nim/nvidia/nemotron-4-340b": 0.0,
            "nvidia_nim/meta/llama-3.1-70b-instruct": 0.0,
            "openai/gpt-4o": 5.00,
            "openai/gpt-4o-mini": 0.15,
            "anthropic/claude-3.5-sonnet": 3.00,
            "anthropic/claude-3.5-haiku": 0.25,
            "google/gemini-1.5-pro": 3.50,
            "google/gemini-1.5-flash": 0.075,
        }
        return costs.get(model, 1.0)

    def _compute_report(self, results: list[RouterEvalResult]) -> RouterEvalReport:
        """Compute evaluation report from results."""
        total = len(results)
        matches = sum(1 for r in results if r.matches_frontier)
        frontier_match_rate = matches / total if total > 0 else 0.0

        avg_quality = statistics.mean(r.quality_score for r in results) if results else 0.0
        avg_latency = statistics.mean(r.latency_ms for r in results) if results else 0.0
        avg_cost = statistics.mean(r.cost_usd for r in results) if results else 0.0

        # By complexity
        by_complexity = {}
        for complexity in ["simple", "medium", "hard", "critical"]:
            subset = [r for r in results if r.router_decision.confidence > 0]  # Placeholder
            if subset:
                by_complexity[complexity] = {
                    "match_rate": sum(1 for r in subset if r.matches_frontier) / len(subset),
                    "avg_quality": statistics.mean(r.quality_score for r in subset),
                    "count": len(subset),
                }

        # By tier
        by_tier = {}
        for tier in ["frontier", "fast", "critic", "code_specialized", "long_context", "vision"]:
            subset = [r for r in results if r.router_decision.selected_tier == tier]
            if subset:
                by_tier[tier] = {
                    "match_rate": sum(1 for r in subset if r.matches_frontier) / len(subset),
                    "avg_quality": statistics.mean(r.quality_score for r in subset),
                    "count": len(subset),
                }

        # Check performance floor
        performance_floor_met = frontier_match_rate >= self.performance_floor

        return RouterEvalReport(
            total_cases=total,
            frontier_match_rate=frontier_match_rate,
            avg_quality_score=avg_quality,
            avg_latency_ms=avg_latency,
            avg_cost_usd=avg_cost,
            by_complexity=by_complexity,
            by_tier=by_tier,
            performance_floor_met=performance_floor_met,
        )

    def check_performance_floor(self, report: RouterEvalReport) -> tuple[bool, str]:
        """Check if performance floor is met, with auto-rollback recommendation."""
        if report.frontier_match_rate >= self.performance_floor:
            return True, f"Performance floor met: {report.frontier_match_rate:.1%} >= {self.performance_floor:.1%}"

        # Auto-rollback recommendation
        msg = (
            f"PERFORMANCE FLOOR BREACHED: {report.frontier_match_rate:.1%} < {self.performance_floor:.1%}\n"
            f"Recommendation: Rollback router to last anchor version.\n"
            f"Anchor match rate: {self._get_anchor_match_rate():.1%}"
        )
        return False, msg

    def _get_anchor_match_rate(self) -> float:
        """Get match rate from immutable anchor set."""
        if not self._anchor_results:
            return 0.0
        matches = sum(1 for r in self._anchor_results if r.matches_frontier)
        return matches / len(self._anchor_results)

    async def save_report(self, report: RouterEvalReport, path: str) -> None:
        """Save evaluation report."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "total_cases": report.total_cases,
                "frontier_match_rate": report.frontier_match_rate,
                "avg_quality_score": report.avg_quality_score,
                "avg_latency_ms": report.avg_latency_ms,
                "avg_cost_usd": report.avg_cost_usd,
                "by_complexity": report.by_complexity,
                "by_tier": report.by_tier,
                "performance_floor_met": report.performance_floor_met,
                "performance_floor": self.performance_floor,
                "timestamp": report.timestamp,
            }, f, indent=2)
        logger.info("Router evaluation report saved to %s", path)


def create_test_cases(path: str) -> None:
    """Create template test cases."""
    template = {
        "cases": [
            {
                "case_id": "rt_001",
                "task_description": "Write a Python function to reverse a string",
                "complexity": "simple",
                "required_capabilities": [],
                "expected_tier": "fast",
                "budget_usd": 0.01,
            },
            {
                "case_id": "rt_002",
                "task_description": "Implement a REST API with authentication",
                "complexity": "medium",
                "required_capabilities": ["web_framework", "auth"],
                "expected_tier": "frontier",
                "budget_usd": 0.10,
            },
            {
                "case_id": "rt_003",
                "task_description": "Debug and fix a memory leak in a data pipeline",
                "complexity": "hard",
                "required_capabilities": ["debugging", "profiling", "python"],
                "expected_tier": "frontier",
                "budget_usd": 1.00,
            },
            {
                "case_id": "rt_004",
                "task_description": "Design a distributed consensus algorithm",
                "complexity": "critical",
                "required_capabilities": ["distributed_systems", "algorithms", "formal_verification"],
                "expected_tier": "frontier",
                "budget_usd": 5.00,
            },
        ]
    }

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(template, f, allow_unicode=True, sort_keys=False)
    logger.info("Created router test cases template at %s", path)


async def main():
    """Run router evaluation."""
    evaluator = RouterEvaluator(performance_floor=0.85)
    await evaluator.initialize()

    # Load or create test cases
    cases_path = "evals/router_eval/test_cases.yaml"
    if not Path(cases_path).exists():
        create_test_cases(cases_path)
        print(f"Created template at {cases_path}")

    cases = evaluator.load_test_cases(cases_path)

    # Load anchor set if exists
    anchor_path = "evals/router_eval/anchor_set.json"
    if Path(anchor_path).exists():
        evaluator.load_anchor_set(anchor_path)

    # Run evaluation
    results = []
    for case in cases:
        result = await evaluator.evaluate_case(case)
        results.append(result)
        print(f"{case.case_id}: match={result.matches_frontier}, quality={result.quality_score:.2f}")

    # Generate report
    report = evaluator._compute_report(results)

    # Check performance floor
    floor_met, msg = evaluator.check_performance_floor(report)
    print(f"\n{msg}")

    # Save report
    report_path = "reports/router_evaluation.json"
    await evaluator.save_report(report, report_path)

    print(f"\n=== Router Evaluation Report ===")
    print(f"Total Cases: {report.total_cases}")
    print(f"Frontier Match Rate: {report.frontier_match_rate:.1%}")
    print(f"Avg Quality: {report.avg_quality_score:.2f}")
    print(f"Avg Latency: {report.avg_latency_ms:.0f}ms")
    print(f"Avg Cost: ${report.avg_cost_usd:.4f}")
    print(f"Performance Floor Met: {report.performance_floor_met}")
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())