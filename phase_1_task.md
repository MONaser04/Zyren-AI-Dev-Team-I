# Phase 1 — Execution Tasks

- [x] **1. Contracts (Pydantic schemas)**
  - [x] `src/contracts/schemas.py` — TaskAssignment, CodePatch, VerificationReport, ReviewDecision, WorkflowState

- [x] **2. State Store (events + SQLite)**
  - [x] `src/state/events.py` — Event model + EventType enum
  - [x] `src/state/store.py` — EventStore ABC + SQLiteEventStore
  - [x] `src/state/projections.py` — project events → WorkflowState

- [x] **3. Gateway Client (litellm wrapper)**
  - [x] `src/gateway/llm_client.py` — LLMClient with structured output

- [x] **4. Role Agents (coder, tester, critic)**
  - [x] `src/agents/base.py` — BaseAgent ABC
  - [x] `src/agents/coder.py` — CoderAgent
  - [x] `src/agents/tester.py` — TesterAgent
  - [x] `src/agents/critic.py` — CriticAgent
  - [x] `config/agents/coder.yaml` — Coder prompt template
  - [x] `config/agents/critic.yaml` — Critic prompt + rubric

- [x] **5. Orchestrator (LangGraph loop)**
  - [x] `src/orchestrator/graph.py` — LangGraph StateGraph
  - [x] `src/orchestrator/runner.py` — run_workflow entry point

- [x] **6. Tests**
  - [x] `tests/test_contracts.py` — 16 tests
  - [x] `tests/test_state.py` — 13 tests
  - [x] `tests/test_agents.py` — 3 tests
  - [x] `tests/test_orchestrator.py` — 8 tests

- [x] **7. Verify + Commit + Push**
  - [x] Lint (ruff) — ✅ All checks passed
  - [x] Type check (mypy) — ✅ No issues in 21 source files
  - [x] All tests pass — ✅ **95/95 passed** in 11.75s
  - [x] Git commit — 26 files, 3,490 insertions
  - [x] Git push — pushed to GitHub
