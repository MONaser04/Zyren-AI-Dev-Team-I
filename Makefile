# ============================================================
# AI Dev-Team — Makefile
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
	@echo "$(BLUE)AI Dev-Team$(RESET) — Available targets:"
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
# Evaluation
# ============================================================

eval: ## Run evaluation harness (golden tasks + SWE-bench)
	@echo "$(YELLOW)⚠ Eval harness not yet wired — coming in Phase 1$(RESET)"
	@echo "  Placeholder: uv run python evals/swebench/run_harness.py"

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
