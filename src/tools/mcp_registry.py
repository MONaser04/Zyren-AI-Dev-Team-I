"""
MCP Tool Registry — Model Context Protocol Tools
==================================================

Defines MCP-compliant tool definitions and a registry that enforces
role-scoped permissions via PolicyEngine.

READ Phase 3 deliverable:
  'Expose tools via MCP (Linux Foundation standard).'
  'Default-deny, role-scoped permission matrix.'
  'Load only needed tool schemas (Tool-RAG) to keep context small.'
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tools.policy_engine import PolicyEngine


# ============================================================
# MCP Tool Definition
# ============================================================


class MCPTool(BaseModel):
    """A single tool definition following MCP standard.

    https://spec.modelcontextprotocol.io/specification/2024-11-05/server/tools/
    """

    name: str = Field(..., description="Unique tool name.")
    description: str = Field(..., description="Human-readable description.")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for tool parameters.",
    )
    required_permissions: list[str] = Field(
        default_factory=list,
        description="Permissions required to use this tool.",
    )
    category: str = Field(
        default="general",
        description="Tool category for Tool-RAG filtering.",
    )


# ============================================================
# Tool Definitions — Registered Tools
# ============================================================

# --- Filesystem ---

FILE_READ_TOOL = MCPTool(
    name="file_read",
    description="Read file content from the sandbox workspace.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path within the sandbox workspace.",
            },
        },
        "required": ["path"],
    },
    required_permissions=["filesystem.read"],
    category="filesystem",
)

FILE_WRITE_TOOL = MCPTool(
    name="file_write",
    description="Write/overwrite a file in the sandbox workspace.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path within sandbox."},
            "content": {"type": "string", "description": "File content."},
        },
        "required": ["path", "content"],
    },
    required_permissions=["filesystem.write"],
    category="filesystem",
)

FILE_LIST_TOOL = MCPTool(
    name="file_list",
    description="List files in the sandbox workspace directory.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to list (default: root).",
            },
        },
    },
    required_permissions=["filesystem.read"],
    category="filesystem",
)

# --- Git ---

GIT_STATUS_TOOL = MCPTool(
    name="git_status",
    description="Run git status in the sandbox workspace.",
    input_schema={"type": "object", "properties": {}},
    required_permissions=["git.read"],
    category="git",
)

GIT_DIFF_TOOL = MCPTool(
    name="git_diff",
    description="Show git diff of changes in the sandbox workspace.",
    input_schema={
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "Show staged changes only (default: false).",
            },
        },
    },
    required_permissions=["git.read"],
    category="git",
)

GIT_COMMIT_TOOL = MCPTool(
    name="git_commit",
    description="Commit changes in the sandbox workspace.",
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Commit message."},
        },
        "required": ["message"],
    },
    required_permissions=["git.write"],
    category="git",
)

# --- Execution ---

EXEC_TEST_TOOL = MCPTool(
    name="exec_test",
    description="Run pytest in the sandbox environment.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Optional test path (default: all tests).",
            },
        },
    },
    required_permissions=["shell.execute_sandboxed"],
    category="execution",
)

EXEC_LINT_TOOL = MCPTool(
    name="exec_lint",
    description="Run ruff linter in the sandbox environment.",
    input_schema={
        "type": "object",
        "properties": {
            "fix": {
                "type": "boolean",
                "description": "Auto-fix violations (default: false).",
            },
        },
    },
    required_permissions=["shell.execute_sandboxed"],
    category="execution",
)

EXEC_TYPECHECK_TOOL = MCPTool(
    name="exec_typecheck",
    description="Run mypy type checker in the sandbox environment.",
    input_schema={"type": "object", "properties": {}},
    required_permissions=["shell.execute_sandboxed"],
    category="execution",
)

EXEC_SAST_TOOL = MCPTool(
    name="exec_sast",
    description="Run bandit security scanner in the sandbox.",
    input_schema={"type": "object", "properties": {}},
    required_permissions=["shell.execute_sandboxed"],
    category="execution",
)

EXEC_SYNTAX_TOOL = MCPTool(
    name="exec_syntax",
    description="Check Python syntax (ast.parse) on all .py files.",
    input_schema={"type": "object", "properties": {}},
    required_permissions=["shell.execute_sandboxed"],
    category="execution",
)

# --- State ---

STATE_READ_TOOL = MCPTool(
    name="state_read",
    description="Read workflow events from the event store.",
    input_schema={
        "type": "object",
        "properties": {
            "workflow_id": {"type": "string", "description": "Workflow ID."},
        },
        "required": ["workflow_id"],
    },
    required_permissions=["state.read"],
    category="state",
)

STATE_WRITE_TOOL = MCPTool(
    name="state_write",
    description="Append an event to the event store.",
    input_schema={
        "type": "object",
        "properties": {
            "workflow_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "event_type": {"type": "string"},
            "payload": {"type": "object"},
        },
        "required": ["workflow_id", "agent_id", "event_type", "payload"],
    },
    required_permissions=["state.write"],
    category="state",
)

# --- Notifications ---

NOTIFY_SEND_TOOL = MCPTool(
    name="notify_send",
    description="Send a notification to the human operator (via console/log).",
    input_schema={
        "type": "object",
        "properties": {
            "level": {"type": "string", "description": "info/warning/critical"},
            "message": {"type": "string"},
        },
        "required": ["level", "message"],
    },
    required_permissions=["notifications.send"],
    category="notifications",
)

# --- Web (Deep Research) ---

WEB_SEARCH_TOOL = MCPTool(
    name="web_search",
    description="Execute an open web search query and return ranked results.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 10).",
            },
        },
        "required": ["query"],
    },
    required_permissions=["web.search"],
    category="web",
)

WEB_SCRAPE_TOOL = MCPTool(
    name="web_scrape",
    description="Fetch and extract text content from a URL (read-only scrape).",
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to scrape.",
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum character count to return (default: 8000).",
            },
        },
        "required": ["url"],
    },
    required_permissions=["web.scrape"],
    category="web",
)

# ============================================================
# ALL_TOOLS — Master Registry
# ============================================================

ALL_TOOLS: dict[str, MCPTool] = {
    t.name: t
    for t in [
        FILE_READ_TOOL,
        FILE_WRITE_TOOL,
        FILE_LIST_TOOL,
        GIT_STATUS_TOOL,
        GIT_DIFF_TOOL,
        GIT_COMMIT_TOOL,
        EXEC_TEST_TOOL,
        EXEC_LINT_TOOL,
        EXEC_TYPECHECK_TOOL,
        EXEC_SAST_TOOL,
        EXEC_SYNTAX_TOOL,
        STATE_READ_TOOL,
        STATE_WRITE_TOOL,
        NOTIFY_SEND_TOOL,
        WEB_SEARCH_TOOL,
        WEB_SCRAPE_TOOL,
    ]
}

# ============================================================
# MCP Registry
# ============================================================


class MCPRegistry:
    """Registry that resolves tools and enforces role-based permissions.

    Delegates permission checks to PolicyEngine.
    Supports Tool-RAG (filtering tools by category for a given task).

    If *policy_engine* is None, a default PolicyEngine is created.
    """

    def __init__(self, policy_engine: PolicyEngine | None = None) -> None:
        self._policy = policy_engine if policy_engine is not None else PolicyEngine()
        self._tools: dict[str, MCPTool] = dict(ALL_TOOLS)  # copy

    # ----------------------------------------------------------
    # Tool Registration
    # ----------------------------------------------------------

    def register(self, tool: MCPTool) -> None:
        """Register a new tool definition."""
        self._tools[tool.name] = tool

    def list_all(self) -> list[MCPTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> MCPTool | None:
        """Return a tool by name, or None if not found."""
        return self._tools.get(tool_name)

    def clear(self) -> None:
        """Remove all tools from the registry (for testing/clean slate)."""
        self._tools.clear()

    def search(self, query: str) -> list[MCPTool]:
        """Search tools by name or description substring match."""
        q = query.lower()
        results: list[MCPTool] = []
        for t in self._tools.values():
            if q in t.name.lower() or q in t.description.lower():
                results.append(t)
        return results

    def describe_for_llm(self, role: str) -> str:
        """Return a human-readable description of tools available to *role*.

        Uses the full tool list (not task-filtered) so all authorized tools
        are described regardless of task type.
        """
        # Check if role is known to policy engine
        perms = self._policy.get_permissions_for_role(role)
        if perms is None:
            return f"No tools available — role '{role}' is not recognized."

        authorized: list[MCPTool] = []
        for t in self._tools.values():
            if self._policy.check(role, t.required_permissions):
                authorized.append(t)

        if not authorized:
            return f"No tools available for role '{role}' with current permissions."

        lines: list[str] = [
            f"Available Tools for '{role}':",
            "-" * 40,
        ]
        for tool in authorized:
            lines.append(f"  {tool.name}: {tool.description}")
            if tool.required_permissions:
                lines.append(f"    Required permissions: {', '.join(tool.required_permissions)}")

        return "\n".join(lines)

    def to_openai_tools(self, role: str) -> list[dict[str, Any]]:
        """Return tools in OpenAI function-calling format for *role*.

        Each entry: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        """
        authorized = self.list_for_role(role)
        result: list[dict[str, Any]] = []
        for t in authorized:
            result.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            })
        return result

    # ----------------------------------------------------------
    # Permission-Aware Resolution
    # ----------------------------------------------------------

    def resolve(self, tool_name: str, role: str) -> MCPTool | None:
        """Resolve a tool by name, enforcing role permissions.

        Args:
            tool_name: Name of the requested tool.
            role: Agent role requesting the tool.

        Returns:
            MCPTool if found AND authorized, None otherwise.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return None

        # Check permissions via PolicyEngine
        if not self._policy.check(role, tool.required_permissions):
            return None

        return tool

    def resolve_or_raise(self, tool_name: str, role: str) -> MCPTool:
        """Resolve a tool, raising PolicyViolationError on denial.

        Args:
            tool_name: Name of the requested tool.
            role: Agent role requesting the tool.

        Returns:
            MCPTool if found AND authorized.

        Raises:
            KeyError: If tool name is not registered.
            PolicyViolationError: If role lacks required permissions.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            msg = f"Tool not registered: '{tool_name}'"
            raise KeyError(msg)

        self._policy.check_or_raise(role, tool.required_permissions, tool_name)
        return tool

    # ----------------------------------------------------------
    # Tool-RAG — Load Only Needed Schemas
    # ----------------------------------------------------------

    def list_for_role(self, role: str) -> list[MCPTool]:
        """Return all tools this role is authorized to use.

        Filters by permission — keeps LLM context small.
        """
        return [
            t
            for t in self._tools.values()
            if self._policy.check(role, t.required_permissions)
        ]

    def list_by_category(self, categories: list[str]) -> list[MCPTool]:
        """Filter tools by category for Tool-RAG.

        Example: for a 'coding' task, load only filesystem + git + execution.
        """
        return [t for t in self._tools.values() if t.category in categories]

    def list_for_task(self, task_type: str) -> list[MCPTool]:
        """Return only the tools relevant to a specific task type.

        Task → Category mapping (Tool-RAG):
          - 'coding':      filesystem, git, execution
          - 'testing':     filesystem, execution
          - 'review':      filesystem, state
          - 'security':    filesystem, execution (sast only)
          - 'architecture': state, filesystem
          - 'notification': notifications

        Keeps LLM context small by loading only needed tool schemas.
        """
        _TASK_CATEGORIES: dict[str, list[str]] = {
            "coding": ["filesystem", "git", "execution"],
            "testing": ["filesystem", "execution"],
            "review": ["filesystem", "state"],
            "security": ["filesystem", "execution"],
            "architecture": ["filesystem", "state"],
            "notification": ["notifications"],
            "research": ["web", "state"],
            "general": ["filesystem", "git", "execution", "state", "notifications", "web"],
        }

        cats = _TASK_CATEGORIES.get(task_type, _TASK_CATEGORIES["general"])
        return self.list_by_category(cats)

    # ----------------------------------------------------------
    # Introspection
    # ----------------------------------------------------------

    def get_schema(self, tool_name: str) -> dict[str, Any] | None:
        """Return the input_schema for a specific tool."""
        tool = self._tools.get(tool_name)
        return tool.input_schema if tool else None

    def generate_system_prompt(
        self,
        role: str,
        task_type: str = "general",
    ) -> str:
        """Generate a system prompt fragment listing available tools.

        This is injected into agent system prompts so the LLM knows
        what tools are available and their schemas.
        """
        tools = self.list_for_task(task_type)
        authorized = [t for t in tools if self._policy.check(role, t.required_permissions)]

        if not authorized:
            return "No tools available for this role."

        lines: list[str] = ["## Available Tools", ""]
        for tool in authorized:
            lines.append(f"### {tool.name}")
            lines.append(f"Description: {tool.description}")
            lines.append(f"Parameters: ```json\n{tool.input_schema}\n```")
            lines.append("")

        return "\n".join(lines)