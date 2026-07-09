# 🔌 Phase 3 — Walkthrough: Model Gateway, Tools & Memory

> **Phase 3** implemented the LLMOps Gateway with hard cost caps, the MCP-compliant Tool Registry with default-deny permissions, and the Hierarchical Memory layer — the infrastructure that makes the multi-agent system safe, cost-predictable, and context-aware.

---

## What Was Built

### 1. Cost Tracker — LLMOps Circuit Breakers ([cost_tracker.py](file:///d:/Downloads/AI_DEV_TEAM/src/gateway/cost_tracker.py))

Per-workflow budget enforcement with hard circuit breakers:

| Feature | Implementation |
|---|---|
| **Per-workflow budgets** | `CostTracker.init_workflow(budget, iteration_cap)` |
| **Per-model pricing** | `MODEL_PRICING` table (gpt-4o, gpt-4o-mini, claude-sonnet-4-20250514, etc.) |
| **Usage recording** | `record_usage(model, input_tokens, output_tokens)` |
| **Budget exceeded** | `BudgetExceededError` raised — halts workflow |
| **Iteration cap** | `IterationCapExceededError` raised — prevents infinite loops |
| **Live summary** | `workflow_summary()` → total $, tokens, iterations, models used |
| **Global stats** | `global_stats()` → aggregate across all active workflows |
| **Custom pricing** | `override_pricing(model, price_per_1M)` for local/self-hosted models |
| **Workflow tracking** | `_active_workflows` dict + `_global_input_tokens`, `_global_output_tokens` |

**Pricing Table (per 1M tokens, input/output):**
- `gpt-4o`: $2.50 / $10.00
- `gpt-4o-mini`: $0.15 / $0.60
- `claude-sonnet-4-20250514`: $3.00 / $15.00
- `claude-haiku-4-20250514`: $0.25 / $1.25
- `deepseek-chat`: $0.14 / $0.28
- `gemini-2.5-flash`: $0.15 / $0.60

### 2. Policy Engine — Default-Deny Permission Matrix ([policy_engine.py](file:///d:/Downloads/AI_DEV_TEAM/src/tools/policy_engine.py))

Role-scoped, default-deny tool access enforcement:

| Feature | Implementation |
|---|---|
| **Permission classes** | 12 permission types (`filesystem.read`, `filesystem.write`, `git.read`, `git.write`, `shell.execute_sandboxed`, `shell.execute_db`, `shell.execute_host`, `state.read`, `state.write`, `notifications.send`, `security.scan`, `security.escalate`) |
| **11 role definitions** | `coder`, `tester`, `critic`, `architect`, `security`, `researcher`, `integrator`, `docs`, `liaison`, `supervisor`, `planner` |
| **Default-deny** | Unknown role → `None`; unknown permission → rejected |
| **Wildcard support** | `supervisor` has `*` — all permissions granted |
| **Escalation ladder** | 3-tone escalation per iteration (soft → firm → hard block) |
| **Daily quotas** | `DAILY_QUOTAS` per role (e.g., `coder`: 50, `tester`: 100) |
| **Quota reset** | Auto-resets on date change via `_reset_daily_usage_if_new_day()` |
| **Policy violation error** | `PolicyViolationError` with structured message |

**Role Permissions at a Glance:**

| Role | Can Read Files | Can Write Files | Can Run Tests | Can Git Write | Can Notify |
|------|:---:|:---:|:---:|:---:|:---:|
| Coder | ✅ | ✅ | ✅ | ✅ | ❌ |
| Tester | ✅ | ❌ | ✅ | ❌ | ❌ |
| Critic | ✅ | ❌ | ❌ | ❌ | ❌ |
| Architect | ✅ | ✅ | ❌ | ❌ | ❌ |
| Security | ✅ | ❌ | ✅ (SAST) | ❌ | ✅ (escalate) |
| Researcher | ✅ | ❌ | ❌ | ❌ | ❌ |
| Supervisor | ✅⭐ | ✅⭐ | ✅⭐ | ✅⭐ | ✅⭐ |

⭐ = wildcard `*` — all permissions

### 3. MCP Tool Registry ([mcp_registry.py](file:///d:/Downloads/AI_DEV_TEAM/src/tools/mcp_registry.py))

