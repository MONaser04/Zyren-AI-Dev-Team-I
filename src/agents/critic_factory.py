"""
Critic Factory — Role-Scoped Critic Instantiation
====================================================

Per README line 233: attach dedicated critics ONLY to the three highest-risk
producers — Coder, Architect, Security. All other outputs are verified by
the shared Grounded Verification Layer.

Each role gets a CriticAgent with a tailored system prompt and rubric.
"""

from __future__ import annotations

from src.observability.instrumentation import trace_agent_invocation

from typing import TYPE_CHECKING

from src.agents.critic import CriticAgent

if TYPE_CHECKING:
    from gateway.llm_client import LLMClient

# ============================================================
# Rubric Descriptions (embedded — external YAML in Phase 4)
# ============================================================

_RUBRICS: dict[str, str] = {
    "code_review": (
        "Code review rubric: correctness, type safety, test coverage, "
        "idiomatic style, error handling, performance, readability."
    ),
    "architecture_review": (
        "Architecture review rubric: separation of concerns, dependency "
        "direction, API contract stability, scalability, SOLID principles."
    ),
    "security_review": (
        "Security review rubric: OWASP Top 10, injection prevention, "
        "authentication/authorization, secrets management, input validation, "
        "dependency vulnerabilities, least privilege."
    ),
}


def create_critic(
    role: str,
    llm_client: LLMClient,
    model: str = "critic",
) -> CriticAgent:
    """Create a role-scoped CriticAgent.

    Args:
        role: The producer role this critic reviews ('coder', 'architect', 'security').
        llm_client: The LLM client for model calls.
        model: Model alias (default: 'critic').

    Returns:
        A CriticAgent configured with the appropriate rubric.

    Raises:
        ValueError: If the role is not a supported high-risk producer.
    """
    role_map: dict[str, tuple[str, str]] = {
        "coder": ("critic-coder", "code_review"),
        "architect": ("critic-architect", "architecture_review"),
        "security": ("critic-security", "security_review"),
    }

    if role not in role_map:
        supported = ", ".join(sorted(role_map.keys()))
        msg = f"No dedicated critic for role '{role}'. Supported: {supported}"
        raise ValueError(msg)

    agent_id, rubric_name = role_map[role]
    return CriticAgent(
        llm_client=llm_client,
        model=model,
        agent_id=agent_id,
        rubric_name=rubric_name,
    )


def list_supported_roles() -> list[str]:
    """Return the list of roles with dedicated critics."""
    return ["coder", "architect", "security"]
