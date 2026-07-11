"""
Metrics Module — Phase 6
=========================
Standardized metrics for trajectory-first evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TrajectoryMetrics:
    """Metrics collected during a workflow trajectory."""
    
    # Task-level metrics
    task_id: str
    workflow_id: str
    resolved: bool  # Primary metric: did the task pass?
    
    # Quality metrics
    test_pass_rate: float = 1.0
    lint_score: float = 1.0
    type_check_passed: bool = True
    security_issues_count: int = 0
    coverage_percent: float | None = None
    
    # Efficiency metrics
    iterations_taken: int = 1
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    total_tokens: int = 0
    
    # Agent interaction metrics
    agent_invocations: dict[str, int] = None  # role -> count
    tool_calls: dict[str, int] = None  # tool -> count
    human_interventions: int = 0
    retries: int = 0
    
    # Error tracking
    errors: list[str] = None
    warnings: list[str] = None
    
    def __post_init__(self):
        if self.agent_invocations is None:
            self.agent_invocations = {}
        if self.tool_calls is None:
            self.tool_calls = {}
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


@dataclass
class EvaluationAggregate:
    """Aggregate metrics across multiple evaluations."""
    
    # Primary metric
    total_tasks: int = 0
    resolved_tasks: int = 0
    percent_resolved: float = 0.0
    
    # Score distribution
    mean_score: float = 0.0
    median_score: float = 0.0
    score_std: float = 0.0
    min_score: float = 0.0
    max_score: float = 0.0
    
    # Efficiency
    mean_iterations: float = 0.0
    mean_cost_usd: float = 0.0
    mean_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0
    total_duration_seconds: float = 0.0
    
    # Quality breakdown
    mean_test_pass_rate: float = 0.0
    mean_lint_score: float = 0.0
    type_check_pass_rate: float = 0.0
    mean_security_issues: float = 0.0
    mean_coverage: float | None = None
    
    # Agent utilization
    agent_utilization: dict[str, float] = None  # role -> fraction of tasks
    tool_usage: dict[str, int] = None
    
    # Reliability
    error_rate: float = 0.0
    timeout_rate: float = 0.0
    human_intervention_rate: float = 0.0
    
    def __post_init__(self):
        if self.agent_utilization is None:
            self.agent_utilization = {}
        if self.tool_usage is None:
            self.tool_usage = {}


def compute_aggregate(metrics: list[TrajectoryMetrics]) -> EvaluationAggregate:
    """Compute aggregate statistics from trajectory metrics."""
    if not metrics:
        return EvaluationAggregate()
    
    n = len(metrics)
    
    # Primary
    resolved = sum(1 for m in metrics if m.resolved)
    
    # Scores
    scores = [m.overall_score if hasattr(m, 'overall_score') else 0.0 for m in metrics]
    # Use test_pass_rate as proxy for score if no overall_score
    if all(s == 0.0 for s in scores):
        scores = [m.test_pass_rate for m in metrics]
    
    scores_sorted = sorted(scores)
    median = scores_sorted[n // 2] if n % 2 == 1 else (scores_sorted[n // 2 - 1] + scores_sorted[n // 2]) / 2
    
    import statistics
    mean = statistics.mean(scores)
    std = statistics.stdev(scores) if n > 1 else 0.0
    
    # Efficiency
    iterations = [m.iterations_taken for m in metrics]
    costs = [m.total_cost_usd for m in metrics]
    durations = [m.total_duration_seconds for m in metrics]
    
    # Quality
    test_rates = [m.test_pass_rate for m in metrics]
    lint_scores = [m.lint_score for m in metrics]
    type_checks = [m.type_check_passed for m in metrics]
    security_counts = [m.security_issues_count for m in metrics]
    
    # Coverage (only where available)
    coverages = [m.coverage_percent for m in metrics if m.coverage_percent is not None]
    
    # Agent utilization
    all_roles = set()
    for m in metrics:
        all_roles.update(m.agent_invocations.keys())
    
    agent_util = {}
    for role in all_roles:
        used = sum(1 for m in metrics if m.agent_invocations.get(role, 0) > 0)
        agent_util[role] = used / n
    
    # Tool usage
    tool_counts = {}
    for m in metrics:
        for tool, count in m.tool_calls.items():
            tool_counts[tool] = tool_counts.get(tool, 0) + count
    
    return EvaluationAggregate(
        total_tasks=n,
        resolved_tasks=resolved,
        percent_resolved=resolved / n * 100,
        mean_score=mean,
        median_score=median,
        score_std=std,
        min_score=min(scores),
        max_score=max(scores),
        mean_iterations=statistics.mean(iterations),
        mean_cost_usd=statistics.mean(costs),
        mean_duration_seconds=statistics.mean(durations),
        total_cost_usd=sum(costs),
        total_duration_seconds=sum(durations),
        mean_test_pass_rate=statistics.mean(test_rates),
        mean_lint_score=statistics.mean(lint_scores),
        type_check_pass_rate=sum(type_checks) / n,
        mean_security_issues=statistics.mean(security_counts),
        mean_coverage=statistics.mean(coverages) if coverages else None,
        agent_utilization=agent_util,
        tool_usage=tool_counts,
        error_rate=sum(1 for m in metrics if m.errors) / n,
        timeout_rate=sum(1 for m in metrics if any("timeout" in e.lower() for e in m.errors)) / n,
        human_intervention_rate=sum(m.human_interventions for m in metrics) / n,
    )


def format_metrics_table(aggregate: EvaluationAggregate) -> str:
    """Format aggregate metrics as a markdown table."""
    lines = [
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Primary Metric** | |",
        f"| % Resolved | {aggregate.percent_resolved:.1f}% |",
        f"| Resolved / Total | {aggregate.resolved_tasks} / {aggregate.total_tasks} |",
        f"| | |",
        f"| **Scores** | |",
        f"| Mean Score | {aggregate.mean_score:.4f} |",
        f"| Median Score | {aggregate.median_score:.4f} |",
        f"| Std Dev | {aggregate.score_std:.4f} |",
        f"| Min / Max | {aggregate.min_score:.4f} / {aggregate.max_score:.4f} |",
        f"| | |",
        f"| **Efficiency** | |",
        f"| Mean Iterations | {aggregate.mean_iterations:.1f} |",
        f"| Mean Cost | ${aggregate.mean_cost_usd:.6f} |",
        f"| Mean Duration | {aggregate.mean_duration_seconds:.1f}s |",
        f"| Total Cost | ${aggregate.total_cost_usd:.6f} |",
        f"| Total Duration | {aggregate.total_duration_seconds:.1f}s |",
        f"| | |",
        f"| **Quality** | |",
        f"| Test Pass Rate | {aggregate.mean_test_pass_rate:.2%} |",
        f"| Lint Score | {aggregate.mean_lint_score:.2%} |",
        f"| Type Check Pass Rate | {aggregate.type_check_pass_rate:.2%} |",
        f"| Security Issues (avg) | {aggregate.mean_security_issues:.2f} |",
    ]
    
    if aggregate.mean_coverage is not None:
        lines.append(f"| Coverage | {aggregate.mean_coverage:.1f}% |")
    
    lines.extend([
        f"| | |",
        f"| **Reliability** | |",
        f"| Error Rate | {aggregate.error_rate:.2%} |",
        f"| Timeout Rate | {aggregate.timeout_rate:.2%} |",
        f"| Human Intervention Rate | {aggregate.human_intervention_rate:.2%} |",
    ])
    
    if aggregate.agent_utilization:
        lines.append(f"| | |")
        lines.append(f"| **Agent Utilization** | |")
        for role, util in sorted(aggregate.agent_utilization.items()):
            lines.append(f"| {role} | {util:.1%} |")
    
    if aggregate.tool_usage:
        lines.append(f"| | |")
        lines.append(f"| **Tool Usage** | |")
        for tool, count in sorted(aggregate.tool_usage.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"| {tool} | {count} |")
    
    return "\n".join(lines)


# SWE-bench specific metrics
@dataclass
class SWEBenchMetrics:
    """Metrics specific to SWE-bench evaluation."""
    
    # Instance-level
    instance_id: str
    repo: str
    resolved: bool
    
    # Patch quality
    patch_generated: bool = False
    patch_applies: bool = False
    tests_pass: bool = False
    
    # Comparison with golden patch
    patch_similarity: float = 0.0  # 0-1 similarity to reference fix
    files_modified: int = 0
    lines_changed: int = 0
    
    # Cost/latency
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    
    # Error info
    error: str | None = None


def compute_swebench_metrics(results: list[SWEBenchMetrics]) -> dict[str, float]:
    """Compute SWE-bench aggregate metrics."""
    if not results:
        return {}
    
    n = len(results)
    resolved = sum(1 for r in results if r.resolved)
    patch_gen = sum(1 for r in results if r.patch_generated)
    patch_applies = sum(1 for r in results if r.patch_applies)
    tests_pass = sum(1 for r in results if r.tests_pass)
    
    return {
        "total_instances": n,
        "resolved": resolved,
        "percent_resolved": resolved / n * 100,
        "patch_generated_rate": patch_gen / n,
        "patch_applies_rate": patch_applies / n,
        "tests_pass_rate": tests_pass / n,
        "avg_patch_similarity": sum(r.patch_similarity for r in results) / n,
        "avg_files_modified": sum(r.files_modified for r in results) / n,
        "avg_lines_changed": sum(r.lines_changed for r in results) / n,
        "avg_cost_usd": sum(r.cost_usd for r in results) / n,
        "avg_duration_seconds": sum(r.duration_seconds for r in results) / n,
        "error_rate": sum(1 for r in results if r.error) / n,
    }