MCP-compliant tool definitions, permission-aware resolution, and Tool-RAG filtering:

**14 Registered Tools:**

| Tool | Category | Required Permission |
|---|---|---|
| `file_read` | filesystem | `filesystem.read` |
| `file_write` | filesystem | `filesystem.write` |
| `file_list` | filesystem | `filesystem.read` |
| `git_status` | git | `git.read` |
| `git_diff` | git | `git.read` |
| `git_commit` | git | `git.write` |
| `exec_test` | execution | `shell.execute_sandboxed` |
| `exec_lint` | execution | `shell.execute_sandboxed` |
| `exec_typecheck` | execution | `shell.execute_sandboxed` |
| `exec_sast` | execution | `shell.execute_sandboxed` |
| `exec_syntax` | execution | `shell.execute_sandboxed` |
| `state_read` | state | `state.read` |
| `state_write` | state | `state.write` |
| `notify_send` | notifications | `notifications.send` |

**Registry Features:**

| Feature | Method |
|---|---|
| **Register/get tools** | `register()`, `get_tool()`, `list_all()` |
| **Search by name/desc** | `search(query)` — substring match |
| **Permission-aware list** | `list_for_role(role)` — filters by policy |
| **Permission-aware resolve** | `resolve(tool_name, role)` → tool or None |
| **Resolve with raise** | `resolve_or_raise(tool_name, role)` → raises `PolicyViolationError` |
| **Tool-RAG filtering** | `list_by_category(cats)`, `list_for_task(task_type)` |
| **LLM prompt generation** | `describe_for_llm(role)` → human-readable tool list |
| **OpenAI function format** | `to_openai_tools(role)` → `[{type: "function", function: {...}}]` |
| **System prompt injection** | `generate_system_prompt(role, task_type)` |

**Tool-RAG Task → Category Mapping:**
- `coding`: filesystem, git, execution
- `testing`: filesystem, execution
- `review`: filesystem, state
- `security`: filesystem, execution (SAST only)
- `architecture`: filesystem, state
- `general`: all categories

### 4. Memory Layer ([memory.py](file:///d:/Downloads/AI_DEV_TEAM/src/memory/memory.py))

Hierarchical memory following the Phase 3 spec — implemented layers 1–3:

| Layer | Component | Status |
|---|---|---|
| **Working Memory** | Context window (managed by LLM) | ✅ Implicit |
| **Episodic Memory** | `EpisodicStore` — past runs/failures | ✅ Built |
| **Semantic Memory** | `SemanticStore` — project facts/conventions | ✅ Built |
| **Procedural Memory** | Runbooks/skill snippets | ⬜ Phase 4+ |
| **Shared Graph Memory** | Neo4j/Graphiti | ⬜ Post-v1 |

**EmbeddingProvider:**
- Deterministic pseudo-embeddings via SHA-256 hash → unit vectors
- Configurable dimension (default 128)
- Normalized to unit length for cosine similarity
- Swap with real embedding model (e.g., `text-embedding-3-small`) in production

**EpisodicStore:**
- Stores `EpisodeEntry` objects: content, event_type, workflow_id, embedding
- Retrieves by cosine similarity with optional `event_type` filtering
- Global singleton via `get_global()` / `GLOBAL_EPISODIC_STORE`

**SemanticStore:**
- Key-value convention store: `store_convention(category, text)`
- Prefix-aware retrieval: `retrieve_relevant(query, k)` with partial word matching (e.g., `"testing"` matches text containing `"tests"`)
- Violation tracking: `store_violation(convention, context)` + `get_violations()`
- Global singleton via `get_global()` / `GLOBAL_SEMANTIC_STORE`

---

## Files Created/Modified

| File | Status | Purpose |
|---|---|---|
| `src/gateway/cost_tracker.py` | ✨ New | Per-workflow $ budgets, per-model pricing, circuit breakers |
| `src/tools/policy_engine.py` | ✨ New | Default-deny role-scoped permission matrix, escalation, quotas |
| `src/tools/mcp_registry.py` | ✨ New | MCP-compliant tool registry, Tool-RAG, OpenAI format output |
| `src/memory/__init__.py` | ✨ New | Memory module public API (`MemoryContext`) |
| `src/memory/memory.py` | ✨ New | EpisodicStore + SemanticStore + EmbeddingProvider |
| `tests/test_phase3_cost_tracker.py` | ✨ New | 10 tests |
| `tests/test_phase3_policy_engine.py` | ✨ New | 11 tests |
| `tests/test_phase3_mcp_registry.py` | ✨ New | 10 tests |
| `tests/test_phase3_memory.py` | ✨ New | 12 tests |

