"""Observability package — OpenTelemetry tracing + metrics + instrumentation (Phase 4)."""

from observability.instrumentation import (
    trace_agent_invocation,
    trace_chat,
    trace_tool_execution,
)
from observability.metrics import (
    MetricsConfig,
    record_agent_invocation,
    record_operation_duration,
    record_token_usage,
    record_tool_execution,
    setup_metrics,
)
from observability.tracing import (
    GEN_AI_AGENT_ROLE,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_FINISH_REASON,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_SYSTEM,
    GEN_AI_TOOL_NAME,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    SPAN_CHAT,
    SPAN_EXECUTE_TOOL,
    SPAN_INVOKE_AGENT,
    SPAN_WORKFLOW,
    TracingConfig,
    get_tracer,
    setup_tracing,
)

__all__ = [
    # Tracing
    "TracingConfig",
    "setup_tracing",
    "get_tracer",
    "GEN_AI_SYSTEM",
    "GEN_AI_REQUEST_MODEL",
    "GEN_AI_RESPONSE_MODEL",
    "GEN_AI_USAGE_INPUT_TOKENS",
    "GEN_AI_USAGE_OUTPUT_TOKENS",
    "GEN_AI_RESPONSE_FINISH_REASON",
    "GEN_AI_TOOL_NAME",
    "GEN_AI_AGENT_ROLE",
    "SPAN_INVOKE_AGENT",
    "SPAN_CHAT",
    "SPAN_EXECUTE_TOOL",
    "SPAN_WORKFLOW",
    # Metrics
    "MetricsConfig",
    "setup_metrics",
    "record_token_usage",
    "record_operation_duration",
    "record_agent_invocation",
    "record_tool_execution",
    # Instrumentation
    "trace_agent_invocation",
    "trace_chat",
    "trace_tool_execution",
]
