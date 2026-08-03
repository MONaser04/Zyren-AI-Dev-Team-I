"""
Type-Safe Inter-Agent Contracts
================================

Pydantic v2 strict-mode schemas for every agent boundary in the minimal
feedback loop. Validate BEFORE committing to the event log.

Schemas:
    - TaskAssignment:      Orchestrator → Coder
    - CodePatch:           Coder → Tester
    - VerificationReport:  Tester → Critic (facts only)
    - ReviewDecision:      Critic → Orchestrator/Coder
    - WorkflowState:       State projection (current workflow status)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ============================================================
# Enums
# ============================================================


class Verdict(StrEnum):
    """Review outcome from the Grounded Critic."""

    PASS = "PASS"
    BLOCK = "BLOCK"


class Severity(StrEnum):
    """Issue severity in review feedback."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationLevel(StrEnum):
    """Critic escalation ladder — tone intensifies per iteration.

    Per README line 231:
    soft (iter 1) → firm (iter 2) → hard block (iter 3) → escalate to Supervisor.
    """

    SOFT = "soft"
    FIRM = "firm"
    HARD_BLOCK = "hard_block"
    ESCALATE = "escalate"


class RebuttalOutcome(StrEnum):
    """Result of the Critic judging a Coder's rebuttal."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


class WorkflowStatus(StrEnum):
    """Lifecycle status of a workflow."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"


# ============================================================
# Base Contract
# ============================================================


