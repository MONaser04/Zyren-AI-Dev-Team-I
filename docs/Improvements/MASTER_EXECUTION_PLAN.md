# 🎯 MASTER EXECUTION PLAN — Zyren AI Dev-Team Auto-Discovery Model Registry

> **Document Version:** 1.0 | **Created:** 2026-07-11 | **Status:** READY FOR EXECUTION
> **Scope:** Fix all critical issues + Build Auto-Discovery Model Registry with Verified Ground Truth + LLM Reasoning separation
> **Location:** `docs/Improvements/MASTER_EXECUTION_PLAN.md`

---

## 📋 EXECUTIVE SUMMARY

| Metric | Current | Target |
|--------|---------|--------|
| **Tests Passing** | ~380/411 (92%) | **411/411 (100%)** |
| **Circular Imports** | 3+ files | **0** |
| **Model Mapping** | Mismatched (NVIDIA vs OpenAI) | **Unified + Configurable** |
| **Real API Calls in Tests** | Yes (multiple test files) | **Zero - Full Mock Infrastructure** |
| **Model Discovery** | Hardcoded 4 aliases | **Auto-Discovery 10+ Providers** |
| **Information Source** | Mixed (LLM knowledge + config) | **Verified Ground Truth Only + Citations** |
| **Manual Control** | Code changes required | **Liaison Chat: Natural Language → System Action** |

---

## 🏗️ ARCHITECTURAL PRINCIPLES (NON-NEGOTIABLE)

### 1. **Verified Ground Truth for Data Layer | Full LLM Reasoning for Reasoning Layer**

| Layer | Policy | Components |
|-------|--------|------------|
| **Data Layer** | **Verified Only + Citations** | ModelRegistry, SmartGateway, ProviderAdapters, CostTracker, ConfigManager |
| **Reasoning Layer** | **Full LLM Reasoning** | Coder, Architect, Critic, Planner, Researcher, Tester, Liaison |

> **Rule:** Data Layer never guesses. Reasoning Layer never stops reasoning.

### 2. **Auto-Discovery Default + Manual Override Via Liaison Chat**
- System starts in **Auto Mode**: discovers, validates, registers models from official sources
- User says: *"أضف gpt-4o-mini من Azure eastus2 واجعله افتراضي للمهام البسيطة"* → System executes end-to-end
- No code changes, no config file edits, no restarts

### 3. **Zero Real API Calls in Tests**
- All tests use `MockGateway`, `MockProviderAPIs`, `MockEventStore`
- CI/CD runs completely offline

### 4. **Circuit Breakers Everywhere**
- Per-model, per-provider, per-workflow budget caps
- Automatic fallback chains with cooldown
- Health monitoring with alerting

---

## 🔴 PHASE 0: CRITICAL FIXES (Day 1) — **BLOCKING**

### 0.1 Fix Circular Imports (3 files)

| File | Line | Fix |
|------|------|-----|
| `src/orchestrator/runner.py` | 23 | Move `from src.orchestrator.graph import GraphState, build_feedback_loop` inside `run_workflow()` |
| `src/agents/supervisor.py` | 38 | Move `from src.orchestrator.runner import run_workflow` inside `WorkflowRunner.run()` |
| `src/agents/__init__.py` | 22 | Remove `from src.agents.supervisor import SupervisorAgent` OR make lazy import via `__getattr__` |

**Verification:** `pytest tests/test_orchestrator.py tests/test_phase5_closed_loop.py -v` → 100% pass

---

### 0.2 Unify Model Mapping (3 sources)

| Source | Current | Required |
|--------|---------|----------|
| `config/litellm.yaml` | NVIDIA NIM models only | **Add OpenAI, Anthropic, Google, Azure entries** |
| `src/gateway/llm_client.py` (lines 43-48) | NVIDIA NIM defaults | **Match litellm.yaml + support all providers** |
| `tests/test_phase3_gateway.py` | Expects OpenAI models | **Update assertions to accept both** |

