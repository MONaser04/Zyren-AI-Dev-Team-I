# 🛡️ Phase 2 — Grounded Verification Layer — Implementation Plan

> **Goal:** Upgrade the Phase 1 "minimal loop" into the full **Grounded Verification Layer** — the heart of the system. Verification becomes tools-first (external signals lead; the LLM only interprets), and the Coder gains a right of rebuttal to prevent false-positive degradation.

---

## Mapping README Requirements → Deliverables

| README Requirement | What Exists (Phase 1) | What Phase 2 Adds |
|---|---|---|
| **Tester Agent (External Signal Generator)** | Basic subprocess runner (ruff, mypy, pytest, AST parse) | Coverage tracking, per-test parsing, security scan (bandit), structured `VerificationReport` with `coverage_delta` |
| **Grounded Critic (Interpreter, Cross-Model)** | LLM-based review with PASS/BLOCK | Escalation ladder (soft→firm→hard→escalate), rubric-driven evaluation, diff-aware context |
| **Agentic Pushback (Right of Rebuttal)** | ❌ Not implemented | New `RebuttalRequest` contract, Coder rebuts once per iteration, Critic judges rebuttal, new graph edge |
| **Dedicated Critics (High-Risk Roles)** | Single CriticAgent only | `CriticFactory` pattern — role-scoped critics for Coder/Architect/Security, shared base |
| **Why "Grounded" (Research Basis)** | Principle mentioned in README | Formalized in `src/verification/` module with docstrings, enforced architecture |

---

## Proposed Changes

### Component 1: Verification Module (`src/verification/`)

> **Rationale:** The `src/verification/` package is currently empty (just `__init__.py`). Phase 2 lifts the verification logic out of the TesterAgent into a composable pipeline of "verification steps" — each step runs one external tool and returns a structured result. This makes steps testable in isolation and extensible for future tools.

#### [NEW] [runner.py](file:///d:/Downloads/AI_DEV_TEAM/src/verification/runner.py)
- `VerificationRunner` class — orchestrates a pipeline of `VerificationStep` instances
- Writes patch files to a temp directory, runs steps in order, collects results
- Returns a `VerificationReport` (same contract as Phase 1)

#### [NEW] [steps.py](file:///d:/Downloads/AI_DEV_TEAM/src/verification/steps.py)
- `VerificationStep` protocol — `run(work_dir: Path) -> StepResult`
- Concrete steps: `RuffLintStep`, `MypyTypeCheckStep`, `PytestStep`, `SyntaxCheckStep`, `BanditSecurityStep`
- Each step captures stdout/stderr/exit code and returns a typed `StepResult`

#### [MODIFY] [\_\_init\_\_.py](file:///d:/Downloads/AI_DEV_TEAM/src/verification/__init__.py)
- Export `VerificationRunner` and all step classes

---

### Component 2: Enhanced Contracts (`src/contracts/schemas.py`)

#### [MODIFY] [schemas.py](file:///d:/Downloads/AI_DEV_TEAM/src/contracts/schemas.py)
- Add `RebuttalRequest` contract — Coder's right-of-rebuttal with justification, exactly one per iteration
- Add `RebuttalOutcome` enum — `ACCEPTED` / `REJECTED`
- Add `coverage_percent` and `coverage_delta` fields to `VerificationReport`
- Add `security_passed` and `security_output` fields to `VerificationReport`
- Update `all_clean` property to include `security_passed`
- Add `EscalationLevel` enum — `SOFT`, `FIRM`, `HARD_BLOCK`, `ESCALATE`
- Add `escalation_level` field to `ReviewDecision`

---

### Component 3: Enhanced Tester Agent

#### [MODIFY] [tester.py](file:///d:/Downloads/AI_DEV_TEAM/src/agents/tester.py)
- Refactor to use `VerificationRunner` from `src/verification/` instead of inline subprocess calls
- Becomes a thin wrapper: receives CodePatch → delegates to VerificationRunner → returns VerificationReport
- All tool-running logic migrates to `src/verification/steps.py`

---

### Component 4: Enhanced Critic Agent + Escalation Ladder

#### [MODIFY] [critic.py](file:///d:/Downloads/AI_DEV_TEAM/src/agents/critic.py)
- Implement the **escalation ladder** in the system prompt — tone varies by iteration:
  - Iteration 1: Constructive and encouraging
  - Iteration 2: Direct and firm
  - Iteration 3: Hard block with exhaustive detail
  - Iteration 4+: Escalate to Supervisor (sets `escalation_level = ESCALATE`)
- Accept and judge **rebuttals** — new `judge_rebuttal()` method
- Include `escalation_level` in the returned `ReviewDecision`

