# 📋 COMPREHENSIVE MASTER EXECUTION PLAN
## Zyren — Provider-Agnostic Implementation to Match README Claims

> **Document Version:** 1.0 | **Created:** 2026-07-11 | **Status:** READY FOR EXECUTION
> **Scope:** Close ALL gaps between README claims (Phase 6 Complete) and actual implementation (Phase 2-3 partial)
> **Location:** `docs/COMPREHENSIVE_MASTER_PLAN.md`

---

## 🎯 EXECUTIVE SUMMARY

### Current Reality vs. README Claims

| Component | README Claims | Actual Implementation | Gap |
|-----------|---------------|----------------------|-----|
| **Model Registry** | AutoModelRegistry with 10+ providers, verified ground truth | ❌ MISSING - Only hardcoded 4 NVIDIA NIM models | 100% |
| **Smart Gateway** | SmartGateway + SmartRouter + Resilience Layer | ❌ MISSING - Only basic LLMClient | 100% |
| **Professional Researcher** | Zero-LLM-knowledge, official docs only, citations | ❌ MISSING - Only basic ResearcherAgent | 100% |
| **Provider Adapters** | 10+ adapters (OpenAI, Anthropic, Google, Azure, AWS, Ollama, Together, Fireworks, Groq, NVIDIA) | ❌ MISSING - No providers/ directory | 100% |
| **MCP Tools** | Full MCP registry with default-deny permissions | ⚠️ PARTIAL - Registry exists, no real MCP server | 70% |
| **Sandbox** | Hardened Docker → gVisor → Firecracker | ⚠️ PARTIAL - DockerSandboxProvider exists but unused | 60% |
| **Observability** | OpenTelemetry GenAI conventions, Langfuse/Phoenix | ⚠️ PARTIAL - Tracing setup exists, not integrated | 50% |
| **Evaluation** | SWE-bench Verified + Golden Set + Red-teaming | ❌ MISSING - Skeleton files only | 90% |
| **Self-Improvement** | DSPy/GEPA optimization loop | ❌ MISSING - Placeholder files only | 100% |
| **HITL/Liaison** | Natural language → system action | ⚠️ PARTIAL - Scaffold exists, not connected | 80% |

### Overall Completion: **~37%** (README says Phase 6 Complete = 100%)

---

## 🏗️ CORE ARCHITECTURAL PRINCIPLES (NON-NEGOTIABLE)

### 1. Provider-Agnostic Architecture (CRITICAL)

```
┌─────────────────────────────────────────────────────────────┐
│                    SMART ROUTER (الدماغ)                    │
│  Input: TaskRequirements {complexity, capabilities, budget}│
│  Logic: Score ALL discovered models from ALL providers     │
│  Output: Best model + fallback chain (ZERO provider bias)  │
└─────────────────────────────────────────────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌─────────┐   ┌─────────┐   ┌─────────┐
        │Provider │   │Provider │   │Provider │
        │ Adapter │   │ Adapter │   │ Adapter │
        │(NVIDIA) │   │(OpenAI) │   │(Local)  │
        └────┬────┘   └────┬────┘   └────┬────┘
             │             │             │
        ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
        │Auto-    │   │Auto-    │   │Auto-    │
        │discovered│  │discovered│  │discovered│
        │models   │   │models   │   │models   │
        └─────────┘   └─────────┘   └─────────┘
```

**Rule:** The SmartRouter knows NOTHING about providers. It only sees ModelSpecs with capabilities, pricing, limits. Provider is just a metadata field.

### 2. Verified Ground Truth for Data Layer | Full LLM Reasoning for Reasoning Layer

| Layer | Policy | Components |
|-------|--------|------------|
| **Data Layer** | **Verified Only + Citations** | ModelRegistry, SmartGateway, ProviderAdapters, CostTracker, ConfigManager |
| **Reasoning Layer** | **Full LLM Reasoning** | Coder, Architect, Critic, Planner, Researcher, Tester, Liaison |

> **Rule:** Data Layer never guesses. Reasoning Layer never stops reasoning.

### 3. Auto-Discovery Default + Manual Override Via Liaison Chat
- System starts in **Auto Mode**: discovers, validates, registers models from official sources
- User says: *"أضف gpt-4o-mini من Azure eastus2 واجعله افتراضي للمهام البسيطة"* → System executes end-to-end
- No code changes, no config file edits, no restarts

### 4. Zero Real API Calls in Tests
- All tests use `MockGateway`, `MockProviderAPIs`, `MockEventStore`
- CI/CD runs completely offline

### 5. Circuit Breakers Everywhere
- Per-model, per-provider, per-workflow budget caps
- Automatic fallback chains with cooldown
- Health monitoring with alerting

---

## 🔑 STRATEGIC ASSET: NVIDIA NIM (Test Case, Not Bias)

**User has NVIDIA API key with access to ~77 models** via single endpoint:
- Single API key → `https://integrate.api.nvidia.com/v1`
- Models include: Nemotron, Llama, Mistral, Gemma, Qwen, DeepSeek, CodeLlama, StarCoder, Phi, and more
- **This is a TEST CASE for auto-discovery** — not a bias toward NVIDIA

The NVIDIA adapter will discover all 77 models and classify them by capabilities (context window, modalities, function calling, etc.) — NOT by provider name.

---

## 📋 PHASE OVERVIEW

| Phase | Focus | Duration | Key Deliverable |
|-------|-------|----------|-----------------|
| **0** | Critical Fixes | Day 1 | Circular imports fixed, mock infra, unified model map |
| **1** | Universal Model Registry | Days 2-4 | AutoModelRegistry + 10 Provider Adapters + NVIDIA 77 models |
| **2** | Professional Researcher | Days 5-7 | Zero-LLM-knowledge agent + 8 Doc Fetchers |
| **3** | Smart Gateway + Router | Days 8-10 | SmartGateway (ONLY gateway) + SmartRouter (6-factor) |
| **4** | Full Agent Roster | Days 11-13 | 14 agents in LangGraph with fan-out/fan-in |
| **5** | Production Hardening | Days 14-16 | OTel GenAI, Docker sandbox, budgets, CI/CD |
| **6** | Evaluation Suite | Days 17-19 | Golden 50+, SWE-bench, Red-team, Judge calibration |
| **7** | Self-Improvement | Days 20-22 | DSPy/GEPA, Model Optimiser, Convergence |
| **8** | E2E Validation | Days 23-25 | 411 tests pass, scenarios verified, sign-off |

---

## ✅ SUCCESS CRITERIA (NON-NEGOTIABLE)

- **411/411 tests pass** with **ZERO real API calls**
- **Zero circular imports**
- **Ruff + MyPy clean** (strict mode)
- **100% ModelSpec fields have SourceCitation**
- **NVIDIA 77 models auto-discovered on startup**
- **Liaison NL commands work** ("أضف gpt-4o من Azure")
- **Golden Set: 50+ tasks, >80% pass rate**
- **SWE-bench: >30% resolved on Verified** (or documented baseline)
- **Red-team: OWASP Top 10 2026 scanned, 0 critical findings**
- **Judge calibrated: Cohen's κ > 0.6**
- **Self-improvement: DSPy GEPA ran, prompts updated, validated on golden**

---

# 🔍 COMPREHENSIVE GAP ANALYSIS
## Every Missing Component Documented (100% Coverage) — Provider-Agnostic View

> Based on systematic analysis of 90+ source files vs. README claims

---

## 📊 GAP CLASSIFICATION LEGEND
- 🔴 **CRITICAL** - Blocking: system cannot function as claimed
- 🟠 **HIGH** - Major: core feature missing/broken
- 🟡 **MEDIUM** - Significant: feature partial/non-functional
- 🟢 **LOW** - Minor: enhancement/polish needed

---

## 1. MODEL REGISTRY & AUTO-DISCOVERY (Phase 1) 🔴🔴🔴

| Missing Component | Status | Effort | Files to Create |
|---|---|---|---|
| `AutoModelRegistry` class | 🔴 MISSING | 3 days | `src/gateway/model_registry.py` |
| `ModelSpec`, `ModelCapabilities`, `ModelPricing`, `ModelLimits` dataclasses | 🔴 MISSING | 1 day | `src/gateway/model_registry.py` |
| `SourceCitation` with confidence scoring | 🔴 MISSING | 0.5 day | `src/gateway/model_registry.py` |
| `ModelStatus` enum (ACTIVE, DEPRECATED, DISABLED, UNVERIFIED) | 🔴 MISSING | 0.5 day | `src/gateway/model_registry.py` |
| `DiscoveryReport`, `RoutingCriteria`, `ModelFilters` | 🔴 MISSING | 0.5 day | `src/gateway/model_registry.py` |
| Provider Adapter base class (ABC) | 🔴 MISSING | 1 day | `src/gateway/providers/base.py` |
| **10 Provider Adapters** | 🔴 MISSING | 5 days | `src/gateway/providers/*.py` |
| ProviderAdapterRegistry | 🔴 MISSING | 0.5 day | `src/gateway/providers/registry.py` |
| Cross-validation with ProfessionalResearcher | 🔴 MISSING | 1 day | `src/gateway/model_registry.py` |
| Scheduled refresh background task | 🔴 MISSING | 0.5 day | `src/gateway/model_registry.py` |
| Manual override API (add/update/disable/enable) | 🔴 MISSING | 1 day | `src/gateway/model_registry.py` |
| Capabilities-based auto-classification | 🔴 MISSING | 1 day | `src/gateway/model_registry.py` |

**Provider Adapters Needed (10 - all equal, no priority):**
1. `openai_adapter.py` - `/v1/models`, pricing.openai.com
2. `anthropic_adapter.py` - static list, anthropic.com/pricing
3. `google_adapter.py` - Vertex Model Garden, cloud pricing
4. `nvidia_nim_adapter.py` - `/v1/models`, build.nvidia.com
5. `azure_adapter.py` - `/openai/deployments`, Azure pricing
6. `aws_bedrock_adapter.py` - Bedrock ListFoundationModels
7. `ollama_adapter.py` - `/api/tags`, free
8. `together_adapter.py` - Together AI API
9. `fireworks_adapter.py` - Fireworks API
10. `groq_adapter.py` - Groq API

**Auto-Classification Logic (Provider-Agnostic):**
```python
def classify_model(model_id: str, details: RawModelDetails) -> ModelTier:
    """Classify by capabilities, NOT provider name"""
    context = details.context_window
    modalities = details.modalities
    func_calling = details.function_calling
    
    # Code-specialized
    if any(kw in model_id.lower() for kw in ["code", "coder", "starcoder"]):
        return ModelTier.CODE_SPECIALIZED
    
    # Vision
    if "vision" in model_id.lower() or "image" in modalities:
        return ModelTier.VISION
    
    # Long context
    if context >= 128000:
        return ModelTier.LONG_CONTEXT
    
    # Frontier (largest, most capable)
    if any(kw in model_id.lower() for kw in ["405b", "nemotron-4-340b", "deepseek-v3", "phi-4"]):
        return ModelTier.FRONTIER
    
    # Critic (different architecture family for blind-spot reduction)
    if any(kw in model_id.lower() for kw in ["gemma-2-27b", "qwen2.5-72b", "llama-3.1-70b"]):
        return ModelTier.CRITIC
    
    # Fast (small, efficient)
    if any(kw in model_id.lower() for kw in ["8b", "7b", "phi-3", "gemma-2-9b", "mistral-7b"]):
        return ModelTier.FAST
    
    return ModelTier.FAST  # Default
```