class BaseContract(BaseModel):
    """Base class for all inter-agent contracts."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        description="UTC timestamp when this contract was created.",
    )


# ============================================================
# TaskAssignment — Orchestrator → Coder
# ============================================================


class TaskAssignment(BaseContract):
    """Task assignment from the Orchestrator to the Coder agent.

    Contains the task description, constraints, and iteration context
    so the Coder knows whether this is a first attempt or a retry
    with feedback.
    """

    task_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:12],
        description="Unique identifier for this task.",
    )
    workflow_id: str = Field(
        description="Parent workflow identifier.",
    )
    description: str = Field(
        min_length=1,
        description="Natural-language description of the coding task.",
    )
    language: str = Field(
        default="python",
        description="Target programming language.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Additional constraints or requirements.",
    )
    iteration: int = Field(
        default=1,
        ge=1,
        description="Current iteration number (1 = first attempt).",
    )
    prior_feedback: str | None = Field(
        default=None,
        description="Structured feedback from the Critic on prior iteration.",
    )


# ============================================================
# CodePatch — Coder → Tester
# ============================================================


class FileContent(BaseContract):
    """A single file with its content."""

    path: str = Field(
        min_length=1,
        description="Relative file path (e.g., 'utils.py').",
    )
    content: str = Field(
        description="Full file content.",
    )


class CodePatch(BaseContract):
    """Code patch produced by the Coder agent.

    Contains one or more files constituting the solution attempt.
    """

    task_id: str = Field(description="Task this patch addresses.")
    workflow_id: str = Field(description="Parent workflow identifier.")
    iteration: int = Field(ge=1, description="Iteration number.")
    files: list[FileContent] = Field(
        min_length=1,
        description="Files in this patch (at least one).",
    )
    explanation: str = Field(
        default="",
        description="Coder's explanation of the approach.",
    )

    @model_validator(mode="after")
    def _validate_unique_paths(self) -> CodePatch:
        """Ensure no duplicate file paths in the patch."""
        paths = [f.path for f in self.files]
        if len(paths) != len(set(paths)):
            msg = "Duplicate file paths in patch."
            raise ValueError(msg)
        return self



# ============================================================
# VerificationReport — Tester → Critic (facts only)
# ============================================================


class TestResult(BaseContract):
    """Result of a single test execution."""

    name: str = Field(description="Test name or identifier.")
    passed: bool = Field(description="Whether the test passed.")
    output: str = Field(default="", description="Test output or error message.")


class VerificationReport(BaseContract):
    """Verification report from the Tester agent.

    Contains ONLY measured facts — no opinions, no suggestions.
    The Grounded Critic interprets these signals.
    """

    task_id: str = Field(description="Task that was verified.")
    workflow_id: str = Field(description="Parent workflow identifier.")
    iteration: int = Field(ge=1, description="Iteration number.")

    # --- External Signals (facts only) ---
    tests_passed: bool = Field(description="Whether ALL tests passed.")
    test_results: list[TestResult] = Field(
        default_factory=list,
        description="Individual test results.",
    )
    type_check_passed: bool = Field(description="Whether type checking passed.")
    type_check_output: str = Field(
        default="",
        description="Raw mypy output.",
    )
    lint_passed: bool = Field(description="Whether linting passed.")
    lint_output: str = Field(
        default="",
        description="Raw ruff output.",
    )
    execution_passed: bool = Field(
        default=True,
        description="Whether the code executed without runtime errors.",
    )
    execution_output: str = Field(
        default="",
        description="Raw stdout/stderr from execution.",
    )

    # --- Phase 2: Security scanning ---
    security_passed: bool = Field(
        default=True,
        description="Whether security scanning passed (bandit).",
    )
    security_output: str = Field(
        default="",
        description="Raw security scanner output.",
    )

    # --- Phase 2: Coverage tracking ---
    coverage_percent: float | None = Field(
        default=None,
        description="Test coverage percentage (0.0–100.0).",
    )
    coverage_delta: float | None = Field(
        default=None,
        description="Coverage change from prior iteration.",
    )

    @property
    def all_clean(self) -> bool:
        """True if every verification signal is clean."""
        return (
            self.tests_passed
            and self.type_check_passed
            and self.lint_passed
            and self.execution_passed
            and self.security_passed
        )

    @classmethod
    def from_stored(cls, data: dict) -> "VerificationReport":
        """Create from stored dict (enums as strings, datetime as ISO strings)."""
        # This model only has bool fields, no enums to convert
        return cls.model_validate(data)


# ============================================================
# ReviewDecision — Critic → Orchestrator / Coder
# ============================================================


class ReviewIssue(BaseContract):
    """A single issue identified by the Grounded Critic."""

    description: str = Field(
        min_length=1,
        description="What the issue is.",
    )
    severity: Severity = Field(description="Issue severity.")
    suggestion: str = Field(
        default="",
        description="Suggested fix or approach.",
    )
    source: str = Field(
        default="",
        description="Source of the signal (e.g., 'pytest', 'mypy', 'ruff').",
    )

    @classmethod
    def from_stored(cls, data: dict) -> "ReviewIssue":
        """Create from stored dict (enums as strings, datetime as ISO strings)."""
        if isinstance(data.get("severity"), str):
            data = {**data, "severity": Severity(data["severity"])}
        return cls.model_validate(data)


class ReviewDecision(BaseContract):
    """Review decision from the Grounded Critic.

    PASS:  All checks clean AND rubric satisfied → proceed to merge.
    BLOCK: Issues found → return structured feedback to the Coder.
    """

    task_id: str = Field(description="Task that was reviewed.")
    workflow_id: str = Field(description="Parent workflow identifier.")
    iteration: int = Field(ge=1, description="Iteration number.")
    verdict: Verdict = Field(description="PASS or BLOCK.")
    justification: str = Field(
        min_length=1,
        description="Why this verdict was chosen.",
    )
    issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="List of issues (empty if PASS).",
    )
    feedback_for_coder: str = Field(
        default="",
        description="Structured feedback for the Coder's next iteration.",
    )
    escalation_level: EscalationLevel = Field(
        default=EscalationLevel.SOFT,
        description="Escalation tone level for this review.",
    )

    @model_validator(mode="after")
    def _validate_block_has_issues(self) -> ReviewDecision:
        """A BLOCK verdict must have at least one issue or feedback."""
        if self.verdict == Verdict.BLOCK and not self.issues and not self.feedback_for_coder:
            msg = "BLOCK verdict must include issues or feedback_for_coder."
            raise ValueError(msg)
        return self

    @classmethod
    def from_stored(cls, data: dict) -> "ReviewDecision":
        """Create from stored dict (enums as strings, datetime as ISO strings)."""
        # Handle verdict
        if isinstance(data.get("verdict"), str):
            data = {**data, "verdict": Verdict(data["verdict"])}
        # Handle escalation_level
        if isinstance(data.get("escalation_level"), str):
            data = {**data, "escalation_level": EscalationLevel(data["escalation_level"])}
        # Handle created_at
        if isinstance(data.get("created_at"), str):
            data = {**data, "created_at": datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))}
        # Handle issues
        if "issues" in data and isinstance(data["issues"], list):
            data = {**data, "issues": [ReviewIssue.from_stored(issue) for issue in data["issues"]]}
        return cls.model_validate(data)


# ============================================================
# RebuttalRequest — Coder's Right of Rebuttal (Phase 2)
# ============================================================


class RebuttalRequest(BaseContract):
    """Coder's right of rebuttal against a BLOCK decision.

    Per README line 232: the Coder may reject feedback **once per iteration**
    with a logical justification. If accepted, code passes; if deadlock
    persists, escalate.
    """

    task_id: str = Field(description="Task being rebutted.")
    workflow_id: str = Field(description="Parent workflow identifier.")
    iteration: int = Field(ge=1, description="Iteration number.")
    original_verdict: Verdict = Field(
        default=Verdict.BLOCK,
        description="The verdict being challenged (always BLOCK).",
    )
    justification: str = Field(
        min_length=10,
        description="Coder's justification for why the feedback is wrong.",
    )
    disputed_issues: list[str] = Field(
        default_factory=list,
        description="Descriptions of the specific issues being disputed.",
    )

    @classmethod
    def from_stored(cls, data: dict) -> "RebuttalRequest":
        """Create from stored dict (enums as strings, datetime as ISO strings)."""
        if isinstance(data.get("original_verdict"), str):
            data = {**data, "original_verdict": Verdict(data["original_verdict"])}
        if isinstance(data.get("created_at"), str):
            data = {**data, "created_at": datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))}
        return cls.model_validate(data)


class RebuttalJudgment(BaseContract):
    """Critic's judgment on a Coder's rebuttal."""

    task_id: str = Field(description="Task being judged.")
    workflow_id: str = Field(description="Parent workflow identifier.")
    iteration: int = Field(ge=1, description="Iteration number.")
    outcome: RebuttalOutcome = Field(description="ACCEPTED or REJECTED.")
    reasoning: str = Field(
        min_length=1,
        description="Why the rebuttal was accepted or rejected.",
    )


# ============================================================
# Phase 4: Semantic Router Contract — Multi-Department
# ============================================================


class TargetDomain(StrEnum):
    """Primary routing domain for the multi-department intent classifier."""

    SOFTWARE_ENGINEERING = "software_engineering"
    DEEP_RESEARCH = "deep_research"
    MEDIA_PRODUCTION = "media_production"


class TaskComplexity(StrEnum):
    """Task complexity classification (Software Engineering sub-route)."""

    SIMPLE = "simple"       # Fast Lane: Coder + Critic only
    MEDIUM = "medium"       # Full SDLC (truncated)
    COMPLEX = "complex"     # Full SDLC (full roster)


class SWEComplexityDecision(BaseContract):
    """Sub-routing decision for Software Engineering complexity.

    Encapsulates the Fast Lane vs. Full SDLC classification that was
    previously the sole purpose of the Semantic Router.
    """

    complexity: TaskComplexity
    confidence: float           # 0.0–1.0
    safe_fallback: bool         # True if confidence < threshold → full pipeline
    reasoning: str
    fast_lane: bool             # convenience: complexity == SIMPLE and not safe_fallback


class RoutingDecision(BaseContract):
    """Output of the Multi-Department Semantic Router.

    Carries the target domain and, when the domain is Software Engineering,
    an optional nested SWE complexity sub-decision.
    """

    domain: TargetDomain
    confidence: float           # 0.0–1.0 — domain classification confidence
    safe_fallback: bool         # True if confidence < threshold → defaults to SE
    reasoning: str
    fast_lane: bool             # convenience: SE + SIMPLE + high confidence
    swe_sub: SWEComplexityDecision | None = None  # populated only for SE domain


# ============================================================
# Deep Research Contract — ResearchReport
# ============================================================


class ResearchSource(BaseContract):
    """A single verified source used in deep research."""

    url: str = Field(
        min_length=1,
        description="Source URL.",
    )
    title: str = Field(
        default="",
        description="Page or document title.",
    )
    accessed_at: str = Field(
        default="",
        description="ISO-8601 timestamp when the source was accessed.",
    )
    reliability_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Estimated reliability of this source (0.0–1.0).",
    )


class ResearchDataPoint(BaseContract):
    """A single research finding backed by evidence and confidence."""

    claim: str = Field(
        min_length=1,
        description="The factual claim or data point.",
    )
    evidence: str = Field(
        default="",
        description="Supporting evidence or excerpt.",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in this data point (0.0–1.0).",
    )
    source_urls: list[str] = Field(
        default_factory=list,
        description="URLs supporting this claim.",
    )


class ResearchReport(BaseContract):
    """Output contract for the DeepResearchAgent.

    Structured for secure commit to the append-only Event-Sourced State
    log. Every finding carries provenance and a confidence score.
    """

    query: str = Field(
        min_length=1,
        description="Original research question or topic.",
    )
    summary: str = Field(
        min_length=1,
        description="Executive summary of findings.",
    )
    sources: list[ResearchSource] = Field(
        default_factory=list,
        description="All sources consulted during research.",
    )
    data_points: list[ResearchDataPoint] = Field(
        default_factory=list,
        description="Structured data points extracted from sources.",
    )
    key_findings: list[str] = Field(
        default_factory=list,
        description="Main conclusions and discoveries.",
    )
    methodology: str = Field(
        default="",
        description="Description of the research methodology.",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Known gaps, biases, or caveats.",
    )
    overall_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Aggregate confidence in the report (0.0–1.0).",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Actionable next steps or conclusions.",
    )

    @classmethod
    def from_stored(cls, data: dict) -> "ResearchReport":
        """Create from stored dict (e.g., event payload)."""
        return cls.model_validate(data)


# ============================================================
# Phase 4: Full Agent Roster Contracts
# ============================================================

# --- Producer Output Contracts ---

class ProductRequirementDoc(BaseContract):
    """Product Analyst output: PRD + user stories + acceptance criteria."""
    user_stories: list[str]
    acceptance_criteria: list[str]
    constraints: list[str]
    non_functional: list[str]

    @classmethod
    def from_stored(cls, data: dict) -> "ProductRequirementDoc":
        """Create from stored dict (enums as strings, datetime as ISO strings)."""
        return cls.model_validate(data)


class TaskDAG(BaseContract):
    """Planner output: task graph with dependencies + agent assignments."""
    nodes: list["TaskNode"]  # id, desc, depends_on[], agent_role, complexity
    critical_path: list[str]

    @classmethod
    def from_stored(cls, data: dict) -> "TaskDAG":
        """Create from stored dict (enums as strings, datetime as ISO strings)."""
        if "nodes" in data and isinstance(data["nodes"], list):
            data = {**data, "nodes": [TaskNode.from_stored(node) for node in data["nodes"]]}
        return cls.model_validate(data)


class TaskNode(BaseContract):
    id: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    agent_role: str
    complexity: TaskComplexity

    @classmethod
    def from_stored(cls, data: dict) -> "TaskNode":
        """Create from stored dict (enums as strings)."""
        if isinstance(data.get("complexity"), str):
            data = {**data, "complexity": TaskComplexity(data["complexity"])}
        return cls.model_validate(data)


class ArchitectDesign(BaseContract):
    """Architect output: ADRs + component diagram + tech choices."""
    adrs: list["ADR"]
    component_diagram: str  # mermaid/plantuml
    tech_choices: list[str]
    interfaces: list["InterfaceSpec"]


class ADR(BaseContract):
    """Architecture Decision Record."""
    title: str
    context: str
    decision: str
    consequences: str
    status: str = "proposed"


class InterfaceSpec(BaseContract):
    name: str
    protocol: str  # "REST" | "gRPC" | "GraphQL" | "async"
    contract: str  # OpenAPI/Protobuf ref


class UXDesign(BaseContract):
    """UX Agent output (conditional: frontend only)."""
    wireframes: list[str]  # descriptions/paths
    accessibility_notes: str
    design_system_refs: list[str]


class DataSchema(BaseContract):
    """DB Engineer output (conditional: persistence only)."""
    tables: list["TableSpec"]
    migrations: list[str]
    indexes: list[str]


class TableSpec(BaseContract):
    name: str
    columns: list["ColumnSpec"]
    primary_key: list[str]
    foreign_keys: list["ForeignKeySpec"]


class ColumnSpec(BaseContract):
    name: str
    type: str
    nullable: bool = False
    default: str | None = None


class ForeignKeySpec(BaseContract):
    columns: list[str]
    references: str  # "table(columns)"


class ResearchNotes(BaseContract):
    """Researcher output (on-demand)."""
    topic: str
    findings: list[str]
    sources: list[str]
    recommendations: list[str]


class SecurityReport(BaseContract):
    """Security Agent output (dedicated critic for Coder/Architect/Security)."""
    vulnerabilities: list["Vulnerability"]
    sast_summary: str
    recommendations: list[str]
    risk_level: str  # "low" | "medium" | "high" | "critical"


class Vulnerability(BaseContract):
    id: str
    severity: str
    description: str
    file: str
    line: int | None = None
    fix_hint: str


class IntegratorOutput(BaseContract):
    """Integrator output (Fan-in merge result)."""
    merged_files: list["FileChange"]
    conflicts_resolved: list[str]
    rollback_plan: str


class FileChange(BaseContract):
    path: str
    action: str  # "create" | "update" | "delete"
    content: str | None = None


class DocsOutput(BaseContract):
    """Docs Agent output (two milestones)."""
    milestone: str  # "post_architecture" | "post_integration"
    adrs: list[ADR] | None = None
    readme: str | None = None
    openapi_spec: str | None = None
    inline_docs: list[str] | None = None


# --- Liaison / Supervisor (no new contracts; use state + events) ---


# ============================================================
# WorkflowState — State Projection
# ============================================================


class WorkflowState(BaseModel):
    """Projected current state of a workflow.

    Built by folding all events for a workflow_id.
    Not frozen because projections are mutable during construction.
    """

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(description="Workflow identifier.")
    status: WorkflowStatus = Field(
        default=WorkflowStatus.PENDING,
        description="Current lifecycle status.",
    )
    task_description: str = Field(
        default="",
        description="Original task description.",
    )
    current_iteration: int = Field(
        default=0,
        description="Current iteration count.",
    )
    max_iterations: int = Field(
        default=3,
        description="Maximum allowed iterations.",
    )
    patches: list[dict[str, Any]] = Field(
        default_factory=list,
        description="History of code patches (serialized).",
    )
    reviews: list[dict[str, Any]] = Field(
        default_factory=list,
        description="History of review decisions (serialized).",
    )
    rebuttals: list[dict[str, Any]] = Field(
        default_factory=list,
        description="History of rebuttals (serialized).",
    )
    rebuttal_judgments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="History of rebuttal judgments (serialized).",
    )
    final_verdict: Verdict | None = Field(
        default=None,
        description="Final review verdict (if workflow is done).",
    )
    error: str | None = Field(
        default=None,
        description="Error message if workflow failed.",
    )
    
    # Phase 4 outputs
    architect_design: dict[str, Any] | None = None
    ux_design: dict[str, Any] | None = None
    data_schema: dict[str, Any] | None = None
    security_report: dict[str, Any] | None = None
    research_notes: dict[str, Any] | None = None
    integrator_output: dict[str, Any] | None = None
    docs_adr: dict[str, Any] | None = None
    docs_final: dict[str, Any] | None = None

    # Deep Research domain output
    deep_research_report: dict[str, Any] | None = None
