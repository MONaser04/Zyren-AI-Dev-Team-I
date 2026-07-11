# Phase 5 Walkthrough: Closed-Loop Self-Improvement

A step-by-step guide to running and understanding the AI Dev Team Supervisor.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Dependencies: `pip install -e .` (includes pyyaml)
- For live mode: API keys in environment (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)

### Dry-Run (No API Costs)
```bash
# Run 2 rounds with simulated results
python run_supervisor.py --dry-run --rounds 2

# Or use the test script
python test_run_phase5.py --rounds 2
```

Expected output:
```
🤖  AI Dev Team Supervisor — Phase 5
    Closed-Loop Self-Improvement: Evaluate → Analyse → Tune → Converge
======================================================================
Config file : config/phase5.yaml
Output dir  : reports/
Session ID  : supervisor-a1b2c3d4
----------------------------------------------------------------------
📦 Dry-run mode — all results are simulated.

🔁 Round 1 / 2 — evaluating...
  📋 Evaluating task 'g0': Write a function `fibonacci(n: int) -> int`...
  📋 Evaluating task 'g1': Write a function `is_palindrome(s: str) -> bool`...
  📋 Evaluating task 'g2': Implement a `Stack[T]` generic class...
  📊 Round 1 mean score: 0.7741 | cost: $0.240498
  🔍 Analysis: pass_rate=1.00 | total=3
  🔄 Model 'openai/gpt-4o-mini' → demote: Success rate 0.50 below threshold 0.60.
  ⏱️ Convergence: collecting (improvement=0.0000, patience=0)

🔁 Round 2 / 2 — evaluating...
  ...
✅ Convergence detected at round 5.

📄 Reports written: {'json': PosixPath('reports/phase5_report_supervisor_xxx.json'), 'markdown': PosixPath('reports/phase5_report_supervisor_xxx.md')}

✅  Supervisor Session Complete
======================================================================
   Status       : converged
   Summary      : Supervisor session supervisor-xxx: converged, 5 rounds, best score 0.9136, cost $1.020880
   Best Score   : 0.9136
   Best Round   : #5
   Total Cost   : $1.020880
   Rounds Run   : 5
   Evaluations  : 15
   Prompt Tunings: 0
======================================================================
```

---

## Understanding the Output

### Session Summary
| Field | Meaning |
|-------|---------|
| **Status** | `completed` \| `converged` \| `budget_exceeded` \| `error` |
| **Rounds Run** | Number of evaluation cycles completed |
| **Best Score** | Highest mean score across all rounds (0.0–1.0) |
| **Best Round** | Round number that achieved best score |
| **Total Cost** | Cumulative LLM API cost in USD |
| **Evaluations** | Total golden tasks evaluated |
| **Prompt Tunings** | Number of prompt optimisation runs |

### Convergence Status
- **collecting** — Not enough rounds yet (need `min_samples`)
- **improving** — Score improving but not yet converged
- **plateaued** — No significant improvement, patience counting
- **converged** — Met all criteria (improvement < threshold + patience exceeded + min_score)

---

## Configuration

### Main Config: `config/phase5.yaml`

Key sections:
```yaml
supervisor:
  max_rounds: 5                 # Maximum optimisation cycles
  eval_instances_per_round: 3   # Golden tasks per round
  max_workflow_iterations: 5    # Inner workflow iterations per task
  cost_cap_per_workflow_usd: 0.50
  session_budget_usd: 10.00     # Total budget for entire session
  enable_prompt_tuning: true
  enable_model_switching: true
  enable_convergence: true

  convergence:
    min_samples: 3              # Rounds before checking
    window_size: 3              # Sliding window for comparison
    improvement_threshold: 0.02 # 2% minimum improvement
    patience: 2                 # Rounds to wait without improvement
    min_score_threshold: 0.70   # Minimum acceptable score

evaluations:
  golden:
    enabled: true
    tasks_file: "evals/golden/tasks.yaml"
    default_instances: 5

optimisation:
  prompt_tuner:
    strategy: "dspy"
    variants_per_agent: 5
    max_llm_calls: 50
  model_optimiser:
    enabled: true
    min_success_rate: 0.60

feedback:
  db_path: "optim/feedback.db"

reporting:
  output_dir: "reports/"
  formats: ["json", "markdown"]
```

### Customising
- **More rounds**: Increase `max_rounds`
- **Faster convergence**: Lower `improvement_threshold` or `patience`
- **Stricter quality**: Raise `min_score_threshold`
- **Different tasks**: Edit `evals/golden/tasks.yaml`
- **Budget control**: Adjust `session_budget_usd`

---

## Golden Tasks

Located in `evals/golden/tasks.yaml` — 11 tasks across categories:

| Category | Tasks |
|----------|-------|
| **Algorithmic** | Fibonacci, Palindrome, Generic Stack |
| **API/Web** | FastAPI CRUD, Async HTTP with retry |
| **Data Structures** | Circular Buffer, K-way Merge |
| **Utilities** | Retry Decorator, Timed Context Manager |
| **Security** | SQL Sanitizer, Rate Limiter |