---

## 2. SMART GATEWAY & ROUTING (Phase 3) 🔴🔴🔴

| Missing Component | Status | Effort | Files to Create |
|---|---|---|---|
| `SmartGateway` class (THE ONLY GATEWAY) | 🔴 MISSING | 2 days | `src/gateway/smart_gateway.py` |
| `SmartRouter` with 6 decision factors | 🔴 MISSING | 2 days | `src/gateway/smart_router.py` |
| `ResilienceLayer` - Circuit Breakers | 🔴 MISSING | 1 day | `src/gateway/resilience.py` |
| Fallback chains with cooldown | 🔴 MISSING | 1 day | `src/gateway/resilience.py` |
| Rate limit tracking per provider/model | 🔴 MISSING | 1 day | `src/gateway/resilience.py` |
| Health monitoring with alerting | 🔴 MISSING | 1 day | `src/gateway/resilience.py` |
| `LLMClient` refactor to delegate to SmartGateway | 🟠 HIGH | 1 day | `src/gateway/llm_client.py` |
| Unified DEFAULT_MODEL_MAP matching litellm.yaml | 🟠 HIGH | 0.5 day | `src/gateway/llm_client.py` |

**Routing Decision Factors (per README):**
1. Task Complexity (simple/medium/hard/critical)
2. Required Capabilities (vision, function_calling, structured_output)
3. Cost Budget (per workflow)
4. Performance History (latency, success rate, quality)
5. Availability (circuit breaker status, rate limits)
6. USER PREFERENCE (Manual Override via Liaison)

---

## 3. PROFESSIONAL RESEARCHER AGENT (Phase 2) 🔴🔴🔴

| Missing Component | Status | Effort | Files to Create |
|---|---|---|---|
| `ProfessionalResearcherAgent` class | 🔴 MISSING | 2 days | `src/agents/professional_researcher.py` |
| Doc Fetchers (8 providers) | 🔴 MISSING | 3 days | `src/agents/researcher_docs/*.py` |
| Research Tasks: model_spec, pricing, capabilities, cross_validate, fetch_docs | 🔴 MISSING | 1 day | `src/agents/professional_researcher.py` |
| Source Citation Structure | 🔴 MISSING | 0.5 day | `src/agents/professional_researcher.py` |
| LLM Tools: fetch_official_page, call_provider_api, parse_pricing_table, validate_model_card | 🔴 MISSING | 1 day | `src/agents/professional_researcher.py` |
| Zero LLM knowledge enforcement | 🔴 MISSING | 0.5 day | `src/agents/professional_researcher.py` |

**Doc Fetchers Needed:**
1. `openai_docs.py` - platform.openai.com
2. `anthropic_docs.py` - docs.anthropic.com
3. `google_docs.py` - cloud.google.com/vertex-ai
4. `nvidia_docs.py` - build.nvidia.com + docs.nvidia.com
5. `azure_docs.py` - learn.microsoft.com
6. `aws_docs.py` - docs.aws.amazon.com/bedrock
7. `ollama_docs.py` - ollama.com/library
8. `base.py` - abstract base class

**Confidence Thresholds:**
- API response: 1.0
- Official pricing page: 0.9
- Official docs: 0.85
- Model card: 0.8
- Changelog: 0.75
- **Reject if confidence < 0.7**

---

## 4. FULL AGENT ROSTER INTEGRATION (Phase 4) 🟠🟠

| Agent | Current Status | Missing Integration |
|---|---|---|
| `ProductAnalystAgent` | ✅ Exists | Not in graph |
| `PlannerAgent` | ✅ Exists | Not in graph |
| `ArchitectAgent` | ✅ Exists | Not in graph |
| `UXAgent` | ✅ Exists | Not in graph |
| `DBEngineerAgent` | ✅ Exists | Not in graph |
| `ResearcherAgent` | ✅ Exists | Basic, not Professional |
| `CoderAgent` | ✅ Exists | Works in Fast Lane only |
| `TesterAgent` | ✅ Exists | Works |
| `CriticAgent` | ✅ Exists | Works |
| `IntegratorAgent` | ✅ Exists | Not in graph |
| `SecurityAgent` | ✅ Exists | Not in graph |
| `DocsAgent` | ✅ Exists | Not in graph |
| `LiaisonAgent` | ⚠️ Scaffold | No real implementation |
| `SupervisorAgent` | ✅ Exists | Circular import issues |

**Graph Integration Missing:**
- Fan-out/Fan-in parallel execution (UX, DB, Security, Researcher, Coder)
- DAG-based task dependencies
- Optimistic locking for concurrent state writes
- Milestone-based documentation (post-arch + post-integration)

---

## 5. OBSERVABILITY & TRACING (Phase 4) 🟡🟡

| Component | Status | Missing |
|---|---|---|
| `tracing.py` setup | ✅ Exists | Not integrated in agents |
| `instrumentation.py` decorators | ✅ Exists | Not used on agent methods |
| GenAI semantic conventions | ⚠️ Constants only | No span attributes emitted |
| `metrics.py` | ✅ Exists | No metrics recorded |
| Langfuse/Phoenix integration | ❌ Missing | No exporter config |
| Prompt capture (OFF by default) | ✅ Config exists | Not enforced |

---

## 6. HITL & LIAISON (Phase 5) 🟠🟠

| Component | Status | Missing |
|---|---|---|
| `hitl.py` - Approval gates | ✅ Exists | Not connected to graph |
| `CLIApprovalBackend` | ⚠️ Scaffold | Auto-approves only |
| `AutoApprovalBackend` | ✅ Exists | Works |
| `WebhookApprovalBackend` | ⚠️ Scaffold | Not functional |
| `HITLManager` with gates | ✅ Exists | Not invoked |
| Break-Glass Protocol | ❌ Missing | No durable interrupt |
| Natural language → system action | ❌ Missing | Core Liaison promise |

---

## 7. EVALUATION & TESTING (Phase 6) 🔴🔴

| Component | Status | Missing |
|---|---|---|
| `evals/harness.py` | ⚠️ Skeleton | No real workflow execution |
| `evals/golden/tasks.yaml` | ✅ 10 tasks | Need 50+ |
| `evals/swebench/harness.py` | ❌ Empty | Full implementation |
| `evals/redteam/attacks.py` | ❌ Empty | PyRIT + garak integration |
| `evals/judges/` | ❌ Empty | Calibrated LLM-as-Judge |
| `evals/router_eval.py` | ✅ Exists | No router to evaluate |
| Mock test infrastructure | ❌ Missing | 5 mock files needed |

---

## 8. SELF-IMPROVEMENT (Phase 7) 🔴🔴

| Component | Status | Missing |
|---|---|---|
| `optim/prompt_tuner.py` | ⚠️ Placeholder | DSPy MIPROv2/GEPA integration |
| `optim/model_optimiser.py` | ⚠️ Placeholder | Model switching logic |
| `optim/analyser.py` | ⚠️ Placeholder | Failure trace analysis |
| `optim/convergence.py` | ✅ Exists | Works |
| `optim/feedback_store.py` | ✅ Exists | Works |
| `optim/reporter.py` | ⚠️ Placeholder | Report generation |

---

## 9. INFRASTRUCTURE & CONFIG 🟠

| File | Status | Issues |
|---|---|---|
| `config/litellm.yaml` | ✅ Exists | Only 4 NVIDIA models, need 10+ providers |
| `config/policies.yaml` | ✅ Exists | Good default-deny matrix |
| `config/phase5.yaml` | ✅ Exists | Good config structure |
| `docker-compose.yml` | ✅ Exists | Needs gVisor/Firecracker options |
| `pyproject.toml` | ✅ Exists | Missing deps (dspy, gepa, pyrit, garak) |
| `.env.example` | ✅ Exists | Needs all provider keys documented |

---

## 10. CIRCULAR IMPORTS (Phase 0) 🔴

| File | Line | Fix |
|---|---|---|
| `src/orchestrator/runner.py` | 23 | Lazy import inside function |
| `src/agents/supervisor.py` | 38 | Lazy import inside method |
| `src/agents/__init__.py` | 22 | Use `__getattr__` for SupervisorAgent |

---

## 📈 GAP SUMMARY STATISTICS

| Category | Total Items | Missing (🔴) | Partial (🟠) | OK (🟢) |
|---|---|---|---|---|
| Model Registry | 12 | 12 | 0 | 0 |
| Smart Gateway | 8 | 8 | 0 | 0 |
| Professional Researcher | 8 | 8 | 0 | 0 |
| Provider Adapters | 10 | 10 | 0 | 0 |
| Agent Roster | 14 | 0 | 14 | 0 |
| Graph Integration | 5 | 5 | 0 | 0 |
| Observability | 6 | 0 | 6 | 0 |
| HITL/Liaison | 7 | 2 | 4 | 1 |
| Evaluation | 6 | 4 | 1 | 1 |
| Self-Improvement | 6 | 3 | 3 | 0 |
| Infrastructure | 6 | 0 | 4 | 2 |
| Circular Imports | 3 | 3 | 0 | 0 |
| **TOTAL** | **97** | **55** | **32** | **4** |

**55 Critical Missing | 32 Partial | 4 Working**

---

## 🎯 KEY INSIGHT: PROVIDER-AGNOSTIC DESIGN

**Every single gap above must be filled WITHOUT hardcoding any provider logic.**

- The Registry discovers models from adapters — adapters are plugins
- The Router scores ModelSpecs — provider is metadata only
- The Researcher validates specs — source is irrelevant
- The Gateway routes requests — provider is transparent

This is the architectural invariant that must never be violated.

---

# 🏗️ PHASE 0 & 1: CRITICAL FIXES + UNIVERSAL MODEL REGISTRY
## Days 1-4 — Foundation & Provider-Agnostic Registry

---

## 📅 DAY 1: PHASE 0 — CRITICAL FIXES (BLOCKING)

### 0.1 Fix Circular Imports (30 min)
```python
# src/orchestrator/runner.py
def run_workflow(...):
    from src.orchestrator.graph import GraphState, build_feedback_loop  # Lazy import

# src/agents/supervisor.py
class WorkflowRunner:
    def run(self, ...):
        from src.orchestrator.runner import run_workflow  # Lazy import

# src/agents/__init__.py
def __getattr__(name):
    if name == "SupervisorAgent":
        from src.agents.supervisor import SupervisorAgent
        return SupervisorAgent
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

**Verification:** `python -c "import src"` — zero errors

---

### 0.2 Unify Model Mapping (1 hour)
```python
# src/gateway/llm_client.py
DEFAULT_MODEL_MAP: dict[str, str] = {
    # These are ALIASES only — resolved at runtime via registry
    "frontier": "frontier",
    "fast": "fast",
    "critic": "critic",
    "fallback": "fallback",
}
```

```yaml
# config/litellm.yaml
model_list:
  # Discovered models auto-registered here by registry on startup
  # Manual overrides via Liaison:
  - model_name: "frontier"
    litellm_params:
      model: "openai/gpt-4o"  # or nvidia_nim/nvidia/nemotron-3-ultra
      api_key: "os.environ/OPENAI_API_KEY"
  - model_name: "fast"
    litellm_params:
      model: "openai/gpt-4o-mini"
      api_key: "os.environ/OPENAI_API_KEY"
  - model_name: "critic"
    litellm_params:
      model: "anthropic/claude-3.5-sonnet"
      api_key: "os.environ/ANTHROPIC_API_KEY"
  - model_name: "fallback"
    litellm_params:
      model: "google/gemini-1.5-pro"
      api_key: "os.environ/GEMINI_API_KEY"
