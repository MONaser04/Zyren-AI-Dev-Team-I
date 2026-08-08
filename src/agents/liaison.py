"""
LiaisonAgent -- Pure Passthrough
==============================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from agents.base import BaseAgent
from gateway.model_registry import AutoModelRegistry
from gateway.smart_gateway import SmartGateway
from resilience import CircuitBreakerRegistry
from contracts.system_commands import CommandResult

logger = logging.getLogger(__name__)

class LiaisonAgent(BaseAgent):
    """
    A 100% pure messenger agent. It receives natural language requests
    and blindly passes them to the Orchestrator for intent classification and execution.
    """

    def __init__(
        self,
        registry: AutoModelRegistry,
        gateway: SmartGateway,
        circuit_breakers: CircuitBreakerRegistry,
        llm_client: Any,
        agent_id: str = "liaison-01",
    ) -> None:
        super().__init__(agent_id=agent_id, role="liaison", llm_client=llm_client)

    def run(self, command: str, workflow_id: str = "", session_messages: list = None) -> CommandResult:
        """Sync wrapper."""
        import asyncio
        return asyncio.run(self.handle_user_command(workflow_id=workflow_id, command=command, session_messages=session_messages))

    async def handle_user_command(
        self,
        workflow_id: str,
        command: str,
        session_messages: list = None,
    ) -> CommandResult:
        if session_messages is None:
            session_messages = []
            
        logger.info("Liaison received command for workflow %s: %s", workflow_id, command)

        # 100% Passthrough to the Orchestrator (SemanticRouter)
        return CommandResult(
            success=True,
            message="Delegating to Orchestrator...",
            data={"intent_category": "unknown", "raw_command": command},
        )