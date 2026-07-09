"""
Tests — Orchestrator (LangGraph Feedback Loop with Rebuttal)
==============================================================

Validates:
- The LangGraph compiles successfully
- The graph structure has the expected nodes (Phase 2: +rebuttal nodes)
- The decision router works correctly
- The rebuttal outcome router works correctly
- Events are emitted at every transition (using mocked agents)
- Rebuttal flow: accepted → PASS, rejected → retry
"""

from __future__ import annotations

from unittest.mock import patch

from contracts.schemas import (
    CodePatch,
    FileContent,
    RebuttalJudgment,
    RebuttalOutcome,
    RebuttalRequest,
    ReviewDecision,
    ReviewIssue,
    RoutingDecision,
    Severity,
    TaskComplexity,
    Verdict,
    ArchitectDesign,
    UXDesign,
    DataSchema,
    SecurityReport,
    ResearchNotes,
    IntegratorOutput,
    DocsOutput,
    ProductRequirementDoc,
    TaskDAG,
)
from gateway.llm_client import LLMClient
from orchestrator.graph import (
    GraphState,
    _rebuttal_outcome_router,
    _should_continue,
    build_feedback_loop,
)
from state.store import SQLiteEventStore


class TestDecisionRouter:
    """Test the _should_continue routing logic."""

    def test_pass_routes_to_complete(self) -> None:
        state: GraphState = {
            "verdict": "PASS",
            "current_iteration": 1,
            "max_iterations": 3,
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _should_continue(state) == "complete"

    def test_block_under_cap_routes_to_should_rebut(self) -> None:
        state: GraphState = {
            "verdict": "BLOCK",
            "current_iteration": 1,
            "max_iterations": 3,
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _should_continue(state) == "should_rebut"

    def test_block_at_cap_routes_to_fail(self) -> None:
        state: GraphState = {
            "verdict": "BLOCK",
            "current_iteration": 3,
            "max_iterations": 3,
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _should_continue(state) == "fail"

    def test_no_verdict_under_cap_routes_to_should_rebut(self) -> None:
        state: GraphState = {
            "verdict": "",
            "current_iteration": 1,
            "max_iterations": 3,
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _should_continue(state) == "should_rebut"


class TestRebuttalOutcomeRouter:
    """Test the _rebuttal_outcome_router logic."""

    def test_accepted_routes_to_accepted(self) -> None:
        state: GraphState = {
            "rebuttal_outcome": "accepted",
            "workflow_id": "wf-001",
            "task_description": "test",
            "fast_lane": True,
        }
        assert _rebuttal_outcome_router(state) == "accepted_fast"
        
        state["fast_lane"] = False
        assert _rebuttal_outcome_router(state) == "accepted_full"

    def test_rejected_routes_to_rejected(self) -> None:
        state: GraphState = {
            "rebuttal_outcome": "rejected",
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _rebuttal_outcome_router(state) == "rejected"

    def test_no_rebuttal_routes_to_rejected(self) -> None:
        state: GraphState = {
            "rebuttal_outcome": "no_rebuttal",
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _rebuttal_outcome_router(state) == "rejected"

    def test_empty_routes_to_rejected(self) -> None:
        state: GraphState = {
            "rebuttal_outcome": "",
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _rebuttal_outcome_router(state) == "rejected"


class TestGraphCompilation:
    """Test that the LangGraph compiles and has correct structure."""

    def test_graph_compiles(self) -> None:
        store = SQLiteEventStore(db_path=":memory:")
        client = LLMClient()
        graph = build_feedback_loop(event_store=store, llm_client=client)

        # Should compile without errors
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self) -> None:
        store = SQLiteEventStore(db_path=":memory:")
        client = LLMClient()
        graph = build_feedback_loop(event_store=store, llm_client=client)

        # Check all expected nodes (Phase 2: includes rebuttal nodes)
        node_names = set(graph.nodes.keys())
        expected = {
            "assign_task", "coder", "tester", "critic",
            "coder_rebut", "judge_rebuttal",
            "complete", "fail", "increment",
        }
        assert expected.issubset(node_names), (
            f"Missing nodes: {expected - node_names}"
        )


class TestGraphExecution:
    """Test end-to-end graph execution with mocked LLM calls."""

    def test_full_pass_workflow(self) -> None:
        """Simulate a workflow that passes on the first iteration."""
        store = SQLiteEventStore(db_path=":memory:")
        client = LLMClient()

        mock_patch = CodePatch(
            task_id="t-001",
            workflow_id="test-wf",
            iteration=1,
            files=[FileContent(
                path="hello.py",
                content="def hello():\n    return 'world'\n",
            )],
            explanation="Simple function",
        )

        mock_decision = ReviewDecision(
            task_id="t-001",
            workflow_id="test-wf",
            iteration=1,
            verdict=Verdict.PASS,
            justification="All checks passed.",
        )
        
        mock_routing_decision = RoutingDecision(
            complexity=TaskComplexity.SIMPLE,
            confidence=1.0,
            safe_fallback=False,
            reasoning="test",
            fast_lane=True,
        )

        graph = build_feedback_loop(
            event_store=store, llm_client=client,
        )
        compiled = graph.compile()

        with (
            patch(
                "orchestrator.graph.CoderAgent.run",
                return_value=mock_patch,
            ),
            patch(
                "orchestrator.graph.CriticAgent.run",
                return_value=mock_decision,
            ),
            patch(
                "orchestrator.semantic_router.SemanticRouter.classify",
                return_value=mock_routing_decision,
            ),
        ):
            result = compiled.invoke({
                "workflow_id": "test-wf",
                "task_description": "Write a hello function",
                "language": "python",
                "constraints": [],
                "max_iterations": 3,
                "current_iteration": 0,
                "event_version": 0,
            })

        assert result["verdict"] == "PASS"

        events = store.get_events("test-wf")
        assert len(events) >= 4

    def test_fail_after_iteration_cap(self) -> None:
        """Simulate a workflow that fails after hitting iteration cap."""
        store = SQLiteEventStore(db_path=":memory:")
        client = LLMClient()

        mock_patch = CodePatch(
            task_id="t-001",
            workflow_id="test-wf-fail",
            iteration=1,
            files=[FileContent(path="bad.py", content="x = 1\n")],
        )

        mock_decision = ReviewDecision(
            task_id="t-001",
            workflow_id="test-wf-fail",
            iteration=1,
            verdict=Verdict.BLOCK,
            justification="Code doesn't address the task.",
            feedback_for_coder="You need to implement the function.",
            issues=[ReviewIssue(
                description="Missing implementation",
                severity=Severity.HIGH,
                source="manual",
            )],
        )

        # Mock rebuttal: coder doesn't rebut (returns None)
        mock_rebuttal_judgment = RebuttalJudgment(
            task_id="t-001",
            workflow_id="test-wf-fail",
            iteration=1,
            outcome=RebuttalOutcome.REJECTED,
            reasoning="The issues are legitimate.",
        )

        mock_routing_decision = RoutingDecision(
            complexity=TaskComplexity.SIMPLE,
            confidence=1.0,
            safe_fallback=False,
            reasoning="test",
            fast_lane=True,
        )

        graph = build_feedback_loop(
            event_store=store, llm_client=client,
        )
        compiled = graph.compile()

        with (
            patch(
                "orchestrator.graph.CoderAgent.run",
                return_value=mock_patch,
            ),
            patch(
                "orchestrator.graph.CriticAgent.run",
                return_value=mock_decision,
            ),
            patch(
                "orchestrator.graph.CoderAgent.rebut",
                return_value=None,
            ),
            patch(
                "orchestrator.graph.CriticAgent.judge_rebuttal",
                return_value=mock_rebuttal_judgment,
            ),
            patch(
                "orchestrator.semantic_router.SemanticRouter.classify",
                return_value=mock_routing_decision,
            ),
        ):
            result = compiled.invoke({
                "workflow_id": "test-wf-fail",
                "task_description": "Implement a calculator",
                "language": "python",
                "constraints": [],
                "max_iterations": 2,
                "current_iteration": 0,
                "event_version": 0,
            })

        assert result.get("error") is not None
        assert (
            "cap" in result["error"].lower()
            or "iteration" in result["error"].lower()
        )

        events = store.get_events("test-wf-fail")
        assert len(events) >= 3

    def test_rebuttal_accepted_passes(self) -> None:
        """Simulate: BLOCK → Coder rebuts → Critic accepts → PASS."""
        store = SQLiteEventStore(db_path=":memory:")
        client = LLMClient()

        mock_patch = CodePatch(
            task_id="t-001",
            workflow_id="test-wf-rebut",
            iteration=1,
            files=[FileContent(
                path="calc.py",
                content="def add(a, b):\n    return a + b\n",
            )],
        )

        mock_decision = ReviewDecision(
            task_id="t-001",
            workflow_id="test-wf-rebut",
            iteration=1,
            verdict=Verdict.BLOCK,
            justification="Test expects wrong behavior.",
            feedback_for_coder="Fix the test.",
            issues=[ReviewIssue(
                description="Test asserts wrong value",
                severity=Severity.MEDIUM,
                source="pytest",
            )],
        )

        mock_rebuttal = RebuttalRequest(
            task_id="t-001",
            workflow_id="test-wf-rebut",
            iteration=1,
            justification=(
                "The failing test asserts wrong behavior. "
                "Per the spec, add(2, 3) should return 5."
            ),
            disputed_issues=["Test asserts wrong value"],
        )

        mock_judgment = RebuttalJudgment(
            task_id="t-001",
            workflow_id="test-wf-rebut",
            iteration=1,
            outcome=RebuttalOutcome.ACCEPTED,
            reasoning="Coder correctly identified false positive.",
        )

        mock_routing_decision = RoutingDecision(
            complexity=TaskComplexity.SIMPLE,
            confidence=1.0,
            safe_fallback=False,
            reasoning="test",
            fast_lane=True,
        )

        graph = build_feedback_loop(
            event_store=store, llm_client=client,
        )
        compiled = graph.compile()

        with (
            patch(
                "orchestrator.graph.CoderAgent.run",
                return_value=mock_patch,
            ),
            patch(
                "orchestrator.graph.CriticAgent.run",
                return_value=mock_decision,
            ),
            patch(
                "orchestrator.graph.CoderAgent.rebut",
                return_value=mock_rebuttal,
            ),
            patch(
                "orchestrator.graph.CriticAgent.judge_rebuttal",
                return_value=mock_judgment,
            ),
            patch(
                "orchestrator.semantic_router.SemanticRouter.classify",
                return_value=mock_routing_decision,
            ),
        ):
            result = compiled.invoke({
                "workflow_id": "test-wf-rebut",
                "task_description": "Implement add function",
                "language": "python",
                "constraints": [],
                "max_iterations": 3,
                "current_iteration": 0,
                "event_version": 0,
            })

        # Rebuttal accepted → should complete as PASS
        print(f"DEBUG: final result = {result}")
        assert result["verdict"] == "PASS"

        # Verify rebuttal events were emitted
        events = store.get_events("test-wf-rebut")
        event_types = [e.event_type.value for e in events]
        assert "rebuttal_submitted" in event_types
        assert "rebuttal_judged" in event_types
        assert "workflow_completed" in event_types

    def test_full_sdlc_workflow(self) -> None:
        """Simulate a workflow that goes through the full SDLC."""
        from contracts.schemas import (
            ArchitectDesign, TaskDAG, UXDesign, DataSchema,
            SecurityReport, ResearchNotes, IntegratorOutput, DocsOutput
        )
        store = SQLiteEventStore(db_path=":memory:")
        client = LLMClient()

        mock_patch = CodePatch(
            task_id="t-001",
            workflow_id="test-wf-sdlc",
            iteration=1,
            files=[FileContent(path="main.py", content="x = 1\n")],
        )
        mock_decision = ReviewDecision(
            task_id="t-001",
            workflow_id="test-wf-sdlc",
            iteration=1,
            verdict=Verdict.PASS,
            justification="Passed SDLC",
        )
        mock_routing_decision = RoutingDecision(
            complexity=TaskComplexity.COMPLEX,
            confidence=1.0,
            safe_fallback=False,
            reasoning="test",
            fast_lane=False,
        )

        graph = build_feedback_loop(event_store=store, llm_client=client)
        compiled = graph.compile()

        with (
            patch("agents.product_analyst.ProductAnalystAgent.run", return_value=ProductRequirementDoc(user_stories=[], acceptance_criteria=[], constraints=[], non_functional=[])),
            patch("agents.planner.PlannerAgent.run", return_value=TaskDAG(nodes=[], critical_path=[])),
            patch("agents.architect.ArchitectAgent.run", return_value=ArchitectDesign(adrs=[], component_diagram="graph TD", tech_choices=[], interfaces=[])),
            patch("agents.ux.UXAgent.run", return_value=UXDesign(wireframes=[], accessibility_notes="none", design_system_refs=[])),
            patch("agents.db_engineer.DBEngineerAgent.run", return_value=DataSchema(tables=[], migrations=[], indexes=[])),
            patch("agents.security.SecurityAgent.run", return_value=SecurityReport(vulnerabilities=[], sast_summary="clean", recommendations=[], risk_level="low")),
            patch("agents.researcher.ResearcherAgent.run", return_value=ResearchNotes(topic="none", findings=[], sources=[], recommendations=[])),
            patch("orchestrator.graph.CoderAgent.run", return_value=mock_patch),
            patch("agents.integrator.IntegratorAgent.run", return_value=IntegratorOutput(merged_files=[], conflicts_resolved=[], rollback_plan="revert")),
            patch("agents.docs.DocsAgent.run", return_value=DocsOutput(milestone="post_architecture", adrs=[], readme="test", openapi_spec="test")),
            patch("orchestrator.graph.CriticAgent.run", return_value=mock_decision),
            patch("orchestrator.semantic_router.SemanticRouter.classify", return_value=mock_routing_decision),
        ):
            result = compiled.invoke({
                "workflow_id": "test-wf-sdlc",
                "task_description": "Complex system",
                "language": "python",
                "constraints": [],
                "max_iterations": 3,
                "current_iteration": 0,
                "event_version": 0,
                "product_requirements": {"reqs": []},
            })

        assert result["verdict"] == "PASS"
        assert "architect_design" in result
        assert "ux_design" in result
        assert "data_schema" in result
        assert "security_report" in result
        assert "research_notes" in result
        assert "integrator_output" in result
        assert "docs_adr" in result
        assert "docs_final" in result
