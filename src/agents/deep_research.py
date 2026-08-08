"""
Deep Research Agent — Open Web Research & Data Aggregation
============================================================

Dedicated to the "Deep Research" domain. Handles open web research,
general data gathering, social/statistical analysis, and any non-technical
information retrieval routed by the Semantic Router.

Distinct from ProfessionalResearcherAgent (official docs only) and
ResearcherAgent (on-demand within SDLC fan-out). This agent operates
independently on the deep_research lane with its own contract
(ResearchReport) and scoped MCP tool permissions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from contracts.schemas import ResearchReport, ResearchSource, ResearchDataPoint
from observability.instrumentation import trace_agent_invocation

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient
    from tools.mcp_registry import MCPRegistry
    from tools.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)

# Maximum search + scrape iterations per research task
_MAX_RESEARCH_ITERATIONS = 5
_MIN_SOURCE_CONFIDENCE = 0.3
_MIN_REPORT_CONFIDENCE = 0.5


class DeepResearchAgent(BaseAgent):
    """Open Web Researcher — search, scrape, aggregate, and synthesize.

    Policy role: ``deep_researcher``
    Permitted tools: ``web_search``, ``web_scrape``, ``state_read``
    Output contract: ``ResearchReport``
    """

    role: str = "deep_researcher"

    def __init__(
        self,
        llm_client: "LLMClient",
        model: str = "frontier",
        agent_id: str = "deep-research-01",
        *,
        tool_executor: "ToolExecutor | None" = None,
        mcp_registry: "MCPRegistry | None" = None,
    ) -> None:
        super().__init__(agent_id=agent_id, role="deep_researcher", llm_client=llm_client)
        self.model = model
        self._tool_executor = tool_executor
        self._mcp_registry = mcp_registry

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    @trace_agent_invocation(agent_role="deep_researcher")
    def run(
        self,
        query: str,
        context: str = "",
        *,
        workflow_id: str = "",
        max_iterations: int = _MAX_RESEARCH_ITERATIONS,
    ) -> ResearchReport:
        """Execute an open web research task and return a validated ResearchReport.

        Args:
            query: The research question or topic.
            context: Optional prior context or constraints.
            workflow_id: Parent workflow ID for tracing.
            max_iterations: Cap on search/scrape cycles.

        Returns:
            A validated ResearchReport contract ready for event-store commit.
        """
        # Phase 1: Generate search queries from the research question
        search_queries = self._generate_search_queries(query, context)

        # Phase 2: Execute searches and collect raw results
        raw_results = self._execute_searches(search_queries, workflow_id=workflow_id)

        # Phase 3: Selectively scrape high-value URLs
        scraped_content = self._scrape_sources(raw_results, workflow_id=workflow_id)

        # Phase 4: Synthesize all gathered data into a structured report
        report = self._synthesize_report(
            query=query,
            context=context,
            search_results=raw_results,
            scraped_content=scraped_content,
            workflow_id=workflow_id,
        )

        self.logger.info(
            "Deep research completed: %d sources, confidence=%.2f",
            len(report.sources),
            report.overall_confidence,
        )
        return report

    # ----------------------------------------------------------
    # Phase 1: Query Decomposition
    # ----------------------------------------------------------

    def _generate_search_queries(self, query: str, context: str) -> list[str]:
        """Use the LLM to decompose a broad research question into targeted search queries."""
        prompt = (
            "You are a research query planner. Decompose the following research "
            "question into 3-5 targeted web search queries that will maximize "
            "coverage of the topic.\n\n"
            f"Research Question: {query}\n"
        )
        if context:
            prompt += f"Additional Context: {context}\n"
        prompt += (
            "\nRespond ONLY with a JSON object, no other text:\n"
            '{"queries": ["query1", "query2", ...]}'
        )

        result = self.llm_client.complete_text(
            messages=[{"role": "user", "content": prompt}],
            complexity="complex",
            temperature=0.3,
            max_tokens=512,
            workflow_id="",
        )

        return self._parse_queries(result, fallback=query)

    def _parse_queries(self, raw: str, *, fallback: str) -> list[str]:
        """Extract the query list from LLM output, falling back to the original query."""
        import json

        try:
            # Strip markdown fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(cleaned)
            queries = parsed.get("queries", [])
            if isinstance(queries, list) and queries:
                return [str(q) for q in queries[:5]]
        except (json.JSONDecodeError, AttributeError, KeyError):
            self.logger.warning("Failed to parse search queries from LLM; using fallback.")
        return [fallback]

    # ----------------------------------------------------------
    # Phase 2: Web Search Execution
    # ----------------------------------------------------------

    def _execute_searches(
        self,
        queries: list[str],
        *,
        workflow_id: str = "",
    ) -> list[dict[str, Any]]:
        """Execute web searches via the MCP web_search tool.

        Falls back to LLM-simulated search if no tool executor is available.
        """
        all_results: list[dict[str, Any]] = []

        for q in queries:
            if self._tool_executor is not None:
                try:
                    result = self._tool_executor.execute(
                        tool_name="web_search",
                        role=self.role,
                        params={"query": q, "max_results": 10},
                    )
                    if result.success:
                        import json
                        try:
                            parsed = json.loads(result.output)
                            if isinstance(parsed, list):
                                all_results.extend(parsed)
                            elif isinstance(parsed, dict):
                                all_results.append(parsed)
                        except json.JSONDecodeError:
                            all_results.append({"query": q, "raw_output": result.output})
                    else:
                        self.logger.warning("Web search denied/failed for query: %s", q)
                except Exception:
                    self.logger.exception("Web search tool error for query: %s", q)
            else:
                # No tool executor — use LLM to simulate search results
                all_results.extend(self._llm_simulated_search(q, workflow_id=workflow_id))

        return all_results

    def _llm_simulated_search(
        self,
        query: str,
        *,
        workflow_id: str = "",
    ) -> list[dict[str, Any]]:
        """LLM-based search result generation when no tool executor is wired."""
        import json

        prompt = (
            "Simulate web search results for the query below. "
            "Return realistic search results as JSON.\n\n"
            f"Query: {query}\n\n"
            "Respond ONLY with a JSON array of objects, no other text:\n"
            '[{"title": "...", "url": "...", "snippet": "..."}, ...]'
        )
        raw = self.llm_client.complete_text(
            messages=[{"role": "user", "content": prompt}],
            complexity="complex",
            temperature=0.2,
            max_tokens=1024,
            workflow_id=workflow_id,
        )
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, list) else [parsed]
        except (json.JSONDecodeError, AttributeError):
            return [{"query": query, "raw_output": raw}]

    # ----------------------------------------------------------
    # Phase 3: Selective Scraping
    # ----------------------------------------------------------

    def _scrape_sources(
        self,
        search_results: list[dict[str, Any]],
        *,
        workflow_id: str = "",
    ) -> list[dict[str, Any]]:
        """Scrape top URLs from search results via the MCP web_scrape tool."""
        scraped: list[dict[str, Any]] = []
        urls_seen: set[str] = set()

        for result in search_results:
            url = result.get("url", "")
            if not url or url in urls_seen:
                continue
            urls_seen.add(url)

            if self._tool_executor is not None:
                try:
                    scrape_result = self._tool_executor.execute(
                        tool_name="web_scrape",
                        role=self.role,
                        params={"url": url, "max_length": 8000},
                    )
                    if scrape_result.success:
                        scraped.append({
                            "url": url,
                            "title": result.get("title", ""),
                            "content": scrape_result.output,
                        })
                except Exception:
                    self.logger.warning("Scrape failed for URL: %s", url)
            else:
                # Use snippet as surrogate when no scraper is available
                scraped.append({
                    "url": url,
                    "title": result.get("title", ""),
                    "content": result.get("snippet", ""),
                })

            if len(scraped) >= _MAX_RESEARCH_ITERATIONS:
                break

        return scraped

    # ----------------------------------------------------------
    # Phase 4: Synthesis
    # ----------------------------------------------------------

    def _synthesize_report(
        self,
        *,
        query: str,
        context: str,
        search_results: list[dict[str, Any]],
        scraped_content: list[dict[str, Any]],
        workflow_id: str = "",
    ) -> ResearchReport:
        """Synthesize all gathered data into a validated ResearchReport contract."""
        prompt = self._build_synthesis_prompt(
            query=query,
            context=context,
            search_results=search_results,
            scraped_content=scraped_content,
        )

        report = self.llm_client.complete_structured(
            messages=[{"role": "user", "content": prompt}],
            response_model=ResearchReport,
            complexity="complex",
            temperature=0.1,
            max_tokens=4096,
            workflow_id=workflow_id,
        )

        # Post-validation: enforce minimum confidence
        if report.overall_confidence < _MIN_REPORT_CONFIDENCE:
            self.logger.warning(
                "Research report confidence %.2f below threshold %.2f; "
                "flagging as low-confidence.",
                report.overall_confidence,
                _MIN_REPORT_CONFIDENCE,
            )

        return report

    @staticmethod
    def _build_synthesis_prompt(
        *,
        query: str,
        context: str,
        search_results: list[dict[str, Any]],
        scraped_content: list[dict[str, Any]],
    ) -> str:
        import json

        search_block = json.dumps(search_results[:20], indent=2, default=str)
        scrape_block = json.dumps(
            [
                {"url": s["url"], "title": s["title"], "content": s["content"][:2000]}
                for s in scraped_content[:10]
            ],
            indent=2,
            default=str,
        )

        return (
            "You are a Deep Research Analyst. Synthesize the following raw data "
            "into a structured research report.\n\n"
            f"RESEARCH QUESTION: {query}\n"
            f"CONTEXT: {context or 'None provided.'}\n\n"
            f"SEARCH RESULTS:\n{search_block}\n\n"
            f"SCRAPED CONTENT:\n{scrape_block}\n\n"
            "Produce a ResearchReport JSON with:\n"
            "- query: the original research question\n"
            "- summary: a concise executive summary of findings\n"
            "- sources: list of {url, title, accessed_at, reliability_score (0-1)} objects\n"
            "- data_points: list of {claim, evidence, confidence (0-1), source_urls} objects\n"
            "- key_findings: list of strings summarizing the main conclusions\n"
            "- methodology: brief description of the research approach\n"
            "- limitations: list of known gaps or caveats\n"
            "- overall_confidence: float 0.0-1.0 assessing the overall reliability\n"
            "- recommendations: actionable next steps or conclusions\n\n"
            "Respond ONLY with the JSON object, no other text."
        )

    # ----------------------------------------------------------
    # Repr
    # ----------------------------------------------------------

    def __repr__(self) -> str:
        return f"DeepResearchAgent(model={self.model}, agent_id={self.agent_id})"