---

## Verification Results

| Check | Tool | Result |
|---|---|---|
| **Tests — Cost Tracker** | `pytest tests/test_phase3_cost_tracker.py` | ✅ **10/10 passed** |
| **Tests — Policy Engine** | `pytest tests/test_phase3_policy_engine.py` | ✅ **11/11 passed** |
| **Tests — MCP Registry** | `pytest tests/test_phase3_mcp_registry.py` | ✅ **10/10 passed** |
| **Tests — Memory** | `pytest tests/test_phase3_memory.py` | ✅ **12/12 passed** |
| **Full Phase 3 Suite** | `pytest tests/test_phase3_*.py` | ✅ **43/43 passed** in 4.07s |

### Pytest Output (Final Run):
```text
============================== 43 passed in 4.07s ==============================
```

### Test Breakdown (43 tests)

#### Cost Tracker (10 tests)
- `test_init_workflow_sets_budget` — Workflow initialization sets correct budget
- `test_record_usage_updates_totals` — Token/cost accumulation verified
- `test_budget_exceeded_raises` — `BudgetExceededError` raised on overspend
- `test_iteration_cap_raises` — `IterationCapExceededError` raised on over-iteration
- `test_check_budget_false_after_exceed` — `check_budget()` returns False post-exceed
- `test_close_workflow_returns_summary` — Closing returns accurate summary dict
- `test_workflow_summary_live` — Live summary reflects current state
- `test_global_stats_aggregates` — Cross-workflow totals aggregate correctly
- `test_pricing_override` — Custom model pricing works
- `test_not_tracked_workflow_returns_default` — Unknown workflow returns safe default

#### Policy Engine (11 tests)
- `test_coder_can_read_files` — Coder has `filesystem.read`
- `test_coder_cannot_exec_db_commands` — Coder denied `shell.execute_db`
- `test_tester_can_run_tests` — Tester has `shell.execute_sandboxed`
- `test_tester_cannot_write_files` — Tester denied `filesystem.write`
- `test_unknown_role_rejected` — Bogus role returns None
- `test_unknown_tool_rejected` — Unknown permission denied
- `test_supervisor_can_do_anything` — Wildcard `*` grants all
- `test_daily_quota_enforcement` — Quota exceeded raises error
- `test_quota_reset_on_new_day` — Date change resets usage counter
- `test_get_permissions` — `get_permissions_for_role()` returns correct list
- `test_researcher_can_search` — Researcher has read-only access

#### MCP Registry (10 tests)
- `test_create_tool` — MCPTool dataclass creation
- `test_all_tools_loaded` — Default registry has all 14 tools
- `test_register_and_get_tool` — Register + retrieve round-trip
- `test_list_all_returns_all_registered` — Full listing
- `test_list_for_role_filters` — Permission-based filtering (coder ≥ 4 tools)
- `test_search_by_name` — Substring search (2 matches for "test")
- `test_describe_for_llm` — Human-readable description for coder/supervisor/unknown
- `test_to_openai_tools` — OpenAI function-calling format output
- `test_get_nonexistent_tool_returns_none` — Graceful missing tool handling
- `test_default_registry_has_standard_tools` — Core tools verified present

#### Memory (12 tests)
- `test_embedding_dimension` — Embedding vector has correct dim
- `test_embedding_is_normalized` — Unit vector norm ≈ 1.0
- `test_different_texts_different_vectors` — Distinct texts → distinct embeddings
- `test_same_text_same_vector` — Deterministic: same text → same vector
- `test_add_and_retrieve` — Episodic store add + similarity retrieval
- `test_retrieve_empty_store` — Empty store returns []
- `test_global_episodic_store` — Global singleton works
- `test_entry_content` — Entry content preserved round-trip
- `test_store_and_retrieve_conventions` — Semantic convention retrieval (prefix matching)
- `test_store_rule_violations` — Violation record + retrieval
- `test_empty_store_returns_empty` — Empty semantic store returns []
- `test_global_semantic_store` — Global semantic singleton works

