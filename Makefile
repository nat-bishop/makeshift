.PHONY: dev dev-servers stop godot play godot-import install test lint fix format typecheck check clear-sprites wait-gpu wait-llm cli-create cli-image cli-sprite cli-status help

GODOT ?= godot
VERBOSE ?= 0
COMPOSE := docker compose -f services/sglang/docker-compose.yml

dev: ## Start all servers + launch game
	$(COMPOSE) up -d --build
	@$(MAKE) wait-gpu && $(MAKE) wait-llm || true
	$(GODOT) --path godot/
	$(MAKE) stop

dev-servers: ## Start GPU/LLM containers + API server (foreground, auto-reload)
	$(COMPOSE) up -d --build
	uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir backend

godot: ## Open Godot editor
	$(GODOT) --editor --path godot/

play: godot-import ## Run the game (VERBOSE=0 to suppress engine output)
	$(GODOT) $(if $(filter 1,$(VERBOSE)),--verbose) --path godot/ 2>&1

godot-import: ## Import Godot resources (runs automatically before play)
	$(GODOT) --headless --import --path godot/

install: ## Install all dependencies
	uv sync
	cd services/sglang && uv sync

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

clear-sprites: ## Delete all cached sprites
	rm -f backend/static/sprites/*.png

stop: ## Stop all servers and clean up
	@powershell -c 'Get-NetTCPConnection -LocalPort 8000 -EA SilentlyContinue | %%{ Stop-Process -Id $$_.OwningProcess -Force }' 2>/dev/null || true
	@$(COMPOSE) down 2>/dev/null || true
	@echo "All servers stopped"

wait-gpu: ## Wait for SGLang to be ready
	@echo "Waiting for SGLang..."
	@until curl -sf http://127.0.0.1:5100/health > /dev/null 2>&1; do sleep 2; done
	@echo "SGLang ready"

wait-llm: ## Wait for SGLang LLM to be ready
	@echo "Waiting for SGLang LLM..."
	@until curl -sf http://127.0.0.1:5200/health > /dev/null 2>&1; do sleep 2; done
	@echo "SGLang LLM ready"

PROMPT ?= fire sword
OUT ?=

cli-create: ## Create a game object via LLM (PROMPT="fire sword")
	cd backend && uv run python -m app.cli create "$(PROMPT)"

cli-image: ## Generate a raw image (PROMPT="a pixel art sword" OUT=output.png)
	cd backend && uv run python -m app.cli image "$(PROMPT)" --out "$(or $(OUT),output.png)"

cli-sprite: ## Full sprite pipeline (PROMPT="fire sword" OUT=sprite.png)
	cd backend && uv run python -m app.cli sprite "$(PROMPT)" $(if $(OUT),--out "$(OUT)")

cli-status: ## Check health of configured services
	cd backend && uv run python -m app.cli status

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
