# Agents — Role-based agent implementations
"""Agents module: BaseAgent, CoderAgent, TesterAgent, CriticAgent, CriticFactory."""

from agents.base import BaseAgent
from agents.coder import CoderAgent
from agents.critic import CriticAgent
from agents.critic_factory import create_critic, list_supported_roles
from agents.tester import TesterAgent

__all__ = [
    "BaseAgent",
    "CoderAgent",
    "CriticAgent",
    "TesterAgent",
    "create_critic",
    "list_supported_roles",
]
