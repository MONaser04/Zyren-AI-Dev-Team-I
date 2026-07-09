"""Smoke tests for Phase 3 — MCP Tool Registry."""

from tools.mcp_registry import ALL_TOOLS, MCPRegistry, MCPTool


class TestMCPTool:
    """Verify MCPTool dataclass."""

    def test_create_tool(self) -> None:
        tool = MCPTool(
            name="test_tool",
            description="A test tool.",
            input_schema={"type": "object", "properties": {}},
            category="dev",
            required_permissions=["filesystem.read"],
        )
        assert tool.name == "test_tool"
        assert tool.category == "dev"


class TestMCPRegistry:
    """Verify registry operations."""

    def test_all_tools_loaded(self) -> None:
        assert len(ALL_TOOLS) >= 10
        # check a few standard tools by name
        assert "file_read" in ALL_TOOLS
        assert "exec_test" in ALL_TOOLS
        assert "exec_lint" in ALL_TOOLS

    def test_register_and_get_tool(self) -> None:
        reg = MCPRegistry()
        reg.clear()
        tool = MCPTool(
            name="custom_tool",
            description="Custom tool.",
            input_schema={"type": "object"},
            category="dev",
            required_permissions=["filesystem.read"],
        )
        reg.register(tool)
        retrieved = reg.get_tool("custom_tool")
        assert retrieved is not None
        assert retrieved.name == "custom_tool"

    def test_list_all_returns_all_registered(self) -> None:
        reg = MCPRegistry()
        reg.clear()
        tool1 = MCPTool(name="t1", description="Tool 1", category="dev")
        tool2 = MCPTool(name="t2", description="Tool 2", category="dev")
        reg.register(tool1)
        reg.register(tool2)
        all_tools = reg.list_all()
        assert len(all_tools) == 2

    def test_list_for_role_filters(self) -> None:
        reg = MCPRegistry()
        # Use default policy engine (coder can read files, etc.)
        # file_read exists in default registry and coder can use it
        coder_tools = reg.list_for_role("coder")
        # coder should have access to filesystem tools
        assert len(coder_tools) >= 4  # file_read, file_write, file_list, git_*, exec_*
        tool_names = {t.name for t in coder_tools}
        assert "file_read" in tool_names

    def test_search_by_name(self) -> None:
        reg = MCPRegistry()
        reg.clear()
        reg.register(MCPTool(name="run_tests", description="Execute test suite", category="test"))
        reg.register(MCPTool(name="read_file", description="Read a file", category="dev"))
        reg.register(MCPTool(name="typecheck_test", description="Type check code", category="test"))

        results = reg.search("test")
        assert len(results) == 2
        names = {t.name for t in results}
        assert "run_tests" in names
        assert "typecheck_test" in names

    def test_describe_for_llm(self) -> None:
        reg = MCPRegistry()
        reg.clear()
        reg.register(MCPTool(
            name="read_file",
            description="Read a file from disk.",
            input_schema={},
            category="dev",
            required_permissions=["filesystem.read"],
        ))
        reg.register(MCPTool(
            name="exec_test",
            description="Run tests in sandbox.",
            input_schema={},
            category="test",
            required_permissions=["shell.execute_sandboxed"],
        ))
        # Check describe works for roles with matching permissions
        coder_desc = reg.describe_for_llm("coder")
        assert len(coder_desc) > 10  # returns something
        # Should contain at least one tool description
        assert "read_file" in coder_desc.lower() or "Read a file" in coder_desc

        # Supervisor with wildcard can see all tools
        sup_desc = reg.describe_for_llm("supervisor")
        assert len(sup_desc) > 10

        # Unknown role gets denied
        unknown_desc = reg.describe_for_llm("bogus_role")
        assert len(unknown_desc) > 0  # returns fallback message

    def test_to_openai_tools(self) -> None:
        reg = MCPRegistry()
        reg.clear()
        reg.register(MCPTool(
            name="read_file",
            description="Read a file.",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            category="dev",
            required_permissions=["filesystem.read"],
        ))
        # coder has filesystem.read permission in default policy
        openai_tools = reg.to_openai_tools("coder")
        assert len(openai_tools) == 1
        tool_def = openai_tools[0]
        assert tool_def["type"] == "function"
        assert tool_def["function"]["name"] == "read_file"

    def test_get_nonexistent_tool_returns_none(self) -> None:
        reg = MCPRegistry()
        reg.clear()
        assert reg.get_tool("nonexistent") is None

    def test_default_registry_has_standard_tools(self) -> None:
        reg = MCPRegistry()
        # Default registry is pre-populated with ALL_TOOLS
        assert reg.get_tool("file_read") is not None
        assert reg.get_tool("exec_test") is not None
        assert reg.get_tool("exec_lint") is not None