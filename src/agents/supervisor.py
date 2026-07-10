"""
Supervisor Agent — Phase 5 (Closed-Loop Self-Improvement)
===========================================================
Orchestrates the evaluation → analysis → tuning → re-evaluation loop.

The Supervisor:
  1. Runs evaluation workflows against Golden Set + SWE-bench
  2. Analyses results with the Feedback Analyser
  3. Triggers prompt tuning and model optimisation
  4. Checks convergence and decides whether to continue
  5. Produces a final OptimReport

Configuration is read from config/phase5.yaml (or equivalent dict).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from evals.scorer import compute_round_score
from optim.analyser import analyse_round
from optim.convergence import ConvergenceConfig, check_convergence
from optim.feedback_store import FeedbackStore
from optim.model_optimiser import optimise_model_routing
from optim.prompt_tuner import tune_prompts
from optim.reporter import write_reports
from src.agents.base import BaseAgent, AgentResult
from src.contracts.eval_result import EvalResult
from src.contracts.optim_report import OptimReport, RoundReport
from src.orchestrator.runner import WorkflowRunner  # Phase 4 enhanced runner

logger = logging.getLogger(__name__)

# ── Configuration Loading ──────────────────────────────────────────────────────


def load_phase5_config(path: str | Path = "config/phase5.yaml") -> dict[str, Any]:
    """Load Phase 5 YAML configuration."""
    config_path = Path(path)
    if not config_path.exists():
        logger.warning("Phase 5 config file %s not found — using defaults.", config_path)
        return _default_config()
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or _default_config()


def _default_config() -> dict[str, Any]:
    """Fallback configuration values."""
    return {
        "supervisor": {
            "max_rounds": 5,
            "eval_instances_per_round": 3,
            "max_workflow_iterations": 5,
            "cost_cap_per_workflow_usd": 0.50,
            "session_budget_usd": 10.00,
            "enable_prompt_tuning": True,
            "enable_model_switching": True,
            "enable_redteam_hardening": False,
            "enable_convergence": True,
            "convergence": {
                "min_samples": 3,
                "window_size": 3,
                "improvement_threshold": 0.02,
                "patience": 2,
                "min_score_threshold": 0.70,
            },
        },
        "evaluations": {
            "golden": {"enabled": True, "tasks_file": "evals/golden/tasks.yaml", "default_instances": 5},
            "swebench": {"enabled": False},
            "redteam": {"enabled": False},
        },
        "optimisation": {
            "prompt_tuner": {"strategy": "dspy", "variants_per_agent": 5, "max_llm_calls": 50, "metric": "weighted"},
            "model_optimiser": {"enabled": True, "min_success_rate": 0.6, "evaluation_interval": 3},
        },
        "feedback": {"db_path": "optim/feedback.db"},
        "reporting": {"output_dir": "reports/", "formats": ["json", "markdown"]},
        "hitl": {"enabled": False},
        "logging": {"level": "INFO"},
    }


# ── Golden Task Loader ─────────────────────────────────────────────────────────


def load_golden_tasks(tasks_file: str | None = None, default_count: int = 5) -> list[dict[str, Any]]:
    """Load golden evaluation tasks from YAML file or return built-in defaults."""
    if tasks_file:
        path = Path(tasks_file)
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
                return data.get("tasks", []) if isinstance(data, dict) else []

    # Built-in defaults
    return [
        {"id": "g0", "prompt": "Write a function `fibonacci(n: int) -> int` that returns the n-th Fibonacci number iteratively."},
        {"id": "g1", "prompt": "Write a function `is_palindrome(s: str) -> bool` ignoring case and punctuation."},
        {"id": "g2", "prompt": "Implement a `Stack[T]` generic class with push, pop, peek, is_empty."},
        {"id": "g3", "prompt": "Create FastAPI app with POST /users and GET /users/{id} with in-memory dict."},
        {"id": "g4", "prompt": "Write `fetch_json(url: str) -> dict` with error handling for connection/HTTP errors."},
    ][:default_count]


# ── Supervisor Class ───────────────────────────────────────────────────────────


class Supervisor(BaseAgent):
    """Phase 5 Supervisor — manages the closed-loop optimisation cycle.

    Workflow per round:
      1. EVALUATE  : Run golden tasks through the full AI Dev Team pipeline
      2. ANALYSE   : Analyse feedback, identify weaknesses
      3. OPTIMISE  : Tune prompts, switch models as needed
      4. CONVERGE  : Check if scores have plateaued
      5. CONTINUE / STOP

    On stop, produces a full OptimReport (JSON + Markdown).
    """

    role: str = "supervisor"

    def __init__(
        self,
        *,
        config_path: str | Path = "config/phase5.yaml",
        runner: WorkflowRunner | None = None,
        feedback_store: FeedbackStore | None = None,
    ) -> None:
        """Initialise the Supervisor.

        Args:
            config_path: Path to phase5.yaml.
            runner: Optional existing WorkflowRunner. Creates one if omitted.
            feedback_store: Optional existing FeedbackStore. Creates one if omitted.
        """
        super().__init__()
        self.config = load_phase5_config(config_path)
        self.sup_cfg = self.config.get("supervisor", {})
        self.eval_cfg = self.config.get("evaluations", {})
        self.optim_cfg = self.config.get("optimisation", {})
        self.rpt_cfg = self.config.get("reporting", {})
        self.fb_cfg = self.config.get("feedback", {})

        self.runner = runner or WorkflowRunner()
        self.store = feedback_store or FeedbackStore(self.fb_cfg.get("db_path", "optim/feedback.db"))

        # Budget tracking
        self.session_budget = float(self.sup_cfg.get("session_budget_usd", 20.00))
        self.cost_spent = 0.0

    # ── Agent Interface ────────────────────────────────────────────────────────

    def run(self, *, task_prompt: str = "", workflow_id: str = "", **kwargs: Any) -> AgentResult:
        """Entry point: run the full closed-loop optimisation session.

        Args:
            task_prompt: Unused (Supervisor uses golden tasks). Accepted for interface compatibility.
            workflow_id: Optional session identifier (auto-generated if empty).
            **kwargs: Passed through to evaluation and tuning calls.

        Returns:
            AgentResult containing the final OptimReport and status.
        """
        session_id = workflow_id or f"supervisor-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc).isoformat()

        logger.info("=" * 60)
        logger.info("🚀 Supervisor session '%s' starting...", session_id)
        logger.info("   Max rounds: %s | Eval/round: %s | Budget: $%.2f",
                     self.sup_cfg.get("max_rounds"),
                     self.sup_cfg.get("eval_instances_per_round"),
                     self.session_budget)
        logger.info("=" * 60)

        report = OptimReport(supervisor_id=session_id, status="running", started_at=started_at)

        try:
            # Load golden tasks
            tasks = load_golden_tasks(
                self.eval_cfg.get("golden", {}).get("tasks_file"),
                self.sup_cfg.get("eval_instances_per_round", 5),
            )

            max_rounds = int(self.sup_cfg.get("max_rounds", 10))
            previous_best_score = 0.0
            patience_counter = 0

            for round_num in range(1, max_rounds + 1):
                logger.info("\n🔁 Round %d / %d — evaluating...", round_num, max_rounds)

                round_report = self._run_single_round(
                    round_num, tasks, session_id, previous_best_score, patience_counter, **kwargs
                )

                report.add_round(round_report)

                # Update state
                self.cost_spent += round_report.total_cost_usd
                if round_report.mean_score > previous_best_score:
                    previous_best_score = round_report.mean_score

                # Budget check
                if self.cost_spent >= self.session_budget:
                    logger.warning("💸 Session budget exceeded ($%.2f / $%.2f).", self.cost_spent, self.session_budget)
                    report.finalize("budget_exceeded")
                    break

                # Convergence check
                if round_report.converged:
                    logger.info("✅ Convergence detected at round %d.", round_num)
                    report.finalize("converged")
                    break

            else:
                # Completed all rounds without convergence
                report.finalize("completed")

        except Exception as exc:
            logger.exception("Supervisor session failed: %s", exc)
            report.errors.append(str(exc))
            report.finalize("error")

        # ── Write Reports ───────────────────────────────────────────────────────
        formats = self.rpt_cfg.get("formats", ["json", "markdown"])
        output_dir = self.rpt_cfg.get("output_dir", "reports/")
        written = write_reports(report, output_dir, formats=formats)

        logger.info("📄 Reports written: %s", written)
        logger.info("🏁 Session '%s' finished — status: %s, best score: %.4f",
                     session_id, report.status, report.best_score)

        return AgentResult(
            verdict="completed" if report.status in ("completed", "converged") else report.status,
            data=report.to_dict(),
            summary=f"Supervisor session {session_id}: {report.status}, "
                     f"{len(report.rounds)} rounds, best score {report.best_score:.4f}, "
                     f"cost ${self.cost_spent:.6f}",
        )

    # ── Single Round ────────────────────────────────────────────────────────────

    def _run_single_round(
        self,
        round_num: int,
        tasks: list[dict[str, Any]],
        session_id: str,
        previous_best_score: float,
        patience_counter: int,
        **kwargs: Any,
    ) -> RoundReport:
        """Execute one full round: evaluate → analyse → optimise → check convergence."""
        round_start = datetime.now(timezone.utc).isoformat()
        round_report = RoundReport(round_num=round_num, started_at=round_start)

        # ── Step 1: EVALUATE ────────────────────────────────────────────────────
        eval_results: list[EvalResult] = []
        sample_tasks = tasks[: int(self.sup_cfg.get("eval_instances_per_round", 5))]

        for task in sample_tasks:
            task_id = task.get("id", f"task-{uuid.uuid4().hex[:6]}")
            prompt = task.get("prompt", "")
            wf_id = f"{session_id}-r{round_num}-{task_id}"
            logger.info("  📋 Evaluating task '%s': %s...", task_id, prompt[:60])

            try:
                wf_result = self.runner.run(
                    task_prompt=prompt,
                    workflow_id=wf_id,
                    max_iterations=int(self.sup_cfg.get("max_workflow_iterations", 5)),
                )

                # Build EvalResult from workflow result
                er = self._build_eval_result(wf_id, task_id, wf_result)
                eval_results.append(er)
                self.cost_spent += er.total_cost_usd

                # Store feedback records
                self._persist_feedback(wf_id, wf_result)
            except Exception as exc:
                logger.warning("  ❌ Task '%s' failed: %s", task_id, exc)
                eval_results.append(
                    EvalResult(
                        workflow_id=wf_id,
                        task_id=task_id,
                        passed=False,
                        overall_score=0.0,
                        issues=[str(exc)],
                    )
                )

        round_report.eval_results = [r.to_dict() for r in eval_results]

        # Compute round aggregate score
        round_scores = [r.overall_score for r in eval_results]
        round_report.mean_score = round(sum(round_scores) / max(1, len(round_scores)), 4)
        sorted_scores = sorted(round_scores)
        mid = len(sorted_scores) // 2
        round_report.median_score = round(
            sorted_scores[mid] if len(sorted_scores) % 2 else
            (sorted_scores[mid - 1] + sorted_scores[mid]) / 2, 4
        ) if sorted_scores else 0.0
        round_report.total_cost_usd = sum(r.total_cost_usd for r in eval_results)

        logger.info("  📊 Round %d mean score: %.4f | cost: $%.6f",
                     round_num, round_report.mean_score, round_report.total_cost_usd)

        # ── Step 2: ANALYSE ─────────────────────────────────────────────────────
        analysis = analyse_round(eval_results, feedback_store=self.store)
        logger.info("  🔍 Analysis: pass_rate=%.2f | weaknesses=%d | recommendations=%d",
                     analysis["summary"].get("pass_rate", 0),
                     len(analysis.get("weaknesses", [])),
                     len(analysis.get("recommendations", [])))

        # ── Step 3: OPTIMISE ────────────────────────────────────────────────────
        # 3a: Prompt Tuning
        if self.sup_cfg.get("enable_prompt_tuning", True):
            tuning_results = tune_prompts(
                eval_results=eval_results,
                n_variants=int(self.optim_cfg.get("prompt_tuner", {}).get("variants_per_agent", 5)),
                feedback_store=self.store,
            )
            round_report.tuning_results = [tr.to_dict() for tr in tuning_results]
            for tr in tuning_results:
                logger.info("  🎯 Tuned '%s': best_score=%.4f", tr.agent, tr.best_score)

        # 3b: Model Routing Optimisation
        if self.sup_cfg.get("enable_model_switching", True):
            model_changes = optimise_model_routing(
                eval_results=eval_results,
                feedback_store=self.store,
                min_success_rate=float(self.optim_cfg.get("model_optimiser", {}).get("min_success_rate", 0.6)),
            )
            round_report.model_changes = model_changes
            for mc in model_changes:
                if mc.get("action") != "keep":
                    logger.info("  🔄 Model '%s' → %s: %s", mc.get("model"), mc.get("action"), mc.get("reason"))

        # ── Step 4: CONVERGENCE CHECK ────────────────────────────────────────────
        if self.sup_cfg.get("enable_convergence", True):
            conv_cfg = ConvergenceConfig(
                min_samples=int(self.sup_cfg.get("convergence", {}).get("min_samples", 3)),
                window_size=int(self.sup_cfg.get("convergence", {}).get("window_size", 3)),
                improvement_threshold=float(self.sup_cfg.get("convergence", {}).get("improvement_threshold", 0.02)),
                patience=int(self.sup_cfg.get("convergence", {}).get("patience", 2)),
                min_score=float(self.sup_cfg.get("convergence", {}).get("min_score_threshold", 0.7)),
                max_rounds=int(self.sup_cfg.get("max_rounds", 10)),
            )
            conv_result = check_convergence(
                eval_results,
                conv_cfg,
                previous_best_score=previous_best_score,
                patience_counter=patience_counter,
                current_round=round_num,
            )
            round_report.converged = conv_result.converged
            logger.info("  ⏱️ Convergence: %s (improvement=%.4f, patience=%d)",
                         conv_result.trend,
                         conv_result.improvement,
                         conv_result.patience_counter)
        else:
            round_report.converged = False

        round_report.finished_at = datetime.now(timezone.utc).isoformat()
        return round_report

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _build_eval_result(
        self,
        workflow_id: str,
        task_id: str,
        wf_result: Any,
    ) -> EvalResult:
        """Build an EvalResult from a WorkflowRunner result."""
        # WorkflowRunner returns an AgentResult or dict
        data = wf_result
        if hasattr(data, "data"):
            data = data.data
        if isinstance(data, dict):
            return EvalResult(
                workflow_id=workflow_id,
                task_id=task_id,
                passed=data.get("passed", data.get("verdict") == "pass"),
                overall_score=data.get("overall_score", data.get("score", 0.0)),
                test_pass_rate=data.get("test_pass_rate", 1.0),
                lint_score=data.get("lint_score", 1.0),
                type_check_passed=data.get("type_check_passed", True),
                security_issues_count=data.get("security_issues_count", 0),
                iterations_taken=data.get("iterations_taken", 1),
                total_cost_usd=data.get("total_cost_usd", 0.0),
                issues=data.get("issues", []),
            )
        return EvalResult(
            workflow_id=workflow_id,
            task_id=task_id,
            passed=getattr(wf_result, "verdict", "pass") == "pass",
            overall_score=getattr(wf_result, "score", 0.0),
            issues=getattr(wf_result, "issues", []),
        )

    def _persist_feedback(
        self,
        workflow_id: str,
        wf_result: Any,
    ) -> None:
        """Persist feedback items from a workflow result into the FeedbackStore."""
        data = wf_result
        if hasattr(data, "data"):
            data = data.data
        if isinstance(data, dict):
            items = data.get("issues", [])
            for item in items:
                try:
                    from optim.feedback_store import FeedbackRecord

                    self.store.insert(
                        FeedbackRecord(
                            workflow_id=workflow_id,
                            source="workflow",
                            severity="error" if "error" in str(item).lower() else "warning",
                            message=str(item)[:500],
                        )
                    )
                except Exception:
                    pass
