# Phase 0 — Execution Tasks

- [x] **1. Git Init + .gitignore + LICENSE**
  - [x] Create `.gitignore`
  - [x] Create `LICENSE` (MIT)
  - [x] `git init` + initial commit

- [x] **2. Directory Structure**
  - [x] Create all `src/` subdirectories with `__init__.py`
  - [x] Create `config/`, `evals/`, `optim/`, `tests/` directories
  - [x] Add `.gitkeep` to empty directories

- [x] **3. pyproject.toml + uv sync**
  - [x] Create `pyproject.toml` with core + dev dependencies
  - [x] Run `uv sync` to generate `uv.lock` — **89 packages installed**

- [x] **4. Makefile**
  - [x] Create `Makefile` with all targets (install, test, lint, format, typecheck, up, down, eval, clean, all)

- [x] **5. Docker Compose + Config**
  - [x] Create `docker-compose.yml` (Postgres, Qdrant, LiteLLM, Jaeger)
  - [x] Create `.env.example`
  - [x] Create `config/litellm.yaml`
  - [x] Create `config/policies.yaml` (skeleton)

- [x] **6. Golden Tasks + Eval Scaffolding**
  - [x] Create `evals/golden/README.md`
  - [x] Create `evals/golden/tasks.yaml`
  - [x] Create `evals/swebench/README.md`
  - [x] Create `evals/swebench/run_harness.py`

- [x] **7. Smoke Tests**
  - [x] Create `tests/test_smoke.py`

- [x] **8. Verification + Initial Commit**
  - [x] Run `uv sync` — ✅ 89 packages
  - [x] Run `ruff check` — ✅ All checks passed
  - [x] Run `mypy` — ✅ No issues in 11 source files
  - [x] Run `pytest` — ✅ **55/55 tests passed** in 21.28s
  - [x] Commit all files — ✅ 34 files, 5121 insertions
