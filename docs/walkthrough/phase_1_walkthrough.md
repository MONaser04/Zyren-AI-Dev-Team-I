# 🧱 Phase 1 — Walkthrough

> **Phase 1** implemented the core state infrastructure, type-safe contracts, and the minimal evaluator-optimizer feedback loop — the first end-to-end workflow that can take a coding task and produce verified code.

---

## What Was Built

### 1. Type-Safe Contracts ([schemas.py](file:///d:/Downloads/AI_DEV_TEAM/src/contracts/schemas.py))
Pydantic v2 strict-mode schemas for every agent boundary:

| Schema | Boundary | Purpose |
|---|---|---|
| `TaskAssignment` | Orchestrator → Coder | Task + constraints + iteration context |
| `CodePatch` | Coder → Tester | Generated files with duplicate-path validation |
| `VerificationReport` | Tester → Critic | Facts only: test/type/lint results |
| `ReviewDecision` | Critic → Orchestrator | PASS/BLOCK with structured feedback |
| `WorkflowState` | State projection | Current lifecycle status |

### 2. Event-Sourced State Store
- [events.py](file:///d:/Downloads/AI_DEV_TEAM/src/state/events.py) — 9-field event schema per README spec + factory functions
- [store.py](file:///d:/Downloads/AI_DEV_TEAM/src/state/store.py) — Abstract `EventStore` + `SQLiteEventStore` with optimistic locking via `UNIQUE(workflow_id, version)`
- [projections.py](file:///d:/Downloads/AI_DEV_TEAM/src/state/projections.py) — Pure-function event fold using `match/case`

### 3. Gateway LLM Client ([llm_client.py](file:///d:/Downloads/AI_DEV_TEAM/src/gateway/llm_client.py))
- Model alias resolution (`frontier`, `fast`, `critic`, `fallback`)
- `complete_text()` for plain text, `complete_structured()` for Pydantic output
- Retry with exponential backoff (3 retries)

### 4. Role Agents
- [base.py](file:///d:/Downloads/AI_DEV_TEAM/src/agents/base.py) — Abstract `BaseAgent` with agent_id, role, LLM client
- [coder.py](file:///d:/Downloads/AI_DEV_TEAM/src/agents/coder.py) — Uses **frontier** model, structured output → `CodePatch`
- [tester.py](file:///d:/Downloads/AI_DEV_TEAM/src/agents/tester.py) — Runs `ruff`, `mypy`, `pytest` in subprocess → `VerificationReport`
- [critic.py](file:///d:/Downloads/AI_DEV_TEAM/src/agents/critic.py) — Uses **critic** model (different family), escalating tone by iteration

### 5. Orchestrator — LangGraph Feedback Loop ([graph.py](file:///d:/Downloads/AI_DEV_TEAM/src/orchestrator/graph.py))

```
START → assign_task → coder → tester → critic → [decision]
                                                     ├─ PASS → complete → END
                                                     └─ BLOCK → increment → coder (loop)
                                                          └─ iteration_cap → fail → END
```

- Every transition emits an event to the store
- Conditional routing based on `Verdict` + iteration cap
- Hard iteration cap (configurable, default 3)

### 6. Runner ([runner.py](file:///d:/Downloads/AI_DEV_TEAM/src/orchestrator/runner.py))
- `run_workflow(task_description)` — single entry point
- Creates event store, builds graph, runs loop, returns `WorkflowResult`

### 7. Agent Configs
- [config/agents/coder.yaml](file:///d:/Downloads/AI_DEV_TEAM/config/agents/coder.yaml) — System prompt + model config
- [config/agents/critic.yaml](file:///d:/Downloads/AI_DEV_TEAM/config/agents/critic.yaml) — System prompt + rubric + escalation rules

---

## Verification Results

| Check | Tool | Result |
|---|---|---|
| **Lint** | `ruff check` | ✅ All checks passed |
| **Type Check** | `mypy` | ✅ No issues in 21 source files |
| **Tests** | `pytest` | ✅ **95/95 passed** in 11.75s |
| **Git** | `git commit` | ✅ 26 files, 3,490 insertions |
| **GitHub** | `git push` | ✅ Pushed to origin/master |

### Test Breakdown (95 total)
- **Phase 0 smoke tests:** 55 (structure, imports, config)
- **Contracts:** 16 (valid/invalid data, validators)
- **State Store:** 13 (append, retrieve, locking, projections)
- **Agents:** 3 (tester with good/bad code)
- **Orchestrator:** 8 (router logic, compilation, mocked end-to-end PASS + FAIL)

### Key Bug Fixed During Development
- **datetime strict-mode issue:** `model_dump(mode="json")` serialized datetimes to strings, but `strict=True` rejected them on `model_validate()`. Fix: use `model_dump()` (native objects) for graph state, `mode="json"` only for event payloads going to SQLite.
