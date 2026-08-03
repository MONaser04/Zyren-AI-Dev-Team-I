"""MockGateway — Zero-real-API gateway for testing.

Provides canned responses for all model calls without hitting any real LLM APIs.
"""

from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MockCompletionChoice:
    """Mock choice object matching litellm response structure."""
    message: dict = field(default_factory=lambda: {"role": "assistant", "content": "Mock response"})
    finish_reason: str = "stop"
    index: int = 0


@dataclass
class MockUsage:
    """Mock usage object matching litellm usage structure."""
    prompt_tokens: int = 10
    completion_tokens: int = 20
    total_tokens: int = 30


@dataclass
class MockCompletionResponse:
    """Mock completion response matching litellm structure."""
    choices: list = field(default_factory=list)
    usage: Optional[MockUsage] = None
    model: str = "mock-model"
    created: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    id: str = "mock-completion-id"
    object: str = "chat.completion"
    system_fingerprint: Optional[str] = None

    def __post_init__(self):
        if not self.choices:
            self.choices = [MockCompletionChoice()]
        if self.usage is None:
            self.usage = MockUsage()


class MockGateway:
    """Mock gateway that returns canned responses without real API calls.
    
    Features:
    - Configurable response content per model
    - Tracks calls for assertion in tests
    - Supports both text and structured output
    - Simulates latency and errors when configured
    """
    
    def __init__(
        self,
        default_response: str = "Mock response",
        error_on_model: Optional[str] = None,
        error_type: Exception = Exception,
        latency_ms: int = 0,
    ):
        self.default_response = default_response
        self.error_on_model = error_on_model
        self.error_type = error_type
        self.latency_ms = latency_ms
        self.call_history: list[dict] = []
        
        # Per-model response overrides
        self._model_responses: dict[str, str] = {}
        
        # Per-model structured responses
        self._structured_responses: dict[str, dict] = {}
    
    def set_model_response(self, model: str, response: str) -> None:
        """Set a custom response for a specific model."""
        self._model_responses[model] = response
    
    def set_structured_response(self, model: str, response: dict) -> None:
        """Set a custom structured (JSON) response for a model."""
        self._structured_responses[model] = response
    
    def complete_text(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        workflow_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Complete text with mock response."""
        self._record_call("complete_text", model, messages, temperature, max_tokens, workflow_id, kwargs)
        
        if self.error_on_model and model == self.error_on_model:
            raise self.error_type(f"Mock error for model {model}")
        
        # Check for custom response
        if model in self._model_responses:
            return self._model_responses[model]
        
        return self.default_response
    
    def complete_structured(
        self,
        model: str,
        messages: list[dict],
        response_model: type,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        workflow_id: str = "",
        **kwargs: Any,
    ) -> Any:
        """Complete with structured output."""
        self._record_call("complete_structured", model, messages, temperature, max_tokens, workflow_id, kwargs)
        
        if self.error_on_model and model == self.error_on_model:
            raise self.error_type(f"Mock error for model {model}")
        
        # Check for custom structured response
        if model in self._structured_responses:
            return response_model.model_validate(self._structured_responses[model])
        
        # Return default empty instance
        return response_model()
    
    def _record_call(
        self,
        method: str,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        workflow_id: str,
        kwargs: dict,
    ) -> None:
        """Record call for test assertions."""
        self.call_history.append({
            "method": method,
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "workflow_id": workflow_id,
            "kwargs": kwargs,
            "timestamp": datetime.now().isoformat(),
        })
    
    def get_calls_for_workflow(self, workflow_id: str) -> list[dict]:
        """Get all calls for a specific workflow."""
        return [c for c in self.call_history if c["workflow_id"] == workflow_id]
    
    def get_calls_for_model(self, model: str) -> list[dict]:
        """Get all calls for a specific model."""
        return [c for c in self.call_history if c["model"] == model]
    
    def clear_history(self) -> None:
        """Clear call history."""
        self.call_history.clear()
    
    def assert_called_with_model(self, model: str) -> bool:
        """Assert that a model was called."""
        return any(c["model"] == model for c in self.call_history)
    
    def assert_workflow_called(self, workflow_id: str) -> bool:
        """Assert that a workflow was called."""
        return any(c["workflow_id"] == workflow_id for c in self.call_history)


# Pre-configured mock gateways for common test scenarios

def create_gateway_with_responses(responses: dict[str, str]) -> MockGateway:
    """Create a gateway with custom responses per model."""
    gw = MockGateway()
    for model, response in responses.items():
        gw.set_model_response(model, response)
    return gw


def create_failing_gateway(model: str, error_type: Exception = Exception) -> MockGateway:
    """Create a gateway that fails on a specific model."""
    return MockGateway(error_on_model=model, error_type=error_type)


def create_latency_gateway(latency_ms: int = 100) -> MockGateway:
    """Create a gateway with simulated latency."""
    return MockGateway(latency_ms=latency_ms)