"""
Observability — Instrumentation Decorators (Phase 4)
=====================================================

Spans emitted (README §4.1):
  invoke_agent.<role>  — wraps BaseAgent.run
  chat                 — wraps LLMClient.complete_text / complete_structured
  execute_tool.<name>  — wraps ToolExecutor.execute

Each span carries gen_ai.* attributes; metrics recorded on exit.
Prompt-content capture is opt-in (privacy off by default).
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from observability.metrics import (
    record_agent_invocation,
    record_operation_duration,
    record_token_usage,
    record_tool_execution,
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
    get_tracer,
)

F = TypeVar("F", bound=Callable[..., Any])


def trace_agent_invocation(agent_role: str) -> Callable[[F], F]:
    """Decorator factory: wrap an agent's run() with an invoke_agent span."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            span_name = SPAN_INVOKE_AGENT.format(role=agent_role)
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute(GEN_AI_AGENT_ROLE, agent_role)
                span.set_attribute(GEN_AI_SYSTEM, "zyren-ai-dev-team")
                # workflow_id and iteration pulled from kwargs if present
                wf = kwargs.get("workflow_id") or (
                    getattr(args[0], "workflow_id", "") if args else ""
                )
                if wf:
                    span.set_attribute("workflow.id", str(wf))
                t0 = time.perf_counter()
                try:
                    result = fn(*args, **kwargs)
                    span.set_attribute("agent.verdict", _extract_verdict(result))
                    record_agent_invocation(agent_role, _extract_verdict(result))
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_attribute("error", True)
                    record_agent_invocation(agent_role, "error")
                    raise
                finally:
                    span.set_attribute("duration_s", time.perf_counter() - t0)

        return wrapper  # type: ignore[return-value]

    return decorator


def trace_chat(model_or_fn: Any = "default") -> Any:
    """Decorator factory or decorator: wrap an LLM call with a chat span + token metrics.
    Supports both @trace_chat and @trace_chat("model_name") on both sync and async functions.
    """
    model_name = "default"
    target_fn = None

    if callable(model_or_fn):
        target_fn = model_or_fn
    elif isinstance(model_or_fn, str):
        model_name = model_or_fn

    def decorator(fn: F) -> F:
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = get_tracer()
                with tracer.start_as_current_span(SPAN_CHAT) as span:
                    span.set_attribute(GEN_AI_REQUEST_MODEL, model_name)
                    span.set_attribute(GEN_AI_SYSTEM, "litellm")
                    t0 = time.perf_counter()
                    try:
                        result = await fn(*args, **kwargs)
                        usage = getattr(result, "usage", None)
                        if usage:
                            in_tok = getattr(usage, "prompt_tokens", 0) or 0
                            out_tok = getattr(usage, "completion_tokens", 0) or 0
                            span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, in_tok)
                            span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, out_tok)
                            record_token_usage(model_name, in_tok, out_tok)
                        finish = getattr(result, "finish_reason", None)
                        if finish:
                            span.set_attribute(GEN_AI_RESPONSE_FINISH_REASON, finish)
                        resp_model = getattr(result, "model", model_name)
                        if resp_model:
                            span.set_attribute(GEN_AI_RESPONSE_MODEL, resp_model)
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_attribute("error", True)
                        record_operation_duration("chat", model_name, time.perf_counter() - t0)
                        raise
                    finally:
                        record_operation_duration("chat", model_name, time.perf_counter() - t0)

            return async_wrapper  # type: ignore[return-value]
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                tracer = get_tracer()
                with tracer.start_as_current_span(SPAN_CHAT) as span:
                    span.set_attribute(GEN_AI_REQUEST_MODEL, model_name)
                    span.set_attribute(GEN_AI_SYSTEM, "litellm")
                    t0 = time.perf_counter()
                    try:
                        result = fn(*args, **kwargs)
                        usage = getattr(result, "usage", None)
                        if usage:
                            in_tok = getattr(usage, "prompt_tokens", 0) or 0
                            out_tok = getattr(usage, "completion_tokens", 0) or 0
                            span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, in_tok)
                            span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, out_tok)
                            record_token_usage(model_name, in_tok, out_tok)
                        finish = getattr(result, "finish_reason", None)
                        if finish:
                            span.set_attribute(GEN_AI_RESPONSE_FINISH_REASON, finish)
                        resp_model = getattr(result, "model", model_name)
                        if resp_model:
                            span.set_attribute(GEN_AI_RESPONSE_MODEL, resp_model)
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_attribute("error", True)
                        record_operation_duration("chat", model_name, time.perf_counter() - t0)
                        raise
                    finally:
                        record_operation_duration("chat", model_name, time.perf_counter() - t0)

            return sync_wrapper  # type: ignore[return-value]

    if target_fn is not None:
        return decorator(target_fn)
    return decorator


def trace_tool_execution(tool_name: str, role: str) -> Callable[[F], F]:
    """Decorator factory: wrap a tool execution with an execute_tool span."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            span_name = SPAN_EXECUTE_TOOL.format(name=tool_name)
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute(GEN_AI_TOOL_NAME, tool_name)
                span.set_attribute(GEN_AI_AGENT_ROLE, role)
                try:
                    result = fn(*args, **kwargs)
                    span.set_attribute("tool.success", True)
                    record_tool_execution(tool_name, role, True)
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_attribute("error", True)
                    span.set_attribute("tool.success", False)
                    record_tool_execution(tool_name, role, False)
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator


def _extract_verdict(result: Any) -> str:
    """Try to pull a verdict string from an agent result (best-effort)."""
    for attr in ("verdict", "decision", "status", "outcome"):
        val = getattr(result, attr, None)
        if val is not None:
            return str(getattr(val, "value", val))
    return "unknown"