**New `DEFAULT_MODEL_MAP` in `llm_client.py`:**
```python
DEFAULT_MODEL_MAP = {
    "frontier": "openai/gpt-4o",
    "fast": "openai/gpt-4o-mini",
    "critic": "anthropic/claude-3.5-sonnet",
    "fallback": "google/gemini-1.5-pro",
    # NVIDIA NIM as alternatives
    "frontier_nim": "nvidia_nim/nvidia/nemotron-3-ultra",
    "fast_nim": "nvidia_nim/minimaxai/minimax-m3",
    "critic_nim": "nvidia_nim/google/gemma-4-31b-it",
}
```

**Verification:** `pytest tests/test_phase3_gateway.py::TestLLMClientRouting -v` → 100% pass

---

### 0.3 Build Mock Test Infrastructure (New Files)

```
tests/
├── conftest.py                          # Shared fixtures
├── mocks/
│   ├── __init__.py
│   ├── mock_gateway.py                  # MockGateway class
│   ├── mock_models.py                   # Dataclasses for responses
│   ├── mock_provider_apis.py            # Mock OpenAI/Anthropic/Google
│   ├── mock_event_store.py              # Mock EventStore
│   └── mock_researcher.py               # MockResearcherAgent
└── fixtures/
    ├── sample_models.json               # Test model data
    ├── sample_pricing.json              # Test pricing data
    └── golden_tasks.yaml                # Golden task definitions
```

**Key Fixtures in `conftest.py`:**
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

**Verification:** All 411 tests pass with **zero real API calls**

---

## 🏗️ PHASE 1: AUTO MODEL REGISTRY CORE (Days 2-3)

### 1.1 Data Models (`src/gateway/model_registry.py`)

```python
@dataclass(frozen=True)
class SourceCitation:
    source_type: Literal["api", "official_docs", "pricing_page", "model_card", "changelog"]
    url: str
    provider: str
    accessed_at: datetime
    field_mapping: dict[str, str]      # field_name → snippet_source
    confidence: float                   # 0.0-1.0
    raw_snippet: str                    # Exact text used

@dataclass(frozen=True)
class ModelCapabilities:
    context_window: int
    modalities: list[str]               # ["text", "vision", "audio", "function_calling"]
    function_calling: bool
    structured_output: bool
    parallel_tool_calls: bool
    max_output_tokens: int

@dataclass(frozen=True)
class ModelPricing:
    input_per_1m_tokens: float
    output_per_1m_tokens: float
    currency: str = "USD"
    citation: SourceCitation = None
    effective_date: datetime = None

@dataclass(frozen=True)
class ModelLimits:
    rpm: int | None = None              # requests per minute
    tpm: int | None = None              # tokens per minute
    rpd: int | None = None              # requests per day
    regions: list[str] = None
    deprecated: bool = False
    sunset_date: datetime | None = None

@dataclass(frozen=True)
class ModelSpec:
    # Identity
    model_id: str                       # "gpt-4o-2024-08-06"
    provider: str                       # "openai"
    provider_model_id: str              # As appears in provider API
    aliases: list[str] = field(default_factory=list)  # ["frontier", "gpt4o"]
    
    # Verified Ground Truth (every field has citation)
    capabilities: ModelCapabilities
    pricing: ModelPricing
    limits: ModelLimits
    
    # Metadata
    discovered_at: datetime
    source_citations: list[SourceCitation]
    confidence_score: float             # Overall 0.0-1.0
    last_verified: datetime
    status: ModelStatus                 # ACTIVE, DEPRECATED, DISCONTINUED, UNVERIFIED
```

### 1.2 Provider Adapters (`src/gateway/providers/`)

```
providers/
├── __init__.py
├── base.py                    # ProviderAdapter (ABC)
├── openai_adapter.py          # OpenAI API
├── anthropic_adapter.py       # Anthropic API
├── google_adapter.py          # Vertex AI / Gemini
├── nvidia_nim_adapter.py      # NVIDIA NIM
├── azure_adapter.py           # Azure OpenAI
├── aws_bedrock_adapter.py     # AWS Bedrock
├── ollama_adapter.py          # Ollama (local)
├── together_adapter.py        # Together AI
├── fireworks_adapter.py       # Fireworks AI
├── groq_adapter.py            # Groq
└── registry.py                # ProviderAdapterRegistry
```

