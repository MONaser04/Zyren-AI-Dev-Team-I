"""
Observability — OpenTelemetry Metrics (Phase 4)
================================================

Implements the two GenAI metrics called out in README §4.1:
  - gen_ai.client.token.usage  (Counter, attrs: model, type=input|output)
  - gen_ai.client.operation.duration  (Histogram, attrs: operation, model)

Plus domain-specific counters:
  - agent.invocations (attrs: agent_role, verdict)
  - tool.executions (attrs: tool_name, role, success)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

_meter_name = "zyren-ai-dev-team.genai"
_initialized = False
_meter: metrics.Meter | None = None

# Metric instruments (lazily created)
token_usage_counter: metrics.Counter | None = None
operation_duration_hist: metrics.Histogram | None = None
agent_invocations_counter: metrics.Counter | None = None
tool_executions_counter: metrics.Counter | None = None


@dataclass(frozen=True)
class MetricsConfig:
    otlp_endpoint: str = "http://localhost:4318"
    export_interval_ms: int = 5000


def setup_metrics(config: MetricsConfig | None = None) -> None:
    """Initialize global metrics. Idempotent."""
    global _initialized, _meter, token_usage_counter, operation_duration_hist
    global agent_invocations_counter, tool_executions_counter
    if _initialized:
        return
    if config is None:
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        config = MetricsConfig(otlp_endpoint=endpoint)
    reader = PeriodicExportingMetricReader(
        exporter=OTLPMetricExporter(
            endpoint=f"{config.otlp_endpoint}/v1/metrics"
        ),
        export_interval_millis=config.export_interval_ms,
    )
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    _meter = metrics.get_meter(_meter_name)
    token_usage_counter = _meter.create_counter(
        "gen_ai.client.token.usage",
        unit="{token}",
        description="Total tokens used by model calls.",
    )
    operation_duration_hist = _meter.create_histogram(
        "gen_ai.client.operation.duration",
        unit="s",
        description="Duration of GenAI operations (LLM calls).",
    )
    agent_invocations_counter = _meter.create_counter(
        "agent.invocations",
        unit="{invocation}",
        description="Number of agent invocations by role and verdict.",
    )
    tool_executions_counter = _meter.create_counter(
        "tool.executions",
        unit="{execution}",
        description="Number of tool executions by name, role, and success.",
    )
    _initialized = True


def record_token_usage(
    model: str, prompt_tokens: int, completion_tokens: int
) -> None:
    """Record token usage for a model call (gen_ai.client.token.usage)."""
    if token_usage_counter is not None:
        token_usage_counter.add(prompt_tokens, {"model": model, "type": "input"})
        token_usage_counter.add(completion_tokens, {"model": model, "type": "output"})


def record_operation_duration(operation: str, model: str, duration_s: float) -> None:
    """Record the duration of a GenAI operation (gen_ai.client.operation.duration)."""
    if operation_duration_hist is not None:
        operation_duration_hist.record(
            duration_s, {"operation": operation, "model": model}
        )


def record_agent_invocation(agent_role: str, verdict: str) -> None:
    """Record an agent invocation (agent.invocations)."""
    if agent_invocations_counter is not None:
        agent_invocations_counter.add(1, {"agent_role": agent_role, "verdict": verdict})


def record_tool_execution(tool_name: str, role: str, success: bool) -> None:
    """Record a tool execution (tool.executions)."""
    if tool_executions_counter is not None:
        tool_executions_counter.add(
            1, {"tool_name": tool_name, "role": role, "success": str(success).lower()}
        )