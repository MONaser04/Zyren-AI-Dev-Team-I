"""
Policy Engine — Default-Deny Permission Matrix
================================================

Loads config/policies.yaml and enforces role-scoped permissions for
every tool invocation. Default-deny means: if a permission is not
EXPLICITLY listed in a role's 'allow' list, it is denied.

READ Phase 3 deliverable: 'Enforce a default-deny, role-scoped permission matrix.'
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class PolicyViolationError(Exception):
    """Raised when a role attempts an unauthorized tool action."""


class PolicyEngine:
    """Load and evaluate the default-deny permission matrix.

    Each role has an explicit `allow` list and an optional `deny` list.
    - If a role is not found → default deny.
    - If a permission is in `deny` → denied even if in `allow`.
    - If a permission is NOT in `allow` → default deny.
    - Wildcard '*' in `allow` → admin override (full access).

    If *policies_path* is None, uses a built-in minimal policy set.
    """

    # Built-in default policies when no YAML file is provided.
    _DEFAULT_POLICIES: dict[str, Any] = {
        "default_policy": "deny",
        "roles": {
            "coder": {
                "allowed_tools": [
                    "read_file", "write_file", "exec_command",
                    "git_diff", "git_commit", "lint",
                    "web_search", "file_read", "sandbox_exec",
                ],
                "allowed_permissions": [
                    "filesystem.read",
                    "filesystem.write",
                    "git.read",
                    "git.write",
                    "shell.execute_sandboxed",
                    "shell.execute_lint",
                    "shell.execute_typecheck",
                    "shell.execute_syntax",
                    "web.search",
                ],
                "denied_tools": ["db_query"],
                "denied_permissions": [],
                "max_daily_calls": 100,
                "requires_approval": ["git_commit", "exec_command"],
            },
            "tester": {
                "allowed_tools": [
                    "run_tests", "typecheck", "lint",
                    "read_file", "sandbox_exec",
                ],
                "allowed_permissions": [
                    "filesystem.read",
                    "shell.execute_sandboxed",
                    "shell.execute_lint",
                    "shell.execute_typecheck",
                    "shell.execute_syntax",
                ],
                "denied_tools": ["write_file", "git_commit", "db_query"],
                "denied_permissions": [],
                "max_daily_calls": 200,
                "requires_approval": [],
            },
            "critic": {
                "allowed_tools": [
                    "read_file", "lint", "run_tests", "typecheck",
                ],
                "allowed_permissions": [
                    "filesystem.read",
                    "shell.execute_sandboxed",
                    "shell.execute_lint",
                    "shell.execute_typecheck",
                    "state.read",
                ],
                "denied_tools": ["write_file", "exec_command", "git_commit", "db_query"],
                "denied_permissions": [],
                "max_daily_calls": 150,
                "requires_approval": [],
            },
            "reviewer": {
                "allowed_tools": [
                    "read_file", "lint", "run_tests", "typecheck",
                ],
                "allowed_permissions": [
                    "filesystem.read",
                    "shell.execute_lint",
                    "shell.execute_typecheck",
                    "state.read",
                ],
                "denied_tools": ["write_file", "exec_command", "git_commit", "db_query"],
                "denied_permissions": [],
                "max_daily_calls": 150,
                "requires_approval": [],
            },
            "researcher": {
                "allowed_tools": ["web_search", "read_file"],
                "allowed_permissions": ["web.search", "filesystem.read"],
                "denied_tools": ["write_file", "exec_command", "git_commit", "db_query", "run_tests"],
                "denied_permissions": [],
                "max_daily_calls": 50,
                "requires_approval": [],
            },
            "deep_researcher": {
                "allowed_tools": ["web_search", "web_scrape", "state_read"],
                "allowed_permissions": [
                    "web.search",
                    "web.scrape",
                    "state.read",
                ],
                "denied_tools": [
                    "write_file", "file_write", "exec_command",
                    "git_commit", "git_diff", "git_status",
                    "db_query", "run_tests", "exec_test",
                    "exec_lint", "exec_typecheck", "exec_sast",
                    "exec_syntax", "state_write", "notify_send",
                ],
                "denied_permissions": [
                    "filesystem.write",
                    "git.read",
                    "git.write",
                    "shell.execute_sandboxed",
                    "shell.execute_lint",
                    "shell.execute_typecheck",
                    "shell.execute_syntax",
                    "state.write",
                    "notifications.send",
                ],
                "max_daily_calls": 100,
                "requires_approval": [],
            },
            "supervisor": {
                "allowed_tools": ["*"],
                "allowed_permissions": ["*"],
                "denied_tools": [],
                "denied_permissions": [],
                "max_daily_calls": 10,
                "requires_approval": [],
            },
        },
    }

    def __init__(self, policies_path: str | Path | None = None) -> None:
        if policies_path is None:
            self._path: Path | None = None
            self._config = self._DEFAULT_POLICIES
        else:
            self._path = Path(policies_path)
            self._config = self._load()

    # ----------------------------------------------------------
    # Load
    # ----------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        """Load and parse the policies YAML file."""
        assert self._path is not None  # only called when path is provided
        if not self._path.exists():
            msg = f"Policies file not found: {self._path}"
            raise FileNotFoundError(msg)

        raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            msg = "Policies file must be a YAML mapping."
            raise ValueError(msg)

        return raw

    # ----------------------------------------------------------
    # Permission Check
    # ----------------------------------------------------------

    def check(
        self,
        role: str,
        required_permissions: list[str],
    ) -> bool:
        """Check whether *role* has ALL *required_permissions*.

        Checks `allowed_permissions` first (matching MCPTool.required_permissions),
        then falls back to `allowed_tools` for backwards compatibility.

        Args:
            role: Agent role name (e.g., 'coder', 'tester', 'critic').
            required_permissions: Permissions the tool demands (e.g., ['filesystem.read']).

        Returns:
            True if all permissions are granted, False otherwise.
        """
        roles_config: dict[str, Any] = self._config.get("roles", {})
        role_policy = roles_config.get(role)

        # Unknown role → default deny
        if role_policy is None:
            return False

        # Use allowed_permissions if available (matches MCPTool.required_permissions)
        allow_list: list[str] = role_policy.get("allowed_permissions", [])
        deny_list: list[str] = role_policy.get("denied_permissions", [])

        # If no allowed_permissions, fallback to allowed_tools (old format)
        if not allow_list:
            allow_list = role_policy.get("allowed_tools", [])
            deny_list = role_policy.get("denied_tools", [])

        # Wildcard admin override
        if "*" in allow_list:
            return True

        for perm in required_permissions:
            # Explicit deny takes precedence
            if perm in deny_list:
                return False
            # Not explicitly allowed → default deny
            if perm not in allow_list:
                return False

        return True

    def check_or_raise(
        self,
        role: str,
        required_permissions: list[str],
        tool_name: str,
    ) -> None:
        """Check permissions, raising PolicyViolationError on failure.

        Args:
            role: Agent role name.
            required_permissions: Permissions the tool demands.
            tool_name: Name of the tool for error message context.

        Raises:
            PolicyViolationError: If any required permission is denied.
        """
        if not self.check(role, required_permissions):
            msg = (
                f"Policy violation: role '{role}' is not authorized to use "
                f"tool '{tool_name}'. Required permissions: {required_permissions}."
            )
            raise PolicyViolationError(msg)

    # ----------------------------------------------------------
    # Introspection
    # ----------------------------------------------------------

    def list_allowed_tools(self, role: str) -> list[str]:
        """Return the list of tool names explicitly allowed for a role."""
        roles_config: dict[str, Any] = self._config.get("roles", {})
        role_policy = roles_config.get(role)
        if role_policy is None:
            return []
        return list(role_policy.get("allowed_tools", []))

    @property
    def deny_list_for(self, role: str) -> list[str]:
        """Return the list of tool names explicitly denied for a role."""
        roles_config: dict[str, Any] = self._config.get("roles", {})
        role_policy = roles_config.get(role)
        if role_policy is None:
            return []
        return list(role_policy.get("denied_tools", []))

    def list_all_roles(self) -> list[str]:
        """Return all defined role names."""
        roles_config: dict[str, Any] = self._config.get("roles", {})
        return list(roles_config.keys())

    @property
    def default_policy(self) -> str:
        """Return the default_policy setting from config."""
        return str(self._config.get("default_policy", "deny"))

    # ----------------------------------------------------------
    # Tool-Role Authorization (convenience API)
    # ----------------------------------------------------------

    def authorize(self, role: str, tool_name: str) -> None:
        """Authorize a role to use a tool, raising on denial.

        Checks:
        1. Role is known
        2. Tool is in allowed list (and not denied)
        3. Daily quota not exceeded

        Args:
            role: Agent role name (e.g., 'coder', 'tester').
            tool_name: The tool ID requesting access.

        Raises:
            PolicyViolationError: On any check failure.
        """
        # Check role exists
        roles_config: dict[str, Any] = self._config.get("roles", {})
        role_policy = roles_config.get(role)
        if role_policy is None:
            msg = f"Policy violation: Unknown role '{role}'."
            raise PolicyViolationError(msg)

        allow_list: list[str] = role_policy.get("allowed_tools", [])
        deny_list: list[str] = role_policy.get("denied_tools", [])

        # Wildcard admin
        if "*" not in allow_list:
            if tool_name in deny_list:
                msg = f"Policy violation: role '{role}' is not permitted to use tool '{tool_name}'."
                raise PolicyViolationError(msg)
            if tool_name not in allow_list:
                msg = f"Policy violation: role '{role}' is not permitted to use tool '{tool_name}'."
                raise PolicyViolationError(msg)

        # Daily quota
        max_daily = role_policy.get("max_daily_calls", 100)
        if not hasattr(self, "_daily_counters"):
            self._daily_counters: dict[str, int] = {}
        current = self._daily_counters.get(role, 0)
        if current >= max_daily:
            msg = f"Policy violation: Daily quota exceeded for role '{role}'."
            raise PolicyViolationError(msg)
        self._daily_counters[role] = current + 1

    def get_permissions_for_role(self, role: str) -> Any:
        """Return the ToolPermission object for a given role.

        Returns a lightweight namespace with allowed_tools, denied_tools,
        max_daily_calls, and requires_approval fields.
        """
        from types import SimpleNamespace

        roles_config: dict[str, Any] = self._config.get("roles", {})
        role_policy = roles_config.get(role)
        if role_policy is None:
            return SimpleNamespace(
                allowed_tools=[], denied_tools=[], max_daily_calls=0, requires_approval=[],
            )
        return SimpleNamespace(
            allowed_tools=list(role_policy.get("allowed_tools", [])),
            denied_tools=list(role_policy.get("denied_tools", [])),
            max_daily_calls=role_policy.get("max_daily_calls", 100),
            requires_approval=list(role_policy.get("requires_approval", [])),
        )

    def reset_quotas(self) -> None:
        """Reset all daily usage counters (simulate new day)."""
        if not hasattr(self, "_daily_counters"):
            self._daily_counters: dict[str, int] = {}
        self._daily_counters.clear()
