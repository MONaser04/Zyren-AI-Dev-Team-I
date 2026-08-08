"""
Project Explorer Agent — Phase 4
=================================

Handles purely exploratory and informational tasks about the local repository.
Uses MCP tools (file_list, file_read) to navigate and analyze the codebase
before synthesizing a definitive response.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from observability.instrumentation import trace_agent_invocation
from agents.base import BaseAgent
from contracts.schemas import ProjectExplorationReport

from tools.mcp_registry import MCPRegistry
from tools.policy_engine import PolicyEngine
from tools.tool_executor import ToolExecutor

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient

logger = logging.getLogger(__name__)

EXPLORER_SYSTEM_PROMPT = """\
You are an expert Software Architect and Project Explorer.
Your goal is to answer questions about the current local repository.

To answer accurately, you must EXPLORE the repository using your tools.
You are equipped with a tool loop. You can use the following tools:
- `file_list(path: str)`: List files in a directory.
- `file_read(path: str)`: Read the contents of a file.

**TOOL USAGE FORMAT:**
To use a tool, you MUST output ONLY a JSON object and NOTHING else. 
Example:
{"action": "file_list", "params": {"path": "./src"}}
{"action": "file_read", "params": {"path": "./src/main.py"}}

**FINAL ANSWER FORMAT:**
Once you have gathered enough information to answer the user's question,
you must output ONLY a JSON object with your final answer and the files you analyzed.
Example:
{"ready": true, "answer": "The project uses LangGraph for orchestration...", "files_analyzed": ["./src/graph.py"]}

CRITICAL RULES:
1. Do NOT guess or hallucinate. Use the tools to read the actual code.
2. If you output a JSON object, do NOT include any markdown formatting (like ```json). Just the raw JSON object.
3. Keep exploring until you are confident in your answer.
4. When evaluating relationships, dependencies, or connections between components (e.g., agents, classes, or modules), DO NOT rely solely on the class definitions or initializations within a single file. You MUST search for and examine orchestration files, graph pipelines, and main execution flows to determine how components interact externally in the broader system architecture.
"""


class ProjectExplorerAgent(BaseAgent):
    """Explorer agent — analyzes the repository to answer informational queries."""

    def __init__(
        self,
        llm_client: LLMClient,
        model: str = "frontier",
        agent_id: str = "explorer-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="explorer", llm_client=llm_client)
        self.model = model
        
        # Initialize tool executor
        mcp_registry = MCPRegistry()
        policy_engine = PolicyEngine()
        self.tool_executor = ToolExecutor(mcp_registry, policy_engine)

    @trace_agent_invocation(agent_role="explorer")
    def run(self, task_description: str, task_id: str, workflow_id: str) -> ProjectExplorationReport:
        """Run the exploration loop and produce a report."""
        
        self.logger.info("ProjectExplorerAgent starting exploration loop for task: %s", task_id)
        
        messages = [
            {"role": "system", "content": EXPLORER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Please explore the repository to answer this task:\n\n{task_description}"}
        ]
        
        final_answer = "Exploration failed to produce a conclusive answer."
        files_analyzed = []
        
        for step in range(15):  # Max 15 tool interactions
            self.logger.debug("Exploration step %d", step + 1)
            raw_response = self.llm_client.complete_text(
                complexity="complex",
                messages=messages,
                temperature=0.1,
                max_tokens=2048,
            )
            
            try:
                # Attempt to extract JSON from the response (handle potential markdown blocks)
                cleaned_response = raw_response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]
                elif cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                    
                start = cleaned_response.find("{")
                if start == -1:
                    self.logger.warning("No JSON found in response. Appending raw response and prompting again.")
                    messages.append({"role": "assistant", "content": raw_response})
                    messages.append({"role": "user", "content": "Error: You must output ONLY a valid JSON object starting with { and ending with }."})
                    continue

                stack = []
                end = start
                in_string = False
                escape = False
                for i, ch in enumerate(cleaned_response[start:], start):
                    if not in_string:
                        if ch == "{":
                            stack.append("}")
                        elif ch == "[":
                            stack.append("]")
                        elif ch == "}" or ch == "]":
                            if stack and stack[-1] == ch:
                                stack.pop()
                            if not stack:
                                end = i + 1
                                break
                        elif ch == '"':
                            in_string = True
                    else:
                        if escape:
                            escape = False
                        elif ch == '\\':
                            escape = True
                        elif ch == '"':
                            in_string = False

                if stack:
                    suffix = ""
                    if in_string:
                        suffix += '"'
                    while stack:
                        suffix += stack.pop()
                    cleaned_obj = cleaned_response[start:] + suffix
                else:
                    cleaned_obj = cleaned_response[start:end]

                try:
                    data = json.loads(cleaned_obj)
                except json.JSONDecodeError as err:
                    if "}" not in suffix:
                        raise ValueError(f"JSONDecodeError: {str(err)} for extracted string: {cleaned_obj[:100]}...")
                    else:
                        raise err
                
                if data.get("ready"):
                    final_answer = data.get("answer", "No answer provided.")
                    files_analyzed = data.get("files_analyzed", [])
                    self.logger.info("Exploration complete. Analyzed %d files.", len(files_analyzed))
                    break
                    
                if "action" in data:
                    tool_name = data["action"]
                    params = data.get("params", {})
                    
                    # Track files analyzed
                    if tool_name == "file_read" and "path" in params:
                        if params["path"] not in files_analyzed:
                            files_analyzed.append(params["path"])
                            
                    result = self.tool_executor.execute(tool_name, role="explorer", params=params)
                    tool_out = result.output
                    
                    # Truncate if too long to prevent context overflow
                    if len(tool_out) > 10000:
                        tool_out = tool_out[:10000] + "\n...[TRUNCATED]"
                        
                    messages.append({"role": "assistant", "content": json.dumps(data)})
                    messages.append({"role": "user", "content": f"Tool Output:\n{tool_out}"})
                    self.logger.info("Executed tool: %s", tool_name)
                else:
                    messages.append({"role": "assistant", "content": raw_response})
                    messages.append({"role": "user", "content": "Output must be valid JSON with 'tool' or 'ready'."})
                    
            except Exception as e:
                self.logger.error("Error parsing or executing tool: %s", str(e))
                messages.append({"role": "assistant", "content": raw_response})
                messages.append({"role": "user", "content": f"Exception occurred: {str(e)}. Please try again and ensure valid JSON."})

        return ProjectExplorationReport(
            task_id=task_id,
            workflow_id=workflow_id,
            answer=final_answer,
            files_analyzed=files_analyzed
        )
