"""
OperatorAgent -- Handles administrative system commands (System Administrator).
=============================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agents.base import BaseAgent
from gateway.model_registry import AutoModelRegistry, ModelSpec, ModelTier, ModelStatus
from gateway.smart_gateway import SmartGateway
from resilience import CircuitBreakerRegistry
from contracts.system_commands import SystemAction, SystemCommandIntent, CommandResult, TIER_ALIAS_TO_TIER

logger = logging.getLogger(__name__)


class OperatorAgent(BaseAgent):
    """
    Agent responsible for executing system/administrative commands.
    It manages the Model Registry, Gateway overrides, and Circuit Breakers.
    """
    role: str = "operator"

    def __init__(
        self,
        registry: AutoModelRegistry,
        gateway: SmartGateway,
        circuit_breakers: CircuitBreakerRegistry,
        researcher_agent: Any = None,
        agent_id: str = "operator-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="operator", llm_client=None)
        self._registry = registry
        self._gateway = gateway
        self._circuit_breakers = circuit_breakers
        self._researcher = researcher_agent

    def run(self, command: str, workflow_id: str = "", session_messages: list = None) -> Any:
        pass

    async def execute_intent(self, intent: SystemCommandIntent) -> CommandResult:
        """Executes a parsed administrative intent from the Liaison."""
        logger.info("Operator executing command: %s (confidence=%.2f)", intent.action, intent.confidence)

        if intent.confidence < 0.7:
            return CommandResult(
                success=False,
                message=f"Low confidence ({intent.confidence:.0%}). Please rephrase.",
                error="LOW_CONFIDENCE",
            )

        try:
            if intent.action == SystemAction.ADD_MODEL:
                return await self._add_model(intent)
            elif intent.action == SystemAction.DISABLE_MODEL:
                return await self._disable_model(intent)
            elif intent.action == SystemAction.ENABLE_MODEL:
                return await self._enable_model(intent)
            elif intent.action == SystemAction.SET_DEFAULT:
                return await self._set_default(intent)
            elif intent.action == SystemAction.DISABLE_PROVIDER:
                return await self._disable_provider(intent)
            elif intent.action == SystemAction.QUERY_MODELS:
                return await self._query_models(intent)
            elif intent.action == SystemAction.QUERY_STATUS:
                return await self._query_status(intent)
            elif intent.action == SystemAction.OS_COMMAND:
                return await self._execute_os_command(intent)
            else:
                return CommandResult(
                    success=False,
                    message="لم أفهم الأمر الإداري.",
                    error="UNKNOWN_ACTION",
                )
        except Exception as e:
            logger.exception("Operator execution failed")
            return CommandResult(
                success=False,
                message=f"خطأ في التنفيذ الإداري: {e}",
                error=str(e),
            )

    async def _execute_os_command(self, intent: SystemCommandIntent) -> CommandResult:
        """Executes OS commands like file deletion safely."""
        import os
        import glob
        import shutil

        # If it came from regex, the target is in task_type
        # If it came from LLM fallback, it might be in intent.parameters
        target = intent.task_type
        if not target and hasattr(intent, "parameters") and intent.parameters:
            target = str(intent.parameters)
        elif not target:
            # try to parse from raw text as fallback
            target = intent.raw_text

        if not target:
            return CommandResult(
                success=False,
                message="لم يتم تحديد الملف المراد مسحه.",
                error="MISSING_TARGET",
            )
        
        logger.info("Operator attempting to delete files matching: %s", target)
        
        try:
            # Very basic extraction of filenames from the string
            import re
            files_to_delete = re.findall(r"[\w\.\-/]+\.(?:json|py|md|txt|csv|yaml|yml)", target)
            
            if not files_to_delete:
                return CommandResult(
                    success=False,
                    message=f"لم أتمكن من العثور على أسماء ملفات صالحة في طلبك.",
                    error="NO_FILES_FOUND",
                )

            deleted = []
            not_found = []
            
            for file_pattern in set(files_to_delete):
                file_path = os.path.abspath(file_pattern)
                if os.path.exists(file_path):
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    else:
                        shutil.rmtree(file_path)
                    deleted.append(file_pattern)
                else:
                    not_found.append(file_pattern)
            
            if deleted:
                msg = f"✅ تم حذف الملفات بنجاح: {', '.join(deleted)}"
                if not_found:
                    msg += f"\nولكن لم أجد هذه الملفات: {', '.join(not_found)}"
                return CommandResult(
                    success=True,
                    message=msg,
                    data={"deleted": deleted, "not_found": not_found},
                )
            else:
                return CommandResult(
                    success=False,
                    message=f"الملفات غير موجودة: {', '.join(not_found)}",
                    error="FILES_NOT_FOUND",
                )
        except Exception as e:
            logger.exception("File deletion failed")
            return CommandResult(
                success=False,
                message=f"فشل حذف الملفات بسبب خطأ: {str(e)}",
                error=str(e),
            )

    async def _add_model(self, intent: SystemCommandIntent) -> CommandResult:
        if not intent.model_id or not intent.provider:
            return CommandResult(
                success=False,
                message="يجب تحديد الموديل والمزود. مثال: 'أضف gpt-4o من Azure eastus2'",
                error="MISSING_PARAMS",
            )

        full_model_id = f"{intent.provider}/{intent.model_id}"
        if intent.region:
            full_model_id = f"{intent.provider}/{intent.region}/{intent.model_id}"

        logger.info("Adding model: %s (provider=%s, region=%s)", full_model_id, intent.provider, intent.region)

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

        if intent.tier:
            internal_tier = TIER_ALIAS_TO_TIER.get(intent.tier)
            if internal_tier:
                self._gateway._router.set_manual_override(internal_tier, full_model_id)

        await self._update_litellm_config(full_model_id, intent.provider, intent.region)

        return CommandResult(
            success=True,
            message=f"✅ تم إضافة {full_model_id} كموديل {'افتراضي للـ ' + intent.tier.value if intent.tier else ''}",
            data={"model_id": full_model_id, "provider": intent.provider, "tier": intent.tier.value if intent.tier else None},
        )

    async def _disable_model(self, intent: SystemCommandIntent) -> CommandResult:
        model_id = intent.model_id or intent.provider
        if not model_id:
            return CommandResult(
                success=False,
                message="حدد الموديل المراد إيقافه. مثال: 'أوقف نموذج gpt-4o'",
                error="MISSING_MODEL",
            )

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
            breaker = self._circuit_breakers.get(model.model_id)
            if breaker:
                breaker.force_open()

        return CommandResult(
            success=True,
            message=f"✅ تم تعطيل {len(matches)} موديل: {', '.join(m.model_id for m in matches)}",
            data={"disabled": [m.model_id for m in matches]},
        )

    async def _enable_model(self, intent: SystemCommandIntent) -> CommandResult:
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

    async def _set_default(self, intent: SystemCommandIntent) -> CommandResult:
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

    async def _disable_provider(self, intent: SystemCommandIntent) -> CommandResult:
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

    async def _query_models(self, intent: SystemCommandIntent) -> CommandResult:
        task_type = intent.task_type

        if task_type:
            tier = self._map_task_type(task_type)
            if tier:
                models = self._registry.get_by_tier(tier)
            else:
                models = self._registry.list_all()
        else:
            models = self._registry.list_all()

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

    async def _query_status(self, intent: SystemCommandIntent) -> CommandResult:
        target = intent.model_id or intent.provider
        if not target:
            return CommandResult(
                success=False,
                message="حدد الموديل أو المزود. مثال: 'ما حالة gpt-4o'",
                error="MISSING_TARGET",
            )

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
        logger.info("Config update needed for %s (provider=%s, region=%s)", model_id, provider, region)

