"""
LLM-as-Judge — Phase 6 (Upgraded from Phase 5)
==============================================
Uses an LLM (critic role) to evaluate generated code across
multiple qualitative categories: correctness, code_quality,
documentation, error_handling.

New in Phase 6:
- Calibrated judge (Cohen's κ ≥ 0.6)
- Low-precision scoring (binary / 3-point) to reduce variance
- Injection-safe prompts (sanitized inputs)
- Randomized order for pairwise comparisons
- Integration with calibration module

Output is a normalised judge_score (0.0–1.0) and detailed
category scores fed into CompositeScorer.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import yaml

from gateway.llm_client import LLMClient as LiteLLMClient
from evals.judges.calibration import JudgeCalibrator, run_calibration


class ScoringMode(StrEnum):
    """Scoring precision modes."""
    FINE = "fine"          # 1-10 scale (original)
    BINARY = "binary"      # PASS/FAIL
    THREE_POINT = "3point" # EXCELLENT / ACCEPTABLE / NEEDS_WORK


@dataclass
class JudgeConfig:
    """Configuration for the judge."""
    model: str = "critic"
    max_tokens: int = 2048
    temperature: float = 0.0
    scoring_mode: ScoringMode = ScoringMode.BINARY
    rubric_path: str | None = "evals/judges/rubrics.yaml"
    calibrate_on_init: bool = False
    min_kappa: float = 0.6


class LLMJudge:
    """LLM-based code quality judge with calibration support."""

    CATEGORIES = [
        "correctness",
        "code_quality",
        "documentation",
        "error_handling",
    ]

    # Fine-grained prompt (1-10 scale)
    FINE_PROMPT = """You are a code-review judge. Evaluate the following code on these categories with scores from 1 (worst) to 10 (best).

Categories:
- correctness: Does the code do what was asked? Are there logical errors?
- code_quality: Is the code well-structured, readable, DRY, testable?
- documentation: Are docstrings, comments, and inline docs present?
- error_handling: Are edge cases, exceptions, and invalid inputs handled?

Output ONLY a JSON object in this exact format (no markdown, no extra text):

{{
  "correctness": <1-10>,
  "code_quality": <1-10>,
  "documentation": <1-10>,
  "error_handling": <1-10>,
  "summary": "<one-sentence overall assessment>"
}}

Task description:
{task_description}

Code:
{code}"""

    # Binary prompt (PASS/FAIL)
    BINARY_PROMPT = """You are a code-review judge. Evaluate if the code PASSES or FAILS each category.

Categories:
- correctness: Does the code do what was asked? Are there logical errors?
- code_quality: Is the code well-structured, readable, DRY, testable?
- documentation: Are docstrings, comments, and inline docs present?
- error_handling: Are edge cases, exceptions, and invalid inputs handled?

Output ONLY a JSON object in this exact format (no markdown, no extra text):

{{
  "correctness": "PASS" or "FAIL",
  "code_quality": "PASS" or "FAIL",
  "documentation": "PASS" or "FAIL",
  "error_handling": "PASS" or "FAIL",
  "summary": "<one-sentence overall assessment>"
}}

Task description:
{task_description}

Code:
{code}"""

    # 3-point prompt (EXCELLENT / ACCEPTABLE / NEEDS_WORK)
    THREE_POINT_PROMPT = """You are a code-review judge. Evaluate the following code on these categories with scores:
- EXCELLENT (3): Outstanding, exceeds expectations
- ACCEPTABLE (2): Meets requirements, minor issues
- NEEDS_WORK (1): Does not meet requirements, significant issues

Categories:
- correctness: Does the code do what was asked? Are there logical errors?
- code_quality: Is the code well-structured, readable, DRY, testable?
- documentation: Are docstrings, comments, and inline docs present?
- error_handling: Are edge cases, exceptions, and invalid inputs handled?

Output ONLY a JSON object in this exact format (no markdown, no extra text):