Each task has:
```yaml
- id: "g0"
  prompt: "Write a function fibonacci(n: int) -> int..."
```

---

## Running Live (Real API Calls)

⚠️ **Costs money!** Ensure API keys are configured.

```bash
# Run with real LLMs
python run_supervisor.py --live --rounds 5 --budget 20.0

# Or with custom config
python run_supervisor.py --live --config config/phase5.yaml --rounds 10 --budget 50.0
```

### Requirements for Live Mode
1. **API Keys** in environment:
   ```bash
   export OPENAI_API_KEY=sk-...
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
2. **Gateway configured** — `config/litellm.yaml` with model routing
3. **Budget awareness** — Set `--budget` to control spend

---

## Reports

### JSON Report (`reports/phase5_report_<session>.json`)
Complete machine-readable session data:
```json
{
  "supervisor_id": "supervisor-abc123",
  "status": "converged",
  "started_at": "2026-07-10T08:26:14.441717+00:00",
  "finished_at": "2026-07-10T08:26:14.490705+00:00",
  "best_score": 0.9136,
  "best_round": 5,
  "total_cost_usd": 1.020880,
  "total_evaluations": 15,
  "total_tunings": 0,
  "rounds": [
    {
      "round_num": 1,
      "mean_score": 0.7741,
      "median_score": 0.7774,
      "total_cost_usd": 0.240498,
      "eval_results": [...],
      "model_changes": [...],
      "converged": false
    },
    ...
  ]
}
```

### Markdown Report (`reports/phase5_report_<session>.md`)
Human-readable summary with tables:

```markdown
# 🔄 AI Dev Team — Optimisation Report

**Session ID**: `supervisor-abc123`
**Status**: `converged`

## 📊 Summary
| Metric | Value |
|--------|-------|
| Total Rounds | 5 |
| Best Score | **0.9136** |
| Best Round | #5 |
| Total Cost | $1.020880 |

## 📈 Round-by-Round Breakdown
### Round #1 ⚙️
| Metric | Value |
|--------|-------|
| Mean Score | 0.7741 |
| Converged | No |

### Round #5 ✅
| Metric | Value |
|--------|-------|
| Mean Score | 0.9136 |
| Converged | Yes |
```

---

## Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| `ImportError: trace_agent_invocation` | Use `run_supervisor.py` (has MinimalSupervisor) not `src.agents.supervisor` directly |
| `circular import` in observability | Known issue in base code; launchers avoid it |
| No reports generated | Check `reports/` directory permissions |
| Convergence never triggers | Lower `min_score_threshold` or increase `max_rounds` |
| Budget exceeded quickly | Reduce `eval_instances_per_round` or `max_workflow_iterations` |

### Debug Mode
```bash
python run_supervisor.py --dry-run --rounds 2 --log-level DEBUG
```

### Inspect Feedback DB
```bash
sqlite3 optim/feedback.db ".tables"
sqlite3 optim/feedback.db "SELECT * FROM feedback LIMIT 5;"
sqlite3 optim/feedback.db "SELECT * FROM model_stats;"
```

---

## Advanced Usage

### Custom Session ID
```bash
python run_supervisor.py --dry-run --session-id "my-experiment-001"
```

### Override Config Values
```bash
python run_supervisor.py --dry-run --rounds 10 --budget 5.0 --tasks-per-round 5
```

### Run Specific Tests
```bash
# All phase 5 tests
python -m pytest tests/test_phase5_supervisor.py -v

# Specific test class
python -m pytest tests/test_phase5_supervisor.py::TestConvergence -v

# With coverage
python -m pytest tests/test_phase5_supervisor.py --cov=optim --cov=src.agents.supervisor
```

### Extend Golden Tasks
Edit `evals/golden/tasks.yaml`:
```yaml
tasks:
  - id: "g11"
    prompt: "Write a function that..."
```

### Custom Model Tiers
Edit `optim/model_optimiser.py`:
```python
MODEL_TIERS = {
    "my/custom-model": {"tier": "fast", "roles": ["coder"], "cost_per_1k": 0.0001},
}
```

---

## Integration with Phases 1-4

| Phase | Role in Phase 5 |
|-------|-----------------|
| **1-2: Agents** | Prompt tuning targets (coder, tester, critic, architect, planner) |
| **3: Orchestration** | WorkflowRunner executes each golden task |
| **3: Gateway** | Model routing optimisation uses gateway |
| **3: Policy** | Cost caps enforced per workflow |
| **4: Observability** | Traces/metrics collected per round |

---

## Next Steps

1. **Run dry-run** to verify setup: `python run_supervisor.py --dry-run --rounds 2`
2. **Check reports** in `reports/` for JSON/Markdown output
3. **Tune config** for your quality/cost requirements
4. **Go live** with `--live` when ready (set budget!)
5. **Monitor feedback DB** for recurring error patterns

---

## Support

- **Issues**: Check `tests/test_phase5_supervisor.py` for expected behavior
- **Logs**: Use `--log-level DEBUG` for verbose output
- **Feedback DB**: Persistent at `optim/feedback.db` across sessions