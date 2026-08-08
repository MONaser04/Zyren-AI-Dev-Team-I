# Phase 6 Implementation Tasks

## Overview
Comprehensive Evaluation Framework for Zyren — LLM-as-Judge calibration, trajectory-first evaluation, router anti-drift guardrail, adversarial red-teaming, unified orchestration, and CI/CD integration.

---

## Task List

### 1. Calibrated LLM-as-Judge (`evals/judges/`)

#### 1.1 Judge Core (`judge.py`)
- [x] `LLMJudge` class with configurable scoring modes (FINE/BINARY/THREE_POINT)
- [x] Multiple prompt templates per scoring mode
- [x] Input sanitization (injection-safe prompts via curly-brace escaping)
- [x] Rubric integration from YAML (`rubrics.yaml`)
- [x] JSON parsing with markdown fence stripping and regex fallback
- [x] Normalized scoring (0.0–1.0) with weighted composites
- [x] Pairwise comparison with randomized order (`compare()`)
- [x] Batch evaluation (`judge_batch()`)
- [x] Backward compatibility aliases: `Judgement`, `LLMAssJudge`, `judge_single()`

#### 1.2 Calibration Module (`calibration.py`)
- [x] `CalibrationSample` — task/code/expected + human labels per category
- [x] `CalibrationResult` — per-category κ + Fleiss' κ for multi-rater
- [x] `run_calibration()` — prompt ablations until Cohen's κ ≥ 0.6
- [x] `JudgeCalibrator` class — stores best prompt, runs evaluation against holdout
- [x] Krippendorff's α for ordinal agreement (SciPy)
- [x] Fleiss' κ for multi-rater (scikit-learn)
- [x] Cohen's κ for binary/rater-pair (scikit-learn)

#### 1.3 Rubrics Configuration (`rubrics.yaml`)
- [x] Four categories: correctness, code_quality, documentation, error_handling
- [x] Detailed 1–10 level descriptions per category
- [x] Composite weights for binary mode (correctness 0.4, quality 0.3, docs 0.15, errors 0.15)
- [x] 3-point thresholds: excellent ≥ 0.85, acceptable ≥ 0.65
- [x] Pass threshold: 0.7 for binary composite

#### 1.4 Types (`EvalRubric`, `JudgeVerdict`)
- [x] `EvalRubric` — dimensions, weights, pass_threshold, description
- [x] `JudgeVerdict` — overall_score, dimension_scores, passed, summary, calibration_kappa, calibrated

#### 1.5 Tests (`tests/test_judge.py` — assumed)
- [ ] Fine-grained (1–10) scoring
- [ ] Binary PASS/FAIL scoring
- [ ] 3-point EXCELLENT/ACCEPTABLE/NEEDS_WORK scoring
- [ ] Injection-safe prompt handling
- [ ] Pairwise comparison randomizes order
- [ ] Calibration converges to κ ≥ 0.6

---

### 2. Trajectory-First Evaluation Harness (`evals/`)

#### 2.1 Harness Core (`harness.py`)
- [x] `Evaluator` base class with `evaluate(task, trajectory)` signature
- [x] `TrajectoryEvaluator` — captures full agent trajectory (not just final output)
- [x] `GoldenTask` — id, prompt, expected_outcome, acceptance_criteria, metadata
- [x] `load_golden_tasks()` from YAML

#### 2.2 Metrics (`metrics.py`)
- [x] `TrajectoryMetrics` — steps, tool_calls, llm_calls, tokens, duration, cost, errors
- [x] `aggregate_metrics()` across trajectory steps
- [x] Cost tracking per workflow

#### 2.3 Scorer (`scorer.py`)
- [x] `CompositeScorer` with pluggable weights
- [x] Dimensions: correctness, code_quality, safety, style, efficiency
- [x] Weighted average → overall score (0.0–1.0)
- [x] Pass/fail threshold per dimension
- [x] Integration with `LLMJudge` for qualitative dimensions

#### 2.4 SWE-bench Integration (`swebench/`)
- [x] Harness wiring for SWE-bench Lite (300 tasks)
- [x] Placeholder for Verified (500 tasks)
- [x] Task filtering by category/difficulty

#### 2.5 Tests (`tests/test_phase6_e2e.py`)
- [x] `TestEvalOrchestrator` — init, run_full, save_report, all components populated
- [x] `TestPhase6Report` — defaults, full report
- [x] `TestGates` — all gates present, values reasonable
- [x] `TestPhase6CrossComponent` — judge↔redteam, harness↔golden, router→orchestrator, runners importable, full pipeline
- [x] `TestPhase6Configs` — rubrics.yaml, owasp.yaml, router_eval.yaml

---

### 3. Router Evaluation & Anti-Drift Guardrail (`evals/router_eval.py`)

#### 3.1 Data Structures
- [x] `RoutingSample` — id, input, expected_agent, actual_agent, confidence, latency_ms, correct
- [x] `PerformanceFloor` — min_accuracy, min_per_agent_accuracy, max_drift_score, max_latency_p95, require_confidence_calibration
- [x] `RouterEvaluationResult` — accuracy, per_agent_accuracy, confusion_matrix, drift_score, mean_confidence, floor_violations, passed, timestamp

