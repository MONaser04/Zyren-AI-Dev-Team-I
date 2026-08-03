"""
LiaisonAgent -- Part 1: Imports and Core Types
==============================================
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Optional

from agents.base import BaseAgent
from gateway.model_registry import AutoModelRegistry, ModelSpec, ModelTier, ModelStatus
from gateway.smart_gateway import SmartGateway
from resilience import CircuitBreakerRegistry
from contracts.intent import ParsedIntent, UserIntentCategory

logger = logging.getLogger(__name__)

# ============================================================
# Enums
# ============================================================

class LiaisonAction(StrEnum):
    """Actions the Liaison can execute."""

    ADD_MODEL = "add_model"
    DISABLE_MODEL = "disable_model"
    ENABLE_MODEL = "enable_model"
    SET_DEFAULT = "set_default"
    DISABLE_PROVIDER = "disable_provider"
    QUERY_MODELS = "query_models"
    QUERY_STATUS = "query_status"
    UNKNOWN = "unknown"

class ModelTierAlias(StrEnum):
    """User-friendly tier names (Arabic/English)."""

    FRONTIER = "frontier"
    FAST = "fast"
    CRITIC = "critic"
    CODE = "code_specialized"
    LONG_CONTEXT = "long_context"
    VISION = "vision"

# ============================================================
# Data Structures
# ============================================================

@dataclass(frozen=True)
class UserIntent:
    """Parsed user intent from natural language."""

    action: LiaisonAction
    model_id: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    tier: Optional[ModelTierAlias] = None
    task_type: Optional[str] = None
    filters: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 0.0
    language: str = "en"  # "ar" or "en"

@dataclass(frozen=True)
class CommandResult:
    """Result of executing a liaison command."""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

# ============================================================
# Intent Parser (Arabic/English)
# ============================================================

class IntentParser:
    """Parses natural language (Arabic/English) into structured UserIntent."""

    # Arabic patterns
    AR_PATTERNS = {
        LiaisonAction.ADD_MODEL: [
            r"أضف\s+(\S+)\s+من\s+(\S+)",  # أضف gpt-4o من Azure
            r"أضف\s+(\S+)\s+(\S+)",       # أضف gpt-4o Azure
            r"add\s+(\S+)\s+from\s+(\S+)", # English fallback
        ],
        LiaisonAction.SET_DEFAULT: [
            r"اجعله\s+افتراضي\s+لـ\s+(\S+)",  # اجعله افتراضي للمهام البسيطة
            r"اجعل\s+(\S+)\s+افتراضي\s+لـ\s+(\S+)",
            r"set\s+(\S+)\s+as\s+default\s+for\s+(\S+)",
        ],
        LiaisonAction.DISABLE_MODEL: [
            r"أوقف\s+نموذج\s+(\S+)",
            r"عطّل\s+(\S+)",
            r"disable\s+model\s+(\S+)",
        ],
        LiaisonAction.ENABLE_MODEL: [
            r"فعّل\s+نموذج\s+(\S+)",
            r"شغّل\s+(\S+)",
            r"enable\s+model\s+(\S+)",
        ],
        LiaisonAction.DISABLE_PROVIDER: [
            r"أوقف\s+كل\s+موديلات\s+(\S+)",
            r"عطّل\s+(\S+)\s+الكامل",
            r"disable\s+provider\s+(\S+)",
        ],
        LiaisonAction.QUERY_MODELS: [
            r"اعرض\s+الموديلات\s+(?:المتاحة\s+)?(?:لـ\s+)?(\S*)",
            r"ما\s+هي\s+الموديلات\s+(?:المتاحة\s+)?(?:لـ\s+)?(\S*)",
            r"list\s+models\s+(?:for\s+)?(\S*)",
        ],
        LiaisonAction.QUERY_STATUS: [
            r"ما\s+حالة\s+(\S+)",
            r"status\s+of\s+(\S+)",
        ],
    }

    # English patterns (fallback)
    EN_PATTERNS = {
        LiaisonAction.ADD_MODEL: [
            r"add\s+(\S+)\s+from\s+(\S+)",
            r"add\s+(\S+)\s+(\S+)",
        ],
        LiaisonAction.SET_DEFAULT: [
            r"set\s+(\S+)\s+as\s+default\s+for\s+(\S+)",
            r"make\s+(\S+)\s+default\s+for\s+(\S+)",
        ],
        LiaisonAction.DISABLE_MODEL: [
            r"disable\s+model\s+(\S+)",
            r"turn\s+off\s+(\S+)",
        ],
        LiaisonAction.ENABLE_MODEL: [
            r"enable\s+model\s+(\S+)",
            r"turn\s+on\s+(\S+)",
        ],
        LiaisonAction.DISABLE_PROVIDER: [
            r"disable\s+provider\s+(\S+)",
            r"disable\s+all\s+(\S+)",
        ],
        LiaisonAction.QUERY_MODELS: [
            r"list\s+models\s+(?:for\s+)?(\S*)",
            r"show\s+models\s+(?:for\s+)?(\S*)",
        ],
        LiaisonAction.QUERY_STATUS: [
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

    def _compile_patterns(self) -> dict[LiaisonAction, list[re.Pattern]]:
        """Compile regex patterns for both languages."""
        compiled = {}
        for action, patterns in {**self.AR_PATTERNS, **self.EN_PATTERNS}.items():
            compiled[action] = [re.compile(p, re.IGNORECASE) for p in patterns]
        return compiled

    def parse(self, text: str) -> UserIntent:
        """Parse natural language text into UserIntent."""
        # Detect language
        language = "ar" if self._is_arabic(text) else "en"

        # Try each action pattern
        best_match: Optional[UserIntent] = None
        best_confidence = 0.0

        for action, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    confidence = 0.9 if language == "ar" else 0.85
                    intent = self._extract_intent(action, match, text, language, confidence)
                    if intent and intent.confidence > best_confidence:
                        best_match = intent
                        best_confidence = intent.confidence

        if best_match:
            return best_match

        return UserIntent(
            action=LiaisonAction.UNKNOWN,
            raw_text=text,
            confidence=0.0,
            language=language,
        )

    def _is_arabic(self, text: str) -> bool:
        """Detect if text is primarily Arabic."""
        arabic_chars = sum(1 for c in text if "\u0600" <= c <= "\u06FF")
        total_chars = sum(1 for c in text if c.isalpha())
        return arabic_chars > total_chars * 0.3 if total_chars > 0 else False

    def _extract_intent(
        self,
        action: LiaisonAction,
        match: re.Match,
        text: str,
        language: str,
        base_confidence: float,
    ) -> Optional[UserIntent]:
        """Extract structured intent from regex match."""
        groups = match.groups()

        if action == LiaisonAction.ADD_MODEL:
            if len(groups) >= 2:
                model_id = groups[0].strip()
                provider = groups[1].strip()
                region = self._extract_region(text)
                tier = self._extract_tier(text)
                return UserIntent(
                    action=action,
                    model_id=model_id,
                    provider=provider,
                    region=region,
                    tier=tier,
                    raw_text=text,
                    confidence=base_confidence,
                    language=language,
                )

        elif action == LiaisonAction.SET_DEFAULT:
            if len(groups) >= 2:
                model_id = groups[0].strip()
                tier_str = groups[1].strip()
                tier = self._map_tier(tier_str)
                return UserIntent(
                    action=action,
                    model_id=model_id,
                    tier=tier,
                    raw_text=text,
                    confidence=base_confidence,
                    language=language,
                )
            elif len(groups) == 1:
                tier = self._map_tier(groups[0].strip())
                return UserIntent(
                    action=action,
                    tier=tier,
                    raw_text=text,
                    confidence=base_confidence * 0.8,
                    language=language,
                )

        elif action == LiaisonAction.DISABLE_MODEL:
            model_id = groups[0].strip() if groups else None
            return UserIntent(
                action=action,
                model_id=model_id,
                raw_text=text,
                confidence=base_confidence,
                language=language,
            )

        elif action == LiaisonAction.ENABLE_MODEL:
            model_id = groups[0].strip() if groups else None
            return UserIntent(
                action=action,
                model_id=model_id,
                raw_text=text,
                confidence=base_confidence,
                language=language,
            )

        elif action == LiaisonAction.DISABLE_PROVIDER:
            provider = groups[0].strip() if groups else None
            return UserIntent(
                action=action,
                provider=provider,
                raw_text=text,
                confidence=base_confidence,
                language=language,
            )

        elif action == LiaisonAction.QUERY_MODELS:
            task_type = groups[0].strip() if groups and groups[0] else None
            return UserIntent(
                action=action,
                task_type=task_type,
                raw_text=text,
                confidence=base_confidence,
                language=language,
            )

        elif action == LiaisonAction.QUERY_STATUS:
            target = groups[0].strip() if groups else None
            return UserIntent(
                action=action,
                model_id=target,
                provider=target,
                raw_text=text,
                confidence=base_confidence,
                language=language,
            )

        return None

    def _extract_region(self, text: str) -> Optional[str]:
        """Extract region from text (e.g., eastus2, us-east-1)."""
        region_patterns = [
            r"(eastus2|westus2|centralus|northeurope|westeurope|southeastasia|eastasia)",
            r"(us-east-1|us-west-2|eu-west-1|eu-central-1|ap-southeast-1|ap-northeast-1)",
        ]
        for pattern in region_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).lower()
        return None

    def _extract_tier(self, text: str) -> Optional[ModelTierAlias]:
        """Extract tier from text."""
        for keyword, tier in self.TIER_MAPPING.items():
            if keyword in text.lower():
                return tier
        return None

    def _map_tier(self, tier_str: str) -> Optional[ModelTierAlias]:
        """Map tier string to ModelTierAlias."""
        tier_lower = tier_str.lower().strip()
        for keyword, tier in self.TIER_MAPPING.items():
            if keyword in tier_lower:
                return tier
        # Direct match
        try:
            return ModelTierAlias(tier_lower)
        except ValueError:
            return None

# Tier mapping from user-friendly to internal
TIER_ALIAS_TO_TIER = {
    ModelTierAlias.FRONTIER: ModelTier.FRONTIER,
    ModelTierAlias.FAST: ModelTier.FAST,
    ModelTierAlias.CRITIC: ModelTier.CRITIC,
    ModelTierAlias.CODE: ModelTier.CODE_SPECIALIZED,
    ModelTierAlias.LONG_CONTEXT: ModelTier.LONG_CONTEXT,
    ModelTierAlias.VISION: ModelTier.VISION,
}

class CommandExecutor:

    def __init__(
        self,
        registry: AutoModelRegistry,
        gateway: SmartGateway,
        circuit_breakers: CircuitBreakerRegistry,
        researcher_agent: Any = None,  # ProfessionalResearcherAgent
    ):
        self._registry = registry
        self._gateway = gateway
        self._circuit_breakers = circuit_breakers
        self._researcher = researcher_agent

    async def execute(self, intent: UserIntent) -> CommandResult:
        logger.info("Executing command: %s (confidence=%.2f)", intent.action, intent.confidence)

        if intent.confidence < 0.7:
            return CommandResult(
                success=False,
                message=f"Low confidence ({intent.confidence:.0%}). Please rephrase.",
                error="LOW_CONFIDENCE",
            )

        try:
            match intent.action:
                case "add_model":
                    return await self._add_model(intent)
                case "disable_model":
                    return await self._disable_model(intent)
                case "enable_model":
                    return await self._enable_model(intent)
                case "set_default":
                    return await self._set_default(intent)
                case "disable_provider":
                    return await self._disable_provider(intent)
                case "query_models":
                    return await self._query_models(intent)
                case "query_status":
                    return await self._query_status(intent)
                case _:
                    return CommandResult(
                        success=False,
                        message="لم أفهم الأمر. حاول: 'أضف gpt-4o من Azure' أو 'اعرض الموديلات للمهام البسيطة'",
                        error="UNKNOWN_ACTION",
                    )
        except Exception as e:
            logger.exception("Command execution failed")
            return CommandResult(
                success=False,
                message=f"خطأ في التنفيذ: {e}",
                error=str(e),
            )

    async def _add_model(self, intent: UserIntent) -> CommandResult:
        if not intent.model_id or not intent.provider:
            return CommandResult(
                success=False,
                message="يجب تحديد الموديل والمزود. مثال: 'أضف gpt-4o من Azure eastus2'",
                error="MISSING_PARAMS",
            )

        # Build full model ID
        full_model_id = f"{intent.provider}/{intent.model_id}"
        if intent.region:
            full_model_id = f"{intent.provider}/{intent.region}/{intent.model_id}"

        logger.info("Adding model: %s (provider=%s, region=%s)", full_model_id, intent.provider, intent.region)

        # 1. Researcher validates specs from official sources
        if self._researcher:
            try:
                spec = await self._researcher.research_model_spec(
                    provider=intent.provider,
                    model_id=full_model_id,
                )
                if not spec or spec.confidence_score < 0.7:
                    return CommandResult(
                        success=False,
                        message=f"تعذر التحقق من مواصفات {full_model_id} من المصادر الرسمية",
                        error="VALIDATION_FAILED",
                    )
                logger.info("Researcher validated: %s (confidence=%.2f)", full_model_id, spec.confidence_score)
            except Exception as e:
                logger.warning("Researcher validation failed: %s", e)
                # Continue with manual spec if researcher fails

        # 2. Registry adds/updates the model
        tier = TIER_ALIAS_TO_TIER.get(intent.tier, ModelTier.FAST) if intent.tier else ModelTier.FAST
        try:
            spec = ModelSpec(
                model_id=full_model_id,
                provider=intent.provider,
                display_name=intent.model_id,
                tier=tier,
                capabilities=self._infer_capabilities(intent.model_id),
                status=ModelStatus.ACTIVE,
            )
            self._registry.register_provider_model(spec)
        except Exception as e:
            logger.exception("Registry add failed")
            return CommandResult(
                success=False,
                message=f"فشل إضافة الموديل للسجل: {e}",
                error="REGISTRY_ERROR",
            )

        # 3. Gateway manual override for tier
        if intent.tier:
            internal_tier = TIER_ALIAS_TO_TIER.get(intent.tier)
            if internal_tier:
                self._gateway._router.set_manual_override(internal_tier, full_model_id)

        # 4. Update litellm.yaml config (async write)
        await self._update_litellm_config(full_model_id, intent.provider, intent.region)

        return CommandResult(
            success=True,
            message=f"✅ تم إضافة {full_model_id} كموديل {'افتراضي للـ ' + intent.tier.value if intent.tier else ''}",
            data={"model_id": full_model_id, "provider": intent.provider, "tier": intent.tier.value if intent.tier else None},
        )

    async def _disable_model(self, intent: UserIntent) -> CommandResult:
        model_id = intent.model_id or intent.provider
        if not model_id:
            return CommandResult(
                success=False,
                message="حدد الموديل المراد إيقافه. مثال: 'أوقف نموذج gpt-4o'",
                error="MISSING_MODEL",
            )

        # Find in registry
        matches = self._registry.get_by_provider(model_id) if "/" not in model_id else [self._registry.get(model_id)]
        matches = [m for m in matches if m and model_id in m.model_id]

        if not matches:
            return CommandResult(
                success=False,
                message=f"الموديل {model_id} غير موجود في السجل",
                error="MODEL_NOT_FOUND",
            )

        for model in matches:
            model.status = ModelStatus.DISABLED
            # Open circuit breaker
            breaker = self._circuit_breakers.get(model.model_id)
            if breaker:
                breaker.force_open()

        return CommandResult(
            success=True,
            message=f"✅ تم تعطيل {len(matches)} موديل: {', '.join(m.model_id for m in matches)}",
            data={"disabled": [m.model_id for m in matches]},
        )

    async def _enable_model(self, intent: UserIntent) -> CommandResult:
        model_id = intent.model_id or intent.provider
        if not model_id:
            return CommandResult(
                success=False,
                message="حدد الموديل المراد تفعيله",
                error="MISSING_MODEL",
            )

        matches = self._registry.get_by_provider(model_id) if "/" not in model_id else [self._registry.get(model_id)]
        matches = [m for m in matches if m and model_id in m.model_id]

        if not matches:
            return CommandResult(
                success=False,
                message=f"الموديل {model_id} غير موجود",
                error="MODEL_NOT_FOUND",
            )

        for model in matches:
            model.status = ModelStatus.ACTIVE
            breaker = self._circuit_breakers.get(model.model_id)
            if breaker:
                breaker.force_close()

        return CommandResult(
            success=True,
            message=f"✅ تم تفعيل {len(matches)} موديل",
            data={"enabled": [m.model_id for m in matches]},
        )

    async def _set_default(self, intent: UserIntent) -> CommandResult:
        if not intent.tier:
            return CommandResult(
                success=False,
                message="حدد نوع المهمة. مثال: 'اجعل gpt-4o افتراضي للمهام البسيطة'",
                error="MISSING_TIER",
            )

        if not intent.model_id:
            return CommandResult(
                success=False,
                message="حدد الموديل. مثال: 'اجعل gpt-4o افتراضي للمهام البسيطة'",
                error="MISSING_MODEL",
            )

        internal_tier = TIER_ALIAS_TO_TIER.get(intent.tier)
        if not internal_tier:
            return CommandResult(
                success=False,
                message=f"نوع مهمة غير معروف: {intent.tier.value}",
                error="INVALID_TIER",
            )

        full_model_id = intent.model_id
        if intent.provider:
            full_model_id = f"{intent.provider}/{intent.model_id}"
        if intent.region:
            full_model_id = f"{intent.provider}/{intent.region}/{intent.model_id}"

        # Verify model exists
        spec = self._registry.get(full_model_id)
        if not spec:
            return CommandResult(
                success=False,
                message=f"الموديل {full_model_id} غير مسجل. أضفه أولاً.",
                error="MODEL_NOT_REGISTERED",
            )

        self._gateway._router.set_manual_override(internal_tier, full_model_id)
        return CommandResult(
            success=True,
            message=f"✅ تم تعيين {full_model_id} كافتراضي للمهام من نوع {intent.tier.value}",
            data={"model_id": full_model_id, "tier": intent.tier.value},
        )

    async def _disable_provider(self, intent: UserIntent) -> CommandResult:
        provider = intent.provider
        if not provider:
            return CommandResult(
                success=False,
                message="حدد المزود. مثال: 'أوقف كل موديلات OpenAI'",
                error="MISSING_PROVIDER",
            )

        models = self._registry.get_by_provider(provider)
        if not models:
            return CommandResult(
                success=False,
                message=f"لا توجد موديلات مسجلة للمزود {provider}",
                error="PROVIDER_EMPTY",
            )

        for model in models:
            model.status = ModelStatus.DISABLED
            breaker = self._circuit_breakers.get(model.model_id)
            if breaker:
                breaker.force_open()

        return CommandResult(
            success=True,
            message=f"✅ تم تعطيل {len(models)} موديل من {provider}",
            data={"provider": provider, "disabled_count": len(models)},
        )

    async def _query_models(self, intent: UserIntent) -> CommandResult:
        task_type = intent.task_type

        if task_type:
            tier = self._map_task_type(task_type)
            if tier:
                models = self._registry.get_by_tier(tier)
            else:
                models = self._registry.list_all()
        else:
            models = self._registry.list_all()

        # Filter active only
        active_models = [m for m in models if m.status == ModelStatus.ACTIVE]

        data = {
            "total": len(active_models),
            "models": [
                {
                    "id": m.model_id,
                    "provider": m.provider,
                    "tier": m.tier.value,
                    "capabilities": m.capabilities.modalities,
                    "context_window": m.capabilities.context_window,
                    "pricing": f"${m.pricing.input_per_1m_tokens:.4f}/${m.pricing.output_per_1m_tokens:.4f} per 1M tokens",
                }
                for m in active_models
            ],
        }

        if task_type:
            message = f"📋 {len(active_models)} موديل متاح للمهام من نوع '{task_type}':"
        else:
            message = f"📋 إجمالي {len(active_models)} موديل نشط:"

        return CommandResult(
            success=True,
            message=message,
            data=data,
        )

    async def _query_status(self, intent: UserIntent) -> CommandResult:
        target = intent.model_id or intent.provider
        if not target:
            return CommandResult(
                success=False,
                message="حدد الموديل أو المزود. مثال: 'ما حالة gpt-4o'",
                error="MISSING_TARGET",
            )

        # Try as model ID first
        spec = self._registry.get(target)
        if spec:
            breaker = self._circuit_breakers.get(spec.model_id)
            breaker_status = breaker.get_status() if breaker else {"state": "unknown"}

            return CommandResult(
                success=True,
                message=f"📊 حالة {spec.model_id}:",
                data={
                    "model_id": spec.model_id,
                    "provider": spec.provider,
                    "status": spec.status.value,
                    "tier": spec.tier.value,
                    "circuit_breaker": breaker_status["state"],
                    "capabilities": spec.capabilities.modalities,
                },
            )

        # Try as provider
        models = self._registry.get_by_provider(target)
        if models:
            active = [m for m in models if m.status == ModelStatus.ACTIVE]
            return CommandResult(
                success=True,
                message=f"📊 حالة المزود {target}:",
                data={
                    "provider": target,
                    "total_models": len(models),
                    "active": len(active),
                    "disabled": len(models) - len(active),
                },
            )

        return CommandResult(
            success=False,
            message=f"لم يتم العثور على {target}",
            error="NOT_FOUND",
        )

    def _infer_capabilities(self, model_id: str) -> Any:
        from gateway.model_registry import ModelCapabilities

        model_lower = model_id.lower()
        has_vision = any(v in model_lower for v in ["vision", "gpt-4o", "claude-3", "gemini", "llava"])
        has_code = any(c in model_lower for c in ["code", "coder", "starcoder", "wizardcoder"])
        has_function = not any(x in model_lower for x in ["instruct", "chat"])

        return ModelCapabilities(
            context_window=128000 if "4o" in model_lower or "3.5" in model_lower else 32768,
            modalities=["text", "vision"] if has_vision else ["text"],
            function_calling=has_function,
            structured_output=has_function,
            parallel_tool_calls=has_function,
            max_output_tokens=8192,
        )

    def _map_task_type(self, task_type: str) -> Optional[ModelTier]:
        task_lower = task_type.lower()
        mapping = {
            "بسيطة": ModelTier.FAST,
            "بسيط": ModelTier.FAST,
            "سريعة": ModelTier.FAST,
            "simple": ModelTier.FAST,
            "fast": ModelTier.FAST,
            "معقدة": ModelTier.FRONTIER,
            "معقد": ModelTier.FRONTIER,
            "صعبة": ModelTier.FRONTIER,
            "complex": ModelTier.FRONTIER,
            "hard": ModelTier.FRONTIER,
            "حرجة": ModelTier.CRITIC,
            "critical": ModelTier.CRITIC,
            "critic": ModelTier.CRITIC,
            "كود": ModelTier.CODE_SPECIALIZED,
            "برمجة": ModelTier.CODE_SPECIALIZED,
            "code": ModelTier.CODE_SPECIALIZED,
            "coding": ModelTier.CODE_SPECIALIZED,
            "سياق طويل": ModelTier.LONG_CONTEXT,
            "long context": ModelTier.LONG_CONTEXT,
            "رؤية": ModelTier.VISION,
            "vision": ModelTier.VISION,
        }
        for keyword, tier in mapping.items():
            if keyword in task_lower:
                return tier
        return None

    async def _update_litellm_config(self, model_id: str, provider: str, region: Optional[str]) -> None:
        # This would write to config/litellm.yaml
        # For now, log the action
        logger.info("Config update needed for %s (provider=%s, region=%s)", model_id, provider, region)
        # TODO: Implement actual YAML write


class LiaisonAgent(BaseAgent):
    role: str = "liaison"

    def __init__(
        self,
        registry: AutoModelRegistry,
        gateway: SmartGateway,
        circuit_breakers: CircuitBreakerRegistry,
        researcher_agent: Any = None,  # ProfessionalResearcherAgent
        llm_client: Any = None,  # LLMClient for intent parsing
        agent_id: str = "liaison-01",
    ) -> None:
        # Liaison doesn't need LLM client for its own work, but uses it for intent parsing
        super().__init__(agent_id=agent_id, role="liaison", llm_client=llm_client)

        self._registry = registry
        self._gateway = gateway
        self._circuit_breakers = circuit_breakers

        # Core components
        self._intent_parser = IntentParser()
        self._executor = CommandExecutor(
            registry=registry,
            gateway=gateway,
            circuit_breakers=circuit_breakers,
            researcher_agent=researcher_agent,
        )

        logger.info("LiaisonAgent initialized: %s", agent_id)

    # ----------------------------------------------------------
    # BaseAgent Abstract Method Implementation
    # ----------------------------------------------------------

    def run(self, command: str, workflow_id: str = "", session_messages: list = None) -> Any:
        import asyncio
        if session_messages is None:
            session_messages = []
        return asyncio.run(self.handle_user_command(workflow_id=workflow_id, command=command, session_messages=session_messages))

    # ----------------------------------------------------------
    # Public API -- Called by humans (via CLI, API, chat, etc.)
    # ----------------------------------------------------------

    async def handle_user_command(
        self,
        workflow_id: str,
        command: str,
        session_messages: list = None,
    ) -> CommandResult:
        if session_messages is None:
            session_messages = []
            
        logger.info("Liaison received command for workflow %s: %s", workflow_id, command)

        # 1. Parse natural language into structured intent
        intent = self._intent_parser.parse(command)

        if intent.action == "unknown" or intent.confidence < 0.5:
            if not self.llm_client:
                return CommandResult(
                    success=False,
                    message="لم أفهم الأمر (الذكاء الاصطناعي معطل في Liaison)",
                    error="PARSE_FAILED",
                )
                
            # Use LLM with structured output to classify the intent
            all_models = self._registry.list_all()
            active_models = self._registry.get_active_models()
            
            models_desc = "\n".join([
                f"- {m.display_name} (ID: {m.model_id}, Tier: {m.tier.value}, Provider: {m.provider}, Status: {m.status.value})"
                for m in all_models
            ]) if all_models else "- None currently registered"
            
            from memory.memory_manager import MemoryManager
            persistent_facts = MemoryManager.load_memory()
            facts_desc = "\n".join([f"- {f}" for f in persistent_facts]) if persistent_facts else "- None yet"

            system_prompt = (
                "You are the Liaison Agent for the AI Dev-Team Autonomous Agency.\n"
                "Your job is to read the user's input and classify their intent into one of the provided categories.\n\n"
                f"System Registry Status:\n"
                f"- Total Models locally: {len(all_models)}\n"
                f"- Active Models locally: {len(active_models)}\n"
                f"Currently Registered Models List:\n{models_desc}\n\n"
                "Persistent User Memory (Facts you must remember):\n"
                f"{facts_desc}\n\n"
                "Classification Guidelines:\n"
                "- conversational: General chat, greetings, or follow-up questions about past actions. You MUST provide a 'reply' using the session context.\n"
                "- system_command: Questions about models, system status, or requests to configure the registry. (Do not write code for these).\n"
                "- research: System-internal research about available models or local technical specs.\n"
                "- deep_research: Deep web research requests, comparing external models or technologies, gathering data from the open internet, or social/statistical analysis.\n"
                "- fast_code: Trivially simple code requests (e.g. 'make a file that prints hello', 'fix typo in line 3').\n"
                "- full_sdlc: Complex software engineering tasks (e.g. 'build an app', 'plan architecture', 'refactor database').\n"
            )
            
            try:
                messages = [{"role": "system", "content": system_prompt}]
                
                # Append last 10 session messages for short-term memory context
                for msg in session_messages[-10:]:
                    messages.append(msg)
                    
                messages.append({"role": "user", "content": command})
                
                # Using complete_structured for robust JSON parsing
                parsed_intent = self.llm_client.complete_structured(
                    messages=messages,
                    response_model=ParsedIntent,
                    model="fast",
                    temperature=0.1
                )
                
                if parsed_intent.extracted_facts or parsed_intent.facts_to_remove:
                    MemoryManager.update_facts(parsed_intent.extracted_facts, parsed_intent.facts_to_remove)
                    
                return CommandResult(
                    success=True,
                    message=parsed_intent.reply.strip() if parsed_intent.reply else "Intent classified.",
                    data={
                        "intent_category": parsed_intent.category.value,
                        "parameters": parsed_intent.extracted_parameters
                    },
                )
            except Exception as e:
                logger.error("Structured LLM classification failed: %s", e)
                
                # Heuristic fallback if API is rate-limited / No models available
                cmd_clean = command.strip().lower()
                greetings = ["hello", "hi", "hey", "مرحبا", "أهلا", "اهلا", "السلام عليكم", "صباح الخير", "مساء الخير", "مرحب"]
                is_greeting = any(cmd_clean.startswith(g) for g in greetings) or len(cmd_clean.split()) <= 2
                
                if is_greeting:
                    return CommandResult(
                        success=True,
                        message=(
                            "مرحباً! أعتذر ولكن يبدو أن نماذج الذكاء الاصطناعي مستنفدة حالياً "
                            "(Rate Limit أو No models available). متواجد للمساعدة متى عاد الاتصال!"
                        ),
                        data={"is_coding_task": False},
                    )

                return CommandResult(
                    success=False,
                    message="لم أفهم الأمر، أو أن النماذج معطلة حالياً (No models available). هل يمكنك التوضيح؟",
                    error="PARSE_FAILED",
                )

        # 2. Execute via CommandExecutor
        result = await self._executor.execute(intent)

        # 3. Notify workflow if workflow_id provided
        if workflow_id and result.success:
            self._notify_workflow(workflow_id, intent, result)

        # 4. Return result to user
        return result

    def _notify_workflow(
        self,
        workflow_id: str,
        intent: UserIntent,
        result: CommandResult,
    ) -> None:
        # In a real implementation, this would append to the event store
        logger.info(
            "Workflow %s: Liaison executed %s - %s",
            workflow_id,
            intent.action.value,
            "success" if result.success else "failed",
        )

    # ----------------------------------------------------------
    # Human Notifications (HITL)
    # ----------------------------------------------------------

    def notify_human(
        self,
        workflow_id: str,
        message: str,
        severity: str = "info",
    ) -> None:
        import logging
        level_map = {
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
        }
        logger.log(
            level_map.get(severity, logging.INFO),
            "[LIAISON] Workflow %s: %s",
            workflow_id,
            message,
        )

    def request_human_input(
        self,
        workflow_id: str,
        question: str,
        options: list[str] | None = None,
    ) -> str:
        prompt = f"\n[HUMAN INPUT REQUIRED] Workflow {workflow_id}: {question}"
        if options:
            prompt += f"\nOptions: {', '.join(options)}"
        prompt += "\n> "

        # For CLI/testing - in production would be async wait
        try:
            return input(prompt)
        except EOFError:
            return ""

    # ----------------------------------------------------------
    # Introspection
    # ----------------------------------------------------------

    def get_system_status(self) -> dict[str, Any]:
        return {
            "registry": self._registry.get_stats(),
            "gateway": self._gateway.get_routing_stats(),
            "circuit_breakers": self._circuit_breakers.get_all_status(),
            "liaison": {
                "agent_id": self.agent_id,
                "status": "active",
            },
        }

    def __repr__(self) -> str:
        return f"LiaisonAgent(agent_id={self.agent_id})"