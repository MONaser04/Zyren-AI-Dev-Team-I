"""
Orchestrator Graph — LangGraph Feedback Loop with Rebuttal + Full SDLC (Phase 4)
================================================================================

Phase 2 upgrade: adds the Agentic Pushback (rebuttal) edge.
Phase 4 upgrade: adds Semantic Router (Fast Lane / Full SDLC) + DAG Fan-out/Fan-in.

Architecture (after Phase 4):
    START → assign_task → route (Semantic Router)
              ├─ fast_lane: SIMPLE + high confidence → Coder → Tester → Critic → PASS/FAIL/Rebuttal
              └─ full_lane: MEDIUM/COMPLEX or low confidence → Product Analyst → Planner → Architect
                    → Fan-out (parallel): UX │ DB Engineer │ Security │ Researcher │ Coder
                    → Fan-in: Integrator → Docs (post-arch ADRs) → Tester → Critic
                    → if PASS → Docs (post-integration) → COMPLETE
                    → if BLOCK → loop back to Coder
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, TypedDict

from langgraph.graph import END, StateGraph

from agents.coder import CoderAgent
from agents.critic import CriticAgent
from agents.tester import TesterAgent
from contracts.schemas import (
    CodePatch,
    RebuttalOutcome,
    RebuttalRequest,
    ReviewDecision,
    TaskAssignment,
    Verdict,
    VerificationReport,
)
from state.events import (
    code_submitted_event,
    rebuttal_judged_event,
    rebuttal_submitted_event,
    review_decided_event,
    task_created_event,
    verification_completed_event,
    workflow_completed_event,
    workflow_failed_event,
)

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from state.store import EventStore

logger = logging.getLogger(__name__)

# ============================================================
# Graph State
# ============================================================


class GraphState(TypedDict, total=False):
    """Typed state for the LangGraph feedback loop.

    All data flows through this state dict. LangGraph manages
    state transitions and checkpointing.
    """

    # Workflow metadata
    workflow_id: str
    task_description: str
    language: str
    constraints: list[str]
    max_iterations: int

    # Iteration tracking
    current_iteration: int

    # Agent outputs (latest)
    task_assignment: dict[str, Any]
    code_patch: dict[str, Any]
    verification_report: dict[str, Any]
    review_decision: dict[str, Any]
    rebuttal: dict[str, Any]
    rebuttal_judgment: dict[str, Any]
    
    # Phase 4 outputs
    product_requirements: dict[str, Any]
    task_dag: dict[str, Any]
    architect_design: dict[str, Any]
    ux_design: dict[str, Any]
    data_schema: dict[str, Any]
    security_report: dict[str, Any]
    research_notes: dict[str, Any]
    integrator_output: dict[str, Any]
    docs_adr: dict[str, Any]
    docs_final: dict[str, Any]
    error: str

    # Loop control
    verdict: str
    feedback: str

    # Phase 2: Rebuttal tracking
    rebuttal_used: bool
    rebuttal_request: dict[str, Any]
    rebuttal_outcome: str

    # Phase 4: Routing & Full SDLC state
    routing_decision: dict[str, Any]  # RoutingDecision.model_dump()
    fast_lane: bool
    complexity: str  # "simple" | "medium" | "complex"
    domain: str  # "software_engineering" | "deep_research" | "media_production"
    swe_sub: dict[str, Any]  # SWEComplexityDecision.model_dump() | None
    
    # Full SDLC outputs
    product_requirements: dict[str, Any]  # ProductRequirementDoc
    task_dag: dict[str, Any]  # TaskDAG
    architect_design: dict[str, Any]  # ArchitectDesign
    ux_design: dict[str, Any]  # UXDesign (optional)
    data_schema: dict[str, Any]  # DataSchema (optional)
    security_report: dict[str, Any]  # SecurityReport
    research_notes: dict[str, Any]  # ResearchNotes (optional)
    integrator_output: dict[str, Any]  # IntegratorOutput
    docs_adr: dict[str, Any]  # DocsOutput (post-arch)
    docs_final: dict[str, Any]  # DocsOutput (post-integration)

    # Deep Research domain output
    deep_research_report: dict[str, Any]  # ResearchReport

    # Exploration domain output
    exploration_report: dict[str, Any]  # ProjectExplorationReport

    # Event versioning
    event_version: int
    last_event_id: str
    correlation_id: str


# ============================================================
# Node Helpers
# ============================================================


def _next_version(state: GraphState) -> int:
    """Get the next event version from state (0 triggers auto-increment in store)."""
    return 0


# ============================================================
# Node Functions — Phase 2 Core Loop (unchanged)
# ============================================================


def _assign_task_node(
    state: GraphState, event_store: EventStore
) -> dict[str, Any]:
    """Create the task and emit the first event."""
    workflow_id = state.get("workflow_id", uuid.uuid4().hex[:12])
    task_desc = state.get("task_description", "")
    max_iter = state.get("max_iterations", 3)

    event = task_created_event(
        workflow_id=workflow_id,
        task_description=task_desc,
        max_iterations=max_iter,
    )
    event_store.append(event)

    task = TaskAssignment(
        workflow_id=workflow_id,
        description=task_desc,
        language=state.get("language", "python"),
        constraints=state.get("constraints", []),
        iteration=1,
    )

    return {
        **state,
        "workflow_id": workflow_id,
        "current_iteration": 1,
        "task_assignment": task.model_dump(),
        "event_version": event.version,
        "last_event_id": event.event_id,
        "correlation_id": event.correlation_id or event.event_id,
        "rebuttal_used": False,
    }


def _coder_node(
    state: GraphState, coder: CoderAgent, event_store: EventStore
) -> dict[str, Any]:
    """Run the Coder agent and emit a CODE_SUBMITTED event."""
    task_data = state["task_assignment"]
    iteration = state["current_iteration"]

    # On retry, inject feedback from the Critic
    feedback = state.get("feedback", "")
    if feedback and iteration > 1:
        task_data = {**task_data, "iteration": iteration, "prior_feedback": feedback}

    task = TaskAssignment.model_validate(task_data)
    patch = coder.run(task)

    # Record coder's model family for Critic diversity enforcement
    from gateway.model_registry import BenchmarkRegistry
    bench_reg = BenchmarkRegistry()
    coder_model_family = bench_reg.get_family(coder.model)

    version = _next_version(state)
    event = code_submitted_event(
        workflow_id=state["workflow_id"],
        version=version,
        patch_data=patch.model_dump(mode="json"),
        iteration=iteration,
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "code_patch": patch.model_dump(),
        "coder_model_family": coder_model_family,
        "event_version": version,
        "last_event_id": event.event_id,
        "rebuttal_used": False,  # Reset per iteration
    }


def _tester_node(
    state: GraphState, tester: TesterAgent, event_store: EventStore
) -> dict[str, Any]:
    """Run the Tester agent and emit a VERIFICATION_COMPLETED event."""
    patch = CodePatch.model_validate(state["code_patch"])
    report = tester.run(patch)

    version = _next_version(state)
    event = verification_completed_event(
        workflow_id=state["workflow_id"],
        version=version,
        report_data=report.model_dump(mode="json"),
        iteration=state["current_iteration"],
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "verification_report": report.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _critic_node(
    state: GraphState, critic: CriticAgent, event_store: EventStore
) -> dict[str, Any]:
    """Run the Critic agent and emit a REVIEW_DECIDED event."""
    patch = CodePatch.model_validate(state["code_patch"])
    report = VerificationReport.model_validate(state["verification_report"])

    # Extract coder's model family for diversity enforcement
    coder_model_family = state.get("coder_model_family")

    decision = critic.run(patch, report, coder_model_family=coder_model_family)

    version = _next_version(state)
    event = review_decided_event(
        workflow_id=state["workflow_id"],
        version=version,
        decision_data=decision.model_dump(mode="json"),
        iteration=state["current_iteration"],
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    # Store enum values as strings in state for LangGraph serialization compatibility
    # Pydantic will auto-convert string values to enum instances during validation
    return {
        **state,
        "review_decision": {
            "task_id": decision.task_id,
            "workflow_id": decision.workflow_id,
            "iteration": decision.iteration,
            "verdict": decision.verdict.value,
            "justification": decision.justification,
            "issues": [
                {
                    "description": issue.description,
                    "severity": issue.severity.value,
                    "suggestion": issue.suggestion,
                    "source": issue.source,
                }
                for issue in decision.issues
            ],
            "feedback_for_coder": decision.feedback_for_coder,
            "escalation_level": decision.escalation_level.value,
            "created_at": decision.created_at.isoformat() if decision.created_at else None,
        },
        "verdict": decision.verdict.value,
        "feedback": decision.feedback_for_coder,
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _coder_rebut_node(
    state: GraphState, coder: CoderAgent, event_store: EventStore
) -> dict[str, Any]:
    """Coder considers and optionally submits a rebuttal."""
    decision = ReviewDecision.from_stored(state["review_decision"])
    report = VerificationReport.from_stored(state["verification_report"])

    rebuttal = coder.rebut(decision, report)

    if rebuttal is None:
        # Coder accepts feedback, no rebuttal
        return {
            **state,
            "rebuttal_used": True,
            "rebuttal_request": {},
            "rebuttal_outcome": "",
        }

    version = _next_version(state)
    event = rebuttal_submitted_event(
        workflow_id=state["workflow_id"],
        version=version,
        rebuttal_data=rebuttal.model_dump(mode="json"),
        iteration=state["current_iteration"],
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "rebuttal_used": True,
        "rebuttal_request": rebuttal.model_dump(mode="json"),
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _judge_rebuttal_node(
    state: GraphState, critic: CriticAgent, event_store: EventStore
) -> dict[str, Any]:
    """Critic judges the Coder's rebuttal."""
    rebuttal_data = state.get("rebuttal_request", {})

    # No rebuttal was submitted
    if not rebuttal_data:
        return {
            **state,
            "rebuttal_outcome": "no_rebuttal",
        }

    rebuttal = RebuttalRequest.from_stored(rebuttal_data)
    decision = ReviewDecision.from_stored(state["review_decision"])
    report = VerificationReport.from_stored(state["verification_report"])

    judgment = critic.judge_rebuttal(rebuttal, decision, report)

    version = _next_version(state)
    event = rebuttal_judged_event(
        workflow_id=state["workflow_id"],
        version=version,
        judgment_data=judgment.model_dump(mode="json"),
        iteration=state["current_iteration"],
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    updates: dict[str, Any] = {
        "rebuttal_outcome": judgment.outcome.value,
        "event_version": version,
        "last_event_id": event.event_id,
    }
    
    if judgment.outcome == RebuttalOutcome.ACCEPTED:
        updates["verdict"] = Verdict.PASS.value

    return {
        **state,
        **updates,
    }


def _complete_node(
    state: GraphState, event_store: EventStore
) -> dict[str, Any]:
    """Mark the workflow as completed."""
    version = _next_version(state)
    event = workflow_completed_event(
        workflow_id=state["workflow_id"],
        version=version,
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        "verdict": Verdict.PASS.value,
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _fail_node(
    state: GraphState, event_store: EventStore
) -> dict[str, Any]:
    """Mark the workflow as failed due to iteration cap."""
    version = _next_version(state)
    reason = (
        f"Iteration cap ({state.get('max_iterations', 3)}) reached "
        f"at iteration {state['current_iteration']}."
    )
    event = workflow_failed_event(
        workflow_id=state["workflow_id"],
        version=version,
        reason=reason,
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    logger.info("Workflow FAILED: %s — %s", state["workflow_id"], reason)
    return {
        **state,
        "error": reason,
        "event_version": version,
        "last_event_id": event.event_id,
    }


# ============================================================
# Decision Routers — Phase 2 Core Loop
# ============================================================


def _should_continue(state: GraphState) -> str:
    """Route after the Critic's verdict.

    Returns:
        'complete' if PASS, 'should_rebut' if BLOCK and under cap,
        'fail' if cap reached.
    """
    verdict = state.get("verdict", "")
    if verdict == Verdict.PASS.value:
        return "complete" if state.get("fast_lane", True) else "docs_int"

    current = state.get("current_iteration", 1)
    max_iter = state.get("max_iterations", 3)

    if current >= max_iter:
        return "fail"

    # Under cap and BLOCK — check if rebuttal is available
    return "should_rebut"


def _should_rebut_router(state: GraphState) -> str:
    """Decide whether to attempt a rebuttal judgment.

    If coder produced a rebuttal_request, we go to judge_rebuttal.
    Otherwise, we increment.
    """
    if state.get("rebuttal_request"):
        return "try_rebut"
    return "no_rebut"


def _rebuttal_outcome_router(state: GraphState) -> str:
    """Route after judge_rebuttal.

    Returns:
        'accepted_fast' if accepted and fast_lane is True
        'accepted_full' if accepted and fast_lane is False
        'rejected' if rejected or no rebuttal → retry loop.
    """
    outcome = state.get("rebuttal_outcome", "")
    if outcome == RebuttalOutcome.ACCEPTED.value or outcome == "ACCEPTED" or outcome == "accepted" or outcome.lower() == "accepted":
        return "accepted_fast" if state.get("fast_lane", True) else "accepted_full"
    return "rejected"


# ============================================================
# Phase 4: Semantic Router & Full SDLC Nodes
# ============================================================


def _supervisor_node(
    state: GraphState, supervisor: "SupervisorAgent", event_store: "EventStore"
) -> dict[str, Any]:
    """Run the dynamic Supervisor agent."""
    
    events_models = event_store.get_events(workflow_id=state["workflow_id"])
    events = [{"source_node": e.source_node if hasattr(e, "source_node") else "unknown", "message": str(e)} for e in events_models]
    
    result = supervisor.run(
        task_description=state["task_description"],
        events=events,
    )
    
    return {
        **state,
        "routing_decision": {"next_agent": result.data.get("next_agent", "complete")},
        "feedback": result.data.get("reasoning", ""),
    }

def _supervisor_decision(state: GraphState) -> str:
    """Route dynamically based on the supervisor's decision."""
    decision = state.get("routing_decision", {})
    return decision.get("next_agent", "complete")


def _deep_research_node(
    state: GraphState, agent: "DeepResearchAgent", event_store: "EventStore"
) -> dict[str, Any]:
    """Run the DeepResearchAgent and emit a DEEP_RESEARCH_COMPLETED event."""
    from state.events import deep_research_completed_event

    report = agent.run(
        query=state["task_description"],
        workflow_id=state.get("workflow_id", ""),
    )

    version = _next_version(state)
    event = deep_research_completed_event(
        workflow_id=state["workflow_id"],
        version=version,
        report_data=report.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "deep_research_report": report.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _explorer_node(
    state: GraphState, agent: "ProjectExplorerAgent", event_store: "EventStore"
) -> dict[str, Any]:
    """Run the ProjectExplorerAgent to explore the local codebase."""
    # We use a custom event or just update state directly for now
    # For Phase 4 we will just update state
    report = agent.run(
        task_description=state["task_description"],
        task_id=state.get("workflow_id", ""),
        workflow_id=state.get("workflow_id", ""),
    )
    
    version = _next_version(state)
    # Using the deep research event as a placeholder since they both produce reports,
    # or ideally we'd define exploration_completed_event. For simplicity, we just update state.
    
    return {
        **state,
        "exploration_report": report.model_dump(),
        "event_version": version,
    }


def _product_analyst_node(
    state: GraphState, agent: "ProductAnalystAgent", event_store: EventStore
) -> dict[str, Any]:
    """Product Analyst: produces PRD from task description."""
    from state.events import product_requirements_event
    from contracts.schemas import ProductRequirementDoc

    prd = agent.run(state["task_description"], state.get("constraints", []))

    version = _next_version(state)
    event = product_requirements_event(
        workflow_id=state["workflow_id"],
        version=version,
        prd_data=prd.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "product_requirements": prd.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _planner_node(
    state: GraphState, agent: "PlannerAgent", event_store: EventStore
) -> dict[str, Any]:
    """Planner: produces TaskDAG from PRD."""
    from state.events import task_dag_event
    from contracts.schemas import TaskDAG, ProductRequirementDoc

    prd_data = state.get("product_requirements", {})
    prd = ProductRequirementDoc.model_validate(prd_data) if prd_data else ProductRequirementDoc(user_stories=[], acceptance_criteria=[], constraints=[], non_functional=[])
    dag = agent.run(prd)

    version = _next_version(state)
    event = task_dag_event(
        workflow_id=state["workflow_id"],
        version=version,
        dag_data=dag.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "task_dag": dag.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }



def _architect_node(
    state: GraphState, agent: "ArchitectAgent", event_store: "EventStore"
) -> dict[str, Any]:
    from state.events import architect_design_event
    from contracts.schemas import TaskDAG, ProductRequirementDoc

    dag_data = state.get("task_dag", {})
    dag = TaskDAG.from_stored(dag_data) if dag_data else TaskDAG(nodes=[], critical_path=[])
    prd_data = state.get("product_requirements", {})
    prd = ProductRequirementDoc.from_stored(prd_data) if prd_data else ProductRequirementDoc(user_stories=[], acceptance_criteria=[], constraints=[], non_functional=[])
    design = agent.run(prd, dag)
    
    version = _next_version(state)
    event = architect_design_event(
        workflow_id=state["workflow_id"],
        version=version,
        design_data=design.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)
    
    return {
        **state,
        "architect_design": design.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }

def _fanout_ux_node(state: GraphState, agent: "UXAgent", event_store: "EventStore") -> dict[str, Any]:
    from state.events import ux_design_event
    from contracts.schemas import ArchitectDesign, ProductRequirementDoc
    
    arch_data = state.get("architect_design", {})
    arch = ArchitectDesign.model_validate(arch_data) if arch_data else ArchitectDesign(adrs=[], component_diagram="", tech_choices=[], interfaces=[])
    prd_data = state.get("product_requirements", {})
    prd = ProductRequirementDoc.model_validate(prd_data) if prd_data else ProductRequirementDoc(user_stories=[], acceptance_criteria=[], constraints=[], non_functional=[])
    
    design = agent.run(arch, prd)
    
    version = _next_version(state)
    event = ux_design_event(
        workflow_id=state["workflow_id"],
        version=version,
        design_data=design.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)
    
    return {
        "ux_design": design.model_dump(),
    }

def _fanout_db_node(state: GraphState, agent: "DBEngineerAgent", event_store: "EventStore") -> dict[str, Any]:
    from state.events import db_schema_event
    from contracts.schemas import ArchitectDesign, TaskDAG
    
    arch_data = state.get("architect_design", {})
    arch = ArchitectDesign.model_validate(arch_data) if arch_data else ArchitectDesign(adrs=[], component_diagram="", tech_choices=[], interfaces=[])
    dag_data = state.get("task_dag", {})
    dag = TaskDAG.model_validate(dag_data) if dag_data else TaskDAG(nodes=[], critical_path=[])
    
    schema = agent.run(arch, dag)
    
    version = _next_version(state)
    event = db_schema_event(
        workflow_id=state["workflow_id"],
        version=version,
        schema_data=schema.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)
    
    return {
        "data_schema": schema.model_dump(),
    }

def _fanout_security_node(state: GraphState, agent: "SecurityAgent", event_store: "EventStore") -> dict[str, Any]:
    from state.events import security_report_event
    from contracts.schemas import ArchitectDesign
    
    code_patch = state.get("code_patch", {}) or state.get("generated_code", {})
    arch_dict = state.get("architect_design", {})
    report = agent.run(code_patch, arch_dict)
    
    version = _next_version(state)
    event = security_report_event(
        workflow_id=state["workflow_id"],
        version=version,
        report_data=report.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)
    
    return {
        "security_report": report.model_dump(),
    }

def _fanout_researcher_node(state: GraphState, agent: "ResearcherAgent", event_store: "EventStore") -> dict[str, Any]:
    from state.events import research_notes_event
    from contracts.schemas import ArchitectDesign, ProductRequirementDoc
    
    arch_data = state.get("architect_design", {})
    arch = ArchitectDesign.model_validate(arch_data) if arch_data else ArchitectDesign(adrs=[], component_diagram="", tech_choices=[], interfaces=[])
    prd_data = state.get("product_requirements", {})
    prd = ProductRequirementDoc.model_validate(prd_data) if prd_data else ProductRequirementDoc(user_stories=[], acceptance_criteria=[], constraints=[], non_functional=[])
    
    notes = agent.run(prd, arch)
    
    version = _next_version(state)
    event = research_notes_event(
        workflow_id=state["workflow_id"],
        version=version,
        notes_data=notes.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)
    
    return {
        "research_notes": notes.model_dump(),
    }

def _fanout_coder_node(state: GraphState, agent: "CoderAgent", event_store: "EventStore") -> dict[str, Any]:
    from state.events import code_submitted_event
    from contracts.schemas import TaskAssignment
    
    iteration = state.get("current_iteration", 1)
    
    if "task_assignment" in state and state["task_assignment"]:
        task = TaskAssignment(**state["task_assignment"])
    else:
        task = TaskAssignment(
            workflow_id=state.get("workflow_id", ""),
            description=state.get("task_description", ""),
            language=state.get("language", "python"),
            constraints=state.get("constraints", []),
            iteration=iteration,
            prior_feedback=state.get("feedback", ""),
        )
        
    patch = agent.run(task)
    
    version = _next_version(state)
    event = code_submitted_event(
        workflow_id=state["workflow_id"],
        version=version,
        patch_data=patch.model_dump(mode="json"),
        iteration=iteration,
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)
    
    return {
        "code_patch": patch.model_dump(),
    }

def _integrator_node(
    state: GraphState, agent: "IntegratorAgent", event_store: "EventStore"
) -> dict[str, Any]:
    from state.events import integration_event
    
    out = agent.run(state)
    
    version = _next_version(state)
    event = integration_event(
        workflow_id=state["workflow_id"],
        version=version,
        integrator_data=out.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)
    
    return {
        **state,
        "integrator_output": out.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }

def _docs_arch_node(state: GraphState, agent: "DocsAgent", event_store: "EventStore") -> dict[str, Any]:
    from state.events import documentation_event
    
    out = agent.run(milestone="post_architecture", context=state)
    
    version = _next_version(state)
    event = documentation_event(
        workflow_id=state["workflow_id"],
        version=version,
        docs_data=out.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)
    
    return {
        **state,
        "docs_adr": out.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }

def _docs_int_node(state: GraphState, agent: "DocsAgent", event_store: "EventStore") -> dict[str, Any]:
    from state.events import documentation_event
    
    out = agent.run(milestone="post_integration", context=state)
    
    version = _next_version(state)
    event = documentation_event(
        workflow_id=state["workflow_id"],
        version=version,
        docs_data=out.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)
    
    return {
        **state,
        "docs_final": out.model_dump(),
        "event_version": version,
        "last_event_id": event.event_id,
    }

def _increment_node(state: GraphState) -> dict[str, Any]:
    return {"current_iteration": state.get("current_iteration", 1) + 1}


# ============================================================
# HITL Gate Nodes
# ============================================================


def _hitl_pre_code_node(
    state: GraphState, hitl_manager: "HITLManager"
) -> dict[str, Any]:
    """HITL gate before code generation (Full SDLC path only)."""
    from orchestrator.hitl import ApprovalStatus

    plan_summary = str(state.get("task_dag", {}))[:500]
    status = hitl_manager.pre_code_approval(
        workflow_id=state.get("workflow_id", ""),
        iteration=state.get("current_iteration", 1),
        plan=plan_summary,
    )

    if status == ApprovalStatus.REJECTED:
        return {**state, "error": "HITL: Pre-code approval rejected by human reviewer"}

    return state


def _hitl_post_test_node(
    state: GraphState, hitl_manager: "HITLManager"
) -> dict[str, Any]:
    """HITL gate after testing — human reviews test results."""
    from orchestrator.hitl import ApprovalStatus

    test_summary = str(state.get("verification_report", {}))[:500]
    status = hitl_manager.post_test_approval(
        workflow_id=state.get("workflow_id", ""),
        iteration=state.get("current_iteration", 1),
        test_results=test_summary,
    )

    if status == ApprovalStatus.REJECTED:
        return {**state, "error": "HITL: Post-test approval rejected by human reviewer"}

    return state


def _hitl_security_node(
    state: GraphState, hitl_manager: "HITLManager"
) -> dict[str, Any]:
    """HITL gate for security review."""
    from orchestrator.hitl import ApprovalStatus

    security_findings = str(state.get("security_report", {}))[:500]
    status = hitl_manager.security_review(
        workflow_id=state.get("workflow_id", ""),
        iteration=state.get("current_iteration", 1),
        findings=security_findings,
    )

    if status == ApprovalStatus.REJECTED:
        return {**state, "error": "HITL: Security review rejected by human reviewer"}

    return state


# ============================================================
# Graph Compilation
# ============================================================

def build_feedback_loop(
    event_store: "EventStore",
    llm_client: "LLMClient",
    hitl_manager: "HITLManager | None" = None,
) -> StateGraph:
    """Compile the LangGraph state machine with all agents (Phase 4).

    Args:
        event_store: Event store for persistence.
        llm_client: LLM client for agent calls.
        hitl_manager: Optional HITL manager for human approval gates.
    """
    from functools import partial
    
    from agents.coder import CoderAgent
    from agents.tester import TesterAgent
    from agents.critic import CriticAgent
    from agents.supervisor import SupervisorAgent
    from agents.product_analyst import ProductAnalystAgent
    from agents.planner import PlannerAgent
    from agents.architect import ArchitectAgent
    from agents.ux import UXAgent
    from agents.db_engineer import DBEngineerAgent
    from agents.security import SecurityAgent
    from agents.researcher import ResearcherAgent
    from agents.integrator import IntegratorAgent
    from agents.docs import DocsAgent
    from agents.deep_research import DeepResearchAgent
    from agents.explorer import ProjectExplorerAgent

    coder = CoderAgent(agent_id="c1", llm_client=llm_client)
    tester = TesterAgent(agent_id="t1")
    critic = CriticAgent(agent_id="cr1", llm_client=llm_client)
    
    supervisor = SupervisorAgent(agent_id="sup1", llm_client=llm_client)
    pa = ProductAnalystAgent(agent_id="pa1", llm_client=llm_client)
    planner = PlannerAgent(agent_id="pl1", llm_client=llm_client)
    arch = ArchitectAgent(agent_id="ar1", llm_client=llm_client)
    ux = UXAgent(agent_id="ux1", llm_client=llm_client)
    db = DBEngineerAgent(agent_id="db1", llm_client=llm_client)
    sec = SecurityAgent(agent_id="sec1", llm_client=llm_client)
    res = ResearcherAgent(agent_id="res1", llm_client=llm_client)
    integ = IntegratorAgent(agent_id="in1", llm_client=llm_client)
    docs = DocsAgent(agent_id="doc1", llm_client=llm_client)
    from tools.mcp_registry import MCPRegistry
    from tools.policy_engine import PolicyEngine
    from tools.tool_executor import ToolExecutor
    
    mcp_reg = MCPRegistry()
    policy_engine = PolicyEngine()
    tool_executor = ToolExecutor(registry=mcp_reg, policy_engine=policy_engine)

    deep_res = DeepResearchAgent(
        llm_client=llm_client, 
        agent_id="dr1",
        mcp_registry=mcp_reg,
        tool_executor=tool_executor
    )
    
    explorer = ProjectExplorerAgent(
        llm_client=llm_client,
        agent_id="exp1"
    )

    # Create default HITL manager if none provided (auto-approve = no-op)
    if hitl_manager is None:
        from orchestrator.hitl import create_hitl_manager
        hitl_manager = create_hitl_manager(backend="auto", enabled_gates=[])

    workflow = StateGraph(GraphState)

    # Core loop nodes
    workflow.add_node("assign_task", partial(_assign_task_node, event_store=event_store))
    workflow.add_node("coder", partial(_coder_node, coder=coder, event_store=event_store))
    workflow.add_node("tester", partial(_tester_node, tester=tester, event_store=event_store))
    workflow.add_node("critic", partial(_critic_node, critic=critic, event_store=event_store))
    workflow.add_node("coder_rebut", partial(_coder_rebut_node, coder=coder, event_store=event_store))
    workflow.add_node("judge_rebuttal", partial(_judge_rebuttal_node, critic=critic, event_store=event_store))
    workflow.add_node("increment", _increment_node)
    workflow.add_node("complete", partial(_complete_node, event_store=event_store))
    workflow.add_node("fail", partial(_fail_node, event_store=event_store))

    # Routing + Full SDLC nodes
    workflow.add_node("supervisor", partial(_supervisor_node, supervisor=supervisor, event_store=event_store))
    workflow.add_node("product_analyst", partial(_product_analyst_node, agent=pa, event_store=event_store))
    workflow.add_node("planner", partial(_planner_node, agent=planner, event_store=event_store))
    workflow.add_node("architect", partial(_architect_node, agent=arch, event_store=event_store))
    
    workflow.add_node("ux", partial(_fanout_ux_node, agent=ux, event_store=event_store))
    workflow.add_node("db", partial(_fanout_db_node, agent=db, event_store=event_store))
    workflow.add_node("security", partial(_fanout_security_node, agent=sec, event_store=event_store))
    workflow.add_node("researcher", partial(_fanout_researcher_node, agent=res, event_store=event_store))
    workflow.add_node("coder_sdlc", partial(_fanout_coder_node, agent=coder, event_store=event_store))
    
    workflow.add_node("integrator", partial(_integrator_node, agent=integ, event_store=event_store))
    
    workflow.add_node("docs_arch", partial(_docs_arch_node, agent=docs, event_store=event_store))
    workflow.add_node("docs_int", partial(_docs_int_node, agent=docs, event_store=event_store))

    # HITL gate nodes
    workflow.add_node("hitl_pre_code", partial(_hitl_pre_code_node, hitl_manager=hitl_manager))
    workflow.add_node("hitl_post_test", partial(_hitl_post_test_node, hitl_manager=hitl_manager))
    workflow.add_node("hitl_security", partial(_hitl_security_node, hitl_manager=hitl_manager))

    # === Graph Edges ===

    workflow.set_entry_point("assign_task")
    
    workflow.add_edge("assign_task", "supervisor")
    workflow.add_node("deep_research_entry", partial(_deep_research_node, agent=deep_res, event_store=event_store))
    # Explorer node
    workflow.add_node("explorer_entry", partial(_explorer_node, agent=explorer, event_store=event_store))
    # Placeholder terminal node for Media Production
    workflow.add_node("media_production_entry", lambda s: {**s, "domain": "media_production"})

    # New domains mapping directly to complete node with some basic text output
    def _conversational_node(s):
        from gateway.llm_client import LLMClient
        client = LLMClient()
        response = client.complete_text(
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant in an autonomous software development agency. Respond conversationally to the user."},
                {"role": "user", "content": s.get("task_description", "")}
            ],
            model="fast"
        )
        return {**s, "domain": "conversational", "code_patch": {"explanation": response.strip()}}

    def _os_command_node(s):
        import asyncio
        from agents.operator import OperatorAgent
        from gateway.model_registry import get_registry
        from resilience import CircuitBreakerRegistry
        from gateway.smart_gateway import SmartGateway
        from contracts.system_commands import SystemCommandIntent, SystemAction
        
        registry = get_registry()
        circuit_breakers = CircuitBreakerRegistry()
        gateway = SmartGateway(registry, circuit_breakers)
        op = OperatorAgent(registry=registry, gateway=gateway, circuit_breakers=circuit_breakers)
        
        intent = SystemCommandIntent(
            action=SystemAction.OS_COMMAND,
            raw_text=s.get("task_description", "")
        )
        res = asyncio.run(op._execute_os_command(intent))
        return {**s, "domain": "os_command", "code_patch": {"explanation": res.message}}

    def _system_command_node(s):
        import asyncio
        from agents.operator import OperatorAgent
        from gateway.model_registry import get_registry
        from resilience import CircuitBreakerRegistry
        from gateway.smart_gateway import SmartGateway
        from contracts.system_commands import SystemCommandParser
        
        registry = get_registry()
        circuit_breakers = CircuitBreakerRegistry()
        gateway = SmartGateway(registry, circuit_breakers)
        op = OperatorAgent(registry=registry, gateway=gateway, circuit_breakers=circuit_breakers)
        
        parser = SystemCommandParser()
        intent = parser.parse(s.get("task_description", ""))
        
        if intent.action == "unknown":
            msg = "System Commands via SemanticRouter are logged and handled. Please be more specific about the system configuration command."
        else:
            res = asyncio.run(op.execute_intent(intent))
            msg = res.message
            
        return {**s, "domain": "system_command", "code_patch": {"explanation": msg}}

    workflow.add_node("conversational_entry", _conversational_node)
    workflow.add_node("os_command_entry", _os_command_node)
    workflow.add_node("system_command_entry", _system_command_node)

    workflow.add_conditional_edges(
        "supervisor",
        _supervisor_decision,
        {
            "planner": "planner",
            "architect": "architect",
            "ux": "ux",
            "db": "db",
            "security": "security",
            "coder": "coder",
            "tester": "tester",
            "critic": "critic",
            "integrator": "integrator",
            "docs": "docs_int",
            "complete": "complete",
            "fail": "fail"
        },
    )

    # Star Topology: all workers return to the supervisor!
    workflow.add_edge("planner", "supervisor")
    workflow.add_edge("architect", "supervisor")
    workflow.add_edge("ux", "supervisor")
    workflow.add_edge("db", "supervisor")
    workflow.add_edge("security", "supervisor")
    workflow.add_edge("coder", "supervisor")
    workflow.add_edge("tester", "supervisor")
    workflow.add_edge("critic", "supervisor")
    workflow.add_edge("integrator", "supervisor")
    workflow.add_edge("docs_int", "supervisor")
    
    # Legacy domains returning to supervisor or complete
    workflow.add_edge("deep_research_entry", "complete")
    workflow.add_edge("media_production_entry", "complete")
    workflow.add_edge("explorer_entry", "complete")
    workflow.add_edge("conversational_entry", "complete")
    workflow.add_edge("os_command_entry", "complete")
    workflow.add_edge("system_command_entry", "complete")

    # Complete and Fail end the workflow
    workflow.add_edge("complete", END)
    workflow.add_edge("fail", END)

    return workflow