```

---

### 0.3 Build Mock Test Infrastructure (2 hours)
```
tests/
├── conftest.py                    # Shared fixtures
├── mocks/
│   ├── __init__.py
│   ├── mock_gateway.py            # MockGateway class
│   ├── mock_models.py             # Dataclass model responses
│   ├── mock_provider_apis.py      # Mock OpenAI/Anthropic/Google/NVIDIA
│   ├── mock_event_store.py        # In-memory event store
│   └── mock_researcher.py         # MockProfessionalResearcher
└── fixtures/
    ├── sample_models.json         # Test model data
    ├── sample_pricing.json        # Test pricing data
    └── golden_tasks.yaml          # 50+ golden evaluation tasks
```

**conftest.py key fixtures:**
```python
@pytest.fixture
def mock_gateway():
    return MockGateway()

@pytest.fixture
def auto_registry(mock_gateway, mock_researcher):
    return AutoModelRegistry(gateway=mock_gateway, researcher=mock_researcher)

@pytest.fixture
def smart_gateway(auto_registry):
    return SmartGateway(registry=auto_registry)

@pytest.fixture
def liaison_agent(smart_gateway, auto_registry):
    return LiaisonAgent(gateway=smart_gateway, registry=auto_registry)
```

**Verification:** `pytest tests/test_smoke.py -v` → **100% pass, 0 real API calls**

---

## 📅 DAY 2: PHASE 1 — MODEL REGISTRY CORE

### Data Models (in `src/gateway/model_registry.py`)
```python
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

# ============================================================
# Enums
# ============================================================

class ModelTier(StrEnum):
    FRONTIER = "frontier"
    FAST = "fast"
    CRITIC = "critic"
    CODE_SPECIALIZED = "code_specialized"
    LONG_CONTEXT = "long_context"
    VISION = "vision"

class ModelStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    UNVERIFIED = "unverified"

class SourceType(StrEnum):
    API = "api"
    OFFICIAL_DOCS = "official_docs"
    PRICING_PAGE = "pricing_page"
    MODEL_CARD = "model_card"
    CHANGELOG = "changelog"

# ============================================================
# Source Citation (Verified Ground Truth)
# ============================================================

@dataclass(frozen=True)
class SourceCitation:
    source_type: SourceType
    url: str
    provider: str
    accessed_at: datetime
    field_mapping: dict[str, str]  # field_name → snippet_source
    confidence: float  # API=1.0, pricing=0.9, docs=0.85, card=0.8, changelog=0.75
    raw_snippet: str

# ============================================================
# Model Specifications
# ============================================================

@dataclass(frozen=True)
class ModelCapabilities:
    context_window: int
    modalities: list[str]  # ["text", "vision", "audio", "function_calling"]
    function_calling: bool
    structured_output: bool
    parallel_tool_calls: bool
    max_output_tokens: int

@dataclass(frozen=True)
class ModelPricing:
    input_per_1m_tokens: float
    output_per_1m_tokens: float
    currency: str = "USD"
    citation: SourceCitation | None = None
    effective_date: datetime | None = None

@dataclass(frozen=True)
class ModelLimits:
    rpm: int | None = None
    tpm: int | None = None
    rpd: int | None = None
    regions: list[str] = field(default_factory=list)
    deprecated: bool = False
    sunset_date: datetime | None = None

