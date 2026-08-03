"""
Workflow Runner — Phase 5 Enhanced
===================================
Enhanced entry point with:
- Convergence detection
- Artifact management
- Human-in-the-Loop gates
- Closed-loop optimisation integration
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gateway.client import LiteLLMClient
    from state.store import EventStore
    from orchestrator.graph import GraphState

from orchestrator.convergence import create_convergence_manager, OrchestratorConvergence
from orchestrator.artifacts import create_artifact_manager, ArtifactManager
from orchestrator.hitl import create_hitl_manager, HITLManager, ApprovalStatus

logger = logging.getLogger(__name__)


def _get_graph_components():
    """Lazy import to avoid circular dependency with agents module."""
    from orchestrator.graph import GraphState, build_feedback_loop
    return GraphState, build_feedback_loop


# ============================================================
# Workflow Result (Phase 5 Enhanced)
# ============================================================


@dataclass
class WorkflowResult:
    """Result of running a workflow through the feedback loop."""

    workflow_id: str
    success: bool
    iterations: int
    final_code: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    events_count: int = 0
    # Phase 5 additions
    converged: bool = False
    convergence_reason: str = ""
    artifacts_summary: dict[str, Any] = field(default_factory=dict)
    hitl_approvals: list[dict[str, Any]] = field(default_factory=list)
    total_cost_usd: float = 0.0


# ============================================================
# Enhanced Runner
# ============================================================


def run_workflow(
    task_description: str,
    *,
    language: str = "python",
    constraints: list[str] | None = None,
    max_iterations: int = 5,
    event_store: "EventStore | None" = None,
    llm_client: "LiteLLMClient | None" = None,
    # Phase 5 features
    enable_convergence: bool = True,
    convergence_config: dict[str, Any] | None = None,
    enable_artifacts: bool = True,
    artifact_types: list[str] | None = None,
    enable_hitl: bool = False,
    hitl_config: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> WorkflowResult:
    """Run a coding task through the enhanced feedback loop (Phase 5).

    Phase 5 adds:
    - Convergence detection (early stopping when improvements plateau)
    - Artifact management (versioned build artifacts)
    - Human-in-the-Loop approval gates
    - Integration with optimisation loops

    Args:
        task_description: Natural-language description of the coding task.
        language: Target programming language.
        constraints: Additional constraints or requirements.
        max_iterations: Maximum feedback loop iterations (hard cap).
        event_store: Pre-existing event store (creates one if None).
        llm_client: Pre-existing LLM client (creates one if None).
        enable_convergence: Enable convergence detection for early stopping.
        convergence_config: Config for ConvergenceDetector.
        enable_artifacts: Enable artifact collection.
        artifact_types: Types of artifacts to collect (default: all).
        enable_hitl: Enable human-in-the-loop approval gates.
        hitl_config: Config for HITLManager (backend, gates, timeout).
        db_path: Path for the SQLite database (None = in-memory).

    Returns:
        A WorkflowResult with the outcome.
    """
    # Initialize dependencies
    if event_store is None:
        from state.store import SQLiteEventStore
        event_store = SQLiteEventStore(db_path=db_path or ":memory:")

    if llm_client is None:
        from gateway.llm_client import LLMClient as LiteLLMClient
        llm_client = LiteLLMClient()

    workflow_id = uuid.uuid4().hex[:16]

    logger.info(
        "Starting workflow %s: %s (max_iterations=%d, conv=%s, artifacts=%s, hitl=%s)",
        workflow_id,
        task_description[:80],
        max_iterations,
        enable_convergence,
        enable_artifacts,
        enable_hitl,
    )

    # Phase 5: Initialize managers
    convergence_mgr: OrchestratorConvergence | None = None
    if enable_convergence:
        conv_cfg = convergence_config or {}
        convergence_mgr = create_convergence_manager(
            min_samples=conv_cfg.get("min_samples", 3),
            window_size=conv_cfg.get("window_size", 3),
            improvement_threshold=conv_cfg.get("improvement_threshold", 0.02),
            patience=conv_cfg.get("patience", 2),
            min_score=conv_cfg.get("min_score", 0.7),
        )

    artifact_mgr: ArtifactManager | None = None
    if enable_artifacts:
        artifact_mgr = create_artifact_manager(workflow_id)

    hitl_mgr: HITLManager | None = None
    if enable_hitl:
        hitl_cfg = hitl_config or {}
        hitl_mgr = create_hitl_manager(
            backend=hitl_cfg.get("backend", "auto"),
            enabled_gates=hitl_cfg.get("enabled_gates"),
            timeout=hitl_cfg.get("timeout", 300),
            policy=hitl_cfg.get("policy", "approve"),
        )

    # Build the graph (lazy import)
    GraphState, build_feedback_loop = _get_graph_components()
    graph = build_feedback_loop(
        event_store=event_store,
        llm_client=llm_client,
    )

    compiled = graph.compile()

    # Initial state
    initial_state: GraphState = {
        "workflow_id": workflow_id,
        "task_description": task_description,
        "language": language,
        "constraints": constraints or [],
        "max_iterations": max_iterations,
        "current_iteration": 0,
        "event_version": 0,
        "rebuttal_used": False,
        "fast_lane": True,
        "domain": "software_engineering",
    }

    # Run the graph with Phase 5 hooks
    try:
        final_state = _run_with_hooks(
            compiled=compiled,
            initial_state=initial_state,
            workflow_id=workflow_id,
            convergence_mgr=convergence_mgr,
            artifact_mgr=artifact_mgr,
            hitl_mgr=hitl_mgr,
            event_store=event_store,
            llm_client=llm_client,
        )
    except Exception as e:
        logger.exception("Workflow %s failed with exception", workflow_id)
        return WorkflowResult(
            workflow_id=workflow_id,
            success=False,
            iterations=0,
            error=str(e),
        )

    # Extract results
    events = event_store.get_events(workflow_id)

    # Extract final code files
    final_code: dict[str, str] = {}
    code_patch = final_state.get("code_patch", {})
    if isinstance(code_patch, dict) and "files" in code_patch:
        for f in code_patch["files"]:
            if isinstance(f, dict):
                final_code[f.get("path", "unknown")] = f.get("content", "")

    # Add deep research report if present
    deep_research = final_state.get("deep_research_report")
    if deep_research:
        import json as _json
        import csv
        import io
        
        # 1. JSON Report
        final_code["deep_research_report.json"] = _json.dumps(deep_research, indent=2, ensure_ascii=False, default=str)
        
        # 2. Markdown Summary
        md = f"# Deep Research Report: {deep_research.get('query', '')}\n\n"
        md += f"## Summary\n{deep_research.get('summary', '')}\n\n"
        md += "## Key Findings\n"
        for finding in deep_research.get("key_findings", []):
            md += f"- {finding}\n"
        md += f"\n## Overall Confidence: {deep_research.get('overall_confidence', 0.0):.2f}\n"
        final_code["deep_research_report.md"] = md
        
        # 3. CSV / Excel-compatible Data Export
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["Claim", "Confidence", "Source URLs", "Evidence"])
        for dp in deep_research.get("data_points", []):
            urls = ", ".join(dp.get("source_urls", []))
            writer.writerow([
                dp.get("claim", ""),
                dp.get("confidence", ""),
                urls,
                dp.get("evidence", "")
            ])
        final_code["deep_research_data.csv"] = csv_buffer.getvalue()

    success = final_state.get("verdict") == "PASS"

    # Phase 5: Collect additional results
    converged = False
    convergence_reason = ""
    if convergence_mgr:
        status = convergence_mgr.status()
        converged = status.get("patience_counter", 0) >= 2  # Simplified
        convergence_reason = "Converged" if converged else "Max iterations"

    artifacts_summary = {}
    if artifact_mgr:
        artifacts_summary = artifact_mgr.summary()

    hitl_approvals = []
    if hitl_mgr:
        hitl_approvals = hitl_mgr.get_history(workflow_id)

    result = WorkflowResult(
        workflow_id=workflow_id,
        success=success,
        iterations=final_state.get("current_iteration", 0),
        final_code=final_code,
        error=final_state.get("error"),
        events_count=len(events),
        converged=converged,
        convergence_reason=convergence_reason,
        artifacts_summary=artifacts_summary,
        hitl_approvals=[
            {
                "gate": a.get("gate"),
                "status": a.get("status", "unknown").value
                if hasattr(a.get("status"), "value") else str(a.get("status")),
                "timestamp": a.get("timestamp"),
            }
            for a in hitl_approvals
        ],
        total_cost_usd=0.0,  # Would be computed from LLM calls
    )

    logger.info(
        "Workflow %s finished: success=%s, iterations=%d, converged=%s, artifacts=%d",
        workflow_id,
        result.success,
        result.iterations,
        result.converged,
        artifacts_summary.get("total_artifacts", 0),
    )

    return result


# ============================================================
# Internal: Run with Phase 5 Hooks
# ============================================================


def _run_with_hooks(
    compiled,
    initial_state: GraphState,
    workflow_id: str,
    convergence_mgr: OrchestratorConvergence | None,
    artifact_mgr: ArtifactManager | None,
    hitl_mgr: HITLManager | None,
    event_store: "EventStore",
    llm_client: "LiteLLMClient",
) -> GraphState:
    """Run graph with Phase 5 hooks injected between nodes."""

    # For now, use standard invoke and add hooks via state inspection
    # A full implementation would use LangGraph's interrupt/checkpoint features
    max_iter = initial_state.get("max_iterations", 5)
    # Each iteration passes through ~8 nodes (coder→tester→hitl→critic→rebut→judge→increment)
    # Plus initial nodes (assign_task, route). Add generous buffer.
    recursion_limit = max(50, max_iter * 10 + 20)
    final_state = compiled.invoke(initial_state, {"recursion_limit": recursion_limit})

    # Post-run: save final artifacts
    if artifact_mgr:
        code_patch = final_state.get("code_patch", {})
        if code_patch:
            artifact_mgr.save(
                content=str(code_patch),
                artifact_type="final_code_patch",
                iteration=final_state.get("current_iteration", 0),
                filename=f"final_patch_iter{final_state.get('current_iteration', 0)}.json",
            )

        # Save logs
        logs = _extract_logs(event_store, workflow_id)
        artifact_mgr.save(
            content=logs,
            artifact_type="logs",
            iteration=final_state.get("current_iteration", 0),
            filename=f"workflow_logs.txt",
        )

    return final_state


def _extract_logs(event_store: "EventStore", workflow_id: str) -> str:
    """Extract log-like summary from events."""
    events = event_store.get_events(workflow_id)
    lines = [f"Workflow: {workflow_id}", f"Events: {len(events)}", ""]
    for e in events:
        xtype = getattr(e, 'event_type', 'UNKNOWN')
        ts = getattr(e, 'timestamp', 0)
        lines.append(f"  [{ts}] {xtype}")
    return "\n".join(lines)


# ============================================================
# Phase 5: Evaluation Runner
# ============================================================


def run_evaluation_batch(
    tasks: list[dict[str, Any]],
    *,
    max_concurrent: int = 1,
    **run_workflow_kwargs,
) -> list[WorkflowResult]:
    """Run multiple evaluation tasks (for Golden Set / SWE-bench).

    This is a simple sequential runner. For production, use async/parallel.
    """
    results: list[WorkflowResult] = []

    for i, task in enumerate(tasks):
        logger.info("Running evaluation task %d/%d: %s", i + 1, len(tasks), task.get("id", "unknown"))
        try:
            result = run_workflow(
                task_description=task.get("prompt", task.get("description", "")),
                **run_workflow_kwargs,
            )
            result.task_id = task.get("id")
            results.append(result)
        except Exception as e:
            logger.exception("Task %s failed", task.get("id"))
            results.append(WorkflowResult(
                workflow_id="error",
                success=False,
                iterations=0,
                error=str(e),
                task_id=task.get("id"),
            ))

    return results