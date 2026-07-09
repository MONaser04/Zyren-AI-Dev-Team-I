# 🏛️ Complete Project Analysis + Professional Phase 3 Implementation Plan

---

## 📊 First: Analysis of the Current Project State (Phase 0 → Phase 2 Completed)

### What has been built so far:

| Layer | Existing Components | Status |
|---|---|---|
| **Phase 0 — Foundation** | `pyproject.toml` + `uv.lock`, `Makefile`, `docker-compose.yml` (Postgres, Qdrant, LiteLLM proxy, Jaeger), complete folder structure, `.env.example`, `config/litellm.yaml`, golden tasks skeleton | ✅ Complete |
| **Phase 1 — Minimal Loop** | `src/contracts/schemas.py` (5 strict Pydantic contracts), `src/state/` (Event Store SQLite + optimistic locking + projections), `src/gateway/llm_client.py` (LiteLLM wrapper with retry + structured output), `src/agents/` (Coder, Tester, Critic + BaseAgent), `src/orchestrator/graph.py` (LangGraph loop with hard cap), `src/orchestrator/runner.py`, `config/agents/coder.yaml` + `critic.yaml` | ✅ Complete |
| **Phase 2 — Founded Verification** | `src/verification/runner.py` + `steps.py` (Ruff, Mypy, Pytest, Syntax, Bandit), added `RebuttalRequest` + `EscalationLevel` + coverage/security for contracts, escalation ladder in Critic, `CriticFactory` (coder/architect/security critics), rebuttal edge in LangGraph, `config/agents/security_critic.yaml` | ✅ Complete |

### Tests: **120+ tests** all passing (Contracts, State, Agents, Orchestrator, Verification)

### Gaps Observed Before Phase 3:
1. `src/memory/` — Completely empty (only `__init__.py`)
2. `src/tools/` — Completely empty (only `__init__.py`)
3. `src/observability/` — Completely empty (only `__init__.py`)
4. `src/resilience/` — Completely empty (only `__init__.py`)
5. No actual use of Docker sandbox — Tester runs in temp dir with subprocess
6. LiteLLM Proxy in `docker-compose.yml` exists but current Gateway (`llm_client.py`) calls `litellm` directly without going through the Proxy
7. No MCP protocol implementation — current tools are embedded directly in Tester
8. No memory system (episodic/semantic) — the only memory is the context window
9. No actual cost tracking or circuit breakers
10. `policies.yaml` exists but is not actually used in the code

---

## 🎯 Second: Professional Phase 3 Implementation Plan

> **Phase 3 = Gateway, Tools & Memory** (Week 10–16 according to README)
> 
> Requirements from README (lines 235–248):
> 1. ✅ LLMOps Gateway (LiteLLM Proxy routing, fallback chains, cost caps)
> 2. ✅ Cost & Iteration Circuit Breakers
> 3. ✅ Decoupled Tool Registry (MCP + default-deny permissions)
> 4. ✅ Secure Execution Sandbox (Docker → gVisor path)
> 5. ✅ Hierarchical Memory (working → episodic → semantic)

---

## 📋 Detailed Implementation Plan — 6 Components:

```
COMPONENT 1  →  Gateway Upgrade (LiteLLM Proxy + Cost Tracking)
COMPONENT 2  →  Circuit Breakers (Budget + Iteration Caps)
COMPONENT 3  →  MCP Tool Registry (Protocol + Default-Deny Matrix)
COMPONENT 4  →  Docker Sandbox (Hardened Execution)
COMPONENT 5  →  Hierarchical Memory (Episodic via Qdrant + Semantic)
COMPONENT 6  →  Tests + Integration + Verification
```

---

### 🔹 COMPONENT 1 — Gateway Upgrade: LiteLLM Proxy + Cost Tracking
**Files:** `src/gateway/llm_client.py` major modification + new files

#### 1A. [MODIFY] `src/gateway/llm_client.py` — Upgrade GatewayClient

Current status: `LLMClient` calls `litellm.completion()` directly (direct SDK calls).
Required in Phase 3: Routing through **LiteLLM Proxy** (located in `docker-compose.yml`) — this provides:
- Automatic routing + fallback chains via Proxy
- Hard cost caps at Proxy level (global budget)
- Single OpenAI-compatible endpoint for all models

**Modifications:**
```python
class GatewayClient:
    """Phase 3: routes ALL calls through self-hosted LiteLLM Proxy."""
    
    def __init__(self, proxy_base_url: str, proxy_api_key: str, 
                 model_map: dict, enable_cost_tracking: bool = True):
        # Use openai.OpenAI client pointing to proxy_base_url
        # Instead of direct litellm.completion
        
    def complete_text(...) -> str:
        # Uses self._openai_client.chat.completions.create(...)
        # Model = alias resolved via proxy
        
    def complete_structured(...) -> T:
        # Same mechanism with response_format={"type": "json_object"}
        
    def estimate_tokens(self, messages) -> int:
        # Token estimation for cost tracking (tiktoken or litellm.token_counter)
        
    def get_usage_stats(self) -> UsageStats:
        # Aggregate usage from all calls (prompt_tokens, completion_tokens, cost)
```

