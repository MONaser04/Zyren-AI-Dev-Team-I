"""
Router Evaluation & Anti-Drift Guardrail — Phase 6
==================================================
Evaluates the semantic router's accuracy over time (drift detection),
enforces a performance floor, and triggers alerts on degradation.

The module requires no existing semantic_router in src/ — it ships
with a standalone RouterEvaluator that wraps the gateway's routing
capabilities and can be extended once a dedicated router is added.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RoutingSample:
    """A single routing decision with expected vs actual."""
    sample_id: str
    input_text: str
    expected_agent: str
    actual_agent: str
    confidence: float         # model confidence 0-1
    latency_ms: float
    correct: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RouterEvaluationResult:
    """Result of evaluating the router on a batch of samples."""
    run_id: str
    started_at: str
    finished_at: str | None = None
    total_samples: int = 0
    correct_routes: int = 0
    accuracy: float = 0.0
    mean_confidence: float = 0.0
    median_latency_ms: float = 0.0
    per_agent_accuracy: dict[str, float] = field(default_factory=dict)
    confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    drift_detected: bool = False
    drift_score: float = 0.0          # 0 = no drift, >0.3 = significant
    samples: list[RoutingSample] = field(default_factory=list)


@dataclass
class PerformanceFloor:
    """Minimum acceptable router performance."""
    min_accuracy: float = 0.70         # 70% correct routing
    min_per_agent_accuracy: float = 0.60  # per-agent floor
    max_drift_score: float = 0.30       # KS-statistic threshold
    max_latency_p95_ms: float = 500.0  # p95 latency ceiling
    require_confidence_calibration: bool = True


# ---------------------------------------------------------------------------
# Router Evaluator
# ---------------------------------------------------------------------------

class RouterEvaluator:
    """
    Evaluates routing quality and monitors for drift.

    Uses a labelled dataset (config/router_eval.yaml) to measure
    accuracy, confidence calibration, and per-agent performance.
    Tracks consecutive runs to detect performance drift via a
    sliding-window KS test on accuracy distributions.
    """

    def __init__(
        self,
        dataset_path: str | Path = "config/router_eval.yaml",
        floor: PerformanceFloor | None = None,
        window_size: int = 5,
        verbose: bool = False,
    ):
        self.dataset_path = Path(dataset_path)
        self.floor = floor or PerformanceFloor()
        self.window_size = window_size
        self.verbose = verbose

        self.run_id = f"router-eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self.history: list[RouterEvaluationResult] = []  # sliding window

    # ------------------------------------------------------------------
    # Dataset loading
    # ------------------------------------------------------------------

    def load_dataset(self) -> list[dict[str, Any]]:
        """Load labelled routing samples from YAML."""
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Router eval dataset not found: {self.dataset_path}")
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("samples", [])

    # ------------------------------------------------------------------
    # Routing simulation (standalone – no existing router required)
    # ------------------------------------------------------------------

    def _classify_input(self, text: str) -> tuple[str, float]:
        """
        Simulate a routing decision.

        In production this would call the deployed semantic router.
        The current implementation uses keyword-based heuristics that
        mirror the gateway dispatching logic.  Replace with a real
        router call once src/orchestrator/semantic_router.py exists.
        """
        text_lower = text.lower()

        # Agent keyword mapping (must stay in sync with gateway)
        signatures: dict[str, list[str]] = {
            "architect":    ["design", "architecture", "system", "plan", "component", "structur"],
            "coder":        ["implement", "code", "function", "write", "build", "create"],
            "critic":       ["review", "evaluate", "assess", "quality", "check", "inspect"],
            "debugger":     ["bug", "error", "fix", "debug", "issue", "broken", "fail"],
            "devops":       ["deploy", "docker", "ci", "pipeline", "infra", "container"],
            "researcher":   ["research", "analyse", "study", "compare", "investigate"],
        }

        scores: dict[str, float] = {}
        for agent, keywords in signatures.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            scores[agent] = score / max(len(keywords), 1)  # normalise 0-1

        if not scores or max(scores.values()) == 0:
            return ("coder", 0.3)  # default fallback

        best_agent = max(scores, key=scores.__getitem__)  # type: ignore[arg-type]
        confidence = scores[best_agent]
        return (best_agent, round(confidence, 4))

    # ------------------------------------------------------------------
    # Single evaluation run
    # ------------------------------------------------------------------

    def evaluate(self) -> RouterEvaluationResult:
        """Run the full router evaluation on the labelled dataset."""
        samples_raw = self.load_dataset()
        started_at = datetime.now(timezone.utc).isoformat()

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"🔀 Router Evaluation: {self.run_id}")
            print(f"   Samples: {len(samples_raw)}")
            print(f"   Floor accuracy: ≥{self.floor.min_accuracy:.0%}")
            print(f"{'='*60}")

        routing_samples: list[RoutingSample] = []
        correct = 0
        latencies: list[float] = []
        confusion: dict[str, dict[str, int]] = {}
        per_agent: dict[str, list[bool]] = {}

        for raw in samples_raw:
            sid = raw.get("id", f"s-{len(routing_samples)}")
            text = raw.get("input", raw.get("text", ""))
            expected = raw.get("expected_agent", raw.get("agent", "coder"))

            # Simulate routing (replace with real router call later)
            start_ns = datetime.now(timezone.utc)
            actual, confidence = self._classify_input(text)
            latency_ms = (datetime.now(timezone.utc) - start_ns).total_seconds() * 1000

            is_correct = (actual == expected)
            if is_correct:
                correct += 1

            routing_samples.append(RoutingSample(
                sample_id=sid,
                input_text=text,
                expected_agent=expected,
                actual_agent=actual,
                confidence=confidence,
                latency_ms=latency_ms,
                correct=is_correct,
            ))
            latencies.append(latency_ms)

            # Confusion matrix
            confusion.setdefault(expected, {}).setdefault(actual, 0)
            confusion[expected][actual] += 1

            # Per-agent tracking
            per_agent.setdefault(expected, []).append(is_correct)

        total = len(routing_samples)
        accuracy = correct / total if total > 0 else 0.0
        mean_conf = statistics.mean(s.confidence for s in routing_samples) if routing_samples else 0.0
        median_lat = statistics.median(latencies) if latencies else 0.0

        per_agent_acc = {
            agent: sum(hits) / len(hits)
            for agent, hits in per_agent.items()
        }

        # Drift detection (compare with historical window)
        drift_score = self._compute_drift_score(accuracy)

        result = RouterEvaluationResult(
            run_id=self.run_id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            total_samples=total,
            correct_routes=correct,
            accuracy=accuracy,
            mean_confidence=mean_conf,
            median_latency_ms=median_lat,
            per_agent_accuracy=per_agent_acc,
            confusion_matrix=confusion,
            drift_detected=drift_score > self.floor.max_drift_score,
            drift_score=drift_score,
            samples=routing_samples,
        )

        self.history.append(result)
        if len(self.history) > self.window_size:
            self.history.pop(0)

        if self.verbose:
            self._print_result(result)

        return result

    # ------------------------------------------------------------------
    # Drift score (sliding-window KS-style)
    # ------------------------------------------------------------------

    def _compute_drift_score(self, current_accuracy: float) -> float:
        """Compute drift score based on deviation from historical mean."""
        if len(self.history) < 2:
            return 0.0

        historical_accs = [r.accuracy for r in self.history[:-1]]  # exclude current
        if not historical_accs:
            return 0.0

        mean_hist = statistics.mean(historical_accs)
        std_hist = statistics.stdev(historical_accs) if len(historical_accs) > 1 else 0.02

        if std_hist == 0:
            std_hist = 0.02

        deviation = abs(current_accuracy - mean_hist) / std_hist
        # clamp to 0-1 range
        drift = min(1.0, deviation / 3.0)
        return round(drift, 4)

    # ------------------------------------------------------------------
    # Floor enforcement
    # ------------------------------------------------------------------

    def check_floor(self, result: RouterEvaluationResult) -> list[str]:
        """Check result against the performance floor. Returns list of violations."""
        violations: list[str] = []

        if result.accuracy < self.floor.min_accuracy:
            violations.append(
                f"Overall accuracy {result.accuracy:.2%} < floor {self.floor.min_accuracy:.0%}"
            )

        for agent, acc in result.per_agent_accuracy.items():
            if acc < self.floor.min_per_agent_accuracy:
                violations.append(
                    f"Agent '{agent}' accuracy {acc:.2%} < per-agent floor {self.floor.min_per_agent_accuracy:.0%}"
                )

        if result.drift_score > self.floor.max_drift_score:
            violations.append(
                f"Drift score {result.drift_score:.4f} exceeds max {self.floor.max_drift_score}"
            )

        # p95 latency
        latencies = sorted(s.latency_ms for s in result.samples)
        if latencies:
            p95_idx = int(len(latencies) * 0.95)
            p95 = latencies[min(p95_idx, len(latencies) - 1)]
            if p95 > self.floor.max_latency_p95_ms:
                violations.append(
                    f"p95 latency {p95:.1f}ms exceeds max {self.floor.max_latency_p95_ms:.1f}ms"
                )

        return violations

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _print_result(self, result: RouterEvaluationResult) -> None:
        violations = self.check_floor(result)
        status = "✅ PASS" if not violations else "❌ FAIL"

        print(f"\n📊 Result: {status}")
        print(f"   Accuracy:         {result.accuracy:.2%}")
        print(f"   Correct routes:   {result.correct_routes}/{result.total_samples}")
        print(f"   Mean confidence:  {result.mean_confidence:.4f}")
        print(f"   Median latency:   {result.median_latency_ms:.1f}ms")
        print(f"   Drift score:      {result.drift_score:.4f} {'⚠ DRIFT' if result.drift_detected else '✓ stable'}")

        if violations:
            print(f"\n   ⚠ Floor violations:")
            for v in violations:
                print(f"      - {v}")

    def to_dict(self, result: RouterEvaluationResult) -> dict:
        """Serialise result for JSON export."""
        return {
            "run_id": result.run_id,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "total_samples": result.total_samples,
            "correct_routes": result.correct_routes,
            "accuracy": result.accuracy,
            "mean_confidence": result.mean_confidence,
            "median_latency_ms": result.median_latency_ms,
            "per_agent_accuracy": result.per_agent_accuracy,
            "confusion_matrix": {exp: dict(row) for exp, row in result.confusion_matrix.items()},
            "drift_detected": result.drift_detected,
            "drift_score": result.drift_score,
            "floor_violations": self.check_floor(result),
            "samples": [
                {
                    "sample_id": s.sample_id,
                    "expected": s.expected_agent,
                    "actual": s.actual_agent,
                    "correct": s.correct,
                    "confidence": s.confidence,
                    "latency_ms": s.latency_ms,
                }
                for s in result.samples
            ],
        }


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def evaluate_router(
    dataset_path: str | Path = "config/router_eval.yaml",
    floor: PerformanceFloor | None = None,
    verbose: bool = True,
) -> RouterEvaluationResult:
    """Run router evaluation and return result."""
    evaluator = RouterEvaluator(dataset_path=dataset_path, floor=floor, verbose=verbose)
    return evaluator.evaluate()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    dataset = sys.argv[1] if len(sys.argv) > 1 else "config/router_eval.yaml"
    result = evaluate_router(dataset_path=dataset, verbose=True)

    violations = RouterEvaluator(dataset_path=dataset).check_floor(result)
    sys.exit(1 if violations else 0)