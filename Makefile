.PHONY: serve godot install test lint fix format typecheck check down help

serve: ## Run backend server
	uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

godot: ## Open Godot editor
	godot --path godot/

install: ## Install all dependencies
	uv sync

test: ## Run all tests
	uv run pytest

lint: ## Lint backend
	uv run ruff check backend/

fix: ## Lint with autofix
	uv run ruff check backend/ --fix

format: ## Format backend
	uv run ruff format backend/

typecheck: ## Type check backend
	uv run mypy backend/

check: lint typecheck test ## Run all checks

down: ## Stop the backend server
	@pkill -f "uvicorn backend.app.main:app" 2>/dev/null || true
	@echo "Server stopped"

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
