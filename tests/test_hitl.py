"""
Tests for HITL (Human-in-the-Loop) — Phase 3
==============================================
Tests Break-Glass Protocol, approval gates, and state persistence.
NO real API calls.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from orchestrator.hitl import (
    ApprovalRequest,
    ApprovalStatus,
    AutoApprovalBackend,
    CLIApprovalBackend,
    HITLManager,
    create_hitl_manager,
)


# ============================================================
# HITLManager Tests
# ============================================================


class TestHITLManager:
    """Tests for HITLManager core functionality."""

    def test_auto_approval_skips_disabled_gates(self):
        """Gates not in enabled_gates should be SKIPPED."""
        manager = create_hitl_manager(backend="auto", enabled_gates=["pre_code"])

        status = manager.request(
            workflow_id="wf-1",
            iteration=1,
            gate="post_test",  # NOT in enabled_gates
            title="Test",
            description="Should be skipped",
        )
        assert status == ApprovalStatus.SKIPPED

    def test_auto_approval_approves_enabled_gates(self):
        """Enabled gates should be auto-approved."""
        manager = create_hitl_manager(
            backend="auto",
            enabled_gates=["pre_code"],
            policy="approve",
        )

        status = manager.request(
            workflow_id="wf-1",
            iteration=1,
            gate="pre_code",
            title="Pre-code review",
            description="Check the plan",
        )
        assert status == ApprovalStatus.APPROVED

    def test_auto_rejection_policy(self):
        """Reject policy should reject all requests."""
        manager = create_hitl_manager(
            backend="auto",
            enabled_gates=["pre_code"],
            policy="reject",
        )

        status = manager.request(
            workflow_id="wf-1",
            iteration=1,
            gate="pre_code",
            title="Pre-code review",
            description="Should be rejected",
        )
        assert status == ApprovalStatus.REJECTED

    def test_convenience_pre_code_approval(self):
        """pre_code_approval convenience method should work."""
        manager = create_hitl_manager(
            backend="auto",
            enabled_gates=["pre_code"],
            policy="approve",
        )

        status = manager.pre_code_approval(
            workflow_id="wf-1",
            iteration=1,
            plan="Build a REST API",
        )
        assert status == ApprovalStatus.APPROVED

    def test_convenience_post_test_approval(self):
        """post_test_approval convenience method should work."""
        manager = create_hitl_manager(
            backend="auto",
            enabled_gates=["post_test"],
            policy="approve",
        )

        status = manager.post_test_approval(
            workflow_id="wf-1",
            iteration=2,
            test_results="All 15 tests passed",
        )
        assert status == ApprovalStatus.APPROVED

    def test_convenience_security_review(self):
        """security_review convenience method should work."""
        manager = create_hitl_manager(
            backend="auto",
            enabled_gates=["security_review"],
            policy="approve",
        )

        status = manager.security_review(
            workflow_id="wf-1",
            iteration=1,
            findings="No issues found",
        )
        assert status == ApprovalStatus.APPROVED

    def test_history_tracking(self):
        """All requests should be recorded in history."""
        manager = create_hitl_manager(
            backend="auto",
            enabled_gates=["pre_code", "post_test"],
        )

        manager.pre_code_approval("wf-1", 1, "plan")
        manager.post_test_approval("wf-1", 1, "results")

        assert len(manager.history) == 2
        assert len(manager.get_history("wf-1")) == 2
        assert len(manager.get_history("wf-nonexistent")) == 0

    def test_pending_tracking(self):
        """get_pending should only return PENDING requests."""
        manager = create_hitl_manager(
            backend="auto",
            enabled_gates=["pre_code"],
        )

        # Auto-approval means no pending requests
        manager.pre_code_approval("wf-1", 1, "plan")
        assert len(manager.get_pending()) == 0


# ============================================================
# Break-Glass Protocol Tests
# ============================================================


class TestBreakGlassProtocol:
    """Tests for Break-Glass emergency bypass."""

    def test_break_glass_not_active_by_default(self):
        """Break-glass should not be active by default."""
        manager = create_hitl_manager()
        assert manager.is_break_glass_active() is False

    def test_break_glass_activation(self):
        """break_glass should activate and approve all pending."""
        manager = HITLManager(
            backend=AutoApprovalBackend(policy="skip"),
            enabled_gates=["pre_code"],
        )

        # Create a pending request manually
        req = ApprovalRequest(
            workflow_id="wf-emergency",
            gate="pre_code",
            title="Blocked",
            status=ApprovalStatus.PENDING,
        )
        manager.history.append(req)

        # Activate break-glass
        manager.break_glass(reason="Production outage", operator="admin-fsaad")

        assert manager.is_break_glass_active() is True
        assert req.status == ApprovalStatus.APPROVED
        assert "break_glass" in (req.resolver or "")
        assert "BREAK-GLASS" in req.comment

    def test_break_glass_reset(self):
        """reset_break_glass should deactivate."""
        manager = create_hitl_manager()
        manager.break_glass(reason="test", operator="admin")
        assert manager.is_break_glass_active() is True

        manager.reset_break_glass(operator="admin")
        assert manager.is_break_glass_active() is False


# ============================================================
# Durable State Tests
# ============================================================


class TestHITLDurableState:
    """Tests for state persistence."""

    def test_get_state(self):
        """get_state should serialize all relevant state."""
        manager = create_hitl_manager(
            backend="auto",
            enabled_gates=["pre_code", "post_test"],
        )
        manager.pre_code_approval("wf-1", 1, "plan")

        state = manager.get_state()

        assert "enabled_gates" in state
        assert "history" in state
        assert "break_glass_active" in state
        assert len(state["history"]) == 1
        assert state["enabled_gates"] == ["pre_code", "post_test"]

    def test_restore_state(self):
        """restore_state should restore gates and break-glass status."""
        manager = create_hitl_manager()

        manager.restore_state({
            "enabled_gates": ["security_review"],
            "break_glass_active": True,
        })

        assert manager.enabled_gates == ["security_review"]
        assert manager.is_break_glass_active() is True

    def test_round_trip_state(self):
        """State should survive serialization round-trip."""
        manager1 = create_hitl_manager(
            backend="auto",
            enabled_gates=["pre_code", "security_review"],
        )
        manager1.pre_code_approval("wf-1", 1, "plan")

        state = manager1.get_state()

        manager2 = create_hitl_manager()
        manager2.restore_state(state)

        assert manager2.enabled_gates == manager1.enabled_gates


# ============================================================
# Factory Tests
# ============================================================


class TestHITLFactory:
    """Tests for create_hitl_manager factory."""

    def test_create_auto_backend(self):
        """Should create auto approval backend."""
        manager = create_hitl_manager(backend="auto")
        assert isinstance(manager.backend, AutoApprovalBackend)

    def test_create_cli_backend(self):
        """Should create CLI approval backend."""
        manager = create_hitl_manager(backend="cli", timeout=60)
        assert isinstance(manager.backend, CLIApprovalBackend)

    def test_create_with_gates(self):
        """Should set enabled gates."""
        manager = create_hitl_manager(
            enabled_gates=["pre_code", "post_test", "security_review"]
        )
        assert len(manager.enabled_gates) == 3
