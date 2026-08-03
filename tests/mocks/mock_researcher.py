"""Mock Professional Researcher for testing."""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


@dataclass
class SourceCitation:
    """Mock source citation."""
    source_type: str
    url: str
    provider: str
    accessed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    field_mapping: dict = field(default_factory=dict)
    confidence: float = 1.0
    raw_snippet: str = ""


@dataclass
class ResearchResult:
    """Mock research result."""
    model_spec: Optional[Any] = None
    sources: list = field(default_factory=list)
    confidence: float = 1.0
    warnings: list = field(default_factory=list)
    raw_evidence: dict = field(default_factory=dict)


class MockProfessionalResearcher:
    """Mock professional researcher that returns canned research results.
    
    Features:
    - Returns verified research results without real API calls
    - Configurable per-model research results
    - Tracks research queries for test assertions
    """
    
    def __init__(self):
        self.research_history: list[dict] = []
        self.custom_results: dict[str, ResearchResult] = {}
        self.default_confidence = 1.0
        self.default_sources = [
            SourceCitation(
                source_type="api",
                url="https://api.example.com/models/test-model",
                provider="nvidia_nim",
                field_mapping={"context_window": "max_context_length"},
                confidence=1.0,
                raw_snippet="max_context_length: 128000",
            ),
        ]
    
    async def research_model_spec(self, provider: str, model_id: str) -> ResearchResult:
        """Research a model specification."""
        self.research_history.append({
            "method": "research_model_spec",
            "provider": provider,
            "model_id": model_id,
            "timestamp": datetime.now().isoformat(),
        })
        
        key = f"{provider}/{model_id}"
        if key in self.custom_results:
            return self.custom_results[key]
        
        # Return default successful research result
        return ResearchResult(
            model_spec=None,  # Would be populated with actual ModelSpec
            sources=self.default_sources,
            confidence=self.default_confidence,
            warnings=[],
            raw_evidence={"provider": provider, "model_id": model_id},
        )
    
    async def research_provider_pricing(self, provider: str) -> ResearchResult:
        """Research provider pricing."""
        self.research_history.append({
            "method": "research_provider_pricing",
            "provider": provider,
            "timestamp": datetime.now().isoformat(),
        })
        
        return ResearchResult(
            model_spec=None,
            sources=[
                SourceCitation(
                    source_type="pricing_page",
                    url=f"https://{provider}.com/pricing",
                    provider=provider,
                    field_mapping={"input_per_1m": "input_price", "output_per_1m": "output_price"},
                    confidence=0.9,
                    raw_snippet="input: $0.00, output: $0.00",
                ),
            ],
            confidence=0.9,
            warnings=[],
            raw_evidence={"provider": provider},
        )
    
    async def research_provider_capabilities(self, provider: str) -> ResearchResult:
        """Research provider capabilities."""
        self.research_history.append({
            "method": "research_provider_capabilities",
            "provider": provider,
            "timestamp": datetime.now().isoformat(),
        })
        
        return ResearchResult(
            model_spec=None,
            sources=[
                SourceCitation(
                    source_type="official_docs",
                    url=f"https://{provider}.com/docs",
                    provider=provider,
                    field_mapping={},
                    confidence=0.85,
                    raw_snippet="Supports function calling, vision, structured output",
                ),
            ],
            confidence=0.85,
            warnings=[],
            raw_evidence={"provider": provider},
        )
    
    async def cross_validate(self, model_id: str, sources: list) -> Any:
        """Cross-validate model information."""
        self.research_history.append({
            "method": "cross_validate",
            "model_id": model_id,
            "timestamp": datetime.now().isoformat(),
        })
        
        @dataclass
        class ValidationResult:
            passed: bool = True
            conflicts: list = field(default_factory=list)
            confidence: float = 1.0
        
        return ValidationResult(passed=True, conflicts=[], confidence=1.0)
    
    async def fetch_official_docs(self, url: str) -> Any:
        """Fetch official documentation."""
        self.research_history.append({
            "method": "fetch_official_docs",
            "url": url,
            "timestamp": datetime.now().isoformat(),
        })
        
        @dataclass
        class ParsedContent:
            content: str = "Mock parsed documentation content"
            metadata: dict = field(default_factory=dict)
        
        return ParsedContent(
            content=f"Mock documentation from {url}",
            metadata={"source": url},
        )
    
    def set_custom_result(self, provider: str, model_id: str, result: ResearchResult):
        """Set a custom research result for a specific model."""
        self.custom_results[f"{provider}/{model_id}"] = result
    
    def get_research_history(self) -> list[dict]:
        """Get all research queries."""
        return self.research_history.copy()
    
    def clear_history(self):
        """Clear research history."""
        self.research_history.clear()