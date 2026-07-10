from src.observability.instrumentation import trace_agent_invocation
# Agents — Role-based agent implementations (Phases 1-4)
"""Agents module: BaseAgent, CoderAgent, TesterAgent, CriticAgent, CriticFactory,
plus Phase 4 full roster: ProductAnalyst, Planner, Architect, UX, DBEngineer,
Researcher, Integrator, Security, Docs, Liaison, Supervisor."""

from agents.base import BaseAgent
from agents.coder import CoderAgent
from agents.critic import CriticAgent
from agents.critic_factory import create_critic, list_supported_roles
from agents.tester import TesterAgent
from agents.product_analyst import ProductAnalystAgent
from agents.planner import PlannerAgent
from agents.architect import ArchitectAgent
from agents.ux import UXAgent
from agents.db_engineer import DBEngineerAgent
from agents.researcher import ResearcherAgent
from agents.integrator import IntegratorAgent
from agents.security import SecurityAgent
from agents.docs import DocsAgent
from agents.liaison import LiaisonAgent
from agents.supervisor import SupervisorAgent

__all__ = [
    "BaseAgent",
    "CoderAgent",
    "CriticAgent",
    "TesterAgent",
    "create_critic",
    "list_supported_roles",
    "ProductAnalystAgent",
    "PlannerAgent",
    "ArchitectAgent",
    "UXAgent",
    "DBEngineerAgent",
    "ResearcherAgent",
    "IntegratorAgent",
    "SecurityAgent",
    "DocsAgent",
    "LiaisonAgent",
    "SupervisorAgent",
]
