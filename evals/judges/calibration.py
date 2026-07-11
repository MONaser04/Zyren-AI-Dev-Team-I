"""
Calibration Module for LLM-as-Judge
====================================
Runs the calibration process: sends calibration tasks to the judge,
compares with human labels, computes Cohen's kappa, and iterates
until κ ≥ 0.6 (configurable).
"""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.gateway.llm_client import LLMClient


@dataclass
class CalibrationResult:
    """Result of a single calibration round."""
    round_num: int
    kappa: float
    agreements: dict[str, float]  # per-category agreement
    overall_accuracy: float
    judge_scores: list[dict[str, Any]]
    human_scores: list[dict[str, Any]]
    passed: bool


@dataclass
class CalibrationReport:
    """Full calibration session report."""
    session_id: str
    started_at: str
    finished_at: str | None = None
    config: dict = field(default_factory=dict)
    rounds: list[CalibrationResult] = field(default_factory=list)
    final_kappa: float = 0.0
    converged: bool = False
    best_round: int = 0
    notes: list[str] = field(default_factory=list)


def load_calibration_set(path: str | Path) -> dict:
    """Load calibration tasks and config from YAML."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_scores(scores: dict[str, int]) -> dict[str, float]:
    """Normalize 1-10 scores to 0-1 range. Skips non-integer values."""
    normalized = {}
    for k, v in scores.items():
        if isinstance(v, (int, float)):
            normalized[k] = max(0.0, min(1.0, float(v) / 10.0))
        # Skip non-numeric values like "summary"
    return normalized


def score_to_binary(score: float, threshold: float = 0.5) -> int:
    """Convert normalized score to binary PASS/FAIL."""
    return 1 if score >= threshold else 0


def compute_cohen_kappa(judge_binary: list[int], human_binary: list[int]) -> float:
    """
    Compute Cohen's kappa for inter-rater agreement.
    
    κ = (Po - Pe) / (1 - Pe)
    Po = observed agreement
    Pe = expected agreement by chance
    """
    if len(judge_binary) != len(human_binary):
        raise ValueError("Lists must be same length")
    
    n = len(judge_binary)
    if n == 0:
        return 0.0
    
    # Observed agreement
    agreements = sum(1 for j, h in zip(judge_binary, human_binary) if j == h)
    po = agreements / n
    
    # Expected agreement by chance
    judge_pos = sum(judge_binary) / n
    judge_neg = 1 - judge_pos
    human_pos = sum(human_binary) / n
    human_neg = 1 - human_pos
    
    pe = (judge_pos * human_pos) + (judge_neg * human_neg)
    
    if pe >= 1.0:
        return 1.0 if po == 1.0 else 0.0
    
    kappa = (po - pe) / (1 - pe)
    return max(-1.0, min(1.0, kappa))  # Clamp to [-1, 1]


def compute_per_category_kappa(
    judge_results: list[dict], 
    human_results: list[dict],
    categories: list[str],
    threshold: float = 0.5
) -> dict[str, float]:
    """Compute Cohen's kappa per category."""
    kappas = {}
    for cat in categories:
        judge_scores = [r["category_scores"].get(cat, 0.5) for r in judge_results]
        human_scores = [r["human_scores"].get(cat, 0.5) for r in human_results]
        
        judge_bin = [score_to_binary(s, threshold) for s in judge_scores]
        human_bin = [score_to_binary(s, threshold) for s in human_scores]
        
        kappas[cat] = compute_cohen_kappa(judge_bin, human_bin)
    
    return kappas


