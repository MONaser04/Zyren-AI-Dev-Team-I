#!/usr/bin/env python3
"""
Phase 5 Supervisor Launcher
============================
Production entry point for running the AI Dev Team Supervisor.

This script launches the closed-loop self-improvement cycle:
  Evaluate → Analyse → Tune → Re-evaluate → Converge

Usage:
    python run_supervisor.py                    # Run with default config
    python run_supervisor.py --config config/phase5.yaml --rounds 10 --budget 50.0
    python run_supervisor.py --dry-run          # Simulated run (no LLM calls)
    python run_supervisor.py --live             # Real LLM calls (requires API keys)
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
src_path = PROJECT_ROOT / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import minimal modules that don't trigger circular imports
from contracts.eval_result import EvalResult
from contracts.optim_report import OptimReport, RoundReport
from optim.feedback_store import FeedbackStore

# ── Logging ────────────────────────────────────────────────────────────────────


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)


# ── Local Base Classes (to avoid circular imports) ─────────────────────────────


class BaseAgent:
    """Minimal base agent for testing."""

    role: str = "base"

    def __init__(self) -> None:
        pass


class AgentResult:
    """Simple result container."""

    def __init__(self, verdict: str, data: dict, summary: str) -> None:
        self.verdict = verdict
        self.data = data
        self.summary = summary


# ── Dry-Run Runner ─────────────────────────────────────────────────────────────


class DryRunWorkflowRunner:
    """Simulates WorkflowRunner with fake results for testing without API calls.

    Useful for CI, demos, or testing the Supervisor logic without spending
    on LLM API calls.
    """

    def __init__(self, base_score: float = 0.72, jitter: float = 0.08, improve_per_call: float = 0.015):
        self.base_score = base_score
        self.jitter = jitter
        self.improve_per_call = improve_per_call
        self.call_count = 0

    def run(self, *, task_prompt: str = "", workflow_id: str = "", max_iterations: int = 5, **kwargs):
        """Return a fake AgentResult-like dict."""
        self.call_count += 1
        # Gradual improvement simulation
        score = min(0.99, self.base_score + self.call_count * self.improve_per_call + random.uniform(-self.jitter, self.jitter))
        passed = score >= 0.60
        issues = [] if passed else ["Simulated failure: test assertion error"]

        return type("DryRunResult", (), {
            "verdict": "pass" if passed else "fail",
            "score": score,
            "data": {
                "passed": passed,
                "overall_score": score,
                "test_pass_rate": random.uniform(0.7, 1.0) if passed else random.uniform(0.3, 0.6),
                "lint_score": random.uniform(0.85, 1.0),
                "type_check_passed": random.choice([True, True, True, False]),
                "security_issues_count": random.randint(0, 1),
                "iterations_taken": random.randint(1, max_iterations),
                "total_cost_usd": random.uniform(0.02, 0.12),
                "issues": issues,
            },
            "issues": issues,
        })()


# ── Supervisor (Minimal Implementation) ────────────────────────────────────────


class MinimalSupervisor(BaseAgent):
    """Minimal Supervisor that runs the Phase 5 loop without full imports."""

    role: str = "supervisor"

    def __init__(
        self,
        *,
        config_path: str = "config/phase5.yaml",
        runner: DryRunWorkflowRunner | None = None,
    ) -> None:
        super().__init__()
        import yaml
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as fh:
                self.config = yaml.safe_load(fh) or {}
        else:
            self.config = {}

        self.config_path = config_path
        self.sup_cfg = self.config.get("supervisor", {})
        self.eval_cfg = self.config.get("evaluations", {})
        self.rpt_cfg = self.config.get("reporting", {})
        self.fb_cfg = self.config.get("feedback", {})

        self.runner = runner or DryRunWorkflowRunner()
        self.store = FeedbackStore(self.fb_cfg.get("db_path", "optim/feedback.db"))

        self.session_budget = float(self.sup_cfg.get("session_budget_usd", 20.00))
        self.cost_spent = 0.0

    def run(self, *, task_prompt: str = "", workflow_id: str = "", **kwargs: dict) -> AgentResult:
        """Run the full closed-loop optimisation session."""
        session_id = workflow_id or f"supervisor-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc).isoformat()

        self.logger = logging.getLogger("phase5_supervisor")
        self.logger.info("=" * 70)
        self.logger.info("🤖  AI Dev Team Supervisor — Phase 5")
        self.logger.info("    Closed-Loop Self-Improvement: Evaluate → Analyse → Tune → Converge")
        self.logger.info("=" * 70)
        self.logger.info("Config file : %s", self.config_path)
        self.logger.info("Output dir  : %s", self.rpt_cfg.get("output_dir", "reports/"))
        self.logger.info("Session ID  : %s", session_id)
        self.logger.info("-" * 70)

        report = OptimReport(supervisor_id=session_id, status="running", started_at=started_at)

        try:
            tasks = self._load_golden_tasks()
            max_rounds = int(self.sup_cfg.get("max_rounds", 5))
            previous_best_score = 0.0
            patience_counter = 0

            for round_num in range(1, max_rounds + 1):
                self.logger.info("\n🔁 Round %d / %d — evaluating...", round_num, max_rounds)

                round_report = self._run_single_round(
                    round_num, tasks, session_id, previous_best_score, patience_counter, **kwargs
                )

                report.add_round(round_report)
                self.cost_spent += round_report.total_cost_usd

                if round_report.mean_score > previous_best_score:
                    previous_best_score = round_report.mean_score

                if self.cost_spent >= self.session_budget:
                    self.logger.warning("💸 Session budget exceeded ($%.2f / $%.2f).", self.cost_spent, self.session_budget)
                    report.finalize("budget_exceeded")
                    break

                if round_report.converged:
                    self.logger.info("✅ Convergence detected at round %d.", round_num)
                    report.finalize("converged")
                    break
            else:
                report.finalize("completed")

        except Exception as exc:
            self.logger.exception("Supervisor session failed: %s", exc)
            report.errors.append(str(exc))
            report.finalize("error")

        # Write Reports
        formats = self.rpt_cfg.get("formats", ["json", "markdown"])
        output_dir = self.rpt_cfg.get("output_dir", "reports/")
        self._write_reports(report, output_dir, formats)

        self.logger.info("📄 Reports written: %s", output_dir)
        self.logger.info("🏁 Session '%s' finished — status: %s, best score: %.4f",
                         session_id, report.status, report.best_score)

        return AgentResult(
            verdict="completed" if report.status in ("completed", "converged") else report.status,
            data=report.to_dict(),
            summary=f"Supervisor session {session_id}: {report.status}, "
                     f"{len(report.rounds)} rounds, best score {report.best_score:.4f}, "
                     f"cost ${self.cost_spent:.6f}",
        )

    def _load_golden_tasks(self) -> list[dict]:
        """Load golden evaluation tasks from YAML or return built-in defaults."""
        import yaml
        tasks_file = self.eval_cfg.get("golden", {}).get("tasks_file")
        default_count = self.sup_cfg.get("eval_instances_per_round", 5)

        if tasks_file:
            path = Path(tasks_file)
            if path.exists():
                with open(path, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                    return data.get("tasks", []) if isinstance(data, dict) else []

        return [
            {"id": "g0", "prompt": "Write a function `fibonacci(n: int) -> int` that returns the n-th Fibonacci number iteratively."},
            {"id": "g1", "prompt": "Write a function `is_palindrome(s: str) -> bool` ignoring case and punctuation."},
            {"id": "g2", "prompt": "Implement a `Stack[T]` generic class with push, pop, peek, is_empty."},
            {"id": "g3", "prompt": "Create FastAPI app with POST /users and GET /users/{id} with in-memory dict."},
            {"id": "g4", "prompt": "Write `fetch_json(url: str) -> dict` with error handling for connection/HTTP errors."},
        ][:default_count]

    def _run_single_round(
        self,
        round_num: int,
        tasks: list[dict],
        session_id: str,
        previous_best_score: float,
        patience_counter: int,
        **kwargs: dict,
    ) -> RoundReport:
        """Execute one full round: evaluate → analyse → optimise → check convergence."""
        round_start = datetime.now(timezone.utc).isoformat()
        round_report = RoundReport(round_num=round_num, started_at=round_start)

        # Step 1: EVALUATE
        eval_results: list[EvalResult] = []
        sample_tasks = tasks[: int(self.sup_cfg.get("eval_instances_per_round", 5))]

        for task in sample_tasks:
            task_id = task.get("id", f"task-{uuid.uuid4().hex[:6]}")
            prompt = task.get("prompt", "")
            wf_id = f"{session_id}-r{round_num}-{task_id}"
            self.logger.info("  📋 Evaluating task '%s': %s...", task_id, prompt[:60])

            try:
                wf_result = self.runner.run(
                    task_prompt=prompt,
                    workflow_id=wf_id,
                    max_iterations=int(self.sup_cfg.get("max_workflow_iterations", 5)),
                )

                er = self._build_eval_result(wf_id, task_id, wf_result)
                eval_results.append(er)
                self.cost_spent += er.total_cost_usd
                self._persist_feedback(wf_id, wf_result)
            except Exception as exc:
                self.logger.warning("  ❌ Task '%s' failed: %s", task_id, exc)
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

        self.logger.info("  📊 Round %d mean score: %.4f | cost: $%.6f",
                         round_num, round_report.mean_score, round_report.total_cost_usd)

        # Step 2: ANALYSE (simplified)
        pass_count = sum(1 for r in eval_results if r.passed)
        self.logger.info("  🔍 Analysis: pass_rate=%.2f | total=%d", pass_count / max(1, len(eval_results)), len(eval_results))

        # Step 3: OPTIMISE - Model routing
        if self.sup_cfg.get("enable_model_switching", True):
            from optim.model_optimiser import optimise_model_routing
            model_changes = optimise_model_routing(
                eval_results=eval_results,
                feedback_store=self.store,
                min_success_rate=float(self.config.get("optimisation", {}).get("model_optimiser", {}).get("min_success_rate", 0.6)),
            )
            round_report.model_changes = model_changes
            for mc in model_changes:
                if mc.get("action") != "keep":
                    self.logger.info("  🔄 Model '%s' → %s: %s", mc.get("model"), mc.get("action"), mc.get("reason"))

        # Step 4: CONVERGENCE CHECK
        if self.sup_cfg.get("enable_convergence", True):
            from optim.convergence import ConvergenceConfig, check_convergence
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
            self.logger.info("  ⏱️ Convergence: %s (improvement=%.4f, patience=%d)",
                             conv_result.trend,
                             conv_result.improvement,
                             conv_result.patience_counter)
        else:
            round_report.converged = False

        round_report.finished_at = datetime.now(timezone.utc).isoformat()
        return round_report

    def _build_eval_result(self, workflow_id: str, task_id: str, wf_result) -> EvalResult:
        """Build an EvalResult from a WorkflowRunner result."""
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

    def _persist_feedback(self, workflow_id: str, wf_result) -> None:
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

    def _write_reports(
        self,
        report: OptimReport,
        output_dir: str,
        formats: list[str],
    ) -> None:
        """Write report files to disk."""
        import json
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        session_id = report.supervisor_id.replace(" ", "_").replace(":", "-")
        base_name = f"phase5_report_{session_id}"

        if "json" in formats:
            json_file = output_path / f"{base_name}.json"
            json_file.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            self.logger.info("JSON report written: %s", json_file)

        if "markdown" in formats:
            md_file = output_path / f"{base_name}.md"
            md_content = self._generate_markdown_report(report)
            md_file.write_text(md_content, encoding="utf-8")
            self.logger.info("Markdown report written: %s", md_file)

    def _generate_markdown_report(self, report: OptimReport) -> str:
        """Generate a simple markdown report."""
        lines = [
            f"# 🔄 AI Dev Team — Optimisation Report\n",
            f"\n**Session ID**: `{report.supervisor_id}`\n",
            f"**Status**: `{report.status}`\n",
            f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n",
            f"---\n",
            f"## 📊 Summary\n",
            f"| Metric | Value |\n",
            f"|--------|-------|\n",
            f"| Total Rounds | {len(report.rounds)} |\n",
            f"| Best Score | **{report.best_score:.4f}** |\n",
            f"| Best Round | #{report.best_round} |\n",
            f"| Total Cost (USD) | `${report.total_cost_usd:.6f}` |\n",
            f"| Total Evaluations | {report.total_evaluations} |\n",
            f"| Total Prompt Tunings | {report.total_tunings} |\n",
            f"| Started At | {report.started_at} |\n",
            f"| Finished At | {report.finished_at or 'In progress'} |\n",
            f"\n---\n",
            f"## 📈 Round-by-Round Breakdown\n",
        ]
        for rnd in report.rounds:
            icon = "✅" if rnd.converged else "⚙️"
            lines.append(f"### Round #{rnd.round_num} {icon}\n")
            lines.append(f"| Metric | Value |\n")
            lines.append(f"|--------|-------|\n")
            lines.append(f"| Mean Score | {rnd.mean_score:.4f} |\n")
            lines.append(f"| Median Score | {rnd.median_score:.4f} |\n")
            lines.append(f"| Total Cost | ${rnd.total_cost_usd:.6f} |\n")
            lines.append(f"| Evaluations | {len(rnd.eval_results)} |\n")
            lines.append(f"| Converged | {'Yes' if rnd.converged else 'No'} |\n")
            lines.append(f"\n")

        lines.append(f"## 🎯 Recommendations\n")
        if report.errors:
            lines.append(f"**Errors:**\n")
            for err in report.errors:
                lines.append(f"- {err}\n")
        else:
            lines.append(f"- Continue monitoring performance.\n")

        lines.append(f"\n---\n")
        lines.append(f"*Report auto-generated by AI Dev Team Supervisor (Phase 5)*\n")
        return "\n".join(lines)

if __name__ == '__main__':
    sup = MinimalSupervisor()
    res = sup.run()
    print(res.summary)