**Each adapter implements:**
```python
class ProviderAdapter(ABC):
    provider_name: str
    
    @abstractmethod
    async def list_models(self) -> list[RawModelInfo]
    
    @abstractmethod
    async def get_model_details(self, model_id: str) -> RawModelDetails
    
    @abstractmethod
    async def get_pricing(self, model_id: str) -> RawPricingInfo
    
    @abstractmethod
    async def get_limits(self, model_id: str) -> RawLimitsInfo
    
    @abstractmethod
    def get_official_docs_url(self, model_id: str) -> str
    
    @abstractmethod
    async def validate_model_exists(self, model_id: str) -> bool
```

**Official Sources per Provider:**
| Provider | Models API | Pricing | Docs |
|----------|-----------|---------|------|
| OpenAI | `/v1/models` | pricing.openai.com | platform.openai.com/docs/models |
| Anthropic | N/A (static) | anthropic.com/pricing | docs.anthropic.com |
| Google | Vertex Model Garden | cloud.google.com/vertex-ai/pricing | cloud.google.com/vertex-ai/docs |
| NVIDIA NIM | `/v1/models` | build.nvidia.com | docs.nvidia.com/nim |
| Azure | `/openai/deployments` | azure.microsoft.com/pricing | learn.microsoft.com/azure/ai-services |
| Ollama | `/api/tags` | Free | ollama.com/library |

---

### 1.3 AutoModelRegistry (`src/gateway/model_registry.py`)

```python
class AutoModelRegistry:
    def __init__(self, gateway, researcher_agent, liaison_agent, config: RegistryConfig):
        self._models: dict[str, ModelSpec] = {}
        self._provider_adapters: dict[str, ProviderAdapter] = {}
        self._gateway = gateway
        self._researcher = researcher_agent
        self._liaison = liaison_agent
        self._config = config
        self._discovery_lock = asyncio.Lock()
    
    # ========== AUTO DISCOVERY ==========
    
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
        
        # 2. Build capabilities from raw data
        capabilities = self._infer_capabilities(details)
        
        # 3. Create citations for EVERY field
        citations = self._create_citations(provider, raw.model_id, details, pricing, limits, adapter)
        
        # 4. Cross-validate with Researcher if needed
        if self._config.cross_validate:
            validation = await self._researcher.cross_validate(provider, raw.model_id, citations)
            if not validation.passed:
                return None  # Reject unverified model
        
        return ModelSpec(
            model_id=raw.model_id,
            provider=provider,
            provider_model_id=raw.model_id,
            capabilities=capabilities,
            pricing=ModelPricing.from_raw(pricing, citations.get("pricing")),
            limits=ModelLimits.from_raw(limits, citations.get("limits")),
            source_citations=citations,
            confidence_score=self._calculate_confidence(citations),
            status=ModelStatus.ACTIVE,
            # ...
        )
    
    async def scheduled_refresh(self, interval_hours: int = 24):
        """Background task: refresh all models periodically"""
        while True:
            await asyncio.sleep(interval_hours * 3600)
            await self.discover_all_providers()
    
    # ========== MANUAL OVERRIDE (via Liaison) ==========
    
    async def manual_add_model(self, spec: ModelSpec, requested_by: str) -> ModelSpec:
        """Add model manually (user command via Liaison)"""
        # Validate with Researcher
        validated = await self._researcher.validate_manual_model(spec)
        self._models[validated.model_id] = validated
        await self._notify_gateway_model_added(validated)
        return validated
    
    async def manual_update_model(self, model_id: str, updates: dict, requested_by: str):
        """Update specific fields"""
        spec = self._models[model_id]
        updated = spec.model_copy(update=updates)
        updated.last_verified = datetime.now(UTC)
        self._models[model_id] = updated
        await self._notify_gateway_model_updated(updated)
    
    async def manual_disable_model(self, model_id: str, reason: str, requested_by: str):
        spec = self._models[model_id]
        updated = spec.model_copy(update={"status": ModelStatus.DISABLED, "disable_reason": reason})
        self._models[model_id] = updated
        await self._notify_gateway_model_disabled(model_id)
    
    async def manual_enable_model(self, model_id: str, requested_by: str):
        spec = self._models[model_id]
        updated = spec.model_copy(update={"status": ModelStatus.ACTIVE})
        self._models[model_id] = updated
        await self._notify_gateway_model_enabled(model_id)
    
    # ========== QUERY ==========
    
    def get_model(self, model_id: str) -> ModelSpec | None:
        return self._models.get(model_id)
    
    def find_best_model(self, criteria: RoutingCriteria) -> ModelSpec:
        candidates = self._filter_models(criteria)
        if not candidates:
            raise NoModelAvailableError(criteria)
        return self._score_and_rank(candidates, criteria)[0]
    
    def list_models(self, filters: ModelFilters = None) -> list[ModelSpec]:
        models = list(self._models.values())
        if filters:
            models = self._apply_filters(models, filters)
        return models
```

