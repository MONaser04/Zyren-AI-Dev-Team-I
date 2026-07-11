from src.observability.instrumentation import trace_agent_invocation
# Agents — Role-based agent implementations (Phases 1-4)
"""Agents module: BaseAgent, CoderAgent, TesterAgent, CriticAgent, CriticFactory,
plus Phase 4 full roster: ProductAnalyst, Planner, Architect, UX, DBEngineer,
Researcher, Integrator, Security, Docs, Liaison, Supervisor."""

from src.agents.base import BaseAgent
from src.agents.coder import CoderAgent
from src.agents.critic import CriticAgent
from src.agents.critic_factory import create_critic, list_supported_roles
from src.agents.tester import TesterAgent
from src.agents.product_analyst import ProductAnalystAgent
from src.agents.planner import PlannerAgent
from src.agents.architect import ArchitectAgent
from src.agents.ux import UXAgent
from src.agents.db_engineer import DBEngineerAgent
from src.agents.researcher import ResearcherAgent
from src.agents.integrator import IntegratorAgent
from src.agents.security import SecurityAgent
from src.agents.docs import DocsAgent
from src.agents.liaison import LiaisonAgent

# Lazy import for SupervisorAgent to avoid circular import
_SupervisorAgent = None

def __getattr__(name):
    global _SupervisorAgent
    if name == "SupervisorAgent":
        if _SupervisorAgent is None:
            from src.agents.supervisor import SupervisorAgent
            _SupervisorAgent = SupervisorAgent
        return _SupervisorAgent
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

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
