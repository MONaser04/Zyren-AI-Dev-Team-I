"""
Tests — Orchestrator (LangGraph Feedback Loop)
================================================

Validates:
- The LangGraph compiles successfully
- The graph structure has the expected nodes and edges
- The decision router works correctly
- Events are emitted at every transition (using mocked agents)
"""

from __future__ import annotations

from unittest.mock import patch

from contracts.schemas import (
    CodePatch,
    FileContent,
    ReviewDecision,
    Verdict,
)
from gateway.llm_client import LLMClient
from orchestrator.graph import GraphState, _should_continue, build_feedback_loop
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

    def test_block_under_cap_routes_to_retry(self) -> None:
        state: GraphState = {
            "verdict": "BLOCK",
            "current_iteration": 1,
            "max_iterations": 3,
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _should_continue(state) == "retry"

    def test_block_at_cap_routes_to_fail(self) -> None:
        state: GraphState = {
            "verdict": "BLOCK",
            "current_iteration": 3,
            "max_iterations": 3,
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _should_continue(state) == "fail"

    def test_no_verdict_under_cap_routes_to_retry(self) -> None:
        state: GraphState = {
            "verdict": "",
            "current_iteration": 1,
            "max_iterations": 3,
            "workflow_id": "wf-001",
            "task_description": "test",
        }
        assert _should_continue(state) == "retry"


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

        # Check that all expected nodes are present
        node_names = set(graph.nodes.keys())
        expected = {"assign_task", "coder", "tester", "critic", "complete", "fail", "increment"}
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


class TestGraphExecution:
    """Test end-to-end graph execution with mocked LLM calls."""

    def test_full_pass_workflow(self) -> None:
        """Simulate a workflow that passes on the first iteration."""
        store = SQLiteEventStore(db_path=":memory:")
        client = LLMClient()

        # Mock the coder to return a simple patch
        mock_patch = CodePatch(
            task_id="t-001",
            workflow_id="test-wf",
            iteration=1,
            files=[FileContent(path="hello.py", content="def hello():\n    return 'world'\n")],
            explanation="Simple function",
        )

        # Mock the critic to PASS
        mock_decision = ReviewDecision(
            task_id="t-001",
            workflow_id="test-wf",
            iteration=1,
            verdict=Verdict.PASS,
            justification="All checks passed.",
        )

        graph = build_feedback_loop(event_store=store, llm_client=client)
        compiled = graph.compile()

        # Patch the coder and critic agent run methods
        with (
            patch("orchestrator.graph.CoderAgent.run", return_value=mock_patch),
            patch("orchestrator.graph.CriticAgent.run", return_value=mock_decision),
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

        # Verify outcome
        assert result["verdict"] == "PASS"

        # Verify events were emitted
        events = store.get_events("test-wf")
        assert len(events) >= 4  # task_created, code_submitted, verification, review, completed

    def test_fail_after_iteration_cap(self) -> None:
        """Simulate a workflow that fails after hitting the iteration cap."""
        store = SQLiteEventStore(db_path=":memory:")
        client = LLMClient()

        # Mock the coder to return code
        mock_patch = CodePatch(
            task_id="t-001",
            workflow_id="test-wf-fail",
            iteration=1,
            files=[FileContent(path="bad.py", content="x = 1\n")],
        )

        # Mock the critic to always BLOCK
        mock_decision = ReviewDecision(
            task_id="t-001",
            workflow_id="test-wf-fail",
            iteration=1,
            verdict=Verdict.BLOCK,
            justification="Code doesn't address the task.",
            feedback_for_coder="You need to actually implement the function.",
        )

        graph = build_feedback_loop(event_store=store, llm_client=client)
        compiled = graph.compile()

        with (
            patch("orchestrator.graph.CoderAgent.run", return_value=mock_patch),
            patch("orchestrator.graph.CriticAgent.run", return_value=mock_decision),
        ):
            result = compiled.invoke({
                "workflow_id": "test-wf-fail",
                "task_description": "Implement a calculator",
                "language": "python",
                "constraints": [],
                "max_iterations": 2,  # Low cap to speed up test
                "current_iteration": 0,
                "event_version": 0,
            })

        # Should fail after cap
        assert result.get("error") is not None
        assert "cap" in result["error"].lower() or "iteration" in result["error"].lower()

        # Events should show multiple iterations
        events = store.get_events("test-wf-fail")
        assert len(events) >= 3  # At minimum: task_created + some iterations + failed
