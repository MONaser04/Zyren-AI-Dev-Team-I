"""
Tools Package — MCP Tool Registry, Policy Engine, Sandbox
==========================================================

Components:
- policy_engine: Default-deny role-scoped permission matrix.
- mcp_registry: MCP-compliant tool definitions and registry.
- tool_executor: Execute tools with permission checks and param validation.
- sandbox: Hardened Docker/local execution sandbox.
"""

from tools.mcp_registry import ALL_TOOLS, MCPRegistry, MCPTool
from tools.policy_engine import PolicyEngine, PolicyViolationError
from tools.sandbox import (
    DockerSandboxProvider,
    SandboxProvider,
    SandboxResult,
    create_sandbox,
)
from tools.tool_executor import ToolExecutor, ToolResult

__all__ = [
    "ALL_TOOLS",
    "MCPRegistry",
    "MCPTool",
    "PolicyEngine",
    "PolicyViolationError",
    "ToolExecutor",
    "ToolResult",
    "SandboxProvider",
    "SandboxResult",
    "DockerSandboxProvider",
    "create_sandbox",
]