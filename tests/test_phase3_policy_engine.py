"""Smoke tests for Phase 3 — Policy Engine default-deny permissions."""

import pytest

from tools.policy_engine import PolicyEngine, PolicyViolationError


class TestPolicyEngine:
    """Verify default-deny permission matrix."""

    def test_coder_can_read_files(self) -> None:
        pe = PolicyEngine()
        assert pe.check("coder", ["filesystem.read"])

    def test_coder_cannot_exec_db_commands(self) -> None:
        pe = PolicyEngine()
        # db_query is in coder's deny list AND not in allowed
        assert not pe.check("coder", ["db.execute"])

    def test_tester_can_run_tests(self) -> None:
        pe = PolicyEngine()
        assert pe.check("tester", ["shell.execute_sandboxed"])

    def test_tester_cannot_write_files(self) -> None:
        pe = PolicyEngine()
        # file_write is in tester's denied_tools
        assert not pe.check("tester", ["filesystem.write"])

    def test_unknown_role_rejected(self) -> None:
        pe = PolicyEngine()
        assert not pe.check("bogus_role", ["filesystem.read"])

    def test_unknown_tool_rejected(self) -> None:
        pe = PolicyEngine()
        # 'flying_drones' is not in coder's allow list → default deny
        assert not pe.check("coder", ["flying_drones"])

    def test_supervisor_can_do_anything(self) -> None:
        pe = PolicyEngine()
        # supervisor has wildcard '*' → can do anything
        assert pe.check("supervisor", ["filesystem.read"])
        assert pe.check("supervisor", ["filesystem.write"])
        assert pe.check("supervisor", ["db.execute"])
        assert pe.check("supervisor", ["anything_at_all"])

    def test_daily_quota_enforcement(self) -> None:
        pe = PolicyEngine()
        pe.reset_quotas()
        # coder has max_daily_calls=100 in default policy
        for _ in range(100):
            pe.authorize("coder", "file_read")
        # 101st call should raise
        with pytest.raises(PolicyViolationError, match="Daily quota exceeded"):
            pe.authorize("coder", "file_read")

    def test_quota_reset_on_new_day(self) -> None:
        pe = PolicyEngine()
        pe.reset_quotas()
        for _ in range(100):
            pe.authorize("coder", "file_read")
        # quota exhausted
        with pytest.raises(PolicyViolationError):
            pe.authorize("coder", "file_read")
        # simulate new day
        pe.reset_quotas()
        # should work again
        pe.authorize("coder", "file_read")

    def test_get_permissions(self) -> None:
        pe = PolicyEngine()
        perms = pe.get_permissions_for_role("coder")
        assert perms.allowed_tools is not None
        assert "file_read" in perms.allowed_tools

    def test_researcher_can_search(self) -> None:
        pe = PolicyEngine()
        # researcher has web_search in allowed
        assert pe.check("researcher", ["web.search"])