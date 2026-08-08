# Phase 6 Walkthrough: Comprehensive Evaluation Framework

A step-by-step guide to running and understanding the Phase 6 evaluation suite for Ž Y R E N AI Dev-Team.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Dependencies: `pip install -e ".[eval]"` (installs deepeval, promptfoo, pyrit, garak, swebench, scipy, scikit-learn)
- For live mode: API keys in environment (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)

### Dry-Run (No API Costs)
```bash
# Run full Phase 6 evaluation with mocked components
python -c "
from evals.orchestrator import run_phase6_evaluation
report = run_phase6_evaluation(verbose=True, save=True)
print(f'Overall Score: {report.overall_score:.3f}')
print(f'Overall Pass: {report.overall_pass}')
print(f'Component Status: {report.component_status}')
print(f'Gates: {report.gates}')
"
```

Expected output:
```
📊 Phase 6 Evaluation Orchestrator
   Run ID: phase6-20260711-143022
   Started: 2026-07-11T14:30:22.123456Z
--------------------------------------------------
🔍 [1/5] Judge Calibration...
   Alignment: 0.82 | Gate: PASSED
🔍 [2/5] Router Evaluation...
   Accuracy: 0.85 | Drift: 0.12 | Gate: PASSED
🔍 [3/5] Red-Team (Built-in)...
   Block Rate: 0.93 | Gate: PASSED
🔍 [4/5] PyRIT Red-Team...
   Block Rate: 0.88 | Gate: PASSED
🔍 [5/5] Garak Scan...
   Vulnerability Rate: 0.04 | Gate: PASSED
--------------------------------------------------
✅ Phase 6 Evaluation Complete
   Overall Score: 0.91
   Overall Pass: True
   Reports saved to reports/
```

---

## Understanding the Output

### Session Summary

| Field | Meaning |
|-------|---------|
| **Run ID** | Unique identifier (timestamp-based) |
| **Overall Score** | Average of passing component scores (0.0–1.0) |
| **Overall Pass** | All gates passed? (boolean) |
| **Component Status** | `pass` / `fail` / `error` per component |
| **Gates** | Per-component threshold pass/fail |

### Component Reports

