# Phase 5: Closed-Loop Self-Improvement

## Overview

Phase 5 introduces the **Supervisor Agent** — a meta-agent that orchestrates a closed-loop self-improvement cycle for the entire Zyren AI Dev-Team. The Supervisor continuously evaluates the team's performance, analyses weaknesses, optimises prompts and model routing, and repeats until convergence or budget exhaustion.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        SUPERVISOR                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ EVALUATE │→ │ ANALYSE  │→ │ OPTIMISE │→ │ CONVERGE?    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────┬───────┘   │
│       ▲                                            │           │
│       │              (loop until converged)        │           │
│       └────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### Loop Steps

1. **EVALUATE** — Run Golden Set tasks through the full Zyren AI Dev-Team pipeline
2. **ANALYSE** — Process feedback, identify patterns, find weaknesses
3. **OPTIMISE** — Tune prompts (DSPy-style) and adjust model routing
4. **CONVERGE** — Check if scores have plateaued; if not, repeat

## Components

### Core Modules (`optim/`)

| Module | Purpose |
|--------|---------|
| `scorer.py` | Weighted composite scoring for workflow results |
| `feedback_store.py` | SQLite persistence for feedback, tunings, model stats |
| `analyser.py` | Pattern detection and weakness analysis |
| `convergence.py` | Convergence detection with patience/sliding window |
| `prompt_tuner.py` | DSPy-inspired prompt variant generation & evaluation |
| `model_optimiser.py` | Per-model performance review & routing optimisation |
| `reporter.py` | JSON/Markdown report generation |

### Contracts (`src/contracts/`)

| Class | Description |
|-------|-------------|
| `EvalResult` | Single task evaluation outcome with scores & metadata |
| `OptimReport` | Full session report with rounds, best scores, costs |
| `RoundReport` | Per-round aggregates: mean/median score, cost, convergence |
| `TuningResult` | Prompt tuning outcome per agent |

### Supervisor Agent (`src/agents/supervisor.py`)

Main orchestrator implementing the closed loop:
- Loads configuration from `config/phase5.yaml`
- Runs Golden Set tasks via `WorkflowRunner`
- Tracks budget and convergence state
- Produces final `OptimReport`

## Configuration

All settings in `config/phase5.yaml`:

```yaml
supervisor:
  max_rounds: 5                    # Maximum optimisation rounds
  eval_instances_per_round: 3      # Golden tasks per round
  max_workflow_iterations: 5       # Pipeline iterations per task
  cost_cap_per_workflow_usd: 0.50  # Per-workflow cost limit
  session_budget_usd: 10.00        # Total session budget
  enable_prompt_tuning: true
  enable_model_switching: true
  enable_convergence: true

  convergence:
    min_samples: 3                 # Minimum rounds before checking
    window_size: 3                 # Sliding window size
    improvement_threshold: 0.02    # 2% minimum improvement
    patience: 2                    # Rounds without improvement
    min_score_threshold: 0.70      # Minimum acceptable score

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
    metric: "weighted"
  model_optimiser:
    enabled: true
    min_success_rate: 0.6
    evaluation_interval: 3

feedback:
  db_path: "optim/feedback.db"

reporting:
  output_dir: "reports/"
  formats: ["json", "markdown"]
```

## Golden Evaluation Tasks

Located in `evals/golden/tasks.yaml` — 11 diverse tasks covering:

- **Algorithmic**: Fibonacci, palindrome, Stack[T]
- **API/Web**: FastAPI CRUD, async HTTP fetch with retries
- **Data Structures**: CircularBuffer, K-way merge
- **Utilities**: Retry decorator, timed context manager
- **Security**: SQL sanitizer, RateLimiter

## Running Phase 5

### Dry-Run Mode (No API Calls)
```bash
python scripts/run_supervisor.py --dry-run --rounds 3
python scripts/test_run_phase5.py --rounds 2
```

