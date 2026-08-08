from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional

class SystemAction(StrEnum):
    """Actions the system can execute."""

    ADD_MODEL = "add_model"
    DISABLE_MODEL = "disable_model"
    ENABLE_MODEL = "enable_model"
    SET_DEFAULT = "set_default"
    DISABLE_PROVIDER = "disable_provider"
    QUERY_MODELS = "query_models"
    QUERY_STATUS = "query_status"
    OS_COMMAND = "os_command"
    UNKNOWN = "unknown"

class ModelTierAlias(StrEnum):
    """User-friendly tier names (Arabic/English)."""

    FRONTIER = "frontier"
    FAST = "fast"
    CRITIC = "critic"
    CODE = "code_specialized"
    LONG_CONTEXT = "long_context"
    VISION = "vision"

from gateway.model_registry import ModelTier

TIER_ALIAS_TO_TIER = {
    ModelTierAlias.FRONTIER: ModelTier.FRONTIER,
    ModelTierAlias.FAST: ModelTier.FAST,
    ModelTierAlias.CRITIC: ModelTier.CRITIC,
    ModelTierAlias.CODE: ModelTier.CODE_SPECIALIZED,
    ModelTierAlias.LONG_CONTEXT: ModelTier.LONG_CONTEXT,
    ModelTierAlias.VISION: ModelTier.VISION,
}

@dataclass(frozen=True)
class CommandResult:
    """Result of executing a system command."""
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

@dataclass(frozen=True)
class SystemCommandIntent:
    """Parsed user intent from natural language."""

    action: SystemAction
    model_id: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    tier: Optional[ModelTierAlias] = None
    task_type: Optional[str] = None
    filters: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 0.0
    language: str = "en"  # "ar" or "en"

