"""
Tests for Phase 4 — Observability Setup
========================================

Validates OpenTelemetry tracing and metrics initialization,
GenAI semantic convention constants, and privacy defaults.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from observability import (
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
    MetricsConfig,
    TracingConfig,
    get_tracer,
    record_agent_invocation,
    record_operation_duration,
    record_token_usage,
    record_tool_execution,
    setup_metrics,
    setup_tracing,
)


class TestTracingSetup:
    """Test OpenTelemetry tracing initialization."""

    def test_setup_tracing_idempotent(self) -> None:
        """setup_tracing() can be called multiple times safely."""
        setup_tracing()
        setup_tracing()  # Should not raise
        assert True  # If we get here, idempotency works

    def test_get_tracer_returns_same_instance(self) -> None:
        """get_tracer() returns the same tracer instance."""
        t1 = get_tracer()
        t2 = get_tracer()
        assert t1 is t2

    def test_tracing_config_defaults(self) -> None:
        """TracingConfig has correct defaults per README §4.1."""
        config = TracingConfig()
        assert config.service_name == "zyren"
        assert config.otlp_endpoint == "http://localhost:4318"
        assert config.capture_prompts is False  # privacy OFF by default

    def test_capture_prompts_off_by_default(self) -> None:
        """Prompt content capture is OFF by default (privacy)."""
        with patch.dict(os.environ, {}, clear=True):
            config = TracingConfig()
            assert config.capture_prompts is False

    def test_config_from_env_respects_endpoint(self) -> None:
        """_config_from_env() reads OTEL_EXPORTER_OTLP_ENDPOINT."""
        with patch.dict(
            os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://custom:4318"}
        ):
            from observability.tracing import _config_from_env

            config = _config_from_env()
            assert config.otlp_endpoint == "http://custom:4318"

    def test_config_from_env_respects_capture_prompts(self) -> None:
        """_config_from_env() reads OTEL_CAPTURE_PROMPTS."""
        with patch.dict(os.environ, {"OTEL_CAPTURE_PROMPTS": "1"}):
            from observability.tracing import _config_from_env

            config = _config_from_env()
            assert config.capture_prompts is True


class TestMetricsSetup:
    """Test OpenTelemetry metrics initialization."""

    def test_setup_metrics_idempotent(self) -> None:
        """setup_metrics() can be called multiple times safely."""
        setup_metrics()
        setup_metrics()  # Should not raise
        assert True

    def test_metrics_config_defaults(self) -> None:
        """MetricsConfig has correct defaults."""
        config = MetricsConfig()
        assert config.otlp_endpoint == "http://localhost:4318"
        assert config.export_interval_ms == 5000


class TestGenAIConventions:
    """Test GenAI semantic convention attribute constants."""

    def test_attribute_constants_match_spec(self) -> None:
        """Attribute keys match OpenTelemetry GenAI spec."""
        assert GEN_AI_SYSTEM == "gen_ai.system"
        assert GEN_AI_REQUEST_MODEL == "gen_ai.request.model"
        assert GEN_AI_RESPONSE_MODEL == "gen_ai.response.model"
        assert GEN_AI_USAGE_INPUT_TOKENS == "gen_ai.usage.input_tokens"
        assert GEN_AI_USAGE_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"
        assert GEN_AI_RESPONSE_FINISH_REASON == "gen_ai.response.finish_reason"
        assert GEN_AI_TOOL_NAME == "gen_ai.tool.name"
        assert GEN_AI_AGENT_ROLE == "agent.role"

    def test_span_name_templates(self) -> None:
        """Span name templates follow convention."""
        assert SPAN_INVOKE_AGENT == "invoke_agent.{role}"
        assert SPAN_CHAT == "chat"
        assert SPAN_EXECUTE_TOOL == "execute_tool.{name}"
        assert SPAN_WORKFLOW == "workflow.{workflow_id}"


class TestMetricsRecording:
    """Test metrics recording functions (smoke tests)."""

    def test_record_token_usage_no_error(self) -> None:
        """record_token_usage() executes without error."""
        setup_metrics()
        record_token_usage("gpt-4o", 100, 50)  # Should not raise

    def test_record_operation_duration_no_error(self) -> None:
        """record_operation_duration() executes without error."""
        setup_metrics()
        record_operation_duration("chat", "gpt-4o", 1.5)  # Should not raise

    def test_record_agent_invocation_no_error(self) -> None:
        """record_agent_invocation() executes without error."""
        setup_metrics()
        record_agent_invocation("coder", "pass")  # Should not raise

    def test_record_tool_execution_no_error(self) -> None:
        """record_tool_execution() executes without error."""
        setup_metrics()
        record_tool_execution("filesystem.read", "coder", True)  # Should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])