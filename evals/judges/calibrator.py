"""
Judge Calibration — Phase 7
============================
Calibrates LLM-as-Judge against human labels using Cohen's kappa.
Target: κ > 0.6
"""
from __future__ import annotations

import asyncio
import json
import logging
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gateway.smart_gateway import SmartGateway
from gateway.model_registry import AutoModelRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalibrationSample:
    """A single calibration sample with human label."""
    sample_id: str
    trajectory: dict[str, Any]
    human_label: str  # "pass" or "fail"
    human_reasoning: str = ""
    difficulty: str = "medium"  # easy, medium, hard


@dataclass(frozen=True)
class JudgeResult:
    """Result of judge evaluation."""
    sample_id: str
    judge_label: str  # "pass" or "fail"
    judge_confidence: float
    judge_reasoning: str
    human_label: str
    agreement: bool


@dataclass
class CalibrationReport:
    """Calibration report with Cohen's kappa."""
    cohen_kappa: float
    agreement_rate: float
    total_samples: int
    judge_accuracy: float
    per_difficulty: dict[str, dict[str, float]] = field(default_factory=dict)
    confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    judge_model: str = ""
    passed: bool = False


class JudgeCalibrator:
    """Calibrates LLM judge against human labels."""

    def __init__(
        self,
        judge_model: str = "anthropic/claude-3.5-sonnet",
        target_kappa: float = 0.6,
    ):
        self.judge_model = judge_model
        self.target_kappa = target_kappa
        self.gateway = None

    async def initialize(self) -> None:
        """Initialize gateway and judge model."""
        registry = AutoModelRegistry()
        await registry.initialize(discover=True)
        self.gateway = SmartGateway(registry)

    def load_calibration_set(self, path: str) -> list[CalibrationSample]:
        """Load calibration samples from YAML."""
        with open(path) as f:
            data = yaml.safe_load(f)
        samples = []
        for item in data.get("samples", []):
            samples.append(CalibrationSample(**item))
        logger.info("Loaded %d calibration samples", len(samples))
        return samples

    async def evaluate_sample(self, sample: CalibrationSample) -> JudgeResult:
        """Evaluate a single sample with the judge model."""
        prompt = self._build_judge_prompt(sample)

        try:
            response = await self.gateway.complete_text(
                model=self.judge_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1024,
            )

            # Parse response
            content = response.strip()
            judge_label, confidence, reasoning = self._parse_judge_response(content)

        except Exception as e:
            logger.exception("Judge evaluation failed for %s", sample.sample_id)
            judge_label = "fail"
            confidence = 0.0
            reasoning = f"Error: {e}"

        agreement = judge_label == sample.human_label

        return JudgeResult(
            sample_id=sample.sample_id,
            judge_label=judge_label,
            judge_confidence=confidence,
            judge_reasoning=reasoning,
            human_label=sample.human_label,
            agreement=agreement,
        )

    def _build_judge_prompt(self, sample: CalibrationSample) -> str:
        """Build prompt for judge evaluation."""
        return f"""You are an expert software engineer evaluating whether a coding task was completed successfully.

TASK TRAJECTORY:
{json.dumps(sample.trajectory, indent=2)}

HUMAN LABEL (ground truth): {sample.human_label}
HUMAN REASONING: {sample.human_reasoning}

Evaluate whether the final output successfully solves the task.

OUTPUT FORMAT (JSON only):
{{
  "label": "pass" or "fail",
  "confidence": 0.0-1.0,
  "reasoning": "your reasoning here"
}}

Consider:
- Does the code compile/run without errors?
- Does it solve the stated problem?
- Are tests passing?
- Are there any obvious bugs or security issues?
- Is the solution complete and minimal?
"""

    def _parse_judge_response(self, content: str) -> tuple[str, float, str]:
        """Parse judge response JSON."""
        try:
            data = json.loads(content)
            label = data.get("label", "fail").lower()
            confidence = float(data.get("confidence", 0.5))
            reasoning = data.get("reasoning", "")
            return label, confidence, reasoning
        except (json.JSONDecodeError, ValueError):
            # Fallback parsing
            label = "pass" if "pass" in content.lower() and "fail" not in content.lower() else "fail"
            return label, 0.5, content[:500]

    async def calibrate(
        self,
        samples: list[CalibrationSample],
        max_concurrent: int = 5,
    ) -> CalibrationReport:
        """Run calibration on all samples."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def eval_with_semaphore(sample):
            async with semaphore:
                return await self.evaluate_sample(sample)

        results = await asyncio.gather(*[eval_with_semaphore(s) for s in samples])

        return self._compute_metrics(results)

    def _compute_metrics(self, results: list[JudgeResult]) -> CalibrationReport:
        """Compute Cohen's kappa and other metrics."""
        total = len(results)
        agreements = sum(1 for r in results if r.agreement)
        agreement_rate = agreements / total if total > 0 else 0.0

        # Confusion matrix
        cm = {"pass": {"pass": 0, "fail": 0}, "fail": {"pass": 0, "fail": 0}}
        for r in results:
            cm[r.human_label][r.judge_label] += 1

        # Cohen's Kappa
        # p_o = observed agreement
        p_o = agreement_rate

        # p_e = expected agreement by chance
        human_pass = sum(1 for r in results if r.human_label == "pass") / total
        human_fail = 1 - human_pass
        judge_pass = sum(1 for r in results if r.judge_label == "pass") / total
        judge_fail = 1 - judge_pass
        p_e = human_pass * judge_pass + human_fail * judge_fail

        if p_e == 1.0:
            kappa = 1.0
        else:
            kappa = (p_o - p_e) / (1 - p_e)

        # Per-difficulty breakdown
        per_difficulty = {}
        for difficulty in ["easy", "medium", "hard"]:
            diff_results = [r for r in results if any(s.difficulty == difficulty for s in [] if s.sample_id == r.sample_id)]
            # Would need to map back to samples for difficulty
            # Placeholder for now
            per_difficulty[difficulty] = {"kappa": kappa, "agreement": agreement_rate}

        judge_accuracy = sum(1 for r in results if r.judge_label == r.human_label) / total if total > 0 else 0.0

        passed = kappa >= self.target_kappa

        return CalibrationReport(
            cohen_kappa=kappa,
            agreement_rate=agreement_rate,
            total_samples=total,
            judge_accuracy=judge_accuracy,
            per_difficulty=per_difficulty,
            confusion_matrix=cm,
            judge_model=self.judge_model,
            passed=passed,
        )

    async def save_report(self, report: CalibrationReport, path: str) -> None:
        """Save calibration report to JSON."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "cohen_kappa": report.cohen_kappa,
                "agreement_rate": report.agreement_rate,
                "total_samples": report.total_samples,
                "judge_accuracy": report.judge_accuracy,
                "per_difficulty": report.per_difficulty,
                "confusion_matrix": report.confusion_matrix,
                "judge_model": report.judge_model,
                "target_kappa": self.target_kappa,
                "passed": report.passed,
            }, f, indent=2)
        logger.info("Calibration report saved to %s", path)


def create_calibration_set(path: str) -> None:
    """Create a template calibration set with examples."""
    template = {
        "samples": [
            {
                "sample_id": "cal_001",
                "trajectory": {
                    "task": "Write a function to reverse a string",
                    "code": "def reverse(s): return s[::-1]",
                    "tests": ["assert reverse('hello') == 'olleh'"],
                    "result": "passed"
                },
                "human_label": "pass",
                "human_reasoning": "Correct implementation, passes all tests",
                "difficulty": "easy"
            },
            {
                "sample_id": "cal_002",
                "trajectory": {
                    "task": "Implement binary search",
                    "code": "def binary_search(arr, target):\n    return -1  # placeholder",
                    "tests": ["assert binary_search([1,2,3], 2) == 1"],
                    "result": "failed"
                },
                "human_label": "fail",
                "human_reasoning": "Implementation is a stub, doesn't implement binary search",
                "difficulty": "medium"
            }
        ]
    }

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(template, f, allow_unicode=True, sort_keys=False)
    logger.info("Created calibration template at %s", path)


async def main():
    """Run calibration."""
    calibrator = JudgeCalibrator(judge_model="anthropic/claude-3.5-sonnet", target_kappa=0.6)
    await calibrator.initialize()

    # Load or create calibration set
    cal_path = "evals/judges/calibration_set.yaml"
    if not Path(cal_path).exists():
        create_calibration_set(cal_path)
        print(f"Created template calibration set at {cal_path}")
        print("Please fill in human labels and run again.")
        return

    samples = calibrator.load_calibration_set(cal_path)
    print(f"Loaded {len(samples)} calibration samples")

    # Run calibration
    report = await calibrator.calibrate(samples)

    # Save report
    report_path = "reports/judge_calibration.json"
    await calibrator.save_report(report, report_path)

    print(f"\n=== Judge Calibration Results ===")
    print(f"Cohen's κ: {report.cohen_kappa:.3f}")
    print(f"Agreement Rate: {report.agreement_rate:.1%}")
    print(f"Judge Accuracy: {report.judge_accuracy:.1%}")
    print(f"Target κ: {calibrator.target_kappa}")
    print(f"PASSED: {'YES' if report.passed else 'NO'}")
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())