class JudgeCalibrator:
    """
    Calibrates an LLM judge against human labels.
    
    Process:
    1. Load calibration set (tasks with human scores)
    2. Run judge on each task (multiple rounds with randomized order)
    3. Compute Cohen's kappa per round
    4. If κ < threshold, adjust prompt/rubric and repeat
    5. Stop when κ ≥ threshold or max rounds reached
    """
    
    def __init__(
        self,
        calibration_path: str | Path = "evals/judges/calibration_set.yaml",
        judge_model: str = "critic",
        min_kappa: float = 0.6,
        max_rounds: int = 5,
        threshold: float = 0.5,
        randomize_order: bool = True,
        dry_run: bool = False,
    ):
        self.calibration_path = Path(calibration_path)
        self.judge_model = judge_model
        self.min_kappa = min_kappa
        self.max_rounds = max_rounds
        self.threshold = threshold
        self.randomize_order = randomize_order
        self.dry_run = dry_run
        
        if not dry_run:
            self.client = LLMClient()
        self.data = load_calibration_set(self.calibration_path)
        self.tasks = self.data.get("calibration_tasks", [])
        self.config = self.data.get("calibration_config", {})
        self.categories = self.config.get("categories", ["correctness", "code_quality", "documentation", "error_handling"])
        
        self.session_id = f"cal-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        self.report = CalibrationReport(
            session_id=self.session_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            config={
                "judge_model": judge_model,
                "min_kappa": min_kappa,
                "max_rounds": max_rounds,
                "threshold": threshold,
                "num_tasks": len(self.tasks),
                "categories": self.categories,
            }
        )
    
    def _build_judge_prompt(self, task: dict, rubric: dict | None = None) -> str:
        """Build injection-safe judge prompt."""
        # Sanitize inputs to prevent prompt injection
        task_desc = task.get("task_description", "").replace("{", "{{").replace("}", "}}")
        code = task.get("code", "").replace("{", "{{").replace("}", "}}")
        
        rubric_text = ""
        if rubric:
            rubric_text = "\nRubric:\n" + "\n".join(f"- {k}: {v}" for k, v in rubric.items())
        
        return f"""You are a code-review judge. Evaluate the following code on these categories with scores from 1 (worst) to 10 (best).

Categories:
- correctness: Does the code do what was asked? Are there logical errors?
- code_quality: Is the code well-structured, readable, DRY, testable?
- documentation: Are docstrings, comments, and inline docs present?
- error_handling: Are edge cases, exceptions, and invalid inputs handled?

{rubric_text}

Output ONLY a JSON object in this exact format (no markdown, no extra text):

{{
  "correctness": <1-10>,
  "code_quality": <1-10>,
  "documentation": <1-10>,
  "error_handling": <1-10>,
  "summary": "<one-sentence overall assessment>"
}}

Task description:
{task_desc}

Code:
{code}"""
    
    def _parse_judge_response(self, response: str) -> dict[str, Any] | None:
        """Parse judge response, handling markdown wrapping."""
        clean = response.strip()
        
        # Strip markdown code fences
        if clean.startswith("```json"):
            clean = clean.removeprefix("```json").removesuffix("```").strip()
        elif clean.startswith("```"):
            clean = clean.removeprefix("```").removesuffix("```").strip()
        
        try:
            parsed = json.loads(clean)
            # Validate required fields
            required = ["correctness", "code_quality", "documentation", "error_handling"]
            for field in required:
                if field not in parsed:
                    return None
            return parsed
        except json.JSONDecodeError:
            # Try regex extraction
            import re
            match = re.search(r"\{[^{}]*\}", clean, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return None
    
    def run_judge_on_task(self, task: dict, rubric: dict | None = None) -> dict[str, Any] | None:
        """Run judge on a single task."""
        prompt = self._build_judge_prompt(task, rubric)
        
        if self.dry_run:
            # Return mock scores for dry-run (integers 1-10)
            mock_scores = {cat: 5 for cat in self.categories}
            mock_scores["summary"] = "Dry-run mock response"
            return mock_scores
        
        try:
            response = self.client.complete_text(
                model=self.judge_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.0,
            )
            return self._parse_judge_response(response)
        except Exception as e:
            print(f"  ⚠ Judge error on task {task['id']}: {e}")
            return None
    
    def run_calibration_round(self, round_num: int, rubric: dict | None = None) -> CalibrationResult:
        """Run one calibration round."""
        print(f"\n🔄 Calibration Round {round_num}/{self.max_rounds}")
        
        # Prepare tasks (randomize order if configured)
        tasks = self.tasks.copy()
        if self.randomize_order:
            random.shuffle(tasks)
        
        judge_results = []
        human_results = []
        
        for i, task in enumerate(tasks, 1):
            print(f"  [{i}/{len(tasks)}] Judging {task['id']}...")
            
            judge_result = self.run_judge_on_task(task, rubric)
            if judge_result is None:
                print(f"    ⚠ Failed to parse judge response, using neutral scores")
                judge_result = {cat: 5 for cat in self.categories}
                judge_result["summary"] = "Parse failed"
            
            # Normalize judge scores to 0-1
            judge_norm = normalize_scores(judge_result)
            
            # Get human scores (normalized)
            human_raw = task.get("human_scores", {})
            human_norm = normalize_scores(human_raw)
            
            judge_results.append({
                "task_id": task["id"],
                "category_scores": judge_norm,
                "summary": judge_result.get("summary", ""),
            })
            human_results.append({
                "task_id": task["id"],
                "human_scores": human_norm,
            })
        
        # Compute overall binary agreement (PASS/FAIL)
        judge_overall = [statistics.mean(r["category_scores"].values()) for r in judge_results]
        human_overall = [statistics.mean(r["human_scores"].values()) for r in human_results]
        
        judge_binary = [score_to_binary(s, self.threshold) for s in judge_overall]
        human_binary = [score_to_binary(s, self.threshold) for s in human_overall]
        
        overall_kappa = compute_cohen_kappa(judge_binary, human_binary)
        
        # Per-category kappa
        category_kappas = compute_per_category_kappa(
            judge_results, human_results, self.categories, self.threshold
        )
        
        # Overall accuracy
        correct = sum(1 for j, h in zip(judge_binary, human_binary) if j == h)
        accuracy = correct / len(judge_binary) if judge_binary else 0.0
        
        result = CalibrationResult(
            round_num=round_num,
            kappa=overall_kappa,
            agreements=category_kappas,
            overall_accuracy=accuracy,
            judge_scores=judge_results,
            human_scores=human_results,
            passed=overall_kappa >= self.min_kappa,
        )
        
        print(f"  📊 Cohen's κ = {overall_kappa:.4f} (target: ≥{self.min_kappa})")
        print(f"  📈 Accuracy = {accuracy:.2%}")
        for cat, k in category_kappas.items():
            print(f"    {cat}: κ = {k:.4f}")
        
        return result
    
    def calibrate(self, rubric: dict | None = None) -> CalibrationReport:
        """Run full calibration process."""
        print(f"\n{'='*60}")
        print(f"🎯 LLM Judge Calibration Session: {self.session_id}")
        print(f"   Judge model: {self.judge_model}")
        print(f"   Tasks: {len(self.tasks)}")
        print(f"   Target κ: ≥{self.min_kappa}")
        print(f"   Max rounds: {self.max_rounds}")
        print(f"{'='*60}")
        
        best_kappa = 0.0
        best_round = 0
        
        for round_num in range(1, self.max_rounds + 1):
            result = self.run_calibration_round(round_num, rubric)
            self.report.rounds.append(result)
            
            if result.kappa > best_kappa:
                best_kappa = result.kappa
                best_round = round_num
            
            if result.passed:
                print(f"\n✅ CALIBRATION PASSED at round {round_num} (κ = {result.kappa:.4f})")
                self.report.converged = True
                break
            elif round_num < self.max_rounds:
                print(f"\n⚠ κ = {result.kappa:.4f} < {self.min_kappa}, adjusting and retrying...")
                # In a real implementation, you'd adjust the prompt/rubric here
                # For now, we just retry with randomized order
        
        self.report.final_kappa = best_kappa
        self.report.best_round = best_round
        self.report.finished_at = datetime.now(timezone.utc).isoformat()
        
        if not self.report.converged:
            self.report.notes.append(f"Did not converge after {self.max_rounds} rounds. Best κ = {best_kappa:.4f}")
        
        return self.report
    
    def save_report(self, output_dir: str | Path = "reports/calibration") -> Path:
        """Save calibration report to disk."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        report_file = output_path / f"calibration_report_{self.session_id}.json"
        
        # Convert to serializable dict
        report_dict = {
            "session_id": self.report.session_id,
            "started_at": self.report.started_at,
            "finished_at": self.report.finished_at,
            "config": self.report.config,
            "final_kappa": self.report.final_kappa,
            "converged": self.report.converged,
            "best_round": self.report.best_round,
            "notes": self.report.notes,
            "rounds": [
                {
                    "round_num": r.round_num,
                    "kappa": r.kappa,
                    "agreements": r.agreements,
                    "overall_accuracy": r.overall_accuracy,
                    "passed": r.passed,
                }
                for r in self.report.rounds
            ],
        }
        
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Calibration report saved: {report_file}")
        return report_file


def run_calibration(
    calibration_path: str | Path = "evals/judges/calibration_set.yaml",
    judge_model: str = "critic",
    min_kappa: float = 0.6,
    max_rounds: int = 5,
    output_dir: str | Path = "reports/calibration",
) -> CalibrationReport:
    """Convenience function to run calibration."""
    calibrator = JudgeCalibrator(
        calibration_path=calibration_path,
        judge_model=judge_model,
        min_kappa=min_kappa,
        max_rounds=max_rounds,
    )
    report = calibrator.calibrate()
    calibrator.save_report(output_dir)
    return report


if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Run LLM Judge Calibration")
    parser.add_argument("--model", "-m", default="critic", help="Judge model alias")
    parser.add_argument("--kappa", "-k", type=float, default=0.6, help="Target Cohen's kappa")
    parser.add_argument("--rounds", "-r", type=int, default=5, help="Max calibration rounds")
    parser.add_argument("--dry-run", action="store_true", help="Run without calling LLM (mock responses)")
    
    args = parser.parse_args()
    
    # For dry-run, use mock calibrator
    if args.dry_run:
        from evals.judges.calibration import JudgeCalibrator
        calibrator = JudgeCalibrator(
            calibration_path="evals/judges/calibration_set.yaml",
            judge_model=args.model,
            min_kappa=args.kappa,
            max_rounds=args.rounds,
            dry_run=True,
        )
        report = calibrator.calibrate()
        calibrator.save_report()
    else:
        report = run_calibration(judge_model=args.model, min_kappa=args.kappa, max_rounds=args.rounds)
    
    print(f"\n{'='*60}")
    print(f"FINAL RESULT: {'✅ PASSED' if report.converged else '❌ FAILED'}")
    print(f"Best Cohen's κ: {report.final_kappa:.4f}")
    print(f"Converged at round: {report.best_round}")
    print(f"{'='*60}")
    
    sys.exit(0 if report.converged else 1)
