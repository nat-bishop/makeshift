.PHONY: dev gpu api stop gpu-restart gpu-logs godot play install test lint fix format typecheck check clear-sprites cli-create cli-image cli-sprite cli-status eval eval-gate eval-compare eval-promote eval-list ollama help

GODOT ?= godot
VERBOSE ?= 0
COMPOSE := docker compose --env-file .env -f services/sglang/docker-compose.yml

# Internal helper: block until all GPU services are healthy
define wait-services
	@echo "Waiting for GPU services..."
	@until curl -sf http://127.0.0.1:5100/health > /dev/null 2>&1; do sleep 2; done; echo "SGLang ready"
	@until curl -sf http://127.0.0.1:5200/health > /dev/null 2>&1; do sleep 2; done; echo "LLM ready"
endef

dev: gpu ollama ## Start all servers + launch game
	$(wait-services)
	uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir backend --reload-include '*.py' &
	@sleep 2
	$(GODOT) --path godot/
	$(MAKE) stop

gpu: ## Start GPU/LLM Docker containers (detached)
	$(COMPOSE) up -d --build

api: ## Start FastAPI dev server (foreground, auto-reload)
	uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir backend --reload-include '*.py'

gpu-restart: ## Rebuild and restart GPU/LLM Docker containers
	$(COMPOSE) up -d --build --force-recreate

gpu-logs: ## Tail GPU/LLM container logs
	$(COMPOSE) logs -f

stop: ## Stop all servers and clean up
	@powershell -c 'Get-NetTCPConnection -LocalPort 8000 -EA SilentlyContinue | %%{ Stop-Process -Id $$_.OwningProcess -Force }' 2>/dev/null || true
	@$(COMPOSE) down 2>/dev/null || true
	@echo "All servers stopped"

godot: ## Open Godot editor
	$(GODOT) --editor --path godot/

play: ## Run the game (VERBOSE=0 to suppress engine output)
	$(GODOT) --headless --import --path godot/
	$(GODOT) $(if $(filter 1,$(VERBOSE)),--verbose) --path godot/ 2>&1

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

PROMPT ?= fire sword
OUT ?=

cli-create: ## Create a game object via LLM (PROMPT="fire sword")
	cd backend && uv run python -m app.cli create "$(PROMPT)"

cli-image: ## Generate a raw image (PROMPT="a pixel art sword" OUT=output.png)
	cd backend && uv run python -m app.cli image "$(PROMPT)" --out "$(or $(OUT),output.png)"

cli-sprite: ## Full sprite pipeline (PROMPT="fire sword" OUT=sprite.png)
	cd backend && uv run python -m app.cli sprite "$(PROMPT)" $(if $(OUT),--out "$(OUT)")

ollama: ## Pull embedding model and verify Ollama is running
	ollama pull qwen3-embedding:0.6b
	@curl -sf http://127.0.0.1:11434/api/tags > /dev/null 2>&1 && echo "Ollama ready" || echo "Ollama not running — start it with 'ollama serve'"

cli-status: ## Check health of configured services
	cd backend && uv run python -m app.cli status

cli-animate: ## Test I2V animation (SPRITE=path.png PROMPT="walk cycle")
	cd backend && uv run python -m experiments.i2v_animation_test $(if $(SPRITE),--sprite "$(SPRITE)") $(if $(PROMPT),--prompt "$(PROMPT)")

PROMPT_A ?= baseline

eval: ## Full eval run (NAME=experiment VARIANT=baseline CASES="rock,sword")
	cd backend && uv run python -m evals.run_eval \
		$(if $(NAME),--name "$(NAME)") \
		$(if $(VARIANT),--variant "$(VARIANT)") \
		$(if $(CASES),--cases "$(CASES)") \
		$(if $(COMPARE),--compare)

eval-gate: ## Fast gate check — deterministic only, no LLM judges
	cd backend && uv run python -m evals.run_eval --gate

eval-compare: ## Compare a run to baseline (NAME=experiment), or two runs (A=x B=y)
	@if [ -n "$(A)" ] && [ -n "$(B)" ]; then \
		cd backend && uv run python -m evals.run_comparison --a "$(A)" --b "$(B)"; \
	elif [ -n "$(NAME)" ]; then \
		cd backend && uv run python -m evals.run_comparison --a current_baseline --b "$(NAME)"; \
	else \
		echo "Usage: make eval-compare NAME=experiment  or  make eval-compare A=run1 B=run2"; \
	fi

eval-promote: ## Promote a run to current baseline (NAME=experiment)
	cd backend && uv run python -m evals.run_eval --promote "$(NAME)"

eval-list: ## List all saved eval runs
	cd backend && uv run python -m evals.run_eval --list

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
