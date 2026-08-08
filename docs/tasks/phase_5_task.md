# Phase 5 Implementation Tasks

## Overview
Closed-Loop Self-Improvement for Zyren — Supervisor orchestrates Evaluate → Analyse → Optimise → Converge cycle.

---

## Task List

### 1. Core Infrastructure

#### 1.1 Evaluation Scorer (`evals/scorer.py`)
- [x] `score_workflow_result()` — weighted composite scoring
- [x] `compute_round_score()` — mean, median, pass_rate from EvalResults
- [x] Default weights: test_pass_rate(0.30), lint_score(0.15), type_check(0.10), security(0.10), efficiency(0.10), base(0.25)
- [x] Handle both EvalResult objects and dicts

#### 1.2 Feedback Store (`optim/feedback_store.py`)
- [x] SQLite schema: feedback, tunings, model_stats tables with indexes
- [x] `FeedbackRecord` dataclass with to_dict()
- [x] CRUD: insert(), insert_batch(), query(), count_by_source(), count_by_severity()
- [x] Error pattern detection: get_error_patterns()
- [x] Tuning history: save_tuning(), get_tuning_history(), get_best_prompt()
- [x] Model stats: record_model_usage(), get_model_performance()
- [x] Maintenance: vacuum(), stats(), record_eval(), get_stats()

#### 1.3 Analyser (`optim/analyser.py`)
- [x] `analyse_round()` — process eval results + feedback store
- [x] Pass rate calculation
- [x] Weakness identification from error patterns
- [x] Recommendation generation

#### 1.4 Convergence Detection (`optim/convergence.py`)
- [x] `ConvergenceConfig` dataclass with all thresholds
- [x] `check_convergence()` — sliding window comparison
- [x] Patience tracking across rounds
- [x] Min score threshold enforcement
- [x] Returns `ConvergenceResult` with converged flag, trend, improvement, patience_counter

#### 1.5 Prompt Tuner (`optim/prompt_tuner.py`)
- [x] `AGENT_DEFAULTS` — base prompts for 5 agent roles
- [x] `generate_variants()` — LLM-based + template fallback
- [x] `evaluate_variants()` — scoring against round results
- [x] `tune_prompts()` — main entry point, returns `TuningResult` list
- [x] Persists to FeedbackStore

#### 1.6 Model Optimiser (`optim/model_optimiser.py`)
- [x] `MODEL_TIERS` — known models with tier (fast/smart) and costs
- [x] `optimise_model_routing()` — reviews per-model success rates
- [x] `recommend_best_model()` — suggests best in tier
- [x] Demotes/removes models below `min_success_rate`

#### 1.7 Reporter (`optim/reporter.py`)
- [x] `generate_json_report()` — full serialization
- [x] `generate_markdown_report()` — human-readable tables
- [x] `write_reports()` — writes both formats to disk

### 2. Contracts (`src/contracts/`)

#### 2.1 EvalResult (`eval_result.py`)
- [x] Dataclass with all evaluation fields
- [x] `to_dict()` / `from_dict()` for serialization

#### 2.2 OptimReport (`optim_report.py`)
- [x] `OptimReport`, `RoundReport`, `TuningResult` dataclasses
- [x] Properties: best_score, best_round, total_cost_usd, total_evaluations, total_tunings
- [x] `add_round()`, `finalize()`, `to_dict()`

### 3. Supervisor Agent (`src/agents/supervisor.py`)

#### 3.1 Configuration & Initialization
- [x] `load_phase5_config()` with defaults
- [x] `Supervisor` class inheriting `BaseAgent`
- [x] Budget tracking (session_budget, cost_spent)
- [x] FeedbackStore and WorkflowRunner injection

#### 3.2 Main Loop (`run()`)
- [x] Load golden tasks
- [x] Iterate rounds up to `max_rounds`
- [x] Per-round: evaluate → analyse → optimise → converge
- [x] Budget check after each round
- [x] Convergence check → early exit
- [x] Final status: completed/converged/budget_exceeded/error
- [x] Report generation via `reporter.write_reports()`