#### 1. Judge Calibration
```json
{
  "judge_calibration": {
    "alignment": 0.82,
    "kappa_per_category": {
      "correctness": 0.78,
      "code_quality": 0.85,
      "documentation": 0.72,
      "error_handling": 0.80
    },
    "gate_passed": true
  }
}
```
- **alignment** — Overall agreement between LLM judge and human labels (Cohen's κ)
- **kappa_per_category** — Per-dimension agreement
- **gate_passed** — alignment ≥ 0.75?

#### 2. Router Evaluation
```json
{
  "router_eval": {
    "accuracy": 0.85,
    "per_agent_accuracy": {
      "architect": 0.83,
      "coder": 0.90,
      "critic": 0.80,
      "debugger": 0.88,
      "devops": 0.85,
      "researcher": 0.87
    },
    "drift_score": 0.12,
    "mean_confidence": 0.91,
    "floor_violations": [],
    "gate_passed": true
  }
```
- **accuracy** — Overall routing correctness
- **per_agent_accuracy** — Breakdown by agent type
- **drift_score** — Jensen-Shannon divergence from baseline (lower = better)
- **floor_violations** — List of PerformanceFloor breaches
- **gate_passed** — accuracy ≥ 0.70 AND drift ≤ 0.20 AND all per-agent ≥ 0.60?

#### 3. Red-Team (Built-in)
```json
{
  "redteam_eval": {
    "total_attacks": 32,
    "blocked": 30,
    "block_rate": 0.93,
    "gate_passed": true
  }
}
```

#### 4. PyRIT Red-Team
```json
{
  "pyrit_eval": {
    "total_attacks": 20,
    "blocked": 18,
    "block_rate": 0.90,
    "risk_distribution": {"critical": 0, "high": 2, "medium": 0, "low": 0},
    "gate_passed": true
  }
```

#### 5. Garak Scan
```json
{
  "garak_eval": {
    "total_probes": 50,
    "vulnerabilities_found": 2,
    "vulnerability_rate": 0.04,
    "severity_distribution": {"high": 0, "medium": 2, "low": 0},
    "gate_passed": true
  }
```

---

## Configuration

### Main Config Files

| File | Purpose |
|------|---------|
| `config/router_eval.yaml` | 44 golden routing samples + PerformanceFloor |
| `evals/judges/rubrics.yaml` | Judge scoring rubrics (1–10, binary, 3-point) |
| `evals/judges/calibration_set.yaml` | 30–50 human-labeled calibration tasks |
| `evals/redteam/owasp_agentic.yaml` | OWASP Top 10 test cases & thresholds |
| `config/phase5.yaml` | Supervisor config (shared budget, etc.) |

### Customizing Gates
Edit `GATES` in `evals/orchestrator.py` or pass custom dict:
```python
from evals.orchestrator import EvalOrchestrator, GATES

custom_gates = GATES.copy()
custom_gates["router_accuracy"] = 0.80  # Stricter
custom_gates["redteam_block_rate"] = 0.95  # Stricter

orch = EvalOrchestrator(gates=custom_gates, verbose=True)
report = orch.run_full()
```

---

## Running Individual Components

### Judge Calibration Only
```python
from evals.judges.judge import LLMJudge, JudgeConfig, ScoringMode
from evals.judges.calibration import run_calibration

# Quick calibration check
result = run_calibration(judge_model="critic", min_kappa=0.6, max_rounds=5)
print(f"Converged: {result.converged}, Kappa: {result.kappa:.3f}")

# Evaluate single code sample
judge = LLMJudge(JudgeConfig(scoring_mode=ScoringMode.BINARY))
result = judge.judge(
    task_description="Write a binary search function",
    code="def binary_search(arr, target):\n    ..."
)
print(f"Score: {result['judge_score']:.2f}")
print(f"Categories: {result['category_scores']}")
```

### Router Evaluation Only
```python
from evals.router_eval import evaluate_router

result = evaluate_router(dataset_path="config/router_eval.yaml", verbose=True)
print(f"Accuracy: {result.accuracy:.2%}")
print(f"Drift: {result.drift_score:.3f}")
print(f"Violations: {result.floor_violations}")
```

### Red-Team Only
```python
# Built-in attacks
from evals.redteam.attacks import run_redteam_eval
result = run_redteam_eval()
print(f"Block rate: {result.overall_score:.1%}")

# PyRIT
from evals.redteam.pyrit_runner import run_pyrit_evaluation
result = run_pyrit_evaluation(num_attacks=20)
print(f"Block rate: {result.overall_score:.1%}")

# Garak
from evals.redteam.garak_runner import run_garak_scan
result = run_garak_scan(probes=["encoding", "continuation"])
print(f"Vuln rate: {result.vulnerability_rate:.1%}")
```

---

## Reports

### JSON Report (`reports/phase6_report_<run_id>.json`)
Complete machine-readable session data:
```json
{
  "run_id": "phase6-20260711-143022",
  "started_at": "2026-07-11T14:30:22.123456Z",
  "finished_at": "2026-07-11T14:30:45.678901Z",
  "judge_calibration": {...},
  "router_eval": {...},
  "redteam_eval": {...},
  "pyrit_eval": {...},
  "garak_eval": {...},
  "component_status": {"judge": "pass", "router": "pass", "redteam": "pass", "pyrit": "pass", "garak": "pass"},
  "gates": {"judge": true, "router": true, "redteam": true, "pyrit": true, "garak": true},
  "overall_pass": true,
  "overall_score": 0.91
}
```

### Markdown Report (`reports/phase6_report_<run_id>.md`)
Human-readable summary with tables:
```markdown
# 📊 Phase 6 Evaluation Report

**Run ID**: `phase6-20260711-143022`
**Status**: `PASSED`
**Overall Score**: **0.91**

## Summary
| Metric | Value |
|--------|-------|
| Judge Calibration (κ) | 0.82 |
| Router Accuracy | 85% |
| Router Drift | 0.12 |
| Red-Team Block Rate | 93% |
| PyRIT Block Rate | 90% |
| Garak Vuln Rate | 4% |

## Gates
| Component | Threshold | Actual | Status |
|-----------|-----------|--------|--------|
| judge_calibration | ≥ 0.75 | 0.82 | ✅ |
| router_accuracy | ≥ 0.70 | 0.85 | ✅ |
| router_drift_max | ≤ 0.20 | 0.12 | ✅ |
| redteam_block_rate | ≥ 0.85 | 0.93 | ✅ |
| pyrit_block_rate | ≥ 0.80 | 0.90 | ✅ |
| garak_vuln_max | ≤ 0.10 | 0.04 | ✅ |
```

---

## CI/CD Integration

### Docker
```bash
# Build test image (slim)
docker build -f Dockerfile.eval --target phase6-test -t zyren-ai-dev-team:phase6-test .

# Run tests in container
docker run --rm zyren-ai-dev-team:phase6-test

# Build full eval image (with PyRIT + garak)
docker build -f Dockerfile.eval --target phase6-full -t zyren-ai-dev-team:phase6-full .
docker run --rm -e OPENAI_API_KEY=$OPENAI_API_KEY zyren-ai-dev-team:phase6-full
```

### GitHub Actions
Workflow: `.github/workflows/phase6-eval.yml`

Triggers:
- Push/PR to `main`
- Weekly schedule (Mondays 02:00 UTC)
- Manual dispatch

Jobs:
1. **lint** — ruff, mypy
2. **test** — pytest (all tests)
3. **eval-slim** — Phase 6 eval (mocked, fast)
4. **eval-garak** — Garak scan (main branch only)
5. **eval-pyrit** — PyRIT campaign (main branch only)
6. **eval-full** — Full suite with real APIs (manual only)

Artifacts uploaded:
- Test results (JUnit XML)
- Evaluation reports (JSON + MD)
- Docker images (GHCR)

---

## Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| `ImportError: deepeval` | Run `pip install -e ".[eval]"` |
| `ImportError: pyrit` | PyRIT requires Python 3.10+; check version |
| `ImportError: garak` | Install with `pip install garak` |
| Calibration κ < 0.6 | Increase `max_rounds`, check `calibration_set.yaml` quality |
| Router accuracy low | Review `router_eval.yaml` samples; adjust keyword classifier |
| Red-team block rate low | Check security model prompt; add more BLOCKED examples |
| Garak vulnerabilities | Review probes; add defensive prompts to security model |
| Docker build fails | Ensure uv.lock is committed; check Dockerfile.eval syntax |

### Debug Mode
```bash
# Verbose evaluation
python -c "
from evals.orchestrator import run_phase6_evaluation
run_phase6_evaluation(verbose=True)
"

# Debug single component
python -c "
from evals.router_eval import evaluate_router
import logging
logging.basicConfig(level=logging.DEBUG)
evaluate_router(verbose=True)
"
```

### Inspect Reports
```bash
# Latest JSON report
cat reports/phase6_report_$(ls -t reports/phase6_report_*.json | head -1)

# Latest Markdown report
cat reports/phase6_report_$(ls -t reports/phase6_report_*.md | head -1)
```

---

## Extending Phase 6

### Add Custom Judge Rubric
Edit `evals/judges/rubrics.yaml`:
```yaml
my_custom_dimension:
  description: "Custom quality dimension"
  levels:
    10: "Perfect"
    7: "Good"
    4: "Acceptable"
    1: "Poor"
```

### Add Golden Routing Samples
Edit `config/router_eval.yaml`:
```yaml
samples:
  - id: "custom-01"
    input: "Your task description here"
    expected_agent: "architect"  # or coder, critic, debugger, devops, researcher
```

### Add Red-Team Attack
Edit `evals/redteam/attacks.py`:
```python
RedTeamAttack.ATTACK_PROMPTS["my_new_attack"] = [
    "First turn prompt",
    "Follow-up escalation prompt",
]
```
Then add to `RedTeamRunner` enabled_types.

### Add OWASP Test Case
Edit `evals/redteam/owasp_agentic.yaml`:
```yaml
owasp_categories:
  - id: "my-category"
    name: "My Category"
    test_cases:
      - id: "tc-01"
        prompt: "Attack prompt"
        expected_behavior: "SAFE refusal"
        severity: "high"
```

---

## Integration with Phases 1-5

| Phase | Role in Phase 6 |
|-------|-----------------|
| **1-2: Agents** | Evaluated by Judge + Trajectory Harness |
| **3: Orchestration** | `WorkflowRunner` executes golden tasks for trajectory eval |
| **3: Gateway** | Router evaluation tests the 4-alias routing + SemanticRouter |
| **3: Policy** | Cost caps enforced during evaluation runs |
| **4: Observability** | Traces/metrics collected per evaluation round |
| **5: Supervisor** | Prompt optimization targets evaluated by Phase 6 judge |

---

## Next Steps

1. **Run dry-run** to verify setup: `python -c "from evals.orchestrator import run_phase6_evaluation; run_phase6_evaluation(verbose=True)"`
2. **Check reports** in `reports/` for JSON/Markdown output
3. **Tune config** for your quality/cost requirements
4. **Go live** with real APIs when ready (set budget!)
5. **Monitor feedback DB** for recurring error patterns

---

## Support

- **Issues**: Check `tests/test_phase6_e2e.py`, `tests/test_phase6_router_eval.py`, `tests/test_phase6_redteam.py` for expected behavior
- **Logs**: Use `--log-level DEBUG` for verbose output
- **Reports**: Persistent in `reports/` with timestamped run IDs
- **Calibration**: Stored in `evals/judges/calibration_set.yaml` (human labels) + best prompt in memory