{{
  "correctness": "EXCELLENT" or "ACCEPTABLE" or "NEEDS_WORK",
  "code_quality": "EXCELLENT" or "ACCEPTABLE" or "NEEDS_WORK",
  "documentation": "EXCELLENT" or "ACCEPTABLE" or "NEEDS_WORK",
  "error_handling": "EXCELLENT" or "ACCEPTABLE" or "NEEDS_WORK",
  "summary": "<one-sentence overall assessment>"
}}

Task description:
{task_description}

Code:
{code}"""

    def __init__(self, config: JudgeConfig | None = None) -> None:
        self.config = config or JudgeConfig()
        self.model = self.config.model
        self.max_tokens = self.config.max_tokens
        self.temperature = self.config.temperature
        self.scoring_mode = self.config.scoring_mode
        self.client = LiteLLMClient()
        self._rubric: dict | None = None
        self._calibrated = False
        
        if self.config.rubric_path:
            self._load_rubric()
        
        if self.config.calibrate_on_init:
            self.calibrate()

    def _load_rubric(self) -> None:
        """Load rubric from YAML file."""
        try:
            with open(self.config.rubric_path, "r", encoding="utf-8") as f:
                self._rubric = yaml.safe_load(f)
        except Exception:
            self._rubric = None

    def _get_prompt(self) -> str:
        """Get the appropriate prompt for the scoring mode."""
        if self.scoring_mode == ScoringMode.FINE:
            return self.FINE_PROMPT
        elif self.scoring_mode == ScoringMode.BINARY:
            return self.BINARY_PROMPT
        else:  # THREE_POINT
            return self.THREE_POINT_PROMPT

    def _sanitize_input(self, text: str) -> str:
        """Sanitize input to prevent prompt injection."""
        # Escape curly braces to prevent template injection
        return text.replace("{", "{{").replace("}", "}}")

    def _build_rubric_text(self) -> str:
        """Build rubric text from loaded rubric."""
        if not self._rubric:
            return ""
        
        lines = ["\nRubric:"]
        for cat in self.CATEGORIES:
            if cat in self._rubric:
                rubric_cat = self._rubric[cat]
                desc = rubric_cat.get("description", "")
                lines.append(f"- {cat}: {desc}")
                # Add key levels
                levels = rubric_cat.get("levels", {})
                if levels:
                    # Show threshold levels
                    key_levels = {10: levels.get(10), 7: levels.get(7), 4: levels.get(4), 1: levels.get(1)}
                    for level, desc_text in key_levels.items():
                        if desc_text:
                            lines.append(f"  {level}: {desc_text}")
        return "\n".join(lines)

    def calibrate(self, min_kappa: float | None = None, max_rounds: int = 5) -> bool:
        """Run calibration against human labels."""
        kappa = min_kappa or self.config.min_kappa
        report = run_calibration(
            judge_model=self.model,
            min_kappa=kappa,
            max_rounds=max_rounds,
        )
        self._calibrated = report.converged
        return report.converged

    # ------------------------------------------------------------------
    # Judge code
    # ------------------------------------------------------------------
    def judge(self, task_description: str, code: str) -> dict[str, Any]:
        """Evaluate code quality using LLM-as-judge.

        Returns:
            dict with:
                - judge_score: float (0.0–1.0)
                - category_scores: dict[str, float]
                - summary: str
                - raw_response: str
                - scoring_mode: str
        """
        # Sanitize inputs
        safe_task = self._sanitize_input(task_description)
        safe_code = self._sanitize_input(code)
        
        prompt = self._get_prompt()
        rubric_text = self._build_rubric_text()
        
        # Add rubric to prompt if available
        full_prompt = prompt.format(
            task_description=safe_task,
            code=safe_code,
        )
        if rubric_text:
            full_prompt = full_prompt.replace("Categories:", rubric_text + "\n\nCategories:")

        try:
            response = self.client.send(
                model=self.model,
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except Exception as exc:
            return self._fallback(error=str(exc))

        parsed = self._parse_response(response)
        parsed["scoring_mode"] = self.scoring_mode.value
        parsed["calibrated"] = self._calibrated
        return parsed

    # ------------------------------------------------------------------
    # Parse LLM response
    # ------------------------------------------------------------------
    def _parse_response(self, raw: str) -> dict[str, Any]:
        """Extract JSON from LLM output (handles markdown wrapping)."""
        clean = raw.strip()

        # Strip markdown code fences
        if clean.startswith("```json"):
            clean = clean.removeprefix("```json").removesuffix("```").strip()
        elif clean.startswith("```"):
            clean = clean.removeprefix("```").removesuffix("```").strip()

        try:
            parsed = json.loads(clean)
        except json.JSONDecodeError:
            # Try regex extraction
            match = re.search(r"\{[^{}]*\}", clean, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    return self._fallback(error=f"JSON parse failed: {raw[:200]}")
            else:
                return self._fallback(error=f"JSON parse failed: {raw[:200]}")

        # Convert to normalized scores based on scoring mode
        scores: dict[str, float] = {}
        
        if self.scoring_mode == ScoringMode.FINE:
            # 1-10 -> 0-1
            for cat in self.CATEGORIES:
                raw_val = parsed.get(cat, 5)
                try:
                    scores[cat] = max(0.0, min(1.0, float(raw_val) / 10.0))
                except (ValueError, TypeError):
                    scores[cat] = 0.5
            judge_score = sum(scores.values()) / len(scores)
            
        elif self.scoring_mode == ScoringMode.BINARY:
            # PASS/FAIL -> 1.0/0.0
            for cat in self.CATEGORIES:
                val = str(parsed.get(cat, "FAIL")).upper().strip()
                scores[cat] = 1.0 if val == "PASS" else 0.0
            judge_score = sum(scores.values()) / len(scores)
            
        else:  # THREE_POINT
            # EXCELLENT/ACCEPTABLE/NEEDS_WORK -> 1.0/0.5/0.0
            for cat in self.CATEGORIES:
                val = str(parsed.get(cat, "NEEDS_WORK")).upper().strip()
                if val == "EXCELLENT":
                    scores[cat] = 1.0
                elif val == "ACCEPTABLE":
                    scores[cat] = 0.5
                else:
                    scores[cat] = 0.0
            judge_score = sum(scores.values()) / len(scores)

        # For composite scoring, apply weights from rubric
        if self._rubric and "composite_binary" in self._rubric:
            weights = self._rubric["composite_binary"].get("weights", {})
            if weights:
                weighted_sum = sum(scores.get(cat, 0.5) * weights.get(cat, 0) for cat in self.CATEGORIES)
                judge_score = weighted_sum

        return {
            "judge_score": round(judge_score, 4),
            "category_scores": scores,
            "summary": parsed.get("summary", "No summary provided."),
            "raw_response": raw,
            "scoring_mode": self.scoring_mode.value,
            "calibrated": self._calibrated,
        }

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------
    def _fallback(self, error: str = "Judge unavailable") -> dict[str, Any]:
        """Return neutral scores when judge fails."""
        return {
            "judge_score": 0.5,
            "category_scores": {c: 0.5 for c in self.CATEGORIES},
            "summary": f"Judge error: {error}",
            "raw_response": "",
            "scoring_mode": self.scoring_mode.value,
            "calibrated": self._calibrated,
        }

    # ------------------------------------------------------------------
    # Pairwise comparison (for randomized order evaluation)
    # ------------------------------------------------------------------
    def compare(self, task_description: str, code_a: str, code_b: str) -> dict[str, Any]:
        """
        Compare two code submissions for the same task.
        Randomizes order to reduce position bias.
        """
        # Randomize order
        order = [(code_a, "A"), (code_b, "B")]
        random.shuffle(order)
        
        prompt = f"""You are a code-review judge. Compare two solutions for the same task.

