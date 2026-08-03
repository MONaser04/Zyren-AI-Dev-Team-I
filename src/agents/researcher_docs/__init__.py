"""Official Documentation Fetchers for Professional Researcher Agent

8 Provider-specific fetchers:
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

from .base import (
    OfficialDocsFetcher,
    FetchResult,
    ModelSummary,
    ModelDetail,
    PricingTable,
    RateLimitInfo,
    ProviderName,
)

from .openai_docs import OpenAIFetcher, create_openai_fetcher
from .anthropic_docs import AnthropicFetcher, create_anthropic_fetcher
from .google_docs import GoogleFetcher, create_google_fetcher
from .nvidia_docs import NvidiaNimFetcher, create_nvidia_nim_fetcher
from .azure_docs import AzureOpenAIFetcher, create_azure_fetcher
from .aws_docs import AWSBedrockFetcher, create_aws_fetcher
from .ollama_docs import OllamaFetcher, create_ollama_fetcher
from .together_docs import TogetherAIFetcher, create_together_fetcher
from .fireworks_docs import FireworksAIFetcher, create_fireworks_fetcher
from .groq_docs import GroqFetcher, create_groq_fetcher

__all__ = [
    # Base
    "OfficialDocsFetcher",
    "FetchResult",
    "ModelSummary",
    "ModelDetail",
    "PricingTable",
    "RateLimitInfo",
    "ProviderName",
    # Fetchers
    "OpenAIFetcher",
    "AnthropicFetcher",
    "GoogleFetcher",
    "NvidiaNimFetcher",
    "AzureOpenAIFetcher",
    "AWSBedrockFetcher",
    "OllamaFetcher",
    "TogetherAIFetcher",
    "FireworksAIFetcher",
    "GroqFetcher",
    # Factory functions
    "create_openai_fetcher",
    "create_anthropic_fetcher",
    "create_google_fetcher",
    "create_nvidia_nim_fetcher",
    "create_azure_fetcher",
    "create_aws_fetcher",
    "create_ollama_fetcher",
    "create_together_fetcher",
    "create_fireworks_fetcher",
    "create_groq_fetcher",
]

# Provider fetcher registry
FETCHER_REGISTRY = {
    ProviderName.OPENAI: OpenAIFetcher,
    ProviderName.ANTHROPIC: AnthropicFetcher,
    ProviderName.GOOGLE: GoogleFetcher,
    ProviderName.NVIDIA_NIM: NvidiaNimFetcher,
    ProviderName.AZURE_OPENAI: AzureOpenAIFetcher,
    ProviderName.AWS_BEDROCK: AWSBedrockFetcher,
    ProviderName.OLLAMA: OllamaFetcher,
    ProviderName.TOGETHER: TogetherAIFetcher,
    ProviderName.FIREWORKS: FireworksAIFetcher,
    ProviderName.GROQ: GroqFetcher,
}

FACTORY_REGISTRY = {
    ProviderName.OPENAI: create_openai_fetcher,
    ProviderName.ANTHROPIC: create_anthropic_fetcher,
    ProviderName.GOOGLE: create_google_fetcher,
    ProviderName.NVIDIA_NIM: create_nvidia_nim_fetcher,
    ProviderName.AZURE_OPENAI: create_azure_fetcher,
    ProviderName.AWS_BEDROCK: create_aws_fetcher,
    ProviderName.OLLAMA: create_ollama_fetcher,
    ProviderName.TOGETHER: create_together_fetcher,
    ProviderName.FIREWORKS: create_fireworks_fetcher,
    ProviderName.GROQ: create_groq_fetcher,
}


def get_fetcher_class(provider: ProviderName) -> type[OfficialDocsFetcher]:
    """Get fetcher class for a provider"""
    if provider not in FETCHER_REGISTRY:
        raise ValueError(f"No fetcher registered for provider: {provider}")
    return FETCHER_REGISTRY[provider]


def create_fetcher(provider: ProviderName, **kwargs) -> OfficialDocsFetcher:
    """Create fetcher instance for a provider"""
    if provider not in FACTORY_REGISTRY:
        raise ValueError(f"No factory registered for provider: {provider}")
    return FACTORY_REGISTRY[provider](**kwargs)


def get_all_fetchers(**kwargs) -> dict[ProviderName, OfficialDocsFetcher]:
    """Create all registered fetchers"""
    return {provider: factory(**kwargs) for provider, factory in FACTORY_REGISTRY.items()}