---

## 🔬 PHASE 2: PROFESSIONAL RESEARCHER AGENT (Days 4-5)

### 2.1 Core Researcher (`src/agents/professional_researcher.py`)

```python
class ProfessionalResearcherAgent(BaseAgent):
    """
    باحث محترف - صفر تخمين، صفر معرفة LLM
    كل معلومة = مصدر رسمي + Timestamp + Confidence
    """
    
    def __init__(self, gateway, http_client, cache):
        self._providers_docs = {
            "openai": OpenAIOfficialDocs(),
            "anthropic": AnthropicOfficialDocs(),
            "google": GoogleOfficialDocs(),
            "nvidia": NvidiaOfficialDocs(),
            "azure": AzureOfficialDocs(),
            "aws": AWSOfficialDocs(),
            "ollama": OllamaOfficialDocs(),
        }
        self._http = http_client
        self._cache = cache  # Redis/memory cache with TTL
    
    # Core Research Tasks
    async def research_model_spec(self, provider: str, model_id: str) -> ResearchResult
    async def research_provider_pricing(self, provider: str) -> ResearchResult
    async def research_provider_capabilities(self, provider: str) -> ResearchResult
    async def cross_validate(self, model_id: str, sources: list) -> ValidationResult
    async def fetch_official_docs(self, url: str) -> ParsedContent
    
    # LLM Tools (for reasoning layer to use)
    def get_tools(self) -> list[Tool]:
        return [
            Tool("fetch_official_page", self._fetch_official_page),
            Tool("call_provider_api", self._call_provider_api),
            Tool("parse_pricing_table", self._parse_pricing_table),
            Tool("validate_model_card", self._validate_model_card),
        ]

@dataclass
class ResearchResult:
    model_spec: ModelSpec | None
    sources: list[SourceCitation]      # Every source: URL, type, accessed_at, confidence
    confidence: float                   # 0.0-1.0
    warnings: list[str]                 # Warnings (stale source, conflicts, etc)
    raw_evidence: dict                  # Raw evidence for audit
```

### 2.2 Provider-Specific Doc Fetchers

Each fetcher handles ONE official source:

```python
class OpenAIOfficialDocs:
    """Scrapes platform.openai.com/docs/models + pricing page"""
    BASE_URL = "https://platform.openai.com/docs/models"
    PRICING_URL = "https://openai.com/pricing"
    
    async def fetch_model_list(self) -> list[ModelSummary]
    async def fetch_model_details(self, model_id: str) -> ModelDetail
    async def fetch_pricing(self) -> PricingTable
    async def fetch_rate_limits(self) -> RateLimitInfo

class AnthropicOfficialDocs:
    """Scrapes docs.anthropic.com + pricing page"""
    BASE_URL = "https://docs.anthropic.com/claude/docs/models-overview"
    PRICING_URL = "https://www.anthropic.com/pricing"

class GoogleOfficialDocs:
    """Vertex AI Model Garden + cloud.google.com/vertex-ai/pricing"""
    
class NvidiaOfficialDocs:
    """build.nvidia.com + docs.nvidia.com/nim"""

class AzureOfficialDocs:
    """learn.microsoft.com/azure/ai-services + pricing calculator"""

class AWSOfficialDocs:
    """aws.amazon.com/bedrock + pricing"""

class OllamaOfficialDocs:
    """ollama.com/library + GitHub repo"""
```