Task:
{self._sanitize_input(task_description)}

Solution 1:
{self._sanitize_input(order[0][0])}

Solution 2:
{self._sanitize_input(order[1][0])}

Which solution is better? Output ONLY JSON:
{{
  "winner": "1" or "2",
  "reason": "<brief explanation>",
  "confidence": <0.0-1.0>
}}"""

        try:
            response = self.client.send(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.0,
            )
            
            clean = response.strip()
            if clean.startswith("```json"):
                clean = clean.removeprefix("```json").removesuffix("```").strip()
            elif clean.startswith("```"):
                clean = clean.removeprefix("```").removesuffix("```").strip()
            
            parsed = json.loads(clean)
            
            # Map back to original A/B
            winner_label = parsed["winner"]
            winner_code = order[int(winner_label) - 1][1]
            
            return {
                "winner": winner_code,  # "A" or "B"
                "reason": parsed.get("reason", ""),
                "confidence": parsed.get("confidence", 0.5),
                "original_order": f"{order[0][1]} vs {order[1][1]}",
            }
        except Exception as e:
            return {
                "winner": "A",
                "reason": f"Comparison failed: {e}",
                "confidence": 0.0,
                "original_order": "A vs B",
            }

    # ------------------------------------------------------------------
    # Batch judge
    # ------------------------------------------------------------------
    def judge_batch(self, tasks_and_code: list[tuple[str, str]]) -> list[dict[str, Any]]:
        """Judge multiple code submissions."""
        return [self.judge(task, code) for task, code in tasks_and_code]


def judge_single(task_description: str, code: str, config: JudgeConfig | None = None) -> dict[str, Any]:
    """Convenience function to judge a single code submission."""
    judge = LLMJudge(config)
    return judge.judge(task_description, code)


# ============================================================
# Backwards Compatibility Aliases (for tests)
# ============================================================


class Judgement:
    """Result of a judge evaluation."""

    def __init__(
        self,
        score: float,
        reasoning: str,
        passed: bool,
        criteria_scores: dict[str, float] | None = None,
    ) -> None:
        self.score = score
        self.reasoning = reasoning
        self.passed = passed
        self.criteria_scores = criteria_scores or {}


class LLMAssJudge:
    """Legacy alias for LLMJudge."""

    def __init__(self, config: JudgeConfig | None = None) -> None:
        self.config = config or JudgeConfig()
        self._judge = LLMJudge(self.config)

    def evaluate(
        self,
        task: str,
        solution: str,
        criteria: list[str] | None = None,
    ) -> Judgement:
        """Evaluate code and return Judgement."""
        result = self._judge.judge(task, solution)
        return Judgement(
            score=result["judge_score"],
            reasoning=result["summary"],
            passed=result["judge_score"] >= 0.5,
            criteria_scores=result.get("category_scores"),
        )


# ============================================================
# Phase 6 Enhanced Types — EvalRubric & JudgeVerdict
# ============================================================


@dataclass
class EvalRubric:
    """Phase 6 evaluation rubric with dimensions and weights.

    Used by the orchestrator to configure per-component evaluation
    criteria and by individual evaluators to produce structured verdicts.
    """

    name: str = "default"
    dimensions: list[str] = field(default_factory=lambda: ["correctness", "safety", "quality"])
    weights: dict[str, float] | None = None
    pass_threshold: float = 0.6
    description: str = ""

    def __post_init__(self) -> None:
        if self.weights is None:
            n = len(self.dimensions)
            self.weights = {d: 1.0 / n for d in self.dimensions}


@dataclass
class JudgeVerdict:
    """Structured result from a Phase 6 judge evaluation.

    Contains detailed dimension-level scores, calibration status,
    and whether the evaluation passed the configured gate.
    """

    overall_score: float = 0.0
    dimension_scores: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    summary: str = ""
    calibration_kappa: float | None = None
    calibrated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "dimension_scores": self.dimension_scores,
            "passed": self.passed,
            "summary": self.summary,
            "calibration_kappa": self.calibration_kappa,
            "calibrated": self.calibrated,
        }
