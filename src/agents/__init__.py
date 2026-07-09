# Agents — Role agents (coder, tester, critic, ...)
"""Role agents module: lean ~14 role-based agents."""

from agents.base import BaseAgent
from agents.coder import CoderAgent
from agents.critic import CriticAgent
from agents.tester import TesterAgent

__all__ = [
    "BaseAgent",
    "CoderAgent",
    "CriticAgent",
    "TesterAgent",
]