### 2.3 Source Citation Structure (Every Piece of Data)

```python
@dataclass(frozen=True)
class SourceCitation:
    source_type: Literal["api", "official_docs", "pricing_page", "model_card", "changelog"]
    url: str
    provider: str
    accessed_at: datetime
    field_mapping: dict[str, str]      # field_name → snippet_source
    confidence: float                   # API=1.0, pricing_page=0.9, docs=0.85
    raw_snippet: str                    # Exact text used
```

---

## 🧠 PHASE 3: SMART GATEWAY + AUTO ROUTER (Days 5-6)

### 3.1 Smart Gateway (`src/gateway/smart_gateway.py`)

```python
class SmartGateway:
    """THE ONLY GATEWAY - no direct litellm calls ever"""
    
    def __init__(self, registry: AutoModelRegistry, resilience: ResilienceLayer):
        self._registry = registry
        self._resilience = resilience
        self._router = SmartRouter(registry)
        self._cost_tracker = CostTracker(registry)
    
    # ONLY PUBLIC INTERFACE
    async def complete(self, request: CompletionRequest) -> CompletionResponse
    async def complete_structured(self, request: StructuredCompletionRequest) -> T
    
    # Smart Routing
    def route_request(self, request: CompletionRequest) -> RoutingDecision:
        """
        Decision Factors (in priority order):
        1. Task Complexity (from Semantic Router)
        2. Required Capabilities (function calling, vision, long context, etc.)
        3. Cost Budget (from request or workflow)
        4. Performance History (latency, success rate, quality)
        5. Availability (circuit breaker, rate limits)
        6. USER PREFERENCE (Manual Override via Liaison)
        """
    
    # Manual Override Handlers (from Liaison)
    async def handle_manual_model_change(self, command: ManualModelCommand) -> Result
    async def handle_provider_disable(self, provider: str, reason: str) -> Result
    async def handle_model_override(self, task_type: str, model_id: str) -> Result
```

### 3.2 Smart Router (`src/gateway/smart_router.py`)

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
    
    def build_fallback_chain(self, primary: ModelSpec, criteria: RoutingCriteria) -> list[ModelSpec]
```

### 3.3 Resilience Layer (`src/gateway/resilience.py`)

- Per-model Circuit Breakers
- Fallback Chains with cooldown
- Rate limit tracking per provider/model
- Health monitoring with alerting

---

## 💬 PHASE 4: LIAISON CHAT INTERFACE (Days 6-7)

### 4.1 Liaison Agent (`src/agents/liaison.py`)

```python
class LiaisonAgent(BaseAgent):
    """ONLY HUMAN INTERFACE - understands natural language, sends structured commands"""
    
    COMMAND_PATTERNS = {
        # Model Management
        r"أضف نموذج\s+(\S+)\s+من\s+(\S+)": ("add_model", ["model_id", "provider"]),
        r"أزل نموذج\s+(\S+)": ("remove_model", ["model_id"]),
        r"أوقف\s+(\S+)\s+مؤقتاً": ("disable_model", ["model_id"]),
        r"أعد تفعيل\s+(\S+)": ("enable_model", ["model_id"]),
        r"اجعل\s+(\S+)\s+الافتراضي\s+لـ\s+(\S+)": ("set_default", ["model_id", "task_type"]),
        r"اعرض النماذج\s+(?:المتاحة\s+)?(?:لـ\s+(\S+))?": ("list_models", ["task_type?"]),
        r"قارن\s+(\S+)\s+و\s+(\S+)": ("compare_models", ["model_a", "model_b"]),
        
        # Provider Management
        r"أوقف موفر\s+(\S+)\s+بالكامل": ("disable_provider", ["provider"]),
        r"أعد تفعيل موفر\s+(\S+)": ("enable_provider", ["provider"]),
        r"حدث معلومات موفر\s+(\S+)": ("refresh_provider", ["provider"]),
        
        # Discovery
        r"اكتشف جميع النماذج": ("discover_all", []),
        r"اكتشف نماذج موفر\s+(\S+)": ("discover_provider", ["provider"]),
        r"ابحث عن معلومات رسمية لـ\s+(\S+)": ("research_model", ["model_id"]),
        
        # Configuration
        r"غير إعداد\s+(\S+)\s+إلى\s+(\S+)": ("change_setting", ["setting", "value"]),
        r"أظهر الإعدادات": ("show_settings", []),
    }
    
    async def process_user_message(self, message: str) -> LiaisonResponse:
        # 1. Parse intent from natural language
        command = self._parse_command(message)
        
        # 2. Validate & enrich
        validated = await self._validate_command(command)
        
        # 3. Send structured command to Orchestrator
        result = await self._orchestrator.execute_command(validated)
        
        # 4. Format response for user
        return self._format_response(result)
