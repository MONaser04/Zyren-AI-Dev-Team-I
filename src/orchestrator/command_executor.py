"""
CommandExecutor — Phase 4
=========================
Distributes Liaison commands to the appropriate system components.

Flow: Liaison → CommandExecutor → (Researcher → Registry → Gateway → Config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.professional_researcher import ProfessionalResearcherAgent
    from gateway.model_registry import AutoModelRegistry
    from gateway.smart_gateway import SmartGateway

logger = logging.getLogger(__name__)


# ============================================================
# Command Types
# ============================================================


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """A parsed command from the Liaison agent."""

    action: str  # add_model, disable_provider, set_default, discover_all, query_models
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "liaison"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CommandResult:
    """Result of executing a command."""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# ============================================================
# CommandExecutor
# ============================================================


class CommandExecutor:
    """Executes Liaison commands by distributing to appropriate agents.

    Orchestrates multi-step flows like:
    - add_model: Researcher (validate) → Registry (register) → Gateway (update routing)
    - disable_provider: Registry (mark disabled) → Gateway (open circuits) → Notify
    - discover_all: Registry (discover_all) → Report
    """

    def __init__(
        self,
        registry: AutoModelRegistry,
        gateway: SmartGateway,
        researcher: ProfessionalResearcherAgent | None = None,
    ) -> None:
        self._registry = registry
        self._gateway = gateway
        self._researcher = researcher

    async def execute_command(self, command: ParsedCommand) -> CommandResult:
        """Execute a parsed command.

        Args:
            command: ParsedCommand with action and parameters.

        Returns:
            CommandResult with success/failure and data.
        """
        try:
            match command.action:
                case "add_model":
                    return await self._add_model_flow(command)
                case "disable_model":
                    return await self._disable_model_flow(command)
                case "enable_model":
                    return await self._enable_model_flow(command)
                case "disable_provider":
                    return await self._disable_provider_flow(command)
                case "set_default":
                    return await self._set_default_flow(command)
                case "discover_all":
                    return await self._discover_all_flow(command)
                case "query_models":
                    return await self._query_models_flow(command)
                case "query_status":
                    return await self._query_status_flow(command)
                case _:
                    return CommandResult(
                        success=False,
                        message=f"Unknown command: {command.action}",
                        error=f"Unsupported action: {command.action}",
                    )
        except Exception as e:
            logger.error("Command execution failed: %s", e, exc_info=True)
            return CommandResult(
                success=False,
                message=f"Command failed: {e}",
                error=str(e),
            )

    # ----------------------------------------------------------
    # Command Flows
    # ----------------------------------------------------------

    async def _add_model_flow(self, command: ParsedCommand) -> CommandResult:
        """Add a model: Researcher validates → Registry registers → Gateway updates."""
        provider = command.params.get("provider", "")
        model_id = command.params.get("model_id", "")

        if not provider or not model_id:
            return CommandResult(
                success=False,
                message="Missing provider or model_id",
                error="Both provider and model_id are required",
            )

        # Step 1: Research the model (if researcher is available)
        if self._researcher:
            research = await self._researcher.research_model_spec(provider, model_id)
            if not research.success:
                return CommandResult(
                    success=False,
                    message=f"Research failed for {model_id}: {research.error}",
                    error=research.error,
                )

            # Step 2: Build verified spec
            spec = await self._researcher.build_model_spec(provider, model_id, research)
            if not spec:
                return CommandResult(
                    success=False,
                    message=f"Model {model_id} rejected: insufficient confidence",
                    error="Confidence below threshold",
                )

            # Step 3: Register in registry
            self._registry.manual_add_model(spec, added_by=command.source)

            return CommandResult(
                success=True,
                message=f"Model {model_id} added from {provider}",
                data={"model_id": spec.model_id, "tier": spec.tier.value},
            )
        else:
            # No researcher — direct registration via gateway
            result = await self._gateway.handle_manual_model_change({
                "action": "add_model",
                "model_id": model_id,
                "provider": provider,
                "spec": command.params.get("spec"),
            })
            return CommandResult(
                success=result.get("status") == "ok",
                message=result.get("message", ""),
            )

    async def _disable_model_flow(self, command: ParsedCommand) -> CommandResult:
        """Disable a model via gateway."""
        result = await self._gateway.handle_manual_model_change({
            "action": "disable_model",
            "model_id": command.params.get("model_id", ""),
            "reason": command.params.get("reason", "Disabled by user"),
        })
        return CommandResult(
            success=result.get("status") == "ok",
            message=result.get("message", ""),
        )

    async def _enable_model_flow(self, command: ParsedCommand) -> CommandResult:
        """Enable a previously disabled model."""
        result = await self._gateway.handle_manual_model_change({
            "action": "enable_model",
            "model_id": command.params.get("model_id", ""),
        })
        return CommandResult(
            success=result.get("status") == "ok",
            message=result.get("message", ""),
        )

    async def _disable_provider_flow(self, command: ParsedCommand) -> CommandResult:
        """Disable all models from a provider."""
        result = await self._gateway.handle_manual_model_change({
            "action": "disable_provider",
            "provider": command.params.get("provider", ""),
            "reason": command.params.get("reason", "Provider disabled by user"),
        })
        return CommandResult(
            success=result.get("status") == "ok",
            message=result.get("message", ""),
        )

    async def _set_default_flow(self, command: ParsedCommand) -> CommandResult:
        """Set a model as default for a tier."""
        result = await self._gateway.handle_manual_model_change({
            "action": "set_default",
            "model_id": command.params.get("model_id", ""),
            "tier": command.params.get("tier", ""),
        })
        return CommandResult(
            success=result.get("status") == "ok",
            message=result.get("message", ""),
        )

    async def _discover_all_flow(self, command: ParsedCommand) -> CommandResult:
        """Trigger model discovery across all providers."""
        total = await self._registry.discover_all()
        return CommandResult(
            success=True,
            message=f"Discovered {total} models across all providers",
            data={"total_models": total, "stats": self._registry.get_stats()},
        )

    async def _query_models_flow(self, command: ParsedCommand) -> CommandResult:
        """Query models with optional filters."""
        filters = command.params.get("filters", {})
        models = self._registry.list_models(filters)
        return CommandResult(
            success=True,
            message=f"Found {len(models)} models",
            data={
                "count": len(models),
                "models": [
                    {
                        "model_id": m.model_id,
                        "provider": m.provider,
                        "tier": m.tier.value,
                        "status": m.status.value,
                    }
                    for m in models
                ],
            },
        )

    async def _query_status_flow(self, command: ParsedCommand) -> CommandResult:
        """Get system status."""
        stats = self._gateway.get_routing_stats()
        return CommandResult(
            success=True,
            message="System status retrieved",
            data=stats,
        )