class SystemCommandParser:
    """Parses natural language (Arabic/English) into structured SystemCommandIntent."""

    # Arabic patterns
    AR_PATTERNS = {
        SystemAction.ADD_MODEL: [
            r"أضف\s+(\S+)\s+من\s+(\S+)",  # أضف gpt-4o من Azure
            r"أضف\s+(\S+)\s+(\S+)",       # أضف gpt-4o Azure
            r"add\s+(\S+)\s+from\s+(\S+)", # English fallback
        ],
        SystemAction.SET_DEFAULT: [
            r"اجعله\s+افتراضي\s+لـ\s+(\S+)",  # اجعله افتراضي للمهام البسيطة
            r"اجعل\s+(\S+)\s+افتراضي\s+لـ\s+(\S+)",
            r"set\s+(\S+)\s+as\s+default\s+for\s+(\S+)",
        ],
        SystemAction.DISABLE_MODEL: [
            r"أوقف\s+نموذج\s+(\S+)",
            r"عطّل\s+(\S+)",
            r"disable\s+model\s+(\S+)",
        ],
        SystemAction.ENABLE_MODEL: [
            r"فعّل\s+نموذج\s+(\S+)",
            r"شغّل\s+(\S+)",
            r"enable\s+model\s+(\S+)",
        ],
        SystemAction.DISABLE_PROVIDER: [
            r"أوقف\s+كل\s+موديلات\s+(\S+)",
            r"عطّل\s+(\S+)\s+الكامل",
            r"disable\s+provider\s+(\S+)",
        ],
        SystemAction.QUERY_MODELS: [
            r"اعرض\s+الموديلات\s+(?:المتاحة\s+)?(?:لـ\s+)?(\S*)",
            r"ما\s+هي\s+الموديلات\s+(?:المتاحة\s+)?(?:لـ\s+)?(\S*)",
            r"list\s+models\s+(?:for\s+)?(\S*)",
        ],
        SystemAction.QUERY_STATUS: [
            r"حالة\s+الموديل\s+(\S+)",
            r"حالة\s+(\S+)",
        ],
    }

    # English patterns (fallback)
    EN_PATTERNS = {
        SystemAction.ADD_MODEL: [
            r"add\s+(\S+)\s+from\s+(\S+)",
            r"add\s+(\S+)\s+(\S+)",
        ],
        SystemAction.SET_DEFAULT: [
            r"set\s+(\S+)\s+as\s+default\s+for\s+(\S+)",
            r"make\s+(\S+)\s+default\s+for\s+(\S+)",
        ],
        SystemAction.DISABLE_MODEL: [
            r"disable\s+model\s+(\S+)",
            r"turn\s+off\s+(\S+)",
        ],
        SystemAction.ENABLE_MODEL: [
            r"enable\s+model\s+(\S+)",
            r"turn\s+on\s+(\S+)",
        ],
        SystemAction.DISABLE_PROVIDER: [
            r"disable\s+provider\s+(\S+)",
            r"disable\s+all\s+(\S+)",
        ],
        SystemAction.QUERY_MODELS: [
            r"list\s+models\s+(?:for\s+)?(\S*)",
            r"show\s+models\s+(?:for\s+)?(\S*)",
        ],
        SystemAction.QUERY_STATUS: [
            r"status\s+of\s+(\S+)",
            r"what(?:'s| is)\s+the\s+status\s+of\s+(\S+)",
        ],
    }

    # Tier mappings (Arabic/English)
    TIER_MAPPING = {
        # Arabic
        "بسيطة": ModelTierAlias.FAST,
        "بسيط": ModelTierAlias.FAST,
        "سريعة": ModelTierAlias.FAST,
        "سريع": ModelTierAlias.FAST,
        "معقدة": ModelTierAlias.FRONTIER,
        "معقد": ModelTierAlias.FRONTIER,
        "صعبة": ModelTierAlias.FRONTIER,
        "حرجة": ModelTierAlias.CRITIC,
        "ناقد": ModelTierAlias.CRITIC,
        "كود": ModelTierAlias.CODE,
        "برمجة": ModelTierAlias.CODE,
        "نصوص طويلة": ModelTierAlias.LONG_CONTEXT,
        "سياق طويل": ModelTierAlias.LONG_CONTEXT,
        "رؤية": ModelTierAlias.VISION,
        "بصرية": ModelTierAlias.VISION,
        # English
        "simple": ModelTierAlias.FAST,
        "fast": ModelTierAlias.FAST,
        "complex": ModelTierAlias.FRONTIER,
        "hard": ModelTierAlias.FRONTIER,
        "critical": ModelTierAlias.CRITIC,
        "critic": ModelTierAlias.CRITIC,
        "code": ModelTierAlias.CODE,
        "coding": ModelTierAlias.CODE,
        "long context": ModelTierAlias.LONG_CONTEXT,
        "vision": ModelTierAlias.VISION,
    }

    def __init__(self):
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict[SystemAction, list[re.Pattern]]:
        """Compile regex patterns for both languages."""
        compiled = {}
        for action, patterns in {**self.AR_PATTERNS, **self.EN_PATTERNS}.items():
            compiled[action] = [re.compile(p, re.IGNORECASE) for p in patterns]
        return compiled

    def parse(self, text: str) -> SystemCommandIntent:
        """Parse natural language text into SystemCommandIntent."""
        # Detect language
        language = "ar" if self._is_arabic(text) else "en"

        for action, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    groups = match.groups()
                    return self._build_intent(action, groups, text, language)

        return SystemCommandIntent(action=SystemAction.UNKNOWN, raw_text=text, confidence=0.0, language=language)

    def _build_intent(self, action: SystemAction, groups: tuple, raw: str, language: str) -> SystemCommandIntent:
        """Build intent object based on matched groups."""
        model_id = None
        provider = None
        tier = None

        if action == SystemAction.ADD_MODEL:
            model_id = groups[0]
            provider = groups[1] if len(groups) > 1 else None
        elif action == SystemAction.SET_DEFAULT:
            model_id = groups[0]
            raw_tier = groups[1].lower() if len(groups) > 1 else ""
            tier = self.TIER_MAPPING.get(raw_tier)
        elif action in [
            SystemAction.DISABLE_MODEL,
            SystemAction.ENABLE_MODEL,
            SystemAction.DISABLE_PROVIDER,
            SystemAction.QUERY_MODELS,
            SystemAction.QUERY_STATUS,
        ]:
            if groups and groups[0]:
                model_id = groups[0]
                provider = groups[0]  # Might be a provider for disable_provider

        return SystemCommandIntent(
            action=action,
            model_id=model_id,
            provider=provider,
            tier=tier,
            raw_text=raw,
            confidence=1.0,
            language=language
        )

    def _is_arabic(self, text: str) -> bool:
        """Simple check if text contains Arabic characters."""
        return any("\u0600" <= c <= "\u06FF" for c in text)
