# Phase 2 — Walkthrough: Grounded Verification Layer

The Grounded Verification Layer (Phase 2) has been successfully implemented, bringing external tool verification and Agentic Pushback to the orchestration loop.

## Changes Made

### 1. Verification Runner (`src/verification`)
- **Extracted Tool Logic:** Separated tool execution from the `TesterAgent`. Verification tools are now pure, composable classes implementing a `VerificationStep` interface.
- **Verification Runner:** Introduced `VerificationRunner` to orchestrate steps securely. It writes code to a temporary workspace, executes tools, and captures `stdout`/`stderr`/exit codes.
- **Included Steps:** Syntax Check, Ruff (Lint), Mypy (Type Check), Pytest (Tests & Coverage), and Bandit (Security).

### 2. Enhanced Tester & Critic (`src/agents`)
- **Thin Tester:** Refactored `TesterAgent` to act as a lightweight wrapper around the `VerificationRunner`, generating data-rich `VerificationReport`s based purely on measured facts.
- **Critic Escalation Ladder:** The `CriticAgent` now adjusts its tone and leniency based on the current iteration count (Soft → Firm → Hard Block → Escalate).
- **Role-Scoped Critics:** Introduced `CriticFactory` to instantiate critics with specialized system prompts based on their role (e.g., Security Reviewer vs. Architect).

### 3. Agentic Pushback (Right of Rebuttal)
- **Coder Rebuttal:** The `CoderAgent` can now formulate a `RebuttalRequest` when blocked, allowing it to argue against false-positive test failures or bad feedback using logical justifications.
- **Rebuttal Judging:** The `CriticAgent` handles `judge_rebuttal()`, evaluating the coder's argument and rendering a `RebuttalJudgment` (Accepted or Rejected).
- **State Integration:** The Orchestrator's `GraphState` now natively tracks rebuttals, routing accepted rebuttals straight to a `PASS` verdict.

### 4. Events & State Store (`src/state`)
- Enhanced the `WorkflowState` projection to include lists of `rebuttals` and `rebuttal_judgments`.
- Added new event types (`rebuttal_submitted`, `rebuttal_judged`) to the `EventType` enum.
- Updated `SQLiteEventStore` logic to support these events safely.

## Validation Results

- All verification steps pass correctly on clean code.
- Validation successfully flags syntax errors, type errors, linting issues, and security vulnerabilities (tested via Bandit).
- The LangGraph Orchestrator compiles with the new rebuttal edges and router functions.
- The `pytest` test suite has expanded to cover all new structures, resulting in **129 passing tests**.
- **Pytest Output:**
  ```text
  ======================= 129 passed, 1 warning in 27.05s =======================
  ```

## Next Steps

Phase 2 is now fully integrated and checked into `master`. The system has a robust verification pipeline capable of agentic pushback. The next target is **Phase 3 — Model Gateway, Tools & Memory**, where we will add LiteLLM routing, MCP tool exposure, and hierarchical memory.
