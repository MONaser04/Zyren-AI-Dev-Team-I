"""
LLM-as-Judge — Phase 5
=======================
Uses an LLM (critic role) to evaluate generated code across
multiple qualitative categories: correctness, code_quality,
documentation, error_handling.

Output is a normalised judge_score (0.0–1.0) and detailed
category scores fed into CompositeScorer.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.gateway.llm_client import LLMClient as LiteLLMClient


class LLMJudge:
    """LLM-based code quality judge."""

    CATEGORIES = [
        "correctness",
        "code_quality",
        "documentation",
        "error_handling",
    ]

    JUDGE_PROMPT = """You are a code-review judge. Evaluate the following code on these categories
with scores from 1 (worst) to 10 (best).

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
{code}
"""

    def __init__(
        self,
        model: str = "critic",
        max_tokens: int = 2048,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.client = LiteLLMClient()

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
        """
        prompt = self.JUDGE_PROMPT.format(
            task_description=task_description, code=code
        )

        try:
            response = self.client.send(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=0.0,
            )
        except Exception as exc:
            return self._fallback(error=str(exc))

        parsed = self._parse_response(response)
        return parsed

    # ------------------------------------------------------------------
    # Parse LLM response
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_response(
        raw: str,
    ) -> dict[str, Any]:
        """Extract JSON from LLM output (handles markdown wrapping)."""
        clean = raw.strip()

        # Strip markdown code fences if present
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
                    return LLMJudge._fallback(error=f"JSON parse failed: {raw[:200]}")
            else:
                return LLMJudge._fallback(error=f"JSON parse failed: {raw[:200]}")

        # Extract category scores, normalise to 0–1
        scores: dict[str, float] = {}
        for cat in LLMJudge.CATEGORIES:
            raw_val = parsed.get(cat, 5)  # Default 5 if missing
            try:
                scores[cat] = max(0.0, min(1.0, float(raw_val) / 10.0))
            except (ValueError, TypeError):
                scores[cat] = 0.5

        # Overall judge_score = mean of categories
        judge_score = sum(scores.values()) / len(scores)

        return {
            "judge_score": round(judge_score, 4),
            "category_scores": scores,
            "summary": parsed.get("summary", "No summary provided."),
            "raw_response": raw,
        }

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------
    @staticmethod
    def _fallback(
        error: str = "Judge unavailable",
    ) -> dict[str, Any]:
        """Return neutral scores when judge fails."""
        return {
            "judge_score": 0.5,
            "category_scores": {c: 0.5 for c in LLMJudge.CATEGORIES},
            "summary": f"Judge error: {error}",
            "raw_response": "",
        }

    # ------------------------------------------------------------------
    # Batch judge
    # ------------------------------------------------------------------
    def judge_batch(
        self, tasks_and_code: list[tuple[str, str]]
    ) -> list[dict[str, Any]]:
        """Judge multiple code submissions."""
        return [self.judge(task, code) for task, code in tasks_and_code]


def judge_single(task_description: str, code: str) -> dict[str, Any]:
    """Convenience function to judge a single code submission."""
    judge = LLMJudge()
    return judge.judge(task_description, code)


# ============================================================
# Backwards Compatibility Aliases (for tests)
# ============================================================


class JudgeConfig:
    """Configuration for the judge."""

    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        rubric: str = "Evaluate code quality",
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.rubric = rubric


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
        self._judge = LLMJudge(model=self.config.model)

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
