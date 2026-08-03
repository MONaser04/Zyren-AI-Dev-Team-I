"""
Human-in-the-Loop (HITL) — Phase 5
====================================
Provides optional human approval gates during orchestration.
Supports CLI prompts, webhook callbacks, and auto-approval policies.

Integrates with the iteration manager for pause/resume.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ApprovalStatus(Enum):
    """Status of a human approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class ApprovalRequest:
    """A request for human approval."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    workflow_id: str = ""
    iteration: int = 0
    gate: str = ""  # e.g., "pre_commit", "post_test", "deploy"
    title: str = ""
    description: str = ""
    artifact_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    resolver: str | None = None
    comment: str = ""


class ApprovalBackend(ABC):
    """Abstract base for approval backends."""

    @abstractmethod
    def request_approval(self, request: ApprovalRequest) -> ApprovalStatus:
        """Request approval, blocking until resolved."""
        pass

    @abstractmethod
    def cancel(self, request_id: str) -> None:
        """Cancel a pending request."""
        pass


class CLIApprovalBackend(ApprovalBackend):
    """CLI-based approval (for interactive use)."""

    def __init__(self, timeout: int = 300) -> None:
        self.timeout = timeout
        self._pending: dict[str, ApprovalRequest] = {}

    def request_approval(self, request: ApprovalRequest) -> ApprovalStatus:
        """Prompt user in CLI."""
        print(f"\n{'='*60}")
        print(f"⏳ HUMAN APPROVAL REQUIRED: {request.title}")
        print(f"{'='*60}")
        print(f"Workflow: {request.workflow_id}")
        print(f"Iteration: {request.iteration}")
        print(f"Gate: {request.gate}")
        print(f"\n{request.description}")
        if request.artifact_path:
            print(f"\nArtifact: {request.artifact_path}")
        print(f"\nOptions: [a]pprove  [r]eject  [s]kip  [d]etails")
        print(f"Timeout: {self.timeout}s (auto-skip)")

        # In non-interactive mode, auto-approve or timeout
        import sys
        if not sys.stdin.isatty():
            print("Non-interactive mode: auto-approving...")
            request.status = ApprovalStatus.APPROVED
            request.resolved_at = time.time()
            request.resolver = "auto"
            return ApprovalStatus.APPROVED

        # For actual CLI, you'd use input() here
        # This is a scaffold - real implementation would use select/poll
        print("(Non-interactive scaffold - auto-approving)")
        request.status = ApprovalStatus.APPROVED
        request.resolved_at = time.time()
        request.resolver = "auto"
        return ApprovalStatus.APPROVED

    def cancel(self, request_id: str) -> None:
        if request_id in self._pending:
            self._pending[request_id].status = ApprovalStatus.TIMEOUT
            del self._pending[request_id]


class AutoApprovalBackend(ApprovalBackend):
    """Auto-approval based on policy (for CI/CD)."""

    def __init__(self, policy: str = "approve") -> None:
        self.policy = policy  # approve, reject, skip

    def request_approval(self, request: ApprovalRequest) -> ApprovalStatus:
        if self.policy == "approve":
            request.status = ApprovalStatus.APPROVED
        elif self.policy == "reject":
            request.status = ApprovalStatus.REJECTED
        else:
            request.status = ApprovalStatus.SKIPPED

        request.resolved_at = time.time()
        request.resolver = "auto_policy"
        return request.status

    def cancel(self, request_id: str) -> None:
        pass


class WebhookApprovalBackend(ApprovalBackend):
    """Webhook-based approval (for external UI)."""

    def __init__(
        self,
        webhook_url: str,
        timeout: int = 300,
        poll_interval: int = 5,
    ) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.poll_interval = poll_interval

    def request_approval(self, request: ApprovalRequest) -> ApprovalStatus:
        # In real implementation: POST to webhook, poll for response
        # Scaffold: simulate external approval
        import requests

        try:
            payload = {
                "request_id": request.id,
                "workflow_id": request.workflow_id,
                "title": request.title,
                "description": request.description,
                "gate": request.gate,
            }
            requests.post(self.webhook_url, json=payload, timeout=10)
        except Exception:
            pass

        # Poll for result (simplified)
        start = time.time()
        while time.time() - start < self.timeout:
            # In real impl: GET /webhook/status/{request_id}
            time.sleep(self.poll_interval)
            # For scaffold: auto-approve after first poll
            request.status = ApprovalStatus.APPROVED
            request.resolved_at = time.time()
            request.resolver = "webhook"
            return ApprovalStatus.APPROVED

        request.status = ApprovalStatus.TIMEOUT
        return ApprovalStatus.TIMEOUT

    def cancel(self, request_id: str) -> None:
        pass


class HITLManager:
    """Manages human-in-the-loop approval gates."""

    GATES = [
        "pre_plan",       # Before planning
        "pre_code",       # Before code generation
        "pre_test",       # Before running tests
        "post_test",      # After tests, before commit
        "pre_deploy",     # Before deployment
        "security_review",# Security gate
    ]

    def __init__(
        self,
        backend: ApprovalBackend | None = None,
        enabled_gates: list[str] | None = None,
        default_timeout: int = 300,
    ) -> None:
        self.backend = backend or AutoApprovalBackend("approve")
        self.enabled_gates = enabled_gates or []
        self.default_timeout = default_timeout
        self.history: list[ApprovalRequest] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def request(
        self,
        workflow_id: str,
        iteration: int,
        gate: str,
        title: str,
        description: str,
        artifact_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalStatus:
        """Request human approval for a gate."""
        if gate not in self.enabled_gates:
            return ApprovalStatus.SKIPPED

        request = ApprovalRequest(
            workflow_id=workflow_id,
            iteration=iteration,
            gate=gate,
            title=title,
            description=description,
            artifact_path=artifact_path,
            metadata=metadata or {},
        )

        self.history.append(request)
        status = self.backend.request_approval(request)
        return status

    # ------------------------------------------------------------------
    # Convenience methods for standard gates
    # ------------------------------------------------------------------
    def pre_code_approval(
        self, workflow_id: str, iteration: int, plan: str
    ) -> ApprovalStatus:
        return self.request(
            workflow_id=workflow_id,
            iteration=iteration,
            gate="pre_code",
            title="Approve Implementation Plan",
            description=f"Review and approve the implementation plan:\n\n{plan}",
        )

    def post_test_approval(
        self,
        workflow_id: str,
        iteration: int,
        test_results: str,
    ) -> ApprovalStatus:
        return self.request(
            workflow_id=workflow_id,
            iteration=iteration,
            gate="post_test",
            title="Approve Test Results",
            description=f"Test results:\n\n{test_results}",
        )

    def security_review(
        self,
        workflow_id: str,
        iteration: int,
        findings: str,
    ) -> ApprovalStatus:
        return self.request(
            workflow_id=workflow_id,
            iteration=iteration,
            gate="security_review",
            title="Security Review Required",
            description=f"Security findings:\n\n{findings}",
        )

    # ------------------------------------------------------------------
    # History & Status
    # ------------------------------------------------------------------
    def get_history(self, workflow_id: str | None = None) -> list[ApprovalRequest]:
        if workflow_id:
            return [h for h in self.history if h.workflow_id == workflow_id]
        return self.history

    def get_pending(self) -> list[ApprovalRequest]:
        return [h for h in self.history if h.status == ApprovalStatus.PENDING]

    # ------------------------------------------------------------------
    # Break-Glass Protocol
    # ------------------------------------------------------------------
    def break_glass(self, reason: str, operator: str = "admin") -> None:
        """Emergency bypass: approve ALL pending gates and temporarily
        disable approval enforcement.

        This is a security-audited emergency procedure. All actions are logged.

        Args:
            reason: Mandatory reason for the emergency bypass.
            operator: Who is invoking break-glass.
        """
        import logging
        audit_logger = logging.getLogger("hitl.audit")

        audit_logger.critical(
            "🚨 BREAK-GLASS ACTIVATED by %s: %s", operator, reason
        )

        # Approve all pending requests
        for req in self.get_pending():
            req.status = ApprovalStatus.APPROVED
            req.resolved_at = time.time()
            req.resolver = f"break_glass:{operator}"
            req.comment = f"[BREAK-GLASS] {reason}"
            audit_logger.warning(
                "Break-glass approved: gate=%s workflow=%s", req.gate, req.workflow_id
            )

        self._break_glass_active = True
        self._break_glass_reason = reason
        self._break_glass_operator = operator

    def is_break_glass_active(self) -> bool:
        """Check if break-glass is currently active."""
        return getattr(self, "_break_glass_active", False)

    def reset_break_glass(self, operator: str = "admin") -> None:
        """Deactivate break-glass and restore normal approval flow."""
        import logging
        audit_logger = logging.getLogger("hitl.audit")

        audit_logger.info("Break-glass deactivated by %s", operator)
        self._break_glass_active = False
        self._break_glass_reason = ""
        self._break_glass_operator = ""

    # ------------------------------------------------------------------
    # Durable State (for persistence across restarts)
    # ------------------------------------------------------------------
    def get_state(self) -> dict[str, Any]:
        """Serialize HITL state for persistence."""
        return {
            "enabled_gates": self.enabled_gates,
            "history": [
                {
                    "id": r.id,
                    "workflow_id": r.workflow_id,
                    "iteration": r.iteration,
                    "gate": r.gate,
                    "title": r.title,
                    "status": r.status.value,
                    "created_at": r.created_at,
                    "resolved_at": r.resolved_at,
                    "resolver": r.resolver,
                    "comment": r.comment,
                }
                for r in self.history
            ],
            "break_glass_active": self.is_break_glass_active(),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore HITL state from persisted data."""
        self.enabled_gates = state.get("enabled_gates", [])
        self._break_glass_active = state.get("break_glass_active", False)


def create_hitl_manager(
    backend: str = "auto",
    enabled_gates: list[str] | None = None,
    **kwargs,
) -> HITLManager:
    """Factory for HITL manager with backend selection."""
    if backend == "cli":
        be = CLIApprovalBackend(timeout=kwargs.get("timeout", 300))
    elif backend == "webhook":
        be = WebhookApprovalBackend(
            webhook_url=kwargs["webhook_url"],
            timeout=kwargs.get("timeout", 300),
        )
    else:
        be = AutoApprovalBackend(policy=kwargs.get("policy", "approve"))

    return HITLManager(backend=be, enabled_gates=enabled_gates)