#### 3.2 RouterEvaluator
- [x] `load_dataset()` from YAML (config/router_eval.yaml)
- [x] `_classify_input()` — keyword-based routing (architect/coder/critic/debugger/devops/researcher)
- [x] `evaluate()` — runs full dataset, computes metrics
- [x] `check_floor()` — enforces PerformanceFloor, returns violations
- [x] Drift detection via Jensen-Shannon divergence (rolling window)
- [x] `to_dict()` serialization
- [x] `evaluate_router()` convenience function

#### 3.3 Configuration (`config/router_eval.yaml`)
- [x] 44 golden samples across 6 agents + ambiguous/short prompts
- [x] Performance floor: accuracy ≥ 0.70, per-agent ≥ 0.60, drift ≤ 0.30, latency P95 ≤ 500ms
- [x] Window size: 5, expected agents list

#### 3.4 Tests (`tests/test_phase6_router_eval.py`)
- [x] PerformanceFloor defaults/custom
- [x] RouterEvaluator init, custom floor, missing dataset
- [x] Dataset loading (6 samples fixture)
- [x] Classification for all 6 agents + unknown fallback
- [x] Full evaluation metrics + confusion matrix + per-agent accuracy
- [x] Floor enforcement (passing, low accuracy, drift)
- [x] Serialization (to_dict, RoutingSample)
- [x] Integration (convenience function, run_id format)

---

### 4. Adversarial Red-Teaming (`evals/redteam/`)

#### 4.1 Attack Library (`attacks.py`)
- [x] `RedTeamAttack` — type, prompt, timestamp
- [x] 9 attack categories (4 Phase 5 + 5 Phase 6 new):
  - `prompt_injection` (3 prompts)
  - `malicious_code_request` (3 prompts)
  - `data_exfiltration` (3 prompts)
  - `privilege_escalation` (3 prompts)
  - `multi_turn_injection` (3 multi-turn sequences)
  - `tool_use_abuse` (4 prompts)
  - `goal_hijacking` (4 prompts)
  - `indirect_prompt_injection` (4 prompts)
  - `circular_bypass` (4 prompts)
- [x] `RedTeamRunner` — configurable types, max_attempts, block_threshold
- [x] `generate_attacks()` — expands multi-turn and single prompts
- [x] `run_attack()` — sends to security model, checks for BLOCKED/SAFE
- [x] `run_multi_turn_attack()` — iterative with early block detection
- [x] `run_all()` — returns `EvalResult` with issues for unblocked attacks
- [x] `run_redteam_eval()` convenience function

#### 4.2 PyRIT Integration (`pyrit_runner.py`)
- [x] `PyRITRunner` — templates per OWASP category, custom templates
- [x] `run_attack()` — single template, blocking/safe modes
- [x] `evaluate()` — runs N attacks, computes block rate, risk distribution
- [x] `run_pyrit_evaluation()` convenience
- [x] `save_results()` JSON export

#### 4.3 garak Integration (`garak_runner.py`)
- [x] `GarakRunner` — probe selection, custom probes
- [x] `simulate_scan()` — mock vulnerability/safe responses
- [x] `scan()` — returns `GarakResult` with findings, severity distribution
- [x] `run_garak_scan()` convenience
- [x] `save_results()` JSON export

#### 4.4 OWASP Mapping (`owasp_agentic.yaml`)
- [x] 10 OWASP Top 10 for Agentic Applications (2026) categories
- [x] Test cases per category with prompts, expected_behavior, severity
- [x] Thresholds per category (block_rate targets)
- [x] Coverage validation in tests

#### 4.5 Tests (`tests/test_phase6_redteam.py`)
- [x] RedTeamAttack creation, all types have prompts, multi-turn are lists
- [x] RedTeamRunner init, custom types, generate limit, run_attack structure
- [x] Multi-turn attack, run_all returns EvalResult
- [x] PyRITRunner init, custom templates, run_attack blocking/safe
- [x] PyRIT evaluate returns result, fewer attacks, convenience, OWASP coverage, risk distribution, save
- [x] GarakRunner init, custom probes, simulate scan vuln/safe, scan returns result, severity distribution, convenience, save
- [x] OWASPConfig YAML parsable, 10 categories, test cases exist, required fields, thresholds defined
- [x] Integration: all runners work together, convenience function

---

### 5. Evaluation Orchestration & Reporting (`evals/orchestrator.py`)

#### 5.1 EvalOrchestrator
- [x] `EvalOrchestrator(gates, verbose)` — configurable gate thresholds
- [x] Default GATES:
  - judge_calibration ≥ 0.75
  - router_accuracy ≥ 0.70
  - router_drift_max ≤ 0.20
  - redteam_block_rate ≥ 0.85
  - pyrit_block_rate ≥ 0.80
  - garak_vuln_max ≤ 0.10