#### 1B. [NEW] `src/gateway/cost_tracker.py` — Cost Tracker

```python
class CostTracker:
    """Per-workflow cost tracking with real-time budget monitoring."""
    
    def __init__(self, workflow_budget_usd: float, global_budget_usd: float):
        ...
    
    def record_call(self, model: str, prompt_tokens: int, completion_tokens: int):
        # Calculates cost based on model pricing table
        # Adds to workflow budget tracker
        
    def check_budget(self) -> BudgetStatus:
        # Returns: OK | WARNING (>80%) | EXCEEDED
        # BudgetStatus contains remaining, consumed, percentage
        
    def remaining_budget(self) -> float:
        ...
```

#### 1C. [NEW] `src/gateway/model_registry.py` — Model Registry with Pricing

```python
@dataclass
class ModelEntry:
    alias: str              # "frontier", "fast", "critic"
    proxy_name: str         # Name registered in LiteLLM proxy
    provider: str           # openai, anthropic, gemini
    input_cost_per_1k: float
    output_cost_per_1k: float
    capabilities: list[str] # ["code", "review", "routing", ...]

MODEL_REGISTRY: dict[str, ModelEntry] = {
    "frontier": ModelEntry(alias="frontier", proxy_name="frontier", ...),
    "fast":     ModelEntry(alias="fast", proxy_name="fast", ...),
    "critic":   ModelEntry(alias="critic", proxy_name="critic", ...),
    "fallback": ModelEntry(alias="fallback", proxy_name="fallback", ...),
}
```

#### 1D. [MODIFY] `config/litellm.yaml` — Add Complexity-Based Routing

Add explicit routing rules:
- `frontier` ← for complex tasks (coding, architecture)
- `fast` ← for simple tasks (routing, classification)
- `critic` ← for review (different model family)
- fallback chain: `frontier → fallback` on 429/5xx with cooldown

---

### 🔹 COMPONENT 2 — Circuit Breakers (Budget + Iteration)
**Files:** `src/resilience/` (was empty)

#### 2A. [NEW] `src/resilience/circuit_breaker.py`

```python
class CircuitBreakerState(StrEnum):
    CLOSED = "closed"           # Normal operation
    OPEN = "open"               # Blocked from operating
    HALF_OPEN = "half_open"     # Testing return possibility

class BudgetCircuitBreaker:
    """Hard per-workflow cost cap circuit breaker.
    
    README spec: 'On breach → halt, block further calls, alert the human.'
    """
    def __init__(self, cost_tracker: CostTracker, 
                 hard_limit_usd: float, workflow_id: str):
        ...
    
    def before_call(self) -> bool:
        # Checks: Did we exceed the hard limit?
        # If yes → open the circuit (OPEN) → prevent any further calls
        
    def after_call(self, usage: UsageRecord):
        # Logs usage and checks proximity to the limit

class IterationCircuitBreaker:
    """Hard iteration ceiling per workflow."""
    def __init__(self, max_iterations: int):
        ...
    def check(self, current_iteration: int) -> bool:
        ...
```

#### 2B. [NEW] `src/resilience/alerting.py`

```python
class AlertLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class AlertManager:
    """Human alerting on circuit breaker trips.
    
    Phase 3 emits structured alerts. Full HITL escalation = Phase 5.
    """
    def emit(self, level: AlertLevel, workflow_id: str, 
             message: str, context: dict):
        # Writes alert to event log + console + (later) OpenClaw channel
        
    def budget_exceeded(self, workflow_id: str, limit: float, consumed: float):
        ...
    
    def iteration_cap_reached(self, workflow_id: str, cap: int):
        ...
```

#### 2C. [MODIFY] `src/orchestrator/graph.py` — Integrate Circuit Breakers

Add `guard` node before `coder`:
```
critic --BLOCK--> increment --> guard --> [check budget + iteration]
                                         ├─ OK → coder
                                         └─ BREACH → fail_with_alert
```

Add `BudgetStatus` and `AlertContext` to `GraphState`.

#### 2D. [MODIFY] `src/orchestrator/runner.py` — Initialize Circuit Breakers

`run_workflow()` accepts `budget_limit_usd: float | None` and initializes `BudgetCircuitBreaker`.

---

### 🔹 COMPONENT 3 — MCP Tool Registry + Default-Deny Permissions
**Files:** `src/tools/` (was empty)

#### 3A. [NEW] `src/tools/mcp_registry.py` — MCP Protocol Tool Registry

