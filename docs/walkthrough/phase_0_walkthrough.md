# Phase 0 — Walkthrough

> **Phase 0** bootstrapped the entire `zyren-ai-dev-team` project from an empty directory to a fully reproducible, verified development environment.

---

## What Was Built

### 1. Git Repository
- Initialized with `.gitignore` (Python, Docker, IDE, OS artifacts)
- MIT `LICENSE` as recommended in the README
- Initial commit: `a5a7676` — 34 files, 5,121 insertions

### 2. Python Monorepo (`uv`)
- [pyproject.toml](file:///d:/Downloads/AI_DEV_TEAM/pyproject.toml) with:
  - **Core deps:** `langgraph`, `langchain-core`, `litellm`, `pydantic`, `python-dotenv`, `psycopg`, `httpx`
  - **Dev deps:** `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `pre-commit`
  - **Tool config:** ruff (lint rules), mypy (strict mode), pytest (asyncio auto mode)
- `uv.lock` generated with **89 pinned packages**

### 3. Full Directory Structure (matching README spec)

```text
zyren-ai-dev-team/
├── README.md
├── pyproject.toml / uv.lock
├── Makefile
├── docker-compose.yml
├── .env.example / .gitignore / LICENSE
├── config/
│   ├── litellm.yaml          ← 4 model tiers (frontier/fast/critic/fallback)
│   ├── agents/               ← per-agent configs (Phase 1+)
│   └── policies.yaml         ← default-deny tool permission matrix
├── src/
│   ├── orchestrator/         ├── agents/
│   ├── contracts/            ├── state/
│   ├── memory/               ├── tools/
│   ├── verification/         ├── resilience/
│   ├── observability/        └── gateway/
├── evals/
│   ├── golden/               ← 5 starter task templates + README
│   ├── swebench/             ← harness placeholder + README
│   ├── judges/               └── redteam/
├── optim/
└── tests/
    └── test_smoke.py         ← 55 verification tests
```

### 4. Docker Compose Infrastructure
- [docker-compose.yml](file:///d:/Downloads/AI_DEV_TEAM/docker-compose.yml) with 4 services:

| Service | Image | Port | Purpose |
|---|---|---|---|
| Postgres 16 | `postgres:16-alpine` | 5432 | Event-sourced state store |
| Qdrant | `qdrant/qdrant:latest` | 6333/6334 | Vector store (memory) |
| LiteLLM | `ghcr.io/berriai/litellm:main-latest` | 4000 | Model gateway proxy |
| Jaeger | `jaegertracing/jaeger:latest` | 16686/4317/4318 | OTLP traces + UI |

### 5. Eval Harness Scaffolding
- [tasks.yaml](file:///d:/Downloads/AI_DEV_TEAM/evals/golden/tasks.yaml) — 5 golden task templates (bugfix, refactor, feature, test, data)
- [run_harness.py](file:///d:/Downloads/AI_DEV_TEAM/evals/swebench/run_harness.py) — CLI-based eval runner placeholder

### 6. Configuration
- [litellm.yaml](file:///d:/Downloads/AI_DEV_TEAM/config/litellm.yaml) — 4 model tiers with different model families for cross-model verification
- [policies.yaml](file:///d:/Downloads/AI_DEV_TEAM/config/policies.yaml) — default-deny permission matrix for 8 agent roles
- [.env.example](file:///d:/Downloads/AI_DEV_TEAM/.env.example) — all env vars documented

---

## Verification Results

| Check | Tool | Result |
|---|---|---|
| **Dependencies** | `uv sync` | ✅ 89 packages installed |
| **Lint** | `ruff check` | ✅ All checks passed |
| **Type Check** | `mypy --strict` | ✅ No issues in 11 source files |
| **Tests** | `pytest` | ✅ **55/55 passed** in 21.28s |
| **Git** | `git commit` | ✅ 34 files, 5,121 insertions |

### Test Breakdown (55 tests)
- `TestPythonEnvironment` — 1 test (Python >= 3.12)
- `TestCoreImports` — 6 tests (pydantic, langgraph, langchain_core, litellm, dotenv, httpx)
- `TestProjectStructure` — 31 tests (18 directories + 13 files)
- `TestSourcePackages` — 11 tests (root package + 10 subpackages)
- `TestConfiguration` — 6 tests (env vars, docker services, litellm models, policies)

---

## Next Steps → Phase 1

Phase 0 is complete. The next phase is **Phase 1 — Core State, Contracts & the Minimal Feedback Loop** (weeks 1–6):

1. **Event-Sourced State Store** — append-only event log in SQLite/Postgres
2. **Minimal Event Schema** — `event_id`, `workflow_id`, `agent_id`, `version`, etc.
3. **Type-Safe Contracts** — Pydantic schemas (`PRD`, `CodePatch`, `ReviewReport`)
4. **Minimal Viable Loop** — Orchestrator → Coder → Tester → Grounded Critic
