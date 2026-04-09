.PHONY: dev gpu api stop gpu-restart llm-restart gpu-logs godot play install test lint fix format format-check typecheck check clear-sprites clear-cache cli-create cli-image cli-sprite cli-status eval eval-creation eval-pairwise eval-creature eval-judge bench-tokens help

GODOT ?= godot
VERBOSE ?= 0
COMPOSE := docker compose --env-file .env -f services/sglang/docker-compose.yml

# Internal helper: block until all GPU services are healthy
define wait-services
	@echo "Waiting for GPU services..."
	@until curl -sf http://127.0.0.1:5100/health > /dev/null 2>&1; do sleep 2; done; echo "SGLang ready"
	@until curl -sf http://127.0.0.1:5200/health > /dev/null 2>&1; do sleep 2; done; echo "LLM ready"
endef

dev: gpu ## Start all servers + launch game
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

llm-restart: ## Restart just the LLM container (reads server config from model_profiles.toml)
	$(eval LLM_NAME := $(shell grep -m1 '^LLM_MODEL=' .env 2>/dev/null | cut -d= -f2))
	$(foreach v,$(shell python services/sglang/profile_env.py "$(LLM_NAME)" 2>/dev/null),$(eval export $(v)))
	$(COMPOSE) up -d --no-build --force-recreate llm

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

format-check: ## Check formatting without modifying files
	uv run ruff format --check backend/

check: format-check lint typecheck test ## Run all checks

clear-sprites: ## Delete all cached sprites
	rm -f backend/static/sprites/*.png

clear-cache: ## Delete LLM creation/pairwise cache (cache.db)
	rm -f backend/data/cache.db
	@echo "Cache cleared"

PROMPT ?= fire sword
OUT ?=
REPEATS ?= 3

cli-create: ## Create a game object via LLM (PROMPT="fire sword")
	cd backend && uv run python -m app.cli create "$(PROMPT)"

cli-image: ## Generate a raw image (PROMPT="a pixel art sword" OUT=output.png)
	cd backend && uv run python -m app.cli image "$(PROMPT)" --out "$(or $(OUT),output.png)"

cli-sprite: ## Full sprite pipeline (PROMPT="fire sword" OUT=sprite.png)
	cd backend && uv run python -m app.cli sprite "$(PROMPT)" $(if $(OUT),--out "$(OUT)")

cli-status: ## Check health of configured services
	cd backend && uv run python -m app.cli status

cli-animate: ## Test I2V animation (SPRITE=path.png PROMPT="walk cycle")
	cd backend && uv run python -m experiments.i2v_animation_test $(if $(SPRITE),--sprite "$(SPRITE)") $(if $(PROMPT),--prompt "$(PROMPT)")

eval: ## Run all quality evals (LLM, costs money, REPEATS=3)
	cd backend && RUN_TS=$$(date +%Y%m%d_%H%M%S) && \
		EVAL_RUN_DIR=$$RUN_TS uv run python -m evals.run_creation --repeat $(REPEATS) && \
		EVAL_RUN_DIR=$$RUN_TS uv run python -m evals.run_pairwise --repeat $(REPEATS) && \
		EVAL_RUN_DIR=$$RUN_TS uv run python -m evals.run_creature --repeat $(REPEATS)

eval-creation: ## Creation quality eval (LLM, costs money, REPEATS=3)
	cd backend && uv run python -m evals.run_creation --repeat $(REPEATS)

eval-pairwise: ## Pairwise + screening eval (LLM, costs money, REPEATS=3)
	cd backend && uv run python -m evals.run_pairwise --repeat $(REPEATS)

eval-creature: ## Creature eval (LLM, costs money, REPEATS=3)
	cd backend && uv run python -m evals.run_creature --repeat $(REPEATS)

bench-tokens: ## Measure token overhead: tool call vs plain text (LLM, cheap)
	cd backend && uv run python scripts/benchmark_token_overhead.py

eval-judge: ## All evals + LLM judge (LLM, costs more money, REPEATS=3)
	cd backend && RUN_TS=$$(date +%Y%m%d_%H%M%S) && \
		EVAL_RUN_DIR=$$RUN_TS uv run python -m evals.run_creation --judge --repeat $(REPEATS) && \
		EVAL_RUN_DIR=$$RUN_TS uv run python -m evals.run_pairwise --repeat $(REPEATS) && \
		EVAL_RUN_DIR=$$RUN_TS uv run python -m evals.run_creature --repeat $(REPEATS)

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