#### [NEW] [critic_factory.py](file:///d:/Downloads/AI_DEV_TEAM/src/agents/critic_factory.py)
- `CriticFactory` — produces role-scoped critic instances
- Registry: `"coder"` → CriticAgent (code review rubric), `"architect"` → ArchitectCritic (design rubric), `"security"` → SecurityCritic (OWASP rubric)
- All critics share the same `CriticAgent` base class with different system prompts and rubrics

#### [NEW] [config/agents/security_critic.yaml](file:///d:/Downloads/AI_DEV_TEAM/config/agents/security_critic.yaml)
- System prompt + rubric for the Security Critic (OWASP-aligned)

---

### Component 5: Agentic Pushback (Right of Rebuttal)

> **README spec (line 232):** "the Coder may reject feedback **once per iteration** with a logical justification. If accepted, code passes; if deadlock persists, escalate."

#### [MODIFY] [coder.py](file:///d:/Downloads/AI_DEV_TEAM/src/agents/coder.py)
- New `rebut()` method — when the Coder disagrees with the Critic, it generates a `RebuttalRequest` with justification

#### [MODIFY] [graph.py](file:///d:/Downloads/AI_DEV_TEAM/src/orchestrator/graph.py)
- Add `rebuttal` node and edge: `critic --BLOCK--> should_rebut? --yes--> coder_rebut --> critic_judge --> [accepted?]`
- Track `rebuttal_used` in `GraphState` to enforce the "once per iteration" rule
- Add `REBUTTAL_SUBMITTED` and `REBUTTAL_JUDGED` event types

#### [MODIFY] [events.py](file:///d:/Downloads/AI_DEV_TEAM/src/state/events.py)
- Add `EventType.REBUTTAL_SUBMITTED` and `EventType.REBUTTAL_JUDGED`
- Add factory functions: `rebuttal_submitted_event()`, `rebuttal_judged_event()`

#### [MODIFY] [projections.py](file:///d:/Downloads/AI_DEV_TEAM/src/state/projections.py)
- Handle new event types in the projection fold

---

### Component 6: Tests

#### [NEW] [test_verification.py](file:///d:/Downloads/AI_DEV_TEAM/tests/test_verification.py)
- Test each `VerificationStep` with known-good and known-bad code
- Test `VerificationRunner` pipeline with mixed results
- Test coverage and security step behavior

#### [MODIFY] [test_contracts.py](file:///d:/Downloads/AI_DEV_TEAM/tests/test_contracts.py)
- Add tests for `RebuttalRequest`, `EscalationLevel`, new `VerificationReport` fields

#### [MODIFY] [test_orchestrator.py](file:///d:/Downloads/AI_DEV_TEAM/tests/test_orchestrator.py)
- Add test for the rebuttal edge (mock: Coder rebuts, Critic accepts → PASS)
- Add test for rebuttal rejection (mock: Coder rebuts, Critic rejects → continue loop)
- Add test for escalation (iteration 4 → ESCALATE level)

#### [MODIFY] [test_agents.py](file:///d:/Downloads/AI_DEV_TEAM/tests/test_agents.py)
- Update TesterAgent tests to work with refactored VerificationRunner
- Add escalation ladder tests for Critic

---

## Open Questions

> [!IMPORTANT]
> **Bandit dependency:** Adding `bandit` for security scanning requires a new dependency. This aligns with the README's security scanning requirement and is lightweight. Shall I add it, or defer security scanning to Phase 3?

> [!NOTE]
> **Coverage tracking:** The README mentions "coverage delta". For v0, I'll track `coverage_percent` as a number in the `VerificationReport` using `pytest-cov`. The delta is computed by comparing against the prior iteration. This is a best-effort metric since the sandbox is ephemeral — fine for Phase 2.

---

## Execution Order

1. **Contracts** — Add new schemas (RebuttalRequest, EscalationLevel, coverage/security fields)
2. **Verification Module** — Build the composable step pipeline
3. **Enhanced Tester** — Refactor to use VerificationRunner
4. **Enhanced Critic** — Escalation ladder + rebuttal judging + CriticFactory
5. **Agentic Pushback** — Coder rebut() method
6. **Orchestrator** — Add rebuttal edge to the LangGraph
7. **Events** — New event types + projection updates
8. **Tests** — Full test suite for all new components
9. **Verify** — Lint (ruff) + Type check (mypy) + All tests passing
10. **Commit + Push** — Git commit with conventional format

---

## Verification Plan

### Automated Tests
```bash
uv run ruff check src/ tests/
uv run mypy --ignore-missing-imports
uv run pytest tests/ -v --tb=short
```

### Expected Test Count
- Phase 0 smoke tests: 55 (unchanged)
- Phase 1 tests: 40 (updated to match refactors)
- Phase 2 new tests: ~25–30
- **Total target: ~120+ tests**
