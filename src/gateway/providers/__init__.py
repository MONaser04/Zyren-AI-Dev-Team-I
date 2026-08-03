"""
Provider Adapters Package
=========================
Exports all provider adapters for the universal model registry.
"""

from gateway.providers.nvidia_nim import NVIDIAProviderAdapter, create_nvidia_nim_adapter
from gateway.providers.openai import OpenAIProviderAdapter, create_openai_adapter
from gateway.providers.anthropic import AnthropicProviderAdapter, create_anthropic_adapter
from gateway.providers.google import GoogleProviderAdapter, create_google_adapter
from gateway.providers.azure import AzureOpenAIProviderAdapter, create_azure_adapter
from gateway.providers.aws_bedrock import AWSBedrockProviderAdapter, create_aws_bedrock_adapter
from gateway.providers.ollama import OllamaProviderAdapter, create_ollama_adapter
from gateway.providers.groq import GroqProviderAdapter, create_groq_adapter
from gateway.providers.together import TogetherProviderAdapter, create_together_adapter
from gateway.providers.fireworks import FireworksProviderAdapter, create_fireworks_adapter

__all__ = [
    "NVIDIAProviderAdapter",
    "create_nvidia_nim_adapter",
    "OpenAIProviderAdapter",
    "create_openai_adapter",
    "AnthropicProviderAdapter",
    "create_anthropic_adapter",
    "GoogleProviderAdapter",
    "create_google_adapter",
    "AzureOpenAIProviderAdapter",
    "create_azure_adapter",
    "AWSBedrockProviderAdapter",
    "create_aws_bedrock_adapter",
    "OllamaProviderAdapter",
    "create_ollama_adapter",
    "GroqProviderAdapter",
    "create_groq_adapter",
    "TogetherProviderAdapter",
    "create_together_adapter",
    "FireworksProviderAdapter",
    "create_fireworks_adapter",
]