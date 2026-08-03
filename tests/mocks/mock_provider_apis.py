"""Mock provider APIs for zero-real-API testing.

This module provides mock implementations of all provider APIs:
- OpenAI
- Anthropic
- Google/Vertex AI
- NVIDIA NIM
- Azure OpenAI
- AWS Bedrock
- Ollama
- Together AI
- Fireworks AI
- Groq
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
from tests.mocks.mock_models import MockModelInfo, MockModelListResponse, MOCK_NVIDIA_MODEL_LIST, MOCK_OPENAI_MODEL_LIST, MOCK_ANTHROPIC_MODEL_LIST


@dataclass
class MockCompletionResponse:
    """Mock completion response matching provider format."""
    id: str
    object: str = "chat.completion"
    created: int = field(default_factory=lambda: int(datetime.now().timestamp()))
    model: str = "mock-model"
    choices: list = field(default_factory=list)
    usage: Optional[dict] = None
    system_fingerprint: Optional[str] = None


@dataclass
class MockErrorResponse:
    """Mock error response."""
    error: dict = field(default_factory=dict)


# ============================================================
# Mock Provider Base Class
# ============================================================

class MockProviderAPI:
    """Base class for all mock provider APIs."""
    
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.call_history: list[dict] = []
        self.error_on_next: Optional[Exception] = None
        self.custom_responses: dict[str, Any] = {}
    
    def record_call(self, method: str, **kwargs):
        """Record API call for test assertions."""
        self.call_history.append({
            "provider": self.provider_name,
            "method": method,
            "params": kwargs,
            "timestamp": datetime.now().isoformat(),
        })
    
    def get_calls(self) -> list[dict]:
        """Get all recorded calls."""
        return self.call_history.copy()
    
    def clear_history(self):
        """Clear call history."""
        self.call_history.clear()
    
    def set_error(self, error: Exception):
        """Set error to raise on next call."""
        self.error_on_next = error
    
    def set_response(self, model: str, response: Any):
        """Set custom response for a model."""
        self.custom_responses[model] = response


# ============================================================
# Mock OpenAI API
# ============================================================

class MockOpenAIAPI(MockProviderAPI):
    """Mock OpenAI API."""
    
    def __init__(self):
        super().__init__("openai")
        self.models_data = MOCK_OPENAI_MODEL_LIST
    
    async def list_models(self) -> MockModelListResponse:
        self.record_call("list_models")
        if self.error_on_next:
            raise self.error_on_next
        return self.models_data
    
    async def create_chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ) -> MockCompletionResponse:
        self.record_call("create_chat_completion", model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
        if self.error_on_next:
            raise self.error_on_next
        
        if model in self.custom_responses:
            return self.custom_responses[model]
        
        return MockCompletionResponse(
            id=f"mock-{model}-{datetime.now().timestamp()}",
            model=model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": f"Mock response from {model}"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )


# ============================================================
# Mock Anthropic API
# ============================================================

class MockAnthropicAPI(MockProviderAPI):
    """Mock Anthropic API."""
    
    def __init__(self):
        super().__init__("anthropic")
        self.models_data = MOCK_ANTHROPIC_MODEL_LIST
    
    async def list_models(self) -> MockModelListResponse:
        self.record_call("list_models")
        if self.error_on_next:
            raise self.error_on_next
        return self.models_data
    
    async def create_message(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        **kwargs,
    ) -> MockCompletionResponse:
        self.record_call("create_message", model=model, messages=messages, max_tokens=max_tokens, temperature=temperature)
        if self.error_on_next:
            raise self.error_on_next
        
        if model in self.custom_responses:
            return self.custom_responses[model]
        
        return MockCompletionResponse(
            id=f"mock-{model}-{datetime.now().timestamp()}",
            model=model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": f"Mock response from {model}"}, "finish_reason": "stop"}],
            usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        )


# ============================================================
# Mock Google/Vertex AI API
# ============================================================

class MockGoogleAPI(MockProviderAPI):
    """Mock Google Vertex AI API."""
    
    def __init__(self):
        super().__init__("google")
    
    async def list_models(self) -> MockModelListResponse:
        self.record_call("list_models")
        if self.error_on_next:
            raise self.error_on_next
        # Return Google models
        return MockModelListResponse(
            data=[
                MockModelInfo(id="gemini-1.5-pro", owned_by="google"),
                MockModelInfo(id="gemini-1.5-flash", owned_by="google"),
                MockModelInfo(id="gemini-1.0-pro", owned_by="google"),
            ]
        )
    
    async def generate_content(
        self,
        model: str,
        contents: list[dict],
        generation_config: Optional[dict] = None,
        **kwargs,
    ) -> MockCompletionResponse:
        self.record_call("generate_content", model=model, contents=contents, generation_config=generation_config)
        if self.error_on_next:
            raise self.error_on_next
        
        if model in self.custom_responses:
            return self.custom_responses[model]
        
        return MockCompletionResponse(
            id=f"mock-{model}-{datetime.now().timestamp()}",
            model=model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": f"Mock response from {model}"}, "finish_reason": "STOP"}],
            usage={"prompt_token_count": 10, "candidates_token_count": 20, "total_token_count": 30},
        )


# ============================================================
# Mock NVIDIA NIM API
# ============================================================

class MockNVIDIAAPI(MockProviderAPI):
    """Mock NVIDIA NIM API."""
    
    def __init__(self):
        super().__init__("nvidia_nim")
        self.models_data = MOCK_NVIDIA_MODEL_LIST
    
    async def list_models(self) -> MockModelListResponse:
        self.record_call("list_models")
        if self.error_on_next:
            raise self.error_on_next
        return self.models_data
    
    async def create_chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ) -> MockCompletionResponse:
        self.record_call("create_chat_completion", model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
        if self.error_on_next:
            raise self.error_on_next
        
        if model in self.custom_responses:
            return self.custom_responses[model]
        
        return MockCompletionResponse(
            id=f"mock-{model}-{datetime.now().timestamp()}",
            model=model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": f"Mock NVIDIA NIM response from {model}"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )


# ============================================================
# Mock Azure OpenAI API
# ============================================================

class MockAzureOpenAIAPI(MockProviderAPI):
    """Mock Azure OpenAI API."""
    
    def __init__(self):
        super().__init__("azure_openai")
        self.models_data = MockModelListResponse(
            data=[
                MockModelInfo(id="gpt-4o-eastus", owned_by="azure"),
                MockModelInfo(id="gpt-4o-mini-eastus2", owned_by="azure"),
                MockModelInfo(id="gpt-4-turbo-westus", owned_by="azure"),
            ]
        )
    
    async def list_models(self) -> MockModelListResponse:
        self.record_call("list_models")
        if self.error_on_next:
            raise self.error_on_next
        return self.models_data
    
    async def create_chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ) -> MockCompletionResponse:
        self.record_call("create_chat_completion", model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
        if self.error_on_next:
            raise self.error_on_next
        
        if model in self.custom_responses:
            return self.custom_responses[model]
        
        return MockCompletionResponse(
            id=f"mock-{model}-{datetime.now().timestamp()}",
            model=model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": f"Mock Azure response from {model}"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )


# ============================================================
# Mock AWS Bedrock API
# ============================================================

class MockAWSBedrockAPI(MockProviderAPI):
    """Mock AWS Bedrock API."""
    
    def __init__(self):
        super().__init__("aws_bedrock")
        self.models_data = MockModelListResponse(
            data=[
                MockModelInfo(id="anthropic.claude-3-sonnet-20240229-v1:0", owned_by="anthropic"),
                MockModelInfo(id="meta.llama3-1-70b-instruct-v1:0", owned_by="meta"),
                MockModelInfo(id="amazon.titan-text-premier-v1:0", owned_by="amazon"),
            ]
        )
    
    async def list_foundation_models(self) -> MockModelListResponse:
        self.record_call("list_foundation_models")
        if self.error_on_next:
            raise self.error_on_next
        return self.models_data
    
    async def invoke_model(
        self,
        model_id: str,
        body: dict,
        **kwargs,
    ) -> dict:
        self.record_call("invoke_model", model_id=model_id, body=body)
        if self.error_on_next:
            raise self.error_on_next
        
        if model_id in self.custom_responses:
            return self.custom_responses[model_id]
        
        return {
            "body": {
                "completion": f"Mock Bedrock response from {model_id}",
                "stop_reason": "end_turn",
            },
            "content_type": "application/json",
        }


# ============================================================
# Mock Ollama API
# ============================================================

class MockOllamaAPI(MockProviderAPI):
    """Mock Ollama API (local models)."""
    
    def __init__(self):
        super().__init__("ollama")
        self.models_data = MockModelListResponse(
            data=[
                MockModelInfo(id="llama3.1:8b", owned_by="ollama"),
                MockModelInfo(id="llama3.1:70b", owned_by="ollama"),
                MockModelInfo(id="codellama:34b", owned_by="ollama"),
                MockModelInfo(id="mistral:7b", owned_by="ollama"),
                MockModelInfo(id="phi3:mini", owned_by="ollama"),
            ]
        )
    
    async def list_models(self) -> MockModelListResponse:
        self.record_call("list_models")
        if self.error_on_next:
            raise self.error_on_next
        return self.models_data
    
    async def generate(
        self,
        model: str,
        prompt: str,
        stream: bool = False,
        options: Optional[dict] = None,
        **kwargs,
    ) -> dict:
        self.record_call("generate", model=model, prompt=prompt, stream=stream, options=options)
        if self.error_on_next:
            raise self.error_on_next
        
        if model in self.custom_responses:
            return self.custom_responses[model]
        
        return {
            "model": model,
            "created_at": datetime.now().isoformat(),
            "response": f"Mock Ollama response from {model}",
            "done": True,
            "context": [],
            "total_duration": 100000000,
            "load_duration": 10000000,
            "prompt_eval_count": 10,
            "prompt_eval_duration": 50000000,
            "eval_count": 20,
            "eval_duration": 40000000,
        }


# ============================================================
# Mock Together AI API
# ============================================================

class MockTogetherAPI(MockProviderAPI):
    """Mock Together AI API."""
    
    def __init__(self):
        super().__init__("together")
        self.models_data = MockModelListResponse(
            data=[
                MockModelInfo(id="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", owned_by="meta"),
                MockModelInfo(id="mistralai/Mixtral-8x7B-Instruct-v0.1", owned_by="mistralai"),
                MockModelInfo(id="Qwen/Qwen2-72B-Instruct", owned_by="qwen"),
            ]
        )
    
    async def list_models(self) -> MockModelListResponse:
        self.record_call("list_models")
        if self.error_on_next:
            raise self.error_on_next
        return self.models_data
    
    async def create_chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ) -> MockCompletionResponse:
        self.record_call("create_chat_completion", model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
        if self.error_on_next:
            raise self.error_on_next
        
        if model in self.custom_responses:
            return self.custom_responses[model]
        
        return MockCompletionResponse(
            id=f"mock-{model}-{datetime.now().timestamp()}",
            model=model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": f"Mock Together response from {model}"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )


# ============================================================
# Mock Fireworks AI API
# ============================================================

class MockFireworksAPI(MockProviderAPI):
    """Mock Fireworks AI API."""
    
    def __init__(self):
        super().__init__("fireworks")
        self.models_data = MockModelListResponse(
            data=[
                MockModelInfo(id="accounts/fireworks/models/llama-v3p1-70b-instruct", owned_by="fireworks"),
                MockModelInfo(id="accounts/fireworks/models/mixtral-8x7b-instruct", owned_by="fireworks"),
                MockModelInfo(id="accounts/fireworks/models/qwen2-72b-instruct", owned_by="fireworks"),
            ]
        )
    
    async def list_models(self) -> MockModelListResponse:
        self.record_call("list_models")
        if self.error_on_next:
            raise self.error_on_next
        return self.models_data
    
    async def create_chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs,
    ) -> MockCompletionResponse:
        self.record_call("create_chat_completion", model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
        if self.error_on_next:
            raise self.error_on_next
        
        if model in self.custom_responses:
            return self.custom_responses[model]
        
        return MockCompletionResponse(
            id=f"mock-{model}-{datetime.now().timestamp()}",
            model=model,
            choices=[{"index": 0, "message": {"role": "assistant", "content": f"Mock Fireworks response from {model}"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )


# ============================================================
# Mock Groq API
# ==========================================================