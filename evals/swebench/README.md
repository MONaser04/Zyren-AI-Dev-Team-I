# 📊 SWE-bench Lite — Evaluation Harness

> **Purpose:** Integration point for [SWE-bench Lite](https://www.swebench.com/) (300 tasks) as the project's **north-star benchmark**.

## What is SWE-bench?

SWE-bench is a benchmark of real GitHub issues used to measure software-engineering agents:
- **SWE-bench Verified** — 500 human-verified tasks
- **SWE-bench Lite** — 300 tasks (our primary smoke test)

## Setup (When Ready)

```bash
# 1. Clone the SWE-bench repository
git clone https://github.com/princeton-nlp/SWE-bench.git

# 2. Install SWE-bench dependencies
cd SWE-bench && pip install -e .

# 3. Run the evaluation harness
python run_harness.py --config ../config.yaml
```

## Integration Status

| Component | Status |
|---|---|
| Harness script | 🟡 Placeholder (`run_harness.py`) |
| SWE-bench Lite dataset | ⬜ Not yet downloaded |
| Baseline measurement | ⬜ Not yet established |
| CI integration | ⬜ Not yet wired |

## Key Metric

**% Resolved** = `(tasks_passed / total_tasks) × 100`

Track this metric after every phase. If a new component doesn't improve it — **cut it**.

## Files

- `run_harness.py` — Entry point for running the evaluation harness
- (Future) `config.yaml` — SWE-bench configuration
- (Future) `results/` — Stored evaluation results