```

### 4.2 Command Executor (`src/orchestrator/command_executor.py`)

```python
class CommandExecutor:
    """Executes Liaison commands by distributing to appropriate agents"""
    
    async def execute_command(self, command: ParsedCommand) -> CommandResult:
        match command.action:
            case "add_model":
                # Liaison → Researcher (fetch official specs) → Registry (register) → Gateway (update routing) → Config (update litellm.yaml)
                return await self._add_model_flow(command)
            case "disable_provider":
                # Liaison → Gateway (disable adapter) → Registry (mark models unavailable)
                return await self._disable_provider_flow(command)
            case "set_default":
                # Liaison → Gateway (update routing rules) → Registry (update defaults)
                return await self._set_default_flow(command)
            case "discover_all":
                # Liaison → Registry (discover_all_providers) → Researcher (for each provider)
                return await self._discover_all_flow(command)
            # ... other commands
```

---

## ✅ PHASE 5: INTEGRATION & FULL TEST SUITE (Days 7-8)

### 5.1 Test Suite Verification

```bash
# Target: 411/411 passed
uv run pytest tests/ -v --tb=short

# Code Quality
uv run ruff check src/ tests/
uv run mypy src/
```

### 5.2 End-to-End Scenarios Testing

| Scenario | Test | Expected |
|----------|------|----------|
| **Auto Discovery** | `discover_all` | Registers 10+ providers with models |
| **Manual Override** | `"أضف gpt-4o من Azure"` | Registry + Gateway + Config updated |
| **Research Flow** | `"ابحث عن o3-mini"` | Researcher fetches from OpenAI official + citations |
| **Routing** | Simple task → gpt-4o-mini, Complex → gpt-4o, Critical → claude-3.5-sonnet | Correct model selected |
| **Fallback** | Primary model fails | Fallback chain activates automatically |
| **Circuit Breaker** | Budget exceeded | Circuit opens, Liaison alerts user |

### 5.3 Documentation Updates

- Update `README.md` with new Auto-Discovery section
- Add `docs/Improvements/ARCHITECTURE_DECISIONS.md` documenting Verified Ground Truth principle
- Update `config/` examples with new provider configurations

---

## 📊 SUCCESS CRITERIA (NON-NEGOTIABLE)

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Test Pass Rate** | 411/411 (100%) | `pytest tests/` |
| **Zero Real API Calls in Tests** | 0 | Network monitor / Mock verification |
| **Circular Imports** | 0 | `python -c "import src"` |
| **Verified Data Coverage** | 100% of ModelSpec fields have citations | Audit script |
| **Liaison Command Coverage** | 15+ natural language commands | Manual test matrix |
| **Auto Discovery** | 10+ providers discovered | Discovery report |
| **Code Quality** | Clean | `ruff check` + `mypy` clean |
| **Response Time** | <2s for routing decision | Benchmark |

---

## 📁 FILE STRUCTURE SUMMARY

### New Files to Create

```
src/
├── gateway/
│   ├── model_registry.py              # AutoModelRegistry + ModelSpec
│   ├── smart_gateway.py               # SmartGateway (only gateway)
│   ├── smart_router.py                # SmartRouter
│   ├── resilience.py                  # Circuit breakers, fallbacks
│   └── providers/
│       ├── __init__.py
│       ├── base.py                    # ProviderAdapter (ABC)
│       ├── openai_adapter.py
│       ├── anthropic_adapter.py
│       ├── google_adapter.py
│       ├── nvidia_nim_adapter.py
│       ├── azure_adapter.py
│       ├── aws_bedrock_adapter.py
│       ├── ollama_adapter.py
│       ├── together_adapter.py
│       ├── fireworks_adapter.py
│       └── groq_adapter.py
├── agents/
│   ├── professional_researcher.py     # ProfessionalResearcherAgent
│   └── researcher_docs/
│       ├── __init__.py
│       ├── base.py                    # OfficialDocsFetcher (ABC)
│       ├── openai_docs.py
│       ├── anthropic_docs.py
│       ├── google_docs.py
│       ├── nvidia_docs.py
│       ├── azure_docs.py
│       ├── aws_docs.py
│       └── ollama_docs.py
├── orchestrator/
│   └── command_executor.py            # CommandExecutor