#### 3.3 Round Execution (`_run_single_round()`)
- [x] Sample golden tasks per `eval_instances_per_round`
- [x] Run each via WorkflowRunner
- [x] Build EvalResult from workflow output
- [x] Persist feedback
- [x] Compute aggregates (mean, median, cost)
- [x] Analyse + prompt tuning + model optimisation
- [x] Convergence check

#### 3.4 Helpers
- [x] `_load_golden_tasks()` — YAML or built-in defaults
- [x] `_build_eval_result()` — handles both dict and object workflow results
- [x] `_persist_feedback()` — stores issues as FeedbackRecords

### 4. Configuration & Data

#### 4.1 Config (`config/phase5.yaml`)
- [x] Complete YAML with all supervisor, evaluation, optimisation, feedback, reporting settings

#### 4.2 Golden Tasks (`evals/golden/tasks.yaml`)
- [x] 11 tasks: algorithmic, API, data structures, utilities, security

### 5. Launchers & Tests

#### 5.1 Production Launcher (`run_supervisor.py`)
- [x] `MinimalSupervisor` (avoids circular imports)
- [x] `DryRunWorkflowRunner` for testing without API calls
- [x] CLI: --dry-run, --live, --rounds, --budget, --config, --session-id
- [x] JSON + Markdown report output

#### 5.2 Integration Test (`test_run_phase5.py`)
- [x] Same MinimalSupervisor pattern
- [x] CLI: --dry-run, --live, --rounds, --tasks-per-round
- [x] Summary output + report listing

#### 5.3 Unit Tests (`tests/test_phase5_supervisor.py`)
- [x] TestEvalResult: roundtrip, defaults
- [x] TestOptimReport: best_score, to_dict, all statuses
- [x] TestFeedbackStore: record_eval, get_model_performance, stats, insert_raw
- [x] TestAnalyser: analyse_round, analyse_empty
- [x] TestConvergence: insufficient_samples, converged_high_score, min_score_not_met
- [x] TestModelOptimiser: optimise, recommend
- [x] TestPromptTuner: tune_prompts_returns_list, tuning_result_to_dict
- [x] TestScorer: compute_round_score, all_passed, all_failed
- [x] TestReporter: json_output, markdown_output

---

## Verification Checklist

### All Tests Pass
```bash
python -m pytest tests/test_phase5_supervisor.py -v
# 23 passed
```

### Dry-Run Execution Works
```bash
python run_supervisor.py --dry-run --rounds 2
# Creates reports/phase5_report_<id>.json and .md
# Status: converged after 5 rounds
# Best score: ~0.91
```

### Reports Generated
- [x] JSON report with full session data
- [x] Markdown report with tables and recommendations

### Convergence Detected
- [x] Sliding window comparison works
- [x] Patience counter increments correctly
- [x] Early exit on convergence

### Budget Tracking
- [x] Per-round cost accumulation
- [x] Session budget enforcement
- [x] Cost reported in summary

---

## Remaining Documentation Tasks

- [ ] `docs/phases/phase5.md` — Technical documentation (✓ Done)
- [ ] `docs/tasks/phase5-tasks.md` — This file (✓ Done)
- [ ] `docs/walkthrough/phase5-walkthrough.md` — User guide
- [ ] Update `README.md` with Phase 5 section

---

## Dependencies

### Required Packages
- `pyyaml` — config loading
- `sqlite3` (stdlib) — feedback store
- `dataclasses` (stdlib) — contracts

### Optional (for live mode)
- `litellm` — via gateway
- API keys in environment

---

## Integration Points

| Component | Used By |
|-----------|---------|
| WorkflowRunner (Phase 3) | Supervisor.run() |
| Agents (Phase 1-2) | Prompt tuning targets |
| Gateway (Phase 3) | Model routing optimisation |
| Observability (Phase 4) | Traces/metrics per round |
| Policy Engine (Phase 3) | Cost caps, constraints |

---

## Notes

- Circular import avoidance: launchers use `MinimalSupervisor` + local base classes
- Dry-run mode enables CI/testing without API costs
- All costs in USD, tracked to 6 decimal places
- SQLite DB at `optim/feedback.db` persists across runs
- Reports in `reports/` with session ID timestamps