```python
class MCPTool(BaseModel):
    """Single tool definition per MCP spec."""
    name: str
    description: str
    input_schema: dict  # JSON Schema for tool parameters
    permissions: list[str]  # required permissions e.g., ["fs.read", "git.status"]
    
class MCPRegistry:
    """Model Context Protocol tool registry.
    
    README spec: 'Expose tools via MCP (Linux Foundation standard).'
    'Default-deny, role-scoped permission matrix.'
    """
    def __init__(self, policies: PolicyConfig):
        self._tools: dict[str, MCPTool] = {}
        self._policies = policies  # from config/policies.yaml
        
    def register(self, tool: MCPTool):
        ...
    
    def list_for_role(self, role: str) -> list[MCPTool]:
        """Filter tools by role permissions (default-deny)."""
        # Coder: fs.read, fs.write_temp, git.status, git.diff, exec.test
        # Tester: fs.read, exec.test, exec.lint, exec.typecheck
        # Security: fs.read, exec.sast
        # Orchestrator: ALL (admin override)
        
    def resolve(self, tool_name: str, role: str) -> MCPTool | None:
        """Resolve a tool, enforcing role permissions."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return None
        allowed = self._policies.check(role, tool.permissions)
        return tool if allowed else None
```

#### 3B. [NEW] `src/tools/sandbox_tools.py` — Tool Definitions

```python
# Each tool is defined as MCPTool with input_schema and permissions

FILE_READ_TOOL = MCPTool(
    name="file_read",
    description="Read file content from sandbox workspace.",
    input_schema={...},
    permissions=["fs.read"],
)

FILE_WRITE_TOOL = MCPTool(
    name="file_write",
    description="Write file content to sandbox workspace.",
    input_schema={...},
    permissions=["fs.write_temp"],
)

GIT_STATUS_TOOL = MCPTool(
    name="git_status",
    description="Run git status in sandbox workspace.",
    input_schema={...},
    permissions=["git.status"],
)

EXEC_TEST_TOOL = MCPTool(
    name="exec_test",
    description="Run pytest in sandbox.",
    input_schema={...},
    permissions=["exec.test"],
)

EXEC_LINT_TOOL = MCPTool(
    name="exec_lint",
    description="Run ruff check in sandbox.",
    input_schema={...},
    permissions=["exec.lint"],
)

EXEC_SAST_TOOL = MCPTool(
    name="exec_sast",
    description="Run bandit security scan in sandbox.",
    input_schema={...},
    permissions=["exec.sast"],
)

# Tool-RAG: load only needed schemas
def get_tools_for_task(task_type: str) -> list[MCPTool]:
    """Return only the tools relevant to the task type.
    
    Keeps LLM context small by loading only needed tool schemas.
    """
    ...
```

#### 3C. [NEW] `src/tools/tool_executor.py` — Tool Execution in Sandbox

```python
class ToolExecutor:
    """Execute MCP tools inside the sandbox."""
    
    def __init__(self, sandbox: SandboxProvider, registry: MCPRegistry):
        ...
    
    def execute(self, tool_name: str, params: dict, role: str) -> ToolResult:
        """Resolve tool, check permissions, execute in sandbox."""
        tool = self._registry.resolve(tool_name, role)
        if tool is None:
            return ToolResult(denied=True, reason=f"Permission denied for {role}")
        
        # Validate params against input_schema
        # Execute in sandbox
        # Return structured ToolResult (stdout, stderr, exit_code, files_changed)
```

#### 3D. [MODIFY] `config/policies.yaml` — Detailed Permission Matrix

```yaml
# Default-Deny Permission Matrix
roles:
  coder:
    allow:
      - fs.read
      - fs.write_temp
      - git.status
      - git.diff
      - exec.test
    deny:
      - fs.write_prod       # No writing to production
      - db.migrate          # No destructive DB operations
      - exec.prod           # No execution on production
      - network.outbound    # No outbound network connections
  
  tester:
    allow:
      - fs.read
      - exec.test
      - exec.lint
      - exec.typecheck
      - exec.sast
    deny:
      - fs.write_temp       # Tester does not write code — only reads and tests
  
  security:
    allow:
      - fs.read
      - exec.sast
    deny:
      - fs.write_temp
      - exec.test
  
  orchestrator:
    allow:
      - "*"                 # Admin override — Orchestrator has full permissions
    deny: []
```

#### 3E. [NEW] `src/tools/policy_engine.py` — Permission Engine

```python
class PolicyEngine:
    """Load and evaluate the default-deny permission matrix."""
    
    def __init__(self, policies_path: Path):
        self._matrix = self._load(policies_path)
    
    def check(self, role: str, required_permissions: list[str]) -> bool:
        """Check if a role has ALL required permissions."""
        role_policy = self._matrix.get("roles", {}).get(role)
        if role_policy is None:
            return False  # Unknown role → default deny
        
        allow_list = role_policy.get("allow", [])
        deny_list = role_policy.get("deny", [])
        
        # Wildcard admin override
        if "*" in allow_list:
            return True
        
        for perm in required_permissions:
            if perm in deny_list:
                return False
            if perm not in allow_list:
                return False  # Not explicitly allowed → default deny
        
        return True
```

---

### 🔹 COMPONENT