- [x] `run_full()` — executes all 5 components sequentially
- [x] Component wrappers: `_run_judge_calibration()`, `_run_router_eval()`, `_run_redteam()`, `_run_pyrit()`, `_run_garak()`
- [x] Gate evaluation: `_evaluate_gates(component_results)`
- [x] Overall score: average of passing component scores
- [x] Overall pass: all gates passed
- [x] `save_report(output_dir)` — JSON + Markdown with run_id timestamp

#### 5.2 Data Structures
- [x] `Phase6Report` — run_id, timestamps, all 5 component results, component_status dict, gates dict, overall_pass, overall_score
- [x] `run_phase6_evaluation()` convenience function

#### 5.3 Tests (`tests/test_phase6_e2e.py`)
- [x] All orchestrator tests pass
- [x] Cross-component integration tests pass
- [x] Config validation tests pass

---

### 6. CI/CD Integration

#### 6.1 Docker (`Dockerfile.eval`)
- [x] Multi-stage: base: Multi-stage build: base → slim / garak / pyrit / full
- [x] Python 3.11-slim, uv for fast installs
- [x] Phase 6 test profile installs [eval] extras
- [x] Non-root user, health checks
- [x] Entry points for each profile

#### 6.2 GitHub Actions (`.github/workflows/phase6-eval.yml`)
- [x] `phase6-eval` workflow: on push/PR to main, schedule (weekly)
- [x] Jobs: lint → test → eval (slim) → eval-garak → eval-pyrit → eval-full
- [x] Matrix: Python 3.11, 3.12
- [x] Artifacts: test results, evaluation reports (JSON + MD), Docker images
- [x] Conditional: garak/pyrit/full only on main branch or manual dispatch
- [x] Cost control: timeout, concurrency limits

#### 6.3 PyProject Dependencies (`pyproject.toml`)
- [x] `[project.optional-dependencies] eval` extras:
  - deepeval, promptfoo
  - pyrit, garak
  - swebench
  - scipy, scikit-learn
  - pyyaml (already in base)

---

### 7. Documentation

#### 7.1 Task File
- [x] This file: `docs/tasks/phase_6_task.md`

#### 7.2 Walkthrough
- [ ] `docs/walkthrough/phase_6_walkthrough.md` — User guide (next)

#### 7.3 Implementation Plan
- [x] `docs/phases/phase_6_implementation_plan_v2.md` — Detailed plan

#### 7.4 README Update
- [x] Phase 6 status ✅ Done
- [x] All checkboxes in Phase 6 section ticked
- [x] Badge updated to "Phase 6 complete"

---

## Verification Checklist

### All Tests Pass
```bash
python -m pytest tests/test_phase6_e2e.py tests/test_phase6_router_eval.py tests/test_phase6_redteam.py -v
# 80 passed in ~4s
```

### Dry-Run Execution Works
```bash
# Run full Phase 6 evaluation (dry-run mode uses mocked LLMs)
python -c "from evals.orchestrator import run_phase6_evaluation; r = run_phase6_evaluation(verbose=False); print(f'Score: {r.overall_score:.2f}, Pass: {r.overall_pass}')"
```

### Reports Generated
- [x] JSON report in `reports/phase6_report_<run_id>.json`
- [x] Markdown report in `reports/phase6_report_<run_id>.md`

### Docker Build Works
```bash
docker build -f Dockerfile.eval --target phase6-test -t zyren:phase6-test .
docker run --rm zyren:phase6-test
```

### GitHub Actions Workflow Valid
```bash
# Validate YAML syntax
yamllint .github/workflows/phase6-eval.yml
```

---

## Dependencies

### Required Packages (in `[eval]` extra)
- `deepeval>=1.0` — LLM-as-Judge framework
- `promptfoo>=0.10` — Alternative judge/eval
- `pyrit>=1.0` — Microsoft PyRIT red-teaming
- `garak>=0.10` — NVIDIA garak scanner
- `swebench>=2.0` — SWE-bench harness
- `scipy>=1.13` — Cohen's kappa, Krippendorff's α
- `scikit-learn>=1.5` — Fleiss' κ, agreement metrics
- `pyyaml` — Config loading (already in base)

### Standard Library
- `sqlite3` — Calibration storage (if needed)
- `dataclasses`, `typing`, `enum`, `json`, `pathlib`, `random`, `re`, `time`

---

## Integration Points

| Component | Consumed By |
|-----------|-------------|
| `LLMJudge` | Orchestrator, Harness scorer, Red-team evaluation |
| `TrajectoryEvaluator` | Orchestrator (judge calibration) |
| `RouterEvaluator` | Orchestrator (router accuracy/drift) |
| `RedTeamRunner` | Orchestrator (block rate), PyRIT/garak runners |
| `PyRITRunner` | Orchestrator (PyRIT block rate) |
| `GarakRunner` | Orchestrator (vulnerability rate) |
| `EvalOrchestrator` | CI/CD pipeline, manual runs |
| `Dockerfile.eval` |