tests/
├── conftest.py                        # Shared fixtures
├── mocks/
│   ├── __init__.py
│   ├── mock_gateway.py
│   ├── mock_models.py
│   ├── mock_provider_apis.py
│   ├── mock_event_store.py
│   └── mock_researcher.py
└── fixtures/
    ├── sample_models.json
    ├── sample_pricing.json
    └── golden_tasks.yaml

docs/
└── Improvements/
    ├── MASTER_EXECUTION_PLAN.md       # THIS FILE
    └── ARCHITECTURE_DECISIONS.md      # Verified Ground Truth principle
```

### Files to Modify

```
src/
├── orchestrator/
│   ├── runner.py                      # Fix circular import (lazy import)
│   └── graph.py                       # Remove SupervisorAgent import from top-level
├── agents/
│   ├── __init__.py                    # Fix circular import (lazy SupervisorAgent)
│   └── supervisor.py                  # Lazy import run_workflow
├── gateway/
│   └── llm_client.py                  # Unify DEFAULT_MODEL_MAP with litellm.yaml
├── gateway/llm_client.py              # Remove direct litellm calls, use SmartGateway
config/
├── litellm.yaml                       # Add OpenAI, Anthropic, Google, Azure models
tests/
├── test_phase3_gateway.py             # Update assertions for unified model map
```

---

## ⚠️ RISKS & MITIGATIONS

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Provider API changes break adapters | Medium | High | Version-pinned adapters, graceful degradation, alerts |
| Official docs scraping blocked | Low | Medium | Fallback to API-only mode, cache with TTL |
| Cross-validation too strict rejects valid models | Medium | Medium | Configurable threshold, manual override always works |
| Circular import fixes incomplete | Low | High | Run import test in CI: `python -c "import src"` |
| Test mock infrastructure incomplete | Medium | High | Build mocks first (Phase 0.3), verify with `pytest tests/test_smoke.py` |

---

## 🚀 EXECUTION ORDER (DEPENDENCY GRAPH)

```
Phase 0 (Day 1) ──────────────────► Phase 1 (Days 2-3)
    │                                    │
    │                                    ▼
    │                              Phase 2 (Days 4-5)
    │                                    │
    ▼                                    ▼
Phase 3 (Days 5-6) ◄──────────── Phase 4 (Days 6-7)
    │                                    │
    └───────────────► Phase 5 (Days 7-8) ◄┘
```

**Critical Path:** 0 → 1 → 3 → 5 (Phases 2 & 4 can run in parallel with 1 & 3 respectively)

---

## 📝 ARCHITECTURE DECISIONS LOG

See `docs/Improvements/ARCHITECTURE_DEC
