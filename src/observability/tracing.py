"""
Observability — OpenTelemetry Tracing Setup (Phase 4)
=====================================================

Initializes the global TracerProvider with an OTLP HTTP exporter
so traces can be viewed in Jaeger (docker-compose service) or any
OTLP-compatible backend (Langfuse, Phoenix).

Implements the OpenTelemetry GenAI semantic conventions (2026):
  - Span names: invoke_agent.<role>, chat, execute_tool.<name>
  - Attributes: gen_ai.system, gen_ai.request.model, gen_ai.response.model,
    gen_ai.usage.input_tokens, gen_ai.usage.output_tokens,
    gen_ai.response.finish_reason

Privacy: prompt/completion content capture is OFF by default
(read .env OTEL_CAPTURE_PROMPTS, default "0").
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# --- GenAI Semantic Convention Attribute Keys (stable subset) ---
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_RESPONSE_FINISH_REASON = "gen_ai.response.finish_reason"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_AGENT_ROLE = "agent.role"

# Span name templates
SPAN_INVOKE_AGENT = "invoke_agent.{role}"
SPAN_CHAT = "chat"
SPAN_EXECUTE_TOOL = "execute_tool.{name}"
SPAN_WORKFLOW = "workflow.{workflow_id}"

_TRACER_NAME = "ai-dev-team.genai"
_initialized = False


@dataclass(frozen=True)
class TracingConfig:
    """Configuration for the OTel tracer."""
    service_name: str = "ai-dev-team"
    otlp_endpoint: str = "http://localhost:4318"  # OTLP HTTP default
    capture_prompts: bool = False  # privacy: OFF by default (README §4.1)


def setup_tracing(config: TracingConfig | None = None) -> None:
    """Initialize global tracing. Idempotent — safe to call multiple times."""
    global _initialized
    if _initialized:
        return
    if config is None:
        config = _config_from_env()
    resource = Resource.create({"service.name": config.service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{config.otlp_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer() -> trace.Tracer:
    """Get the GenAI tracer (lazily initializes if needed)."""
    if not _initialized:
        setup_tracing()
    return trace.get_tracer(_TRACER_NAME)


def _config_from_env() -> TracingConfig:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    capture = os.getenv("OTEL_CAPTURE_PROMPTS", "0") == "1"
    return TracingConfig(otlp_endpoint=endpoint, capture_prompts=capture)