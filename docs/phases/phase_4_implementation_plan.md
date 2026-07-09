# 📊 Phase 4 — Observability & the Full Agent Roster

> **Implementation Plan — Professional, Ready-to-Execute**
>
> *Estimated effort: ~5–6 weeks (README: Week 16–22)*
> *Status before: Phases 0–3 ✅ Done · Phase 4 🟨 In progress*

---

## 📑 Table of Contents

1. [Context Snapshot](#context-snapshot)
2. [Phase 4 Goals (from README)](#phase-4-goals)
3. [Gap Analysis](#gap-analysis)
4. [Architecture Overview](#architecture-overview)
5. [Component Plan (6 Components)](#component-plan)
   - [Component 1 — OpenTelemetry Setup + GenAI Semantic Conventions](#component-1)
   - [Component 2 — Agent Instrumentation (Spans + Metrics)](#component-2)
   - [Component 3 — Semantic Router (Fast Lane / Full SDLC)](#component-3)
   - [Component 4 — Full Agent Roster (11 New Agents)](#component-4)
   - [Component 5 — DAG Concurrency: Fan-out / Fan-in](#component-5)
   - [Component 6 — Milestone-Based Docs + Integration + Tests](#component-6)
6. [New Event Types](#new-event-types)
7. [New Dependencies](#new-dependencies)
8. [Configuration Changes](#configuration-changes)
9. [Testing Strategy](#testing-strategy)
10. [Definition of Done — Phase 4](#definition-of-done)
11. [Execution Sequence (Task Order)](#execution-sequence)
12. [Risks & Mitigations](#risks)

---

<a id="context-snapshot"></a>
## 1. Context Snapshot (What Exists Today)

### Stack Confirmed from Code Reading

| Layer | Implemented Component | Status |
|---|---|---|
| **Engine** | LangGraph StateGraph with rebuttal edge (`src/orchestrator/graph.py`) + `runner.py` | ✅ |
| **State** | SQLite Event Store (`src/state/store.py`) + 11 EventTypes (`events.py`) + projections + optimistic locking (`version`) | ✅ |
| **Contracts** | 10 Pydantic v2 strict contracts (`src/contracts/schemas.py`) | ✅ |
| **Gateway** | LiteLLM client with cost tracking + fallback + jitter + circuit breaker (`src/gateway/`) | ✅ |
| **Agents** | `BaseAgent` (ABC) + Coder + Tester + Critic + CriticFactory — **4 of 14 roles** | ✅ partial |
| **Verification** | Ruff, Mypy, Pytest, Syntax, Bandit + escalation ladder + rebuttal | ✅ |
| **Tools** | MCP registry (14 tools) + PolicyEngine (11 roles × 12 permissions) + sandbox + executor | ✅ |
| **Memory** | Memory + EpisodicStore + SemanticStore + EmbeddingProvider | ✅ |
| **Resilience** | **Empty** (`__init__.py` only — Phase 5 scope) | ⬜ |
| **Observability** | **Empty** (`__init__.py` only) — Phase 4 builds this | ⬜ |

### Code Conventions (to be followed in Phase 4)
- `snake_case.py` file names, docstrings cite the phase explicitly (`"Phase 4 additions:"`).
- `BaseAgent(ABC)` for every new agent: `agent_id`, `role`, `llm_client`, `__repr__`.
- Pydantic v2 `BaseContract(strict=True, frozen=True, extra="forbid")` for inter-agent contracts.
- `EventType` StrEnum + `_make_event()` factory + event→store.
- LangGraph `StateGraph(GraphState)` with `add_conditional_edges` and pure-function routers.
- Tests in `tests/test_phase4_*.py`, isolated, mocked LLM, ~10–12 assertions per component.

---

<a id="phase-4-goals"></a>
## 2. Phase 4 Goals (Verbatim from README §10, Lines 282–296)

> **4.1 Observability (OpenTelemetry GenAI Conventions):** instrument with OTel GenAI semantic conventions (2026 standard). Emit `invoke_agent → chat → execute_tool` spans with `gen_ai.*` attributes (model, in/out tokens, finish reason) and metrics (`gen_ai.client.token.usage`, `gen_ai.client.operation.duration`). Prompt-content capture **off by default** (privacy). View traces in Langfuse/Phoenix or any OTLP backend. Exposes silent failures, loops, cost hotspots.

> **4.2 Dynamic Routing Orchestrator (Decoupled):**
> 1. a fast Semantic Router on a small model classifies task complexity with confidence-aware routing — below threshold it falls back to the safe full pipeline;
> 2. a deterministic State Machine (LangGraph) executes. Simple tasks take a Fast Lane (Coder + Grounded Critic); complex tasks take the full SDLC path.

> **4.3 Concurrency (DAG Fan-out / Fan-in):** independent agents (Architect, UX, Security research) run in parallel; outputs converge (Fan-in) at the Integrator. Concurrent writes to the state log are made safe by optimistic locking. LangGraph does this natively.

> **4.4 Milestone-Based Documentation:** the Docs agent runs **twice**, not every step — post-architecture (ADRs) and post-integration (READMEs, OpenAPI/Swagger, inline docs) from the final verified output only.

---

<a id="gap-analysis"></a>
## 3. Gap Analysis (Phase 3 → Phase 4)

| # | Gap | README Requirement | Phase 4 Component |
|:---:|---|---|---|
| 1 | `src/observability/` is empty; no OTel deps in `pyproject.toml` | §4.1 Observability | **C1** |
| 2 | No span/metric instrumentation on agents, LLM calls, tools | §4.1 Observability | **C2** |
| 3 | Orchestrator is single-path (`assign_task → coder → tester → critic`); no routing | §4.2 Semantic Router + Fast Lane | **C3** |
| 4 | Only 4 agents built; 10 roles missing: Product Analyst, Planner, Architect, UX, DB Engineer, Researcher, Integrator, Security, Docs, Liaison, Supervisor | §Roster (14 roles); §4.2 full SDLC path | **C4** |
| 5 | No DAG Fan-out/Fan-in; no Integrator; no parallel agent execution | §4.3 Concurrency | **C5** |
| 6 | No Docs agent; no ADR post-architecture; no READMEs/OpenAPI post-integration | §4.4 Milestone-Based Docs | **C6** |
| 7 | `OTLP_GRPC_PORT`/`OTLP_HTTP_PORT` set in `.env`, Jaeger in `docker-compose.yml`, but nothing emits traces yet | §4.1 (infra ready, code missing) | **C1+C2** |

---

<a id="architecture-overview"></a>
## 4. Architecture Overview (After Phase 4)

```mermaid
graph TD
    START["START"] --> ASSIGN["assign_task<br/>(emit TASK_CREATED)"]
    ASSIGN --> ROUTE["route (Semantic Router)"]

    ROUTE -->|"fast_lane: SIMPLE + high confidence"| FAST["Fast Lane:<br/>Coder → Tester → Critic"]
    ROUTE -->|"full_lane: MEDIUM/COMPLEX or low confidence"| FULL["Full SDLC"]

    subgraph FAST["Fast Lane"]
        C1["coder"] --> T1["tester"] --> K1["critic"]
        K1 -->|"PASS"| COMPLETE
        K1 -->|"BLOCK + cap"| FAIL
        K1 -->|"BLOCK + rebuttal"| REBUT_PATH
    end

    subgraph FULL["Full SDLC Path"]
        PA["Product Analyst<br/>(PRD)"] --> PL["Planner<br/>(TaskDAG)"] --> AR["Architect<br/>(ADRs)"]
        AR --> FANOUT["Fan-out (parallel)"]
        FANOUT --> UX["UX<br/>(conditional)"]
        FANOUT --> DB["DB Engineer<br/>(conditional)"]
        FANOUT --> SEC["Security<br/>(SAST)"]
        FANOUT --> RES["Researcher<br/>(on-demand)"]
        FANOUT --> COD2["Coder"]
        UX --> INTEG["Integrator (Fan-in)"]
        DB --> INTEG
        SEC --> INTEG
        RES --> INTEG
        COD2 --> INTEG
        INTEG --> DOC_ARCH["Docs (post-arch ADRs)"]
        DOC Arch --> VERIFY2["Tester → Critic"]
        VERIFY2 -->|"PASS"| DOC_INT["Docs (post-integration)"]
        VERIFY2 -->|"BLOCK"| COD2
        DOC_INT --> COMPLETE
    end

    COMPLETE["complete<br/>(WORKFLOW_COMPLETED)"] --> ENDNODE["END"]
    FAIL["fail<br/>(WORKFLOW_FAILED)"] --> ENDNODE
    REBUT_PATH["coder_rebut → judge"] --> COMPLETE

    classDef phase4 fill:#fef3c7,stroke:#d97706
    class ROUTE,PA,PL,AR,FANOUT,UX,DB,SEC,RES,INTEG,DOC Arch,DOC_INT phase4
    straight-arrow: def default
```

**New Phase 4 components are highlighted.** The Fast Lane reuses the existing Phase 1–2 feedback loop as-is; the Full SDLC path is the new roster + DAG.

---

<a id="component-plan"></a>
## 5. Component Plan (6 Components)

Each component is independently buildable and testable, ordered by dependency.

---

<a id="component-1"></a>
### 🔹 Component 1 — OpenTelemetry Setup + GenAI Semantic Conventions

**Goal:** Provide the tracing/metrics foundation that every agent, LLM call, and tool execution will emit to.

**Files:**
| Action | File | Description |
|---|---|---|
| modify | `pyproject.toml` | Add OTel deps |
| modify | `src/observability/__init__.py` | Public API exports |
| new | `src/observability/tracing.py` | Tracer setup + OTLP exporter + GenAI attribute constants |
| new | `src/observability/metrics.py` | Counters + Histograms (`gen_ai.client.token.usage`, `gen_ai.client.operation.duration`) |
| new | `tests/test_phase4_observability_setup.py` | Unit tests |

#### 1A. `pyproject.toml` — Add Dependencies

```toml
dependencies = [
    # ... existing ...
    # --- Observability (Phase 4) ---
    "opentelemetry-api>=1.28,<2.0",
    "opentelemetry-sdk>=1.28,<2.0",
    "opentelemetry-exporter-otlp-proto-http>=1.28,<2.0",
]
```

> **Note:** `opentelemetry-semantic-conventions-ai` is used as an optional helper only. The GenAI attribute key constants are also defined locally in `tracing.py` as a fallback (the spec is open and stable enough). If the helper package is unavailable on PyPI at build time, fall back to local constants — identical string values.

#### 1B. `src/observability/tracing.py`

```python
"""
Observability — OpenTelemetry Tracing Setup (Phase 4)
=====================================================

Initializes the global TracerProvider with an OTLP HTTP exporter
so traces can be viewed in Jaeger (docker-compose service) or any
OTLP-compatible backend (Langfuse, Phoenix).

Implements the OpenTelemetry GenAI semantic conventions (2026):
  - Span names: invoke_agent.<role>, chat, execute_tool.<name>
  - Attributes: gen_ai.system, gen_ai.request.model, gen_ai.response.model,
    gen_ai.usage.input_tokens, gen_ai.usage.output_tokens,
    gen_ai.response.finish_reason

Privacy: prompt/completion content capture is OFF by default
(read .env OTEL_CAPTURE_PROMPTS, default "0").
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# --- GenAI Semantic Convention Attribute Keys (stable subset) ---
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_RESPONSE_FINISH_REASON = "gen_ai.response.finish_reason"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_AGENT_ROLE = "agent.role"

# Span name templates
SPAN_INVOKE_AGENT = "invoke_agent.{role}"
SPAN_CHAT = "chat"
SPAN_EXECUTE_TOOL = "execute_tool.{name}"
SPAN_WORKFLOW = "workflow.{workflow_id}"

_TRACER_NAME = "ai-dev-team.genai"
_initialized = False


@dataclass(frozen=True)
class TracingConfig:
    """Configuration for the OTel tracer."""
    service_name: str = "ai-dev-team"
    otlp_endpoint: str = "http://localhost:4318"  # OTLP HTTP default
    capture_prompts: bool = False  # privacy: OFF by default (README §4.1)


def setup_tracing(config: TracingConfig | None = None) -> None:
    """Initialize global tracing. Idempotent — safe to call multiple times."""
    global _initialized
    if _initialized:
        return
    if config is None:
        config = _config_from_env()
    resource = Resource.create({"service.name": config.service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{config.otlp_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer() -> trace.Tracer:
    """Get the GenAI tracer (lazily initializes if needed)."""
    if not _initialized:
        setup_tracing()
    return trace.get_tracer(_TRACER_NAME)


def _config_from_env() -> TracingConfig:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    capture = os.getenv("OTEL_CAPTURE_PROMPTS", "0") == "1"
    return TracingConfig(otlp_endpoint=endpoint, capture_prompts=capture)
```

#### 1C. `src/observability/metrics.py`

```python
"""
Observability — OpenTelemetry Metrics (Phase 4)
================================================

Implements the two GenAI metrics called out in README §4.1:
  - gen_ai.client.token.usage  (Counter, attrs: model, type=input|output)
  - gen_ai.client.operation.duration  (Histogram, attrs: operation, model)

Plus domain-specific counters:
  - agent.invocations (attrs: agent_role, verdict)
  - tool.executions (attrs: tool_name, role, success)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

_meter_name = "ai-dev-team.genai"
_initialized = False
_meter: metrics.Meter | None = None

# Metric instruments (lazily created)
token_usage_counter: metrics.Counter | None = None
operation_duration_hist: metrics.Histogram | None = None
agent_invocations_counter: metrics.Counter | None = None
tool_executions_counter: metrics.Counter | None = None


@dataclass(frozen=True)
class MetricsConfig:
    otlp_endpoint: str = "http://localhost:4318"
    export_interval_ms: int = 5000


def setup_metrics(config: MetricsConfig | None = None) -> None:
    """Initialize global metrics. Idempotent."""
    global _initialized