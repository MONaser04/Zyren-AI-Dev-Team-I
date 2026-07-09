"""
Tool Executor — Execute MCP Tools in the Sandbox
==================================================

Resolves tools via MCPRegistry, validates parameters against JSON Schema,
checks permissions via PolicyEngine, and executes tools inside the sandbox.

READ Phase 3 deliverable: 'Secure Execution Sandbox.'
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.mcp_registry import MCPRegistry
from tools.policy_engine import PolicyEngine, PolicyViolationError

logger = logging.getLogger(__name__)


# ============================================================
# Tool Result
# ============================================================


@dataclass(frozen=True)
class ToolResult:
    """Structured result from a tool execution."""

    tool_name: str
    success: bool
    output: str = ""
    exit_code: int = 0
    denied: bool = False
    reason: str = ""
    details: dict[str, object] = field(default_factory=dict)

    @classmethod
    def denied_result(cls, tool_name: str, reason: str) -> ToolResult:
        """Factory for permission-denied results."""
        return cls(
            tool_name=tool_name,
            success=False,
            denied=True,
            reason=reason,
            exit_code=403,
        )

    @classmethod
    def success_result(
        cls,
        tool_name: str,
        output: str,
        details: dict[str, object] | None = None,
    ) -> ToolResult:
        """Factory for successful results."""
        return cls(
            tool_name=tool_name,
            success=True,
            output=output,
            details=details or {},
        )

    @classmethod
    def error_result(
        cls,
        tool_name: str,
        output: str,
        exit_code: int = 1,
    ) -> ToolResult:
        """Factory for execution error results."""
        return cls(
            tool_name=tool_name,
            success=False,
            output=output,
            exit_code=exit_code,
        )


# ============================================================
# Tool Executor
# ============================================================


class ToolExecutor:
    """Execute MCP tools inside the sandbox workspace.

    Flow:
    1. Resolve tool definition via MCPRegistry.
    2. Validate parameters against tool.input_schema.
    3. Check role permissions via PolicyEngine (delegates to registry).
    4. Execute the tool in the sandbox workspace.
    5. Return structured ToolResult.
    """

    def __init__(
        self,
        registry: MCPRegistry,
        policy_engine: PolicyEngine,
        workspace_path: str | Path = "",
        timeout: int = 30,
    ) -> None:
        """Initialize the tool executor.

        Args:
            registry: The MCP tool registry.
            policy_engine: The permission policy engine.
            workspace_path: Sandbox workspace directory path.
            timeout: Default subprocess timeout in seconds.
        """
        self._registry = registry
        self._policy = policy_engine
        self._workspace = Path(workspace_path) if workspace_path else Path.cwd()
        self._timeout = timeout

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        role: str,
    ) -> ToolResult:
        """Execute a tool by name with given parameters.

        Args:
            tool_name: Name of the tool to execute.
            params: Tool parameters (validated against schema).
            role: Agent role requesting execution.

        Returns:
            ToolResult with execution outcome.
        """
        # 1. Resolve + permission check
        tool = self._registry.resolve(tool_name, role)
        if tool is None:
            # Check: not registered or permission denied?
            if tool_name not in self._registry.list_all():
                return ToolResult.denied_result(
                    tool_name, f"Tool '{tool_name}' not registered."
                )
            return ToolResult.denied_result(
                tool_name,
                f"Permission denied: role '{role}' cannot use '{tool_name}'.",
            )

        # 2. Validate parameters
        validation_error = self._validate_params(tool.input_schema, params)
        if validation_error:
            return ToolResult.error_result(
                tool_name,
                f"Parameter validation failed: {validation_error}",
            )

        # 3. Dispatch to handler
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return ToolResult.error_result(
                tool_name,
                f"No handler registered for tool '{tool_name}'.",
            )

        try:
            from observability.instrumentation import trace_tool_execution
            wrapped_handler = trace_tool_execution(tool_name, role)(handler)
            return wrapped_handler(self._workspace, params, self._timeout)
        except Exception as exc:
            logger.exception("Tool execution error: %s", tool_name)
            return ToolResult.error_result(
                tool_name,
                f"Execution error: {exc}",
            )

    def set_workspace(self, path: str | Path) -> None:
        """Update the sandbox workspace path."""
        self._workspace = Path(path)

    # ----------------------------------------------------------
    # Parameter Validation
    # ----------------------------------------------------------

    @staticmethod
    def _validate_params(schema: dict[str, Any], params: dict[str, Any]) -> str | None:
        """Basic JSON Schema validation for tool parameters.

        Checks required fields and types. Returns error message or None.
        """
        required: list[str] = schema.get("required", [])
        properties: dict[str, Any] = schema.get("properties", {})

        # Check required fields
        for field in required:
            if field not in params:
                return f"Missing required parameter: '{field}'."

        # Basic type checking
        _TYPE_MAP: dict[str, type] = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        for field, value in params.items():
            prop = properties.get(field)
            if prop is None:
                continue  # Unknown field — allow extra params

            expected_type_str = prop.get("type")
            if expected_type_str is None:
                continue

            expected_type = _TYPE_MAP.get(expected_type_str)
            if expected_type is None:
                continue

            if not isinstance(value, expected_type):
                return (
                    f"Parameter '{field}' must be of type {expected_type_str}, "
                    f"got {type(value).__name__}."
                )

        return None


# ============================================================
# Tool Handlers
# ============================================================


def _handle_file_read(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    path = workspace / params["path"]
    try:
        content = path.read_text(encoding="utf-8")
        return ToolResult.success_result(
            "file_read",
            content,
            {"file_path": str(path), "lines": str(content.count("\n") + 1)},
        )
    except FileNotFoundError:
        return ToolResult.error_result("file_read", f"File not found: {path}")
    except PermissionError:
        return ToolResult.error_result("file_read", f"Permission denied: {path}")


def _handle_file_write(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    path = workspace / params["path"]
    content = params["content"]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult.success_result(
            "file_write",
            f"Written {len(content)} chars to {path}.",
            {"file_path": str(path), "size_bytes": str(len(content.encode()))},
        )
    except OSError as e:
        return ToolResult.error_result("file_write", str(e))


def _handle_file_list(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    target = workspace / params.get("path", ".")
    try:
        entries = []
        for item in sorted(target.iterdir()):
            entry_type = "dir" if item.is_dir() else "file"
            entries.append(f"{entry_type}: {item.name}")
        output = "\n".join(entries) if entries else "Empty directory."
        return ToolResult.success_result(
            "file_list", output, {"count": len(entries)}
        )
    except FileNotFoundError:
        return ToolResult.error_result("file_list", f"Directory not found: {target}")


def _handle_exec(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    """Generic execution handler (wraps subprocess)."""
    cmd: list[str] = params.get("cmd", [])
    if not cmd:
        return ToolResult.error_result("exec", "No command provided.")

    cwd = workspace
    if extra_path := params.get("cwd"):
        cwd = workspace / extra_path

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        return ToolResult.success_result(
            params.get("tool_name", "exec"),
            output,
            {"exit_code": result.returncode, "cwd": str(cwd)},
        )
    except subprocess.TimeoutExpired:
        return ToolResult.error_result(
            params.get("tool_name", "exec"),
            f"Command timed out after {timeout}s.",
        )
    except FileNotFoundError:
        return ToolResult.error_result(
            params.get("tool_name", "exec"),
            f"Command not found: {cmd[0] if cmd else '?'}",
        )


def _handle_exec_test(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    test_path = params.get("path", ".")
    cmd = ["pytest", "-v", "--tb=short", "--no-header", test_path]
    return _handle_exec(
        workspace,
        {**params, "cmd": cmd, "tool_name": "exec_test"},
        timeout,
    )


def _handle_exec_lint(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    fix = params.get("fix", False)
    cmd = ["ruff", "check"]
    if fix:
        cmd.append("--fix")
    cmd.append(".")
    return _handle_exec(
        workspace,
        {**params, "cmd": cmd, "tool_name": "exec_lint"},
        timeout,
    )


def _handle_exec_typecheck(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    cmd = ["mypy", "--ignore-missing-imports", "--no-error-summary", "."]
    return _handle_exec(
        workspace,
        {**params, "cmd": cmd, "tool_name": "exec_typecheck"},
        timeout,
    )


def _handle_exec_sast(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    cmd = ["bandit", "-r", ".", "--exclude", "test_*", "-f", "json", "-q"]
    return _handle_exec(
        workspace,
        {**params, "cmd": cmd, "tool_name": "exec_sast"},
        timeout,
    )


def _handle_exec_syntax(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    """Check Python syntax on all .py files."""
    py_files = list(workspace.rglob("*.py"))
    if not py_files:
        return ToolResult.success_result("exec_syntax", "No Python files found.")

    errors: list[str] = []
    for f in py_files:
        result = subprocess.run(
            ["python", "-c", f"import ast; ast.parse(open(r'{f}').read())"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            errors.append(f"{f.name}: {result.stderr.strip()}")

    if errors:
        return ToolResult.error_result(
            "exec_syntax", "\n".join(errors), exit_code=1
        )
    return ToolResult.success_result("exec_syntax", "All files parse OK.")


def _handle_git_status(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    cmd = ["git", "status", "--short"]
    return _handle_exec(
        workspace,
        {**params, "cmd": cmd, "tool_name": "git_status"},
        timeout,
    )


def _handle_git_diff(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    cmd = ["git", "diff"]
    if params.get("staged", False):
        cmd.append("--staged")
    return _handle_exec(
        workspace,
        {**params, "cmd": cmd, "tool_name": "git_diff"},
        timeout,
    )


def _handle_git_commit(
    workspace: Path, params: dict[str, Any], timeout: int
) -> ToolResult:
    message = params["message"]
    cmd = ["git", "commit", "-m", message]
    return _handle_exec(
        workspace,
        {**params, "cmd": cmd, "tool_name": "git_commit"},
        timeout,
    )


# ============================================================
# Handler Dispatch Table
# ============================================================

_TOOL_HANDLERS: dict[str, Any] = {
    "file_read": _handle_file_read,
    "file_write": _handle_file_write,
    "file_list": _handle_file_list,
    "git_status": _handle_git_status,
    "git_diff": _handle_git_diff,
    "git_commit": _handle_git_commit,
    "exec_test": _handle_exec_test,
    "exec_lint": _handle_exec_lint,
    "exec_typecheck": _handle_exec_typecheck,
    "exec_sast": _handle_exec_sast,
    "exec_syntax": _handle_exec_syntax,
}

# Note: state_read, state_write, and notify_send are handled at the agent
# level (they interact with the event store), not via subprocess.