# ============================================================
# Zyren AI Dev-Team — Makefile
# ============================================================
# Usage:
#   make install    — Install all dependencies via uv
#   make test       — Run test suite
#   make lint       — Lint code with ruff
#   make format     — Auto-format code with ruff
#   make typecheck  — Static type checking with mypy
#   make up         — Start local infrastructure (Docker)
#   make down       — Stop local infrastructure
#   make eval       — Run evaluation harness
#   make clean      — Remove caches and build artifacts
#   make all        — Full CI check (lint + typecheck + test)
# ============================================================

.DEFAULT_GOAL := help
.PHONY: help install test lint format typecheck up down eval clean all

# --- Colors ---
BLUE   := \033[34m
GREEN  := \033[32m
YELLOW := \033[33m
RESET  := \033[0m

help: ## Show this help message
	@echo ""
	@echo "$(BLUE)Zyren AI Dev-Team$(RESET) — Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ============================================================
# Development
# ============================================================

install: ## Install all dependencies via uv
	uv sync

test: ## Run test suite with pytest
	uv run pytest tests/ -v --tb=short

lint: ## Lint code with ruff
	uv run ruff check src/ tests/

format: ## Auto-format code with ruff
	uv run ruff format src/ tests/

typecheck: ## Static type checking with mypy
	uv run mypy src/

# ============================================================
# Infrastructure
# ============================================================

up: ## Start local infrastructure (Docker Compose)
	docker compose up -d
	@echo "$(GREEN)✓ Infrastructure is up$(RESET)"
	@echo "  Postgres:  localhost:5432"
	@echo "  Qdrant:    localhost:6333 (REST) / 6334 (gRPC)"
	@echo "  LiteLLM:   localhost:4000"
	@echo "  Jaeger UI: localhost:16686"

down: ## Stop local infrastructure
	docker compose down
	@echo "$(YELLOW)✓ Infrastructure stopped$(RESET)"

logs: ## Tail infrastructure logs
	docker compose logs -f

ps: ## Show infrastructure status
	docker compose ps

# ============================================================
# Evaluation (Phase 5)
# ============================================================

eval: ## Run evaluation harness (Golden + SWE-bench + Red-team)
	uv run python -m evals.golden.runner

eval-golden: ## Run only Golden Set evaluation
	uv run python -m evals.golden.runner

eval-swebench: ## Run SWE-bench evaluation
	uv run python -m evals.swebench.harness

eval-redteam: ## Run Red-team security evaluation
	uv run python -m evals.redteam.attacks

eval-all: ## Run all evaluation suites
	uv run python -m evals.golden.runner && \
	uv run python -m evals.swebench.harness && \
	uv run python -m evals.redteam.attacks

# ============================================================
# Phase 5: Closed-Loop Optimisation
# ============================================================

supervisor: ## Run Supervisor closed-loop optimisation
	uv run python -m src.agents.supervisor

supervisor-round: ## Run single optimisation round
	uv run python -c "from src.agents.supervisor import run_single_optimisation_round; run_single_optimisation_round()"

optim-report: ## Generate optimisation report from latest results
	uv run python -m optim.reporter

# ============================================================
# Cleanup
# ============================================================

clean: ## Remove caches and build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ htmlcov/ .coverage
	@echo "$(GREEN)✓ Cleaned$(RESET)"

# ============================================================
# CI / Full Check
# ============================================================

all: lint typecheck test ## Full CI check (lint + typecheck + test)
	@echo "$(GREEN)✓ All checks passed$(RESET)"
