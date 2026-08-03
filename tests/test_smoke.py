"""
Smoke Tests — Phase 0 Foundation Verification
==============================================

Validates that the Phase 0 foundation is correctly set up:
- Python version meets minimum requirements
- All core packages are importable
- Project directory structure exists
- Configuration files are present
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Project root (two levels up from tests/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestPythonEnvironment:
    """Verify the Python environment meets requirements."""

    def test_python_version_minimum(self) -> None:
        """Python version must be >= 3.11."""
        assert sys.version_info >= (3, 11), (
            f"Python >= 3.11 required, got {sys.version_info.major}.{sys.version_info.minor}"
        )


class TestCoreImports:
    """Verify all core dependencies are importable."""

    def test_import_pydantic(self) -> None:
        """Pydantic must be importable (type-safe contracts)."""
        import pydantic

        assert pydantic.VERSION is not None

    def test_import_langgraph(self) -> None:
        """LangGraph must be importable (orchestration engine)."""
        import langgraph  # noqa: F401

    def test_import_langchain_core(self) -> None:
        """LangChain Core must be importable (base abstractions)."""
        import langchain_core  # noqa: F401

    def test_import_litellm(self) -> None:
        """LiteLLM must be importable (model gateway)."""
        import litellm  # noqa: F401

    def test_import_dotenv(self) -> None:
        """python-dotenv must be importable (configuration)."""
        import dotenv  # noqa: F401

    def test_import_httpx(self) -> None:
        """httpx must be importable (async HTTP)."""
        import httpx  # noqa: F401


class TestProjectStructure:
    """Verify the project directory structure exists as specified in README."""

    @pytest.mark.parametrize(
        "directory",
        [
            "src",
            "src/orchestrator",
            "src/agents",
            "src/contracts",
            "src/state",
            "src/memory",
            "src/tools",
            "src/verification",
            "src/resilience",
            "src/observability",
            "src/gateway",
            "config",
            "config/agents",
            "evals",
            "evals/golden",
            "evals/swebench",
            "evals/judges",
            "evals/redteam",
            "optim",
            "tests",
        ],
    )
    def test_directory_exists(self, directory: str) -> None:
        """Each directory from the README structure must exist."""
        path = PROJECT_ROOT / directory
        assert path.is_dir(), f"Directory missing: {directory}"

    @pytest.mark.parametrize(
        "filepath",
        [
            "pyproject.toml",
            "Makefile",
            "docker-compose.yml",
            ".env.example",
            ".gitignore",
            "LICENSE",
            "README.md",
            "config/litellm.yaml",
            "config/policies.yaml",
            "evals/golden/tasks.yaml",
            "evals/golden/README.md",
            "evals/swebench/README.md",
            "evals/swebench/run_harness.py",
        ],
    )
    def test_file_exists(self, filepath: str) -> None:
        """Each key file from Phase 0 must exist."""
        path = PROJECT_ROOT / filepath
        assert path.is_file(), f"File missing: {filepath}"


class TestSourcePackages:
    """Verify that source packages are importable."""

    def test_src_package(self) -> None:
        """The src package must have a version string."""
        src_init = PROJECT_ROOT / "src" / "__init__.py"
        assert src_init.is_file()
        content = src_init.read_text()
        assert '__version__ = "0.1.0"' in content

    @pytest.mark.parametrize(
        "package",
        [
            "orchestrator",
            "agents",
            "contracts",
            "state",
            "memory",
            "tools",
            "verification",
            "resilience",
            "observability",
            "gateway",
        ],
    )
    def test_subpackage_has_init(self, package: str) -> None:
        """Each src subpackage must have an __init__.py."""
        init_file = PROJECT_ROOT / "src" / package / "__init__.py"
        assert init_file.is_file(), f"Missing __init__.py in src/{package}"


class TestConfiguration:
    """Verify configuration files have required content."""

    def test_env_example_has_required_vars(self) -> None:
        """The .env.example must document all critical env vars."""
        content = (PROJECT_ROOT / ".env.example").read_text()
        required_vars = [
            "OPENAI_API_KEY",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_DB",
            "DATABASE_URL",
            "LITELLM_MASTER_KEY",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
        ]
        for var in required_vars:
            assert var in content, f"Missing env var in .env.example: {var}"

    def test_docker_compose_has_required_services(self) -> None:
        """docker-compose.yml must define all 4 required services."""
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        required_services = ["postgres", "qdrant", "litellm", "jaeger"]
        for svc in required_services:
            assert svc in content, f"Missing service in docker-compose.yml: {svc}"

    def test_litellm_config_has_models(self) -> None:
        """LiteLLM config must define model entries."""
        content = (PROJECT_ROOT / "config" / "litellm.yaml").read_text()
        assert "model_list" in content
        assert "frontier" in content
        assert "fast" in content
        assert "critic" in content

    def test_policies_default_deny(self) -> None:
        """Policies must use default-deny."""
        content = (PROJECT_ROOT / "config" / "policies.yaml").read_text()
        assert "default_policy: deny" in content