class ModelSpec(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    
    # Identity
    model_id: str = Field(description="e.g., 'nvidia/nemotron-3-ultra'")
    provider: str = Field(description="e.g., 'nvidia_nim'")
    provider_model_id: str = Field(description="As appears in provider API")
    aliases: list[str] = Field(default_factory=list)  # ["frontier", "nemotron3u"]
    
    # Verified Ground Truth (EVERY field has citation)
    capabilities: ModelCapabilities
    pricing: ModelPricing
    limits: ModelLimits
    
    # Metadata
    discovered_at: datetime
    source_citations: list[SourceCitation]
    confidence_score: float  # Overall 0.0-1.0
    last_verified: datetime
    status: ModelStatus = ModelStatus.ACTIVE
    tier: ModelTier = ModelTier.FAST
```

---

## 📅 DAY 3: PROVIDER ADAPTER FRAMEWORK

### Base Adapter (`src/gateway/providers/base.py`)
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class RawModelInfo:
    model_id: str
    owned_by: str = ""
    permission: list = field(default_factory=list)
    root: str | None = None
    parent: str | None = None

@dataclass
class RawModelDetails:
    model_id: str
    context_window: int
    modalities: list[str]
    function_calling: bool
    structured_output: bool
    parallel_tool_calls: bool

@dataclass
class RawPricingInfo:
    input_per_1m: float
    output_per_1m: float
    currency: str = "USD"

@dataclass
class RawLimitsInfo:
    rpm: int | None = None
    tpm: int | None = None
    rpd: int | None = None
    regions: list[str] = field(default_factory=list)

class ProviderAdapter(ABC):
    provider_name: str
    
    @abstractmethod
    async def list_models(self) -> list[RawModelInfo]:
        """Discover all available models from provider"""
        pass
    
    @abstractmethod
    async def get_model_details(self, model_id: str) -> RawModelDetails:
        """Get capabilities for a specific model"""
        pass
    
    @abstractmethod
    async def get_pricing(self, model_id: str) -> RawPricingInfo:
        """Get pricing from official source"""
        pass
    
    @abstractmethod
    async def get_limits(self, model_id: str) -> RawLimitsInfo:
        """Get rate limits, regions, deprecation info"""
        pass
    
    @abstractmethod
    def get_official_docs_url(self, model_id: str) -> str:
        """URL for official documentation"""
        pass
    
    @abstractmethod
    async def validate_model_exists(self, model_id: str) -> bool:
        """Verify model exists and is accessible"""
        pass
```

### Registry (`src/gateway/providers/registry.py`)
```python
class ProviderAdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, ProviderAdapter] = {}
    
    def register(self, adapter: ProviderAdapter) -> None:
        self._adapters[adapter.provider_name] = adapter
    
    def get(self, provider: str) -> ProviderAdapter | None:
        return self._adapters.get(provider)
    
    def all(self) -> list[ProviderAdapter]:
        return list(self._adapters.values())
```

---

## 📅 DAY 3 (cont): NVIDIA NIM ADAPTER (TEST CASE)

### `src/gateway/providers/nvidia_nim_adapter.py`
```python
import httpx
from src.gateway.providers.base import (
    ProviderAdapter, RawModelInfo, RawModelDetails,
    RawPricingInfo, RawLimitsInfo
)

class NvidiaNimAdapter(ProviderAdapter):
    provider_name = "nvidia_nim"
    BASE_URL = "https://integrate.api.nvidia.com/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0
        )
    
    async def list_models(self) -> list[RawModelInfo]:
        resp = await self._client.get("/models")
        resp.raise_for_status()
        data = resp.json()
        return [
            RawModelInfo(
                model_id=m["id"],
                owned_by=m.get("owned_by", "nvidia"),
                permission=m.get("permission", []),
                root=m.get("root"),
                parent=m.get("parent"),
            )
            for m in data.get("data", [])
        ]
    
    async def get_model_details(self, model_id: str) -> RawModelDetails:
        # NVIDIA doesn't have per-model detail endpoint
        # Infer from model_id patterns
        return RawModelDetails(
            model_id=model_id,
            context_window=self._infer_context_window(model_id),
            modalities=self._infer_modalities(model_id),
            function_calling=self._infer_function_calling(model_id),
            structured_output=True,
            parallel_tool_calls=True,
        )
    
    async def get_pricing(self, model_id: str) -> RawPricingInfo:
        # Free tier for development
        return RawPricingInfo(
            input_per_1m=0.0,
            output_per_1m=0.0,
            currency="USD",
        )
    
    async def get_limits(self, model_id: str) -> RawLimitsInfo:
        return RawLimitsInfo(regions=["global"])
    
    def get_official_docs_url(self, model_id: str) -> str:
        return f"https://build.nvidia.com/{model_id}"
    
    async def validate_model_exists(self, model_id: str) -> bool:
        models = await self.list_models()
        return any(m.model_id == model_id for m in models)
    
    def _infer_context_window(self, model_id: str) -> int:
        model_lower = model_id.lower()
        if "128k" in model_lower or "405b" in model_lower:
            return 128000
        if "32k" in model_lower or "70b" in model_lower:
            return 32768
        if "16k" in model_lower:
            return 16384
        return 4096
    
    def _infer_modalities(self, model_id: str) -> list[str]:
        if "vision" in model_id.lower():
            return ["text", "image"]
        return ["text"]
    
    def _infer_function_calling(self, model_id: str) -> bool:
        excluded = ["phi-3", "gemma-2-2b", "gemma-2-9b"]
        return not any(ex in model_id.lower() for ex in excluded)
```

---

## 📅 DAY 4: AUTO-DISCOVERY & CLASSIFICATION

### Registry Implementation (extend `model_registry.py`)
```python
class AutoModelRegistry:
    def __init__(self, gateway, researcher_agent, liaison_agent, config):
        self._models: dict[str, ModelSpec] = {}
        self._provider_adapters: dict[str, ProviderAdapter] = {}
        self._gateway = gateway
        self._researcher = researcher_agent
        self._liaison = liaison_agent
        self._config = config
        self._discovery_lock = asyncio.Lock()
    
    async def discover_all_providers(self) -> DiscoveryReport:
        """Discover all models from all registered providers"""
        async with self._discovery_lock:
            report = DiscoveryReport(started_at=datetime.now(UTC))
            for provider_name, adapter in self._provider_adapters.items():
                try:
                    models = await self._discover_provider(provider_name, adapter)
                    report.add_provider_result(provider_name, models)
                except Exception as e:
                    report.add_error(provider_name, str(e))
            report.finished_at = datetime.now(UTC)
            return report
    
    async def _discover_provider(self, provider: str, adapter: ProviderAdapter) -> list[ModelSpec]:
        raw_models = await adapter.list_models()
        specs = []
        for raw in raw_models:
            spec = await self._build_model_spec(provider, raw, adapter)
            if spec:
                self._models[spec.model_id] = spec
                specs.append(spec)
        return specs
    
    async def _build_model_spec(self, provider: str, raw: RawModelInfo, adapter: ProviderAdapter) -> ModelSpec | None:
        # 1. Get detailed info
        details = await adapter.get_model_details(raw.model_id)
        pricing = await adapter.get_pricing(raw.model_id)
        limits = await adapter.get_limits(raw.model_id)
        
        # 2. Build capabilities
        capabilities = ModelCapabilities(
            context_window=details.context_window,
            modalities=details.modalities,
            function_calling=details.function_calling,
            structured_output=details.structured_output,
            parallel_tool_calls=details.parallel_tool_calls,
            max_output_tokens=details.max_output_tokens or 4096,
        )
        
        # 3. Create citations for EVERY field
        citations = self._create_citations(provider, raw.model_id, details, pricing, limits, adapter)
        
        # 4. Cross-validate with ProfessionalResearcher if enabled
        if self._config.cross_validate:
            validation = await self._researcher.cross_validate(provider, raw.model_id, citations)
            if not validation.passed:
                return None  # Reject unverified model
        
        # 5. Classify by capabilities (NOT provider)
        tier = self._classify_model(raw.model_id, details)
        
        # 6. Calculate confidence
        confidence = self._calculate_confidence(citations)
        
        if confidence < 0.7:
            return None
        
        return ModelSpec(
            model_id=raw.model_id,
            provider=provider,
            provider_model_id=raw.model_id,
            aliases=self._generate_aliases(raw.model_id, tier),
            capabilities=capabilities,
            pricing=ModelPricing.from_raw(pricing, citations.get("pricing")),
            limits=ModelLimits.from_raw(limits, citations.get("limits")),
            source_citations=citations,
            confidence_score=confidence,
            tier=tier,
            # ...
        )
    
    def _classify_model(self, model_id: str, details: RawModelDetails) -> ModelTier:
        """Classify by capabilities, NOT provider name"""
        model_lower = model_id.lower()
        context = details.context_window
        
        if any(kw in model_lower for kw in ["code", "coder", "starcoder"]):

---

# 🧠 PHASE 2 & 3: PROFESSIONAL RESEARCHER + SMART GATEWAY
## Days 5-10 — Intelligence Layer & Routing Brain

---

## 📅 DAYS 5-7: PHASE 2 — PROFESSIONAL RESEARCHER AGENT
**Zero LLM knowledge. Verified sources only. Every claim cited.**

---

### Core Agent (`src/agents/professional_researcher.py`)
```python
class ProfessionalResearcherAgent(BaseAgent):
    """
    باحث محترف - صفر تخمين، صفر معرفة LLM
    كل معلومة = مصدر رسمي + Timestamp + Confidence
    """
    
    def __init__(self, gateway, http_client, cache):
        self._providers_docs = {
            "openai": OpenAIOfficialDocs(http_client),
            "anthropic": AnthropicOfficialDocs(http_client),
            "google": GoogleOfficialDocs(http_client),
            "nvidia": NvidiaOfficialDocs(http_client),  # TEST CASE
            "azure": AzureOfficialDocs(http_client),
            "aws": AWSOfficialDocs(http_client),
            "ollama": OllamaOfficialDocs(http_client),
        }
        self._http = http_client
        self._cache = cache  # TTL 24h
    
    # Core Research Tasks
    async def research_model_spec(self, provider: str, model_id: str) -> ResearchResult: ...
    async def research_provider_pricing(self, provider: str) -> ResearchResult: ...
    async def research_provider_capabilities(self, provider: str) -> ResearchResult: ...
    async def cross_validate(self, model_id: str, sources: list) -> ValidationResult: ...
    async def fetch_official_docs(self, url: str) -> ParsedContent: ...
    
    # LLM Tools (for reasoning layer to use)
    def get_tools(self) -> list[Tool]:
        return [
            Tool("fetch_official_page", self._fetch_official_page),
            Tool("call_provider_api", self._call_provider_api),
            Tool("parse_pricing_table", self._parse_pricing_table),
            Tool("validate_model_card", self._validate_model_card),
        ]
```

### Doc Fetchers (`src/agents/researcher_docs/`)
```python
# base.py - Abstract base
class OfficialDocsFetcher(ABC):
    def __init__(self, http_client):
        self._http = http_client
        self._cache = TTLCache(ttl=86400)  # 24h
    
    @abstractmethod
    async def fetch_model_list(self) -> list[ModelSummary]: ...
    
    @abstractmethod
    async def fetch_model_details(self, model_id: str) -> ModelDetail: ...
    
    @abstractmethod
    async def fetch_pricing(self) -> PricingTable: ...
    
    @abstractmethod
    async def fetch_rate_limits(self) -> RateLimitInfo: ...

# Concrete implementations (8 providers)
# openai_docs.py, anthropic_docs.py, google_docs.py, nvidia_docs.py,
# azure_docs.py, aws_docs.py, ollama_docs.py
```

### Source Citation Enforcement
```python
@dataclass(frozen=True)
class SourceCitation:
    source_type: Literal["api", "official_docs", "pricing_page", "model_card", "changelog"]
    url: str
    provider: str
    accessed_at: datetime
    field_mapping: dict[str, str]  # field_name → snippet_source
    confidence: float  # API=1.0, pricing=0.9, docs=0.85, card=0.8, changelog=0.75
    raw_snippet: str

# EVERY ModelSpec field MUST have citation
# Confidence thresholds:
# - API response: 1.0
# - Official pricing page: 0.9
# - Official docs: 0.85
# - Model card: 0.8
# - Changelog: 0.75
# REJECT if confidence < 0.7
```

### Integration with Registry
```python
# In AutoModelRegistry._build_model_spec()
if self._config.cross_validate:
    validation = await self._researcher.cross_validate(provider, model_id, citations)
    if not validation.passed:
        return None  # Reject unverified model
```

---

## 📅 DAYS 8-10: PHASE 3 — SMART GATEWAY (THE ONLY GATEWAY)

---

### SmartGateway (`src/gateway/smart_gateway.py`)
```python
class SmartGateway:
    """THE ONLY GATEWAY - no direct litellm calls ever"""
    
    def __init__(self, registry: AutoModelRegistry, resilience: ResilienceLayer):
        self._registry = registry
        self._resilience = resilience
        self._router = SmartRouter(registry)
        self._cost_tracker = CostTracker(registry)
    
    # ONLY PUBLIC INTERFACE
    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...
    async def complete_structured(self, request: StructuredCompletionRequest) -> T: ...
    
    # Smart Routing
    def route_request(self, request: CompletionRequest) -> RoutingDecision:
        """
        Decision Factors (priority order):
        1. Task Complexity (from Semantic Router)
        2. Required Capabilities (vision, function_calling, long_context)
        3. Cost Budget (from request or workflow)
        4. Performance History (latency, success_rate, quality)
        5. Availability (circuit breaker, rate limits)
        6. USER PREFERENCE (Manual Override via Liaison)
        """
    
    # Manual Override Handlers (from Liaison)
    async def handle_manual_model_change(self, command: ManualModelCommand) -> Result: ...
    async def handle_provider_disable(self, provider: str, reason: str) -> Result: ...
    async def handle_model_override(self, task_type: str, model_id: str) -> Result: ...
```

### SmartRouter (`src/gateway/smart_router.py`)
```python
class SmartRouter:
    def __init__(self, registry: AutoModelRegistry):
        self._registry = registry
    
    def find_optimal_model(self, criteria: RoutingCriteria) -> ModelSpec:
        """
        Algorithm:
        1. Filter by capabilities (must-have)
        2. Filter by availability (circuit closed, within rate limits)
        3. Score by: quality_score * perf_weight + cost_efficiency * cost_weight
        4. Apply manual overrides (from Liaison)
        5. Return best + alternatives (fallback chain)
        """
    
    def build_fallback_chain(self, primary: ModelSpec, criteria: RoutingCriteria) -> list[ModelSpec]:
        # Next best models with DIFFERENT provider/family
        pass
```

### ResilienceLayer (`src/gateway/resilience.py`)
```python
class ResilienceLayer:
    # Per-model Circuit Breakers
    # Fallback Chains with cooldown
    # Rate limit tracking per provider/model
    # Health monitoring with alerting
    pass
```

### LLMClient Refactor (`src/gateway/llm_client.py`)
```python
# NOW delegates to SmartGateway
class LLMClient:
    def __init__(self, smart_gateway: SmartGateway, cost_tracker: CostTracker):
        self._gateway = smart_gateway
        self._cost_tracker = cost_tracker
    
    async def complete_text(self, model: str, messages: list[dict], **kwargs) -> str:
        request = CompletionRequest(model=model, messages=messages, **kwargs)
        response = await self._gateway.complete(request)
        return response.content
    
    async def complete_structured(self, model: str, messages: list[dict], response_model: type[T], **kwargs) -> T:
        request = StructuredCompletionRequest(model=model, messages=messages, response_model=response_model, **kwargs)
        return await self._gateway.complete_structured(request)
```

### Unified DEFAULT_MODEL_MAP
```python
# src/gateway/llm_client.py
DEFAULT_MODEL_MAP: dict[str, str] = {
    "frontier": "frontier",
    "fast": "fast",
    "critic": "critic",
    "fallback": "fallback",
}
# Matches litellm.yaml aliases — resolved at runtime via registry
```

---

## ✅ PHASE 2-3 COMPLETION CRITERIA

| Criteria | Verification |
|---|---|
| ProfessionalResearcher has 8 doc fetchers | `pytest tests/test_doc_fetchers/ -v` |
| Zero LLM knowledge in researcher | Grep for LLM calls in researcher_docs/ → 0 |
| Every ModelSpec field has SourceCitation | Audit script: `python scripts/audit_ground_truth.py` |
| SmartGateway is ONLY gateway | Grep for `litellm.completion` in src/ → 0 |
| SmartRouter uses 6 decision factors | Unit tests for each factor |
| Circuit breakers on every provider/model | Integration test: kill primary → fallback activates |
| Fallback chains auto-built with different provider/family | Verify chain diversity |
| LLMClient delegates to SmartGateway | No direct litellm calls in llm_client.py |
| Manual override via Liaison works | E2E test: "disable nemotron" → registry + gateway + config updated |
| 100% ModelSpec fields have citations | `python scripts/audit_ground_truth.py` → 100% |

---

# 🤖 PHASE 4: FULL AGENT ROSTER INTEGRATION
## Days 11-13 — All 14 Agents in LangGraph with Fan-out/Fan-in

---

## 📅 DAYS 11-13: PHASE 4 — AGENT ROSTER INTEGRATION

---

### Graph Integration (`src/orchestrator/graph.py`)

```python
def build_feedback_loop(event_store, llm_client) -> StateGraph:
    """Compile the LangGraph state machine with ALL agents (Phase 4)."""
    from functools import partial
    
    from src.agents.coder import CoderAgent
    from src.agents.tester import TesterAgent
    from src.agents.critic import CriticAgent
    from src.agents.product_analyst import ProductAnalystAgent
    from src.agents.planner import PlannerAgent
    from src.agents.architect import ArchitectAgent
    from src.agents.ux import UXAgent
    from src.agents.db_engineer import DBEngineerAgent
    from src.agents.researcher import ResearcherAgent
    from src.agents.integrator import IntegratorAgent
    from src.agents.security import SecurityAgent
    from src.agents.docs import DocsAgent
    from src.agents.liaison import LiaisonAgent
    
    # Core agents
    coder = CoderAgent(agent_id="c1", llm_client=llm_client)
    tester = TesterAgent(agent_id="t1")
    critic = CriticAgent(agent_id="cr1", llm_client=llm_client)
    
    # Phase 4 agents
    router = SemanticRouter(llm_client=llm_client)
    pa = ProductAnalystAgent(agent_id="pa1", llm_client=llm_client)
    planner = PlannerAgent(agent_id="pl1", llm_client=llm_client)
    arch = ArchitectAgent(agent_id="ar1", llm_client=llm_client)
    ux = UXAgent(agent_id="ux1", llm_client=llm_client)
    db = DBEngineerAgent(agent_id="db1", llm_client=llm_client)
    sec = SecurityAgent(agent_id="sec1", llm_client=llm_client)
    res = ResearcherAgent(agent_id="res1", llm_client=llm_client)
    integ = IntegratorAgent(agent_id="in1", llm_client=llm_client)
    docs = DocsAgent(agent_id="doc1", llm_client=llm_client)
    liaison = LiaisonAgent(smart_gateway, auto_registry, hitl_manager)
    
    workflow = StateGraph(GraphState)
    
    # Entry point
    workflow.set_entry_point("assign_task")
    
    # Semantic Router — Fast Lane vs Full SDLC
    workflow.add_edge("assign_task", "route")
    workflow.add_conditional_edges("route", _route_decision, {
        "fast": "coder",
        "full": "product_analyst"
    })
    
    # ============ FAST LANE (Simple + High Confidence) ============
    workflow.add_edge("coder", "tester")
    workflow.add_edge("tester", "critic")
    workflow.add_conditional_edges(
        "critic",
        _should_continue,
        {
            "complete": "complete",
            "should_rebut": "coder_rebut",
            "fail": "fail"
        }
    )
    # Rebuttal logic (same as before)
    workflow.add_conditional_edges(
        "coder_rebut",
        _should_rebut_router,
        {"try_rebut": "judge_rebuttal", "no_rebut": "increment"}
    )
    workflow.add_conditional_edges(
        "judge_rebuttal",
        _rebuttal_outcome_router,
        {"accepted_fast": "complete", "rejected": "increment"}
    )
    workflow.add_edge("increment", "coder")
    workflow.add_edge("complete", END)
    workflow.add_edge("fail", END)
    
    # ============ FULL SDLC PATH (Medium/Complex or Low Confidence) ============
    workflow.add_edge("product_analyst", "planner")
    workflow.add_edge("planner", "architect")
    
    # Fan-out: Parallel execution
    workflow.add_edge("architect", "ux")
    workflow.add_edge("architect", "db")
    workflow.add_edge("architect", "security")
    workflow.add_edge("architect", "researcher")
    workflow.add_edge("architect", "coder_sdlc")
    
    # Fan-in: All parallel agents converge at Integrator
    workflow.add_edge(["ux", "db", "security", "researcher", "coder_sdlc"], "integrator")
    
    # Docs milestone 1: Post-architecture ADRs
    workflow.add_edge("integrator", "docs_arch")
    workflow.add_edge("docs_arch", "tester")
    
    # Tester → Critic → loop or complete
    workflow.add_edge("tester", "critic")
    workflow.add_conditional_edges(
        "critic",
        _should_continue_full,
        {
            "complete": "docs_int",
            "should_rebut": "coder_rebut",
            "fail": "fail"
        }
    )
    
    # Docs milestone 2: Post-integration docs
    workflow.add_edge("docs_int", "complete")
    
    # HITL Gates (if enabled)
    # Pre-code approval, Post-test approval, Security review
    
    return workflow
```

---

### Full SDLC Node Functions

```python
# Product Analyst: PRD from task description
def _product_analyst_node(state, agent, event_store):
    prd = agent.run(state["task_description"], state.get("constraints", []))
    event = product_requirements_event(...)
    event_store.append(event)
    return {"product_requirements": prd.model_dump(), ...}

# Planner: Task DAG from PRD
def _planner_node(state, agent, event_store):
    prd = ProductRequirementDoc.model_validate(state["product_requirements"])
    dag = agent.run(prd)
    event = task_dag_event(...)
    event_store.append(event)
    return {"task_dag": dag.model_dump(), ...}

# Architect: ADRs + Component Diagram + Tech Choices
def _architect_node(state, agent, event_store):
    dag = TaskDAG.from_stored(state.get("task_dag", {}))
    prd = ProductRequirementDoc.from_stored(state.get("product_requirements", {}))
    design = agent.run(prd, dag)
    event = architect_design_event(...)
    event_store.append(event)
    return {"architect_design": design.model_dump(), ...}

# Fan-out nodes (parallel)
def _fanout_ux_node(state, agent, event_store):
    arch = ArchitectDesign.model_validate(state["architect_design"])
    prd = ProductRequirementDoc.model_validate(state["product_requirements"])
    design = agent.run(arch, prd)
    event = ux_design_event(...)
    event_store.append(event)
    return {"ux_design": design.model_dump()}

def _fanout_db_node(state, agent, event_store):
    arch = ArchitectDesign.model_validate(state["architect_design"])
    prd = ProductRequirementDoc.model_validate(state["product_requirements"])
    schema = agent.run(arch, prd)
    event = db_schema_event(...)
    event_store.append(event)
    return {"data_schema": schema.model_dump()}

def _fanout_security_node(state, agent, event_store):
    arch = ArchitectDesign.model_validate(state["architect_design"])
    report = agent.run(arch)
    event = security_report_event(...)
    event_store.append(event)
    return {"security_report": report.model_dump()}

def _fanout_researcher_node(state, agent, event_store):
    arch = ArchitectDesign.model_validate(state["architect_design"])
    prd = ProductRequirementDoc.model_validate(state["product_requirements"])
    notes = agent.run(prd, arch)
    event = research_notes_event(...)
    event_store.append(event)
    return {"research_notes": notes.model_dump()}

def _fanout_coder_node(state, agent, event_store):
    iteration = state.get("current_iteration", 1)
    patch = agent.run(state)  # Uses full state context
    event = code_submitted_event(...)
    event_store.append(event)
    return {"code_patch": patch.model_dump()}

# Integrator: Fan-in merge
def _integrator_node(state, agent, event_store):
    out = agent.run(state)
    event = integration_event(...)
    event_store.append(event)
    return {"integrator_output": out.model_dump(), ...}

# Docs milestones
def _docs_arch_node(state, agent, event_store):
    out = agent.run(state, phase="architecture")
    event = documentation_event(...)
    event_store.append(event)
    return {"docs_adr": out.model_dump(), ...}

def _docs_int_node(state, agent, event_store):
    out = agent.run(state, phase="integration")
    event = documentation_event(...)
    event_store.append(event)
    return {"docs_final": out.model_dump(), ...}
```

---

### Optimistic Locking for Concurrent Writes
```python
# In event store append - already implemented with UNIQUE(workflow_id, version)
# Each agent writes events with version = current + 1
# Concurrent writes → IntegrityError → retry with new version
```

---

### HITL Gates Integration
```python
# Add HITL nodes to graph
workflow.add_node("hitl_pre_code", partial(_hitl_pre_code_node, hitl_manager=hitl_manager))
workflow.add_node("hitl_post_test", partial(_hitl_post_test_node, hitl_manager=hitl_manager))
workflow.add_node("hitl_security", partial(_hitl_security_node, hitl_manager=hitl_manager))

# Pre-code gate
workflow.add_edge("integrator", "hitl_pre_code")
workflow.add_conditional_edges("hitl_pre_code", _hitl_router, {
    "approved": "coder_sdlc",
    "rejected": "replan",
    "timeout": "fail"
})

# Post-test gate
workflow.add_edge("tester", "hitl_post_test")
workflow.add_conditional_edges("hitl_post_test", _hitl_router, {
    "approved": "critic",
    "rejected": "coder_sdlc",
    "timeout": "fail"
})

# Security gate
workflow.add_edge("security", "hitl_security")
workflow.add_conditional_edges("hitl_security", _hitl_router, {
    "approved": "integrator",
    "rejected": "architect",
    "timeout": "fail"
})
```

---

## 🤖 LIAISON AGENT — REAL IMPLEMENTATION

### `src/agents/liaison.py`
```python
class LiaisonAgent(BaseAgent):
    """The ONLY human interface - translates state ⇄ operator"""
    
    def __init__(self, smart_gateway, auto_registry, hitl_manager):
        self._gateway = smart_gateway
        self._registry = auto_registry
        self._hitl = hitl_manager
    
    # Natural Language → System Action
    async def handle_user_command(self, workflow_id: str, command: str) -> Result:
        """
        Parses Arabic/English commands like:
        - "أضف gpt-4o-mini من Azure eastus2 واجعله افتراضي للمهام البسيطة"
        - "Add gpt-4o-mini from Azure eastus2 as default for simple tasks"
        - "أوقف نموذج nemotron-3-ultra مؤقتاً"
        - "Disable model nemotron-3-ultra temporarily"
        - "اعرض النماذج المتاحة للمهام المعقدة"
        - "Show available models for complex tasks"
        """
        intent = await self._parse_intent(command)
        return await self._execute_intent(workflow_id, intent)
    
    async def _parse_intent(self, command: str) -> UserIntent:
        # Use LLM with structured output
        pass
    
    async def _execute_intent(self, workflow_id: str, intent: UserIntent) -> Result:
        if intent.action == "ADD_MODEL":
            spec = await self._build_spec_from_intent(intent)
            return await self._registry.manual_add_model(spec, "user")
        elif intent.action == "DISABLE_MODEL":
            return await self._registry.manual_disable_model(intent.model_id, intent.reason, "user")
        elif intent.action == "ENABLE_MODEL":
            return await self._registry.manual_enable_model(intent.model_id, "user")
        elif intent.action == "SET_DEFAULT":
            return await self._gateway.handle_model_override(intent.task_type, intent.model_id)
        elif intent.action == "DISABLE_PROVIDER":
            return await self._gateway.handle_provider_disable(intent.provider, intent.reason)
        elif intent.action == "QUERY_MODELS":
            return self._registry.list_models(filters=intent.filters)
        elif intent.action == "QUERY_STATUS":
            return self._get_workflow_status(workflow_id)
        # ... etc
```

### Command Executor (`src/orchestrator/command_executor.py`)
```python
class CommandExecutor:
    """Executes Liaison commands by distributing to appropriate agents"""
    
    async def execute_command(self, command: ParsedCommand) -> CommandResult:
        match command.action:
            case "add_model":
                return await self._add_model_flow(command)
            case "disable_provider":
                return await self._disable_provider_flow(command)
            case "set_default":
                return await self._set_default_flow(command)
            case "discover_all":
                return await self._discover_all_flow(command)
            # ... other commands
    
    async def _add_model_flow(self, command) -> CommandResult:
        # Liaison → Researcher (fetch official specs) → Registry (register) → Gateway (update routing) → Config (update litellm.yaml)
        pass

---

# 🔐 PHASE 5: HITL, OBSERVABILITY & PRODUCTION HARDENING
## Days 14-16 — Enterprise-Grade Reliability

---

## 📅 DAYS 14-16: PHASE 5 — PRODUCTION HARDENING

---

### Day 14: Full Observability Stack

#### OpenTelemetry GenAI on ALL Agents
```python
# src/observability/instrumentation.py
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from functools import wraps

# GenAI Semantic Convention Attributes
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_USAGE_INPUT = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT = "gen_ai.usage.output_tokens"
GEN_AI_FINISH_REASON = "gen_ai.response.finish_reason"
AGENT_ROLE = "agent.role"

def trace_agent_invocation(agent_role: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = trace.get_tracer("zyren.genai")
            with tracer.start_as_current_span(f"invoke_agent.{agent_role}") as span:
                span.set_attribute(AGENT_ROLE, agent_role)
                span.set_attribute(GEN_AI_SYSTEM, "litellm")
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
        return wrapper
    return decorator

def trace_chat(model: str):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = trace.get_tracer("zyren.genai")
            with tracer.start_as_current_span("chat") as span:
                span.set_attribute(GEN_AI_SYSTEM, "litellm")
                span.set_attribute(GEN_AI_REQUEST_MODEL, model)
                try:
                    result = func(*args, **kwargs)
                    if hasattr(result, 'usage'):
                        span.set_attribute(GEN_AI_USAGE_INPUT, result.usage.prompt_tokens)
                        span.set_attribute(GEN_AI_USAGE_OUTPUT, result.usage.completion_tokens)
                    span.set_attribute(GEN_AI_FINISH_REASON, getattr(result.choices[0], 'finish_reason', 'unknown'))
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
        return wrapper
    return decorator
```

#### Apply to ALL Agent Methods
```python
# In every agent:
@trace_agent_invocation(agent_role="coder")
def run(self, task): ...

@trace_agent_invocation(agent_role="critic")
def run(self, patch, report): ...

@trace_agent_invocation(agent_role="tester")
def run(self, patch): ...

# In LLMClient:
@trace_chat("frontier")
async def complete_text(self, ...): ...
```

#### Jaeger + Langfuse in Docker Compose
```yaml
# docker-compose.yml additions
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"
      - "4317:4317"
      - "4318:4318"
    environment:
      - COLLECTOR_OTLP_ENABLED=true
  
  langfuse:
    image: langfuse/langfuse:latest
    environment:
      - DATABASE_URL=postgresql://langfuse:langfuse@postgres:5432/langfuse
      - NEXTAUTH_SECRET=${LANGFUSE_SECRET}
    ports:
      - "3000:3000"
    depends_on:
      - postgres
```

#### Prometheus Metrics Exposure
```python
# src/observability/metrics.py
from prometheus_client import Counter, Histogram, Gauge

workflow_total = Counter('workflow_total', 'Total workflows', ['status'])
workflow_duration = Histogram('workflow_duration_seconds', 'Workflow duration', ['phase'])
routing_decision = Counter('routing_decision_total', 'Routing decisions', ['model', 'complexity'])
fallback_activations = Counter('fallback_activations_total', 'Fallback activations', ['primary_model', 'fallback_model'])
circuit_breaker_state = Gauge('circuit_breaker_state', 'Circuit breaker state', ['model', 'state'])

# In SmartGateway.route_request():
routing_decision.labels(model=selected.model_id, complexity=criteria.complexity).inc()

# In ResilienceLayer:
circuit_breaker_state.labels(model=model, state="open").set(1)
fallback_activations.labels(primary=primary, fallback=fallback).inc()
```

---

### Day 15: Production Sandbox + Security Hardening

#### DockerSandboxProvider DEFAULT
```python
# src/tools/sandbox.py
def create_sandbox(use_docker: bool = True, **kwargs) -> SandboxProvider:
    if use_docker:
        return DockerSandboxProvider(**kwargs)
    return SandboxProvider(**kwargs)

# DockerSandboxProvider hardening:
HARDENED_FLAGS = [
    "--network=none",           # No network access
    "--cap-drop=ALL",           # Drop all Linux capabilities
    "--read-only",              # Read-only root filesystem
    "--tmpfs=/tmp:rw,noexec,nosuid,size=256M",  # Writable /tmp only
    "--memory=512m",            # Memory limit
    "--cpus=1",                 # CPU limit
    "--pids-limit=100",         # Process limit
    "--security-opt=no-new-privileges:true",
]
```

#### gVisor/Firecracker Options
```yaml
# docker-compose.yml - Add sandbox runner options
services:
  sandbox-gvisor:
    image: gvisor/gvisor:latest
    runtime: runsc
    security_opt:
      - "apparmor:unconfined"
    cap_add:
      - SYS_ADMIN
    devices:
      - /dev/fuse
  
  sandbox-firecracker:
    image: firecracker-microvm/firecracker:latest
    privileged: true
```

#### Default-Deny Policy Engine Enforced
```python
# Already implemented in src/tools/policy_engine.py
# Verify all agents respect permissions:
# - Coder: filesystem.read, filesystem.write, git.read, git.write, shell.execute_sandboxed
# - Tester: filesystem.read, shell.execute_sandboxed
# - Critic: filesystem.read, shell.execute_sandboxed, state.read
# - Security: filesystem.read, shell.execute_sandboxed, git.read
```

---

### Day 16: Cost Tracking + Budget Enforcement + CI/CD

#### CostTracker Hard Caps
```python
# src/gateway/cost_tracker.py
class CostTracker:
    def __init__(self, global_budget_usd: float = 50.0, budget_duration: str = "30d"):
        self._workflow_budgets: dict[str, float] = {}
        self._global_budget = global_budget_usd
    
    def record_usage(self, workflow_id: str, model: str, prompt_tokens: int, completion_tokens: int):
        cost = self._calculate_cost(model, prompt_tokens, completion_tokens)
        
        # Check workflow cap
        workflow_spent = self._workflow_budgets.get(workflow_id, 0) + cost
        if workflow_spent > MAX_WORKFLOW_COST_USD:
            raise BudgetExceededError(f"Workflow {workflow_id} exceeded ${MAX_WORKFLOW_COST_USD}")
        
        # Check global budget
        if self._total_spent + cost > self._global_budget:
            raise BudgetExceededError(f"Global budget ${self._global_budget} exceeded")
        
        self._workflow_budgets[workflow_id] = workflow_spent
        self._total_spent += cost
```

#### CI/CD Pipeline
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install deps
        run: uv sync --dev
      - name: Lint
        run: uv run ruff check src/ tests/
      - name: Format check
        run: uv run ruff format --check src/ tests/
      - name: Type check
        run: uv run mypy src/
      - name: Unit tests (mocked)
        run: uv run pytest tests/ -v --tb=short -k "not integration"
      - name: Integration tests
        run: uv run pytest tests/ -v --tb=short -k "integration"
        env:
          # No real API keys!
          OPENAI_API_KEY: "test-key"
          ANTHROPIC_API_KEY: "test-key"
          NVIDIA_NIM_API_KEY: "test-key"
```

---

## ✅ PHASE 5 COMPLETION CRITERIA

| Criteria | Verification |
|---|---|
| OTel GenAI traces on all agents | Jaeger shows `invoke_agent.*` spans with `gen_ai.*` attributes |
| Jaeger + Langfuse accessible | UI reachable at :16686 and :3000 |
| Prometheus metrics exposed | `/metrics` endpoint returns workflow, routing, circuit metrics |
| DockerSandboxProvider default | `create_sandbox()` returns Docker provider by default |
| Hardened flags applied | `docker inspect` shows all hardening flags |
| gVisor/Firecracker available | `docker run --runtime=runsc` works |
| Default-deny enforced | Agent tries unauthorized tool → `PolicyViolationError` |
| CostTracker hard caps | Workflow exceeds $5 → `BudgetExceededError` |
| CI/CD green | `act` or GitHub Actions: lint → typecheck → test all pass |
| Zero real API calls in CI | Network monitor shows 0 outbound to provider APIs |

---

# 📊 PHASE 6: EVALUATION & RED-TEAMING
## Days 17-19 — Comprehensive Quality Gates

---

## 📅 DAYS 17-19: PHASE 6 — EVALUATION SUITE

---

### Day 17: Golden Set Expansion + Harness

#### `evals/golden/tasks.yaml` — 50+ Tasks Across 6 Categories
```yaml
tasks:
  # ── Algorithmic (10) ──────────────────────────────────────
  - id: "g0"
    prompt: |
      Write a Python function `fibonacci(n: int) -> int` that returns
      the n-th Fibonacci number using an iterative approach (no recursion).
      Include type hints and a docstring. Return 0 for n=0, 1 for n=1.
    category: "algorithmic"
    expected_files: ["fibonacci.py", "test_fibonacci.py"]

  - id: "g1"
    prompt: |
      Write a Python function `is_palindrome(s: str) -> bool` that checks
      if a string is a palindrome, ignoring case, spaces, and punctuation.
      Include type hints, docstring, and at least 3 assert-based tests.
    category: "algorithmic"
    expected_files: ["palindrome.py", "test_palindrome.py"]

  # ... 8 more algorithmic tasks

  # ── API / Web (10) ────────────────────────────────────────
  - id: "g10"
    prompt: |
      Create a FastAPI application with two endpoints:
      - POST /users — creates a user with name and email, stores in memory
      - GET /users/{user_id} — retrieves a user by ID
      Use Pydantic models for request/response validation.
      Include proper HTTP status codes and error responses.
    category: "api"
    expected_files: ["main.py", "models.py", "test_main.py"]

  - id: "g11"
    prompt: |
      Write an async Python function `fetch_json(url: str) -> dict` using
      aiohttp that fetches JSON from a URL with proper error handling for:
      connection errors, HTTP errors (4xx, 5xx), and invalid JSON responses.
      Include type hints, docstring, and a retry mechanism (max 3 retries
      with exponential backoff).
    category: "api"
    expected_files: ["fetch_json.py", "test_fetch_json.py"]

  # ... 8 more API tasks

  # ── Data Structures (10) ──────────────────────────────────
  - id: "g20"
    prompt: |
      Implement a `CircularBuffer[T]` class with fixed capacity. Methods:
      `enqueue(item: T)`, `dequeue() -> T`, `is_full() -> bool`,
      `is_empty() -> bool`, `peek() -> T`, `size() -> int`.
      Overwrite oldest items when full. Include type hints and tests.
    category: "data_structures"
    expected_files: ["circular_buffer.py", "test_circular_buffer.py"]

  - id: "g21"
    prompt: |
      Write a function `merge_sorted_lists(lists: list[list[int]]) -> list[int]`
      that merges K sorted lists into one sorted list using a min-heap
      (heapq). Include type hints, docstring, and complexity analysis
      in the docstring.
    category: "data_structures"
    expected_files: ["merge_sorted.py", "test_merge_sorted.py"]

  # ... 8 more data structure tasks

  # ── Utility (5) ───────────────────────────────────────────
  - id: "g30"
    prompt: |
      Write a decorator `@retry_on_failure(max_retries=3, backoff_factor=2.0)`
      that retries a function on exception with exponential backoff.
      Include type hints, docstring, and an example usage.
    category: "utility"
    expected_files: ["retry_decorator.py", "test_retry_decorator.py"]

  - id: "g31"
    prompt: |
      Write a Python context manager `timed_block(name: str)` that logs
      the execution time of a block of code using `time.perf_counter()`.
      Print: "[name] took X.XXX seconds". Include type hints.
    category: "utility"
    expected_files: ["timed_block.py", "test_timed_block.py"]

  # ... 3 more utility tasks

  # ── Security / Validation (5) ─────────────────────────────
  - id: "g35"
    prompt: |
      Write a function `sanitize_sql_input(value: str) -> str` that
      escapes single quotes and removes semicolons from a string to
      prevent basic SQL injection. Include type hints, docstring,
      and assert-based validation tests with malicious inputs.
    category: "security"
    expected_files: ["sanitize_sql.py", "test_sanitize_sql.py"]

  - id: "g36"
    prompt: |
      Implement a `RateLimiter` class with methods:
      `allow_request(client_id: str) -> bool` and `reset(client_id: str)`.
      Uses a sliding window algorithm with configurable max_requests per
      window_seconds. Use `time.monotonic()` for timing.
      Include type hints and docstrings.
    category: "security"
    expected_files: ["rate_limiter.py", "test_rate_limiter.py"]

  # ... 3 more security tasks

  # ── Real-world (10) ───────────────────────────────────────
  - id: "g40"
    prompt: |
      Create a `ConfigManager` class that loads configuration from
      environment variables, YAML files, and command-line arguments
      with priority: CLI > ENV > YAML > defaults. Support type coercion
      (str, int, float, bool, list). Include type hints and tests.
    category: "real_world"
    expected_files: ["config_manager.py", "test_config_manager.py"]

  # ... 9 more real-world tasks
```

#### `evals/harness.py` — Full Workflow Execution
```python
class EvaluationHarness:
    """Runs tasks through the complete Zyren pipeline."""
    
    def __init__(self, max_iterations: int = 5, timeout_seconds: int = 300, cost_cap_usd: float = 1.0):
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        self.cost_cap_usd = cost_cap_usd
    
    async def evaluate_task(self, task_id: str, task_prompt: str, expected: dict) -> EvaluationResult:
        # 1. Create workflow with task prompt
        # 2. Run full Zyren pipeline
        # 3. Apply patch to temp repo
        # 4. Run expected tests
        # 5. Return pass/fail + trajectory + metrics
        pass
    
    async def evaluate_batch(self, tasks: list[dict], max_tasks: int | None = None) -> EvaluationSummary:
        # Parallel execution with semaphore
        pass
```

---

### Day 18: SWE-bench + Red-Teaming

#### SWE-bench Integration (`evals/swebench/harness.py`)
```python
class SWEBenchHarness:
    def __init__(self, dataset: str = "verified", split: str = "test"):
        self.dataset = load_dataset("princeton-nlp/SWE-bench_Verified", split=split)
    
    async def evaluate_instance(self, instance: dict) -> EvalResult:
        # 1. Create workflow with instance problem statement
        # 2. Run full Zyren pipeline
        # 3. Apply patch to test repo
        # 4. Run instance tests
        # 5. Return pass/fail + trajectory
        pass
    
    def evaluate(self, max_instances: int = 500) -> EvaluationSummary:
        # Parallel execution with semaphore
        # Track % Resolved (target: >30% on Verified)
        pass
```

#### Red-Teaming (`evals/redteam/attacks.py`)
```python
class RedTeamEvaluator:
    def __init__(self):
        self.pyrit = PyRITOrchestrator()
        self.garak = GarakScanner()
    
    async def run_owasp_top10_2026(self, target_system) -> RedTeamReport:
        """
        OWASP Top 10 for Agentic Applications (2026):
        1. Indirect Prompt Injection
        2. Tool Use Privilege Escalation
        3. Goal Hijacking
        4. Multi-turn Jailbreaks
        5. Data Exfiltration
        6. Unauthorized Tool Access
        7. Agent Impersonation
        8. Memory Poisoning
        9. Supply Chain Attacks
        10. Excessive Agency
        """
        results = {}
        for attack in OWASP_ATTACKS_2026:
            results[attack.name] = await attack.execute(target_system)
        return RedTeamReport(results)
    
    async def run_pyrit_campaigns(self) -> RedTeamReport:
        # Multi-turn conversations, roleplay, encoding attacks
        pass
    
    async def run_garak_scans(self) -> RedTeamReport:
        # garak built-in probes
        pass
```

---

### Day 19: LLM-as-Judge Calibration + Router Evals

#### Judge Calibration (`evals/judges/calibration.py`)
```python
class JudgeCalibrator:
    def __init__(self, judge_model: str = "anthropic/claude-3.5-sonnet"):
        self.judge = LLMClient(model=judge_model)
    
    def calibrate(self, golden_samples: list[CalibrationSample]) -> CalibrationResult:
        """
        1. Judge evaluates golden samples (human-labeled)
        2. Compute Cohen's κ vs human labels
        3. Target: κ > 0.6
        4. If κ < 0.6: refine rubric, repeat
        """
        pass
    
    def evaluate_trajectory(self, trajectory: Trajectory) -> TrajectoryScore:
        # Single clear pass/fail rubrics
        # Low-precision scoring (binary or 3-point)
        # Randomize order in pairwise comparisons
        pass
```

#### Router Evaluations (`evals/router_eval.py`)
```python
class RouterEvaluator:
    def __init__(self, smart_gateway: SmartGateway):
        self.gateway = smart_gateway
    
    def evaluate_routing_decisions(self, test_cases: list[RoutingTestCase]) -> RouterEvalReport:
        """
        Shadow-sample traffic vs frontier model ground truth
        Immutable Performance Floor: auto-tuned threshold must pass
        static human-verified anchor set, auto-rollback if win-rate drops
        """
        pass
    
    def evaluate_complexity_classification(self) -> ClassificationReport:
        # Compare SemanticRouter vs human labels
        # Target: >90% accuracy on simple/medium/complex
        pass

---

# 🔄 PHASE 7: SELF-IMPROVEMENT LOOP
## Days 20-22 — Continuous Optimization

---

## 📅 DAYS 20-22: PHASE 7 — SELF-IMPROVEMENT

---

### Day 21: DSPy/GEPA Prompt Optimization

#### `optim/prompt_tuner.py` — Full Implementation
```python
class PromptTuner:
    def __init__(self, strategy: str = "dspy_gepa"):
        self.strategy = strategy
        self.optimizer = self._create_optimizer()
    
    def _create_optimizer(self):
        if self.strategy == "dspy_gepa":
            import dspy
            from dspy.teleprompt import GEPA
            return GEPA(
                metric=self._composite_metric,
                reflection_model="openai/gpt-4o",
                max_iterations=10,
            )
        elif self.strategy == "textgrad":
            from textgrad import TextGradOptimizer
            return TextGradOptimizer(...)
    
    def _composite_metric(self, example, prediction) -> float:
        # Weighted: test_pass_rate * 0.5 + lint_score * 0.2 + type_check * 0.2 + security * 0.1
        pass
    
    async def tune_all_agents(self, failure_traces: list[Trajectory]) -> TuningReport:
        # Run offline on observability logs
        # Update agent system prompts
        # Validate improvement on golden set
        pass
```

### Day 22: Model Optimiser (Auto-Switch Weak Models)

#### `optim/model_optimiser.py`
```python
class ModelOptimiser:
    def __init__(self, registry: AutoModelRegistry, gateway: SmartGateway):
        self.registry = registry
        self.gateway = gateway
    
    async def evaluate_model_performance(self) -> ModelPerformanceReport:
        """
        Per-model metrics from observability:
        - Success rate (tests pass)
        - Avg latency
        - Cost per task
        - Fallback rate
        - Error types
        """
        pass
    
    async def auto_switch_weak_models(self, min_success_rate: float = 0.6) -> SwitchReport:
        """
        If model success_rate < threshold for N consecutive workflows:
        1. Disable model (mark DISABLED in registry)
        2. Gateway fallback chain activates
        3. Liaison notifies user
        4. Re-enable after fix confirmed
        """
        pass
    
    async def recommend_model_for_task(self, task_type: str) -> ModelSpec:
        # Based on historical performance for task category
        pass
```

---

### Day 22 (cont): Convergence + Decision Provenance

#### Convergence Detection (`optim/convergence.py`)
```python
class ConvergenceDetector:
    def __init__(self, config: ConvergenceConfig):
        self.config = config
    
    def check_convergence(self, round_scores: list[float]) -> ConvergenceResult:
        """
        - Minimum 3 rounds
        - Sliding window comparison
        - Improvement threshold: 0.02
        - Patience: 2 rounds
        - Min score floor: 0.7
        """
        pass
    
    def should_continue_optimization(self, report: OptimReport) -> bool:
        # Stop if converged OR budget exceeded OR max rounds
        pass
```

#### Decision Provenance Traces (`optim/analyser.py`)
```python
@dataclass
class DecisionProvenance:
    decision_id: str
    timestamp: datetime
    decision_type: Literal["model_selection", "fallback", "override", "budget_enforce"]
    inputs_examined: list[str]           # What data was considered
    policies_checked: list[str]          # Which rules applied
    tradeoffs_weighed: dict[str, float]  # Cost vs quality vs speed
    final_choice: str
    rationale: str
    human_override: bool
    override_reason: str | None

# Log to event store for audit trail
```

---

## ✅ PHASE 7 COMPLETION CRITERIA

| Criteria | Verification |
|---|---|
| DSPy GEPA / TextGrad runs on failure traces | `pytest tests/test_prompt_tuner.py -v` |
| Weak models auto-switched (success rate < 60%) | Integration test: inject failures → verify disable |
| Convergence stops optimization loops | Unit test: plateauing scores → convergence detected |
| Decision provenance logged for high-stakes decisions | Audit: check event store for DecisionProvenance entries |
| Prompt updates validated on golden set | Before/after golden pass rate improvement |
| Model optimiser recommends best model per task type | Test: task_type → recommended model matches best performer |

---

# 🚀 EXECUTION ORDER & DEPENDENCY GRAPH
## Precise Day-by-Day Plan with Dependencies

---

## 📅 OVERALL TIMELINE: 25 WORKING DAYS (5 WEEKS)

```
Week 1 (Days 1-5):  ██████████████████████████████████████████████████████████████████
  Day 1:   Phase 0 - Critical Fixes (MUST complete first)
  Day 2-3: Phase 1 - Model Registry Core (depends on Phase 0)
  Day 4-5: Phase 1 cont. - Provider Adapters (NVIDIA priority)

Week 2 (Days 6-10): ██████████████████████████████████████████████████████████████████
  Day 6-7: Phase 1 complete + Phase 2 start (depends on Phase 1)
  Day 8-10: Phase 3 - Smart Gateway + Router (depends on Phase 1)

Week 3 (Days 11-15): ██████████████████████████████████████████████████████████████████
  Day 11-12: Phase 4 - Agent Roster Integration (depends on Phase 1+3)
  Day 13:    Phase 4 - DAG + HITL + Testing (depends on Phase 4 start)
  Day 14-15: Phase 5 - Observability + Sandbox + Budgets (depends on Phase 4)

Week 4 (Days 16-20): ██████████████████████████████████████████████████████████████████
  Day 16-17: Phase 5 cont. + Phase 6 start (depends on Phase 5)
  Day 18:    Phase 6 - Golden Set + SWE-bench (depends on Phase 5)
  Day 19-20: Phase 6 - Red-team + Judge Calibration (depends on Phase 6 start)

Week 5 (Days 21-25): ██████████████████████████████████████████████████████████████████
  Day 21-22: Phase 7 - Self-Improvement (depends on Phase 6)
  Day 23:    Phase 7 - Convergence + Provenance (depends on Phase 7 start)
  Day 24:    E2E Integration Testing (depends on ALL phases)
  Day 25:    Final Validation + Documentation + Sign-off (depends on Day 24)
```

---

## 🔗 DEPENDENCY GRAPH

```mermaid
graph TD
    A[Phase 0: Critical Fixes] --> B[Phase 1: Model Registry]
    A --> C[Mock Infrastructure]
    
    B --> D[Phase 2: Professional Researcher]
    C --> D
    C --> E[Phase 3: Smart Gateway]
    B --> E
    
    D --> F[Phase 4: Agent Roster]
    E --> F
    
    F --> G[Phase 5: Production Hardening]
    G --> H[Phase 6: Evaluation Suite]
    H --> I[Phase 7: Self-Improvement]
    I --> J[E2E Integration Test]
    J --> K[Final Validation]
    
    J -.-> B
    J -.-> C
    J -.-> D
    J -.-> E
    J -.-> F
    J -.-> G
    J -.-> H
    J -.-> I
```

### Critical Path (Must Be Sequential)
```
Phase 0 → Phase 1 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → E2E
    ↓        ↓        ↓        ↓        ↓        ↓        ↓        ↓
   Day 1   Days 2-4  Days 8-10  Days 11-13 Days 14-16 Days 17-19 Days 20-22 Day 23-25
```

### Parallel Tracks (Can Run Concurrently)
| Track | Phases | Starts After |
|---|---|---|
| **Track A (Data Layer)** | Phase 1 → Phase 2 | Phase 0 |
| **Track B (Gateway Layer)** | Phase 3 | Phase 0 + Phase 1 (partial) |
| **Track C (Reasoning Layer)** | Phase 4 | Phase 1 + Phase 3 (partial) |
| **Track D (Production)** | Phase 5 | Phase 4 (partial) |
| **Track E (Quality)** | Phase 6 | Phase 5 (partial) |
| **Track F (Optimization)** | Phase 7 | Phase 6 (partial) |

---

## 📋 DAY-BY-DAY CHECKLIST

### WEEK 1: FOUNDATION

#### Day 1: Phase 0 — Critical Fixes (BLOCKING)
- [ ] Fix 3 circular imports (runner.py, supervisor.py, agents/__init__.py)
- [ ] Unify model mapping (llm_client.py + litellm.yaml + tests)
- [ ] Build mock infrastructure (5 mocks + 3 fixtures)
- [ ] Verify: `python -c "import src"` → 0 errors
- [ ] Verify: `pytest tests/test_smoke.py -v` → 100% pass, 0 real API calls
- [ ] **SIGN-OFF** before proceeding

#### Day 2: Phase 1 — Model Registry Core
- [ ] Create data models: SourceCitation, ModelCapabilities, ModelPricing, ModelLimits, ModelSpec, ModelTier, ModelStatus
- [ ] Implement AutoModelRegistry class with discovery, classification, cross-validation
- [ ] Create ProviderAdapter ABC + ProviderAdapterRegistry
- [ ] Unit tests for registry + classification logic

#### Day 3: Phase 1 — Provider Adapter Framework
- [ ] Base Adapter class
- [ ] NVIDIA NIM Adapter (PRIORITY — 77 models test case)
- [ ] Adapter registry integration
- [ ] Auto-classification by capabilities (NOT provider)

#### Day 4: Phase 1 — Auto-Discovery & Classification
- [ ] Startup bootstrap: discover NVIDIA 77 models on init
- [ ] Cross-validation with ProfessionalResearcher (stub)
- [ ] Manual override API (add/update/disable/enable)
- [ ] Scheduled refresh (24h)
- [ ] Integration test: startup → 77 models registered in tiers

#### Day 5: Phase 1 Complete + Phase 2 Start
- [ ] Remaining 9 provider adapters (stubs)
- [ ] Phase 1 integration test: auto-discovery flow
- [ ] **Phase 1 SIGN-OFF**
- [ ] Begin Phase 2: ProfessionalResearcherAgent core

---

### WEEK 2: INTELLIGENCE LAYER

#### Day 6: Phase 2 — Professional Researcher Core
- [ ] Core agent with zero-LLM-knowledge enforcement
- [ ] 8 doc fetcher registry (base + 8 implementations)
- [ ] Research tasks: model_spec, pricing, capabilities, cross_validate, fetch_docs

#### Day 7: Phase 2 — 8 Doc Fetchers
- [ ] NVIDIA docs fetcher (PRIORITY)
- [ ] OpenAI, Anthropic, Google, Azure, AWS, Ollama fetchers
- [ ] TTL caching (24h), confidence scoring
- [ ] SourceCitation enforcement (API=1.0, pricing=0.9, docs=0.85, card=0.8, changelog=0.75)
- [ ] Reject if confidence < 0.7

#### Day 8: Phase 2 Complete + Phase 3 Start
- [ ] Cross-validation integration with Registry
- [ ] Unit tests for all fetchers + researcher
- [ ] **Phase 2 SIGN-OFF**
- [ ] Begin Phase 3: SmartGateway (THE ONLY GATEWAY)

#### Day 9: Phase 3 — SmartGateway + SmartRouter
- [ ] SmartGateway: complete(), complete_structured(), route_request()
- [ ] SmartRouter: 6-factor decision algorithm
- [ ] ResilienceLayer: circuit breakers, fallback chains, rate limits, health monitoring

#### Day 10: Phase 3 — Resilience + LLMClient Refactor
- [ ] Circuit breakers per provider/model
- [ ] Fallback chains with cooldown (different provider/family)
- [ ] Rate limit tracking per provider/model
- [ ] Health monitoring + alerting
- [ ] LLMClient refactor → delegates to SmartGateway
- [ ] Unified DEFAULT_MODEL_MAP matching litellm.yaml
- [ ] **Phase 3 SIGN-OFF**

---

### WEEK 3: AGENT ROSTER INTEGRATION

#### Day 11: Phase 4 — Graph Integration
- [ ] Extend graph.py: instantiate all 14 agents
- [ ] Semantic Router conditional entry (fast vs full)
- [ ] Fast Lane: Coder → Tester → Critic → Complete/Rebuttal
- [ ] Full SDLC: PA → Planner → Architect → Fan-out → Fan-in → Docs → Tester → Critic

#### Day 12: Phase 4 — Fan-out/Fan-in + DAG
- [ ] Fan-out nodes: UX, DB, Security, Researcher, Coder (parallel)
- [ ] Fan-in: Integrator merge
- [ ] Milestone docs: post-arch ADRs + post-int docs
- [ ] DAG-based task dependencies with optimistic locking
- [ ] HITL gates: pre-code, post-test, security review

#### Day 13: Phase 4 — Liaison + Testing
- [ ] LiaisonAgent REAL implementation (NL → system action)
- [ ] CommandExecutor: distributes Liaison commands
- [ ] Arabic/English command parsing
- [ ] Integration tests: full SDLC, fan-out/fan-in, HITL gates
- [ ] **Phase 4 SIGN-OFF**

---

### WEEK 4: PRODUCTION + EVALUATION

#### Day 14: Phase 5 — Observability
- [ ] OTel GenAI on ALL agents (traces + spans)
- [ ] Jaeger + Langfuse in docker-compose
- [ ] Prometheus metrics: workflow, routing, fallback, circuit breaker
- [ ] Jaeger at :16686, Langfuse at :3000

#### Day 15: Phase 5 — Sandbox + Security
- [ ] DockerSandboxProvider DEFAULT (hardened flags)
- [ ] gVisor/Firecracker options in docker-compose
- [ ] Default-deny policy engine enforced
- [ ] Verify all agents respect permissions

#### Day 16: Phase 5 — Cost + CI/CD
- [ ] CostTracker hard caps (per-workflow + global)
- [ ] CI/CD pipeline: lint → typecheck → unit → integration
- [ ] Zero real API calls in CI (mock verification)
- [ ] **Phase 5 SIGN-OFF**

#### Day 17: Phase 6 — Golden Set Expansion
- [ ] evals/golden/tasks.yaml: 10 → 50+ tasks across 6 categories
- [ ] evals/harness.py: full workflow execution per task
- [ ] Parallel execution with semaphore

#### Day 18: Phase 6 — SWE-bench + Red-Team
- [ ] SWE-bench Verified harness (500 instances)
- [ ] RedTeamEvaluator: PyRIT + garak
- [ ] OWASP Top 10 2026 for Agentic Apps

#### Day 19: Phase 6 — Judge Calibration + Router Evals
- [ ] JudgeCalibrator: Cohen's κ > 0.6
- [ ] RouterEvaluator: shadow-sample vs frontier ground truth
- [ ] Immutable performance floor + auto-rollback
- [ ] **Phase 6 SIGN-OFF**

---

### WEEK 5: OPTIMIZATION + VALIDATION

#### Day 20: Phase 7 — DSPy/GEPA Prompt Tuning
- [ ] PromptTuner with DSPy GEPA + TextGrad fallback
- [ ] Composite metric: test_pass*0.5 + lint*0.2 + type*0.2 + security*0.1
- [ ] Offline tuning on failure traces → update prompts → validate on golden

#### Day 21: Phase 7 — Model Optimiser + Convergence
- [ ] ModelOptimiser: per-model metrics → auto-switch weak (<60% success)
- [ ] ConvergenceDetector: min 3 rounds, 2% threshold, patience 2, floor 0.7
- [ ] DecisionProvenance: audit trail for high-stakes decisions

#### Day 22: Phase 7 Complete
- [ ] Integration tests for prompt tuning + model switching
- [ ] Before/after golden set validation
- [ ] **Phase 7 SIGN-OFF**

#### Day 23: E2E Integration Testing
- [ ] Full test matrix (see below)
- [ ] Real-world scenario verification (8 scenarios)
- [ ] Performance benchmarks

#### Day 24: Final Validation
- [ ] Complete validation checklist
- [ ] Documentation update (README, COMPREHENSIVE_MASTER_PLAN)

#### Day 25: Sign-off
- [ ] Final sign-off ceremony

---

## 🧪 FULL TEST MATRIX (Day 23)

| Test Suite | Command | Expected |
|---|---|---|
| **Smoke** | `pytest tests/test_smoke.py -v` | 100% pass |
| **Unit** | `pytest tests/ -k "not phase" -v` | 100% pass |
| **Phase 1** | `pytest tests/test_model_registry.py tests/test_providers/ -v` | 100% pass |
| **Phase 2** | `pytest tests/test_professional_researcher.py tests/test_doc_fetchers/ -v` | 100% pass |
| **Phase 3** | `pytest tests/test_smart_gateway.py tests/test_smart_router.py tests/test_resilience.py -v` | 100% pass |
| **Phase 4** | `pytest tests/test_graph_integration.py tests/test_liaison_agent.py tests/test_hitl_gates.py -v` | 100% pass |
| **Phase 5** | `pytest tests/test_observability.py tests/test_sandbox.py tests/test_cost_tracker.py -v` | 100% pass |
| **Phase 6** | `pytest tests/test_golden_harness.py tests/test_swebench.py tests/test_redteam.py tests/test_judge_calibration.py -v` | 100% pass |
| **Phase 7** | `pytest tests/test_prompt_tuner.py tests/test_model_optimiser.py -v` | 100% pass |
| **FULL** | `pytest tests/ -v --tb=short` | **411/411 pass** |

---

## 🎯 REAL-WORLD SCENARIOS (Manual Verification Day 23)

| Scenario | Test | Verification |
|---|---|---|
| **NVIDIA Auto-Discovery** | Start system, check logs | 77 models registered in tiers |
| **Liaison NL Command** | "أضف gpt-4o من Azure" | Model in registry + gateway + litellm.yaml |
| **Fast Lane** | Simple function task | Coder → Tester → Critic → PASS in 1 iter |
| **Full SDLC** | Complex API task | PA → Planner → Arch → Fan-out → Integrator → Docs → PASS |
| **HITL Gate** | Enable pre_code gate | Workflow pauses, Liaison approves, continues |
| **Fallback** | Kill primary model | Circuit opens, fallback activates, alert logged |
| **Budget Cap** | Set $0.10 workflow cap | BudgetExceededError raised, workflow stops |
| **Self-Improve** | Run Supervisor | Prompts tuned, weak models switched, report generated |

---

## 📝 SIGN-OFF CHECKLIST (Day 25)

```
☐ All 411 tests pass (0 real API calls)
☐ Zero circular imports
☐ Ruff clean (lint + format)
☐ MyPy clean (strict mode)
☐ Architecture principles verified:
  ☐ Verified Ground Truth (Data