### Live Mode (Real LLM Calls)
```bash
python scripts/run_supervisor.py --live --rounds 5 --budget 25.0
```

### Custom Configuration
```bash
python scripts/run_supervisor.py --config config/phase5.yaml --rounds 10 --budget 50.0
```

## Output Reports

Reports saved to `reports/` directory:

### JSON Report (`phase5_report_<session_id>.json`)
Full structured data for programmatic consumption:
- Session metadata (ID, status, timestamps)
- Round-by-round scores and costs
- Model routing changes
- Prompt tuning results
- Convergence details

### Markdown Report (`phase5_report_<session_id>.md`)
Human-readable summary:
- Executive summary with key metrics
- Round-by-round breakdown tables
- Convergence status
- Recommendations

## Convergence Criteria

The loop stops when **any** condition is met:

1. **Budget Exceeded** — Total cost > `session_budget_usd`
2. **Converged** — Score plateau detected:
   - ≥ `min_samples` rounds completed
   - Improvement < `improvement_threshold` over `window_size` rounds
   - `patience` consecutive rounds without improvement
   - Current score ≥ `min_score_threshold`
3. **Max Rounds** — Reached `max_rounds`
4. **Error** — Unrecoverable failure

## Prompt Tuning (DSPy-Inspired)

For each agent role (coder, tester, critic, architect, planner):
1. Generate N prompt variants (LLM + templates)
2. Evaluate each variant against Golden Set results
3. Select highest-scoring variant
4. Persist to FeedbackStore for longitudinal tracking

## Model Routing Optimisation

Per-model performance tracking in `model_stats` table:
- Success rate per model
- Average latency and cost
- Automatic demotion of models below `min_success_rate`
- Suggests replacements within same tier (fast/smart)

## Budget Management

- Per-workflow cap: `cost_cap_per_workflow_usd`
- Session cap: `session_budget_usd`
- Real-time tracking with early termination
- Cost reported per round and in final report

## Testing

Run all Phase 5 tests:
```bash
python -m pytest tests/test_phase5_supervisor.py -v
```

Test categories:
- Contracts (EvalResult, OptimReport, TuningResult)
- FeedbackStore (CRUD, model stats, tuning history)
- Analyser (pattern detection, weakness identification)
- Convergence (insufficient samples, high score, min score)
- Model Optimiser (routing changes, recommendations)
- Prompt Tuner (variant generation, result serialization)
- Scorer (mean/median/pass_rate, edge cases)
- Reporter (JSON/Markdown output)

## Integration with Previous Phases

| Phase | Integration Point |
|-------|-------------------|
| Phase 1-2 | Uses existing agents (planner, coder, tester, critic, architect) |
| Phase 3 | Leverages WorkflowRunner, policy engine, gateway |
| Phase 4 | Observability integration (traces, metrics) |
| Phase 5 | **Adds closed-loop self-improvement on top** |

## Extending Phase 5

### Adding New Golden Tasks
Edit `evals/golden/tasks.yaml`:
```yaml
tasks:
  - id: "g11"
    prompt: "Your new task description here..."
```

### Custom Convergence Logic
Subclass `ConvergenceConfig` or implement custom `check_convergence()`

### Additional Optimisation Strategies
Extend `prompt_tuner.py` with new variant generation methods

### New Report Formats
Add formatters in `reporter.py` (HTML, PDF, etc.)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Circular import errors | Use minimal imports in launchers (see `run_supervisor.py`) |
| Convergence never triggers | Lower `min_score_threshold` or increase `patience` |
| Budget exhausted too quickly | Increase `session_budget_usd` or reduce `eval_instances_per_round` |
| Poor prompt tuning results | Increase `variants_per_agent` or enable LLM-based generation |

## Future Enhancements (Post-Phase 5)

- SWE-bench integration for real-world task evaluation
- Red-team adversarial hardening
- Human-in-the-loop (HITL) approval gates
- Multi-objective optimisation (speed vs quality vs cost)
- Cross-session learning (persist best prompts across sessions)