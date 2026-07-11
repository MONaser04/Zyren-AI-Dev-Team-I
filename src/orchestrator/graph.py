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

from src.agents.coder import CoderAgent
from src.agents.critic import CriticAgent
from src.agents.tester import TesterAgent
from src.contracts.schemas import (
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
    decision = critic.run(patch, report)

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


def _route_node(
    state: GraphState, router: "SemanticRouter", event_store: EventStore
) -> dict[str, Any]:
    """Run semantic router and emit a ROUTING_DECIDED event."""
    from state.events import routing_decided_event  # imported here to avoid circular
    from contracts.schemas import RoutingDecision

    decision = router.classify(
        task_description=state["task_description"],
        workflow_id=state["workflow_id"],
    )

    version = _next_version(state)
    event = routing_decided_event(
        workflow_id=state["workflow_id"],
        version=version,
        decision_data=decision.model_dump(mode="json"),
        causation_id=state.get("last_event_id"),
        correlation_id=state.get("correlation_id"),
    )
    event_store.append(event)

    return {
        **state,
        "routing_decision": decision.model_dump(),
        "complexity": decision.complexity.value,
        "fast_lane": decision.fast_lane,
        "event_version": version,
        "last_event_id": event.event_id,
    }


def _route_decision(state: GraphState) -> str:
    """Route to Fast Lane or Full SDLC based on semantic router decision."""
    return "fast" if state.get("fast_lane", False) else "full"


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

    prd = ProductRequirementDoc.model_validate(state["product_requirements"])
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

    dag = TaskDAG.from_stored(state.get("task_dag", {})) if "task_dag" in state else None
    prd = ProductRequirementDoc.from_stored(state.get("product_requirements", {})) if "product_requirements" in state else None
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
    
    arch = ArchitectDesign.model_validate(state.get("architect_design", {}))
    prd = ProductRequirementDoc.model_validate(state.get("product_requirements", {}))
    
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
    from contracts.schemas import ArchitectDesign, ProductRequirementDoc
    
    arch = ArchitectDesign.model_validate(state.get("architect_design", {}))
    prd = ProductRequirementDoc.model_validate(state.get("product_requirements", {}))
    
    schema = agent.run(arch, prd)
    
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
    
    arch = ArchitectDesign.model_validate(state.get("architect_design", {}))
    report = agent.run(arch)
    
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
    
    arch = ArchitectDesign.model_validate(state.get("architect_design", {}))
    prd = ProductRequirementDoc.model_validate(state.get("product_requirements", {}))
    
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
    
    iteration = state.get("current_iteration", 1)
    # The SDLC path uses the full state dict for Coder
    patch = agent.run(state)
    
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
    
    out = agent.run(state, phase="architecture")
    
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
    
    out = agent.run(state, phase="integration")
    
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
# Graph Compilation
# ============================================================

def build_feedback_loop(
    event_store: "EventStore",
    llm_client: "LLMClient",
) -> StateGraph:
    """Compile the LangGraph state machine with all agents (Phase 4)."""
    from functools import partial
    
    from src.agents.coder import CoderAgent
    from src.agents.tester import TesterAgent
    from src.agents.critic import CriticAgent
    from src.orchestrator.semantic_router import SemanticRouter
    from src.agents.product_analyst import ProductAnalystAgent
    from src.agents.planner import PlannerAgent
    from src.agents.architect import ArchitectAgent
    from src.agents.ux import UXAgent
    from src.agents.db_engineer import DBEngineerAgent
    from src.agents.security import SecurityAgent
    from src.agents.researcher import ResearcherAgent
    from src.agents.integrator import IntegratorAgent
    from src.agents.docs import DocsAgent

    coder = CoderAgent(agent_id="c1", llm_client=llm_client)
    tester = TesterAgent(agent_id="t1")
    critic = CriticAgent(agent_id="cr1", llm_client=llm_client)
    
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

    workflow = StateGraph(GraphState)

    workflow.add_node("assign_task", partial(_assign_task_node, event_store=event_store))
    workflow.add_node("coder", partial(_coder_node, coder=coder, event_store=event_store))
    workflow.add_node("tester", partial(_tester_node, tester=tester, event_store=event_store))
    workflow.add_node("critic", partial(_critic_node, critic=critic, event_store=event_store))
    workflow.add_node("coder_rebut", partial(_coder_rebut_node, coder=coder, event_store=event_store))
    workflow.add_node("judge_rebuttal", partial(_judge_rebuttal_node, critic=critic, event_store=event_store))
    workflow.add_node("increment", _increment_node)
    workflow.add_node("complete", partial(_complete_node, event_store=event_store))
    workflow.add_node("fail", partial(_fail_node, event_store=event_store))

    workflow.add_node("route", partial(_route_node, router=router, event_store=event_store))
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

    workflow.set_entry_point("assign_task")
    
    workflow.add_edge("assign_task", "route")
    workflow.add_conditional_edges("route", _route_decision, {"fast": "coder", "full": "product_analyst"})

    workflow.add_edge("coder", "tester")
    workflow.add_edge("tester", "critic")
    workflow.add_conditional_edges(
        "critic",
        _should_continue,
        {
            "complete": "complete",
            "docs_int": "docs_int",
            "should_rebut": "coder_rebut",
            "fail": "fail"
        }
    )
    workflow.add_conditional_edges(
        "coder_rebut",
        _should_rebut_router,
        {
            "try_rebut": "judge_rebuttal",
            "no_rebut": "increment"
        }
    )
    workflow.add_conditional_edges(
        "judge_rebuttal",
        _rebuttal_outcome_router,
        {
            "accepted_fast": "complete",
            "accepted_full": "docs_int",
            "rejected": "increment"
        }
    )
    workflow.add_edge("increment", "coder")
    
    workflow.add_edge("complete", END)
    workflow.add_edge("fail", END)

    workflow.add_edge("product_analyst", "planner")
    workflow.add_edge("planner", "architect")
    
    workflow.add_edge("architect", "ux")
    workflow.add_edge("architect", "db")
    workflow.add_edge("architect", "security")
    workflow.add_edge("architect", "researcher")
    workflow.add_edge("architect", "coder_sdlc")
    
    workflow.add_edge(["ux", "db", "security", "researcher", "coder_sdlc"], "integrator")
    
    workflow.add_edge("integrator", "docs_arch")
    workflow.add_edge("docs_arch", "tester")
    
    workflow.add_edge("docs_int", "complete")

    return workflow