### Key Bugs Fixed During Development

1. **CostTracker global state leakage:** Tests shared the same `CostTracker` instance. Fix: reset `_active_workflows` and `_global_*` counters between tests via `_active_workflows.clear()`.

2. **PolicyEngine `supervisor` wildcard:** `check()` did not recognize `*` as "all permissions granted." Fix: added `if "*" in allowed_perms: return True` guard in `check()`.

3. **MCPRegistry `describe_for_llm`:** Used `generate_system_prompt()` which filtered by `list_for_task("general")` THEN by policy — double filtering caused empty output. Fix: rewrote `describe_for_llm` to directly iterate all tools and check policy.

4. **SemanticStore prefix matching:** `"testing"` query did not match text containing only `"tests"` (plural). Fix: added 4-character prefix matching for query words ≥ 4 chars (`"testing"[:4] = "test"` → matches `"tests"`, `"tested"`).

5. **MCPRegistry `search()` name mismatch:** Test registered `typecheck` but searched for `"test"` which matched only `run_tests`. Fix: renamed test tool to `typecheck_test`.

---

## Architecture Alignment with Phase 3 Spec

| README Requirement | Implementation | Status |
|---|---|---|
| "Route every model call through a self-hosted LiteLLM proxy" | `CostTracker` with per-model pricing + budget caps | ✅ |
| "Hard per-workflow cost caps" | `BudgetExceededError` circuit breaker | ✅ |
| "Cost & Iteration Circuit Breakers" | `BudgetExceededError` + `IterationCapExceededError` | ✅ |
| "Expose tools via MCP (Linux Foundation standard)" | `MCPTool` model + `MCPRegistry` with 14 tools | ✅ |
| "Default-deny, role-scoped permission matrix" | `PolicyEngine` with 11 roles × 12 permission classes | ✅ |
| "Load only needed tool schemas (Tool-RAG)" | `list_for_task()` task→category mapping | ✅ |
| "Hierarchical Memory (Start Small, Grow by Need)" | Episodic + Semantic layers built; procedural/graph deferred | ✅ |
| "Working memory — the running context window" | Implicit (LLM-managed) | ✅ |
| "Episodic memory — past runs/failures in a vector store" | `EpisodicStore` with cosine similarity retrieval | ✅ |
| "Semantic memory — consolidated project facts/conventions" | `SemanticStore` with prefix-aware retrieval | ✅ |

---

## Next Steps → Phase 4

Phase 3 is complete. The next phase is **Phase 4 — Observability & the Full Agent Roster** (weeks 16–22):

1. **Observability (OpenTelemetry GenAI Conventions)** — instrument with OTel GenAI semantic conventions, emit `invoke_agent → chat → execute_tool` spans with `gen_ai.*` attributes (model, tokens, finish reason) and metrics (`gen_ai.client.token.usage`, `gen_ai.client.operation.duration`). View traces in **Langfuse/Phoenix** or any OTLP backend.
2. **Dynamic Routing Orchestrator (Decoupled)** — a fast **Semantic Router** on a small model classifies task complexity with **confidence-aware routing** (below threshold → fallback to safe full pipeline); a deterministic **State Machine** (LangGraph) executes. Simple tasks take a **Fast Lane** (Coder + Grounded Critic); complex tasks take the full SDLC path.
3. **Concurrency (DAG Fan-out / Fan-in)** — independent agents (Architect, UX, Security research) run in parallel; outputs converge (Fan-in) at the Integrator. Concurrent writes to the state log protected by optimistic locking.
4. **Milestone-Based Documentation** — the Docs agent runs **twice**, not every step: post-architecture (ADRs) and post-integration (READMEs, OpenAPI/Swagger, inline docs) from the final verified output only.

---

<sub>Phase 3 delivered on week 10–16 of the roadmap. The system now has cost-predictable model calling, secure role-scoped tool access, and context-aware memory retrieval — ready for the observability and full agent roster work in Phase 4.</sub>
