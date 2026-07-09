"""
Base Agent — Abstract Interface for All Role Agents
=====================================================

Every agent in the system inherits from BaseAgent and implements
a typed run() method that takes a contract in and returns a contract out.
"""

from __future__ import annotations

from observability.instrumentation import trace_agent_invocation

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient


class BaseAgent(ABC):
    """Abstract base class for all role agents.

    Provides common infrastructure:
    - agent_id and role identification
    - LLM client access
    - Logging
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        llm_client: LLMClient,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.llm_client = llm_client
        self.logger = logging.getLogger(f"agent.{role}.{agent_id}")

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the agent's primary function.

        Each subclass defines its own typed signature.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.agent_id} role={self.role}>"
