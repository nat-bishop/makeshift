.PHONY: serve godot play godot-import install test lint fix format typecheck check down clear-sprites serve-gpu wait-gpu stop-gpu help

serve: ## Run backend server
	uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

GODOT ?= godot

godot: ## Open Godot editor
	$(GODOT) --editor --path godot/

VERBOSE ?= 0

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

serve-gpu: ## Start SGLang FLUX server (runs in WSL2, blocks terminal)
	wsl -d Ubuntu-24.04 -u root -- /bin/bash -c '\
		export COLUMNS=80 LINES=24 SGLANG_ENABLE_JIT_DEEPGEMM=0 SGLANG_CACHE_DIT_ENABLED=true; \
		/opt/sglang/bin/python -m sglang.launch_server \
			--model-path black-forest-labs/FLUX.2-klein-4b-fp8 \
			--port 5100'

wait-gpu: ## Wait for SGLang to be ready
	@echo "Waiting for SGLang..."
	@until curl -sf http://127.0.0.1:5100/health > /dev/null 2>&1; do sleep 2; done
	@echo "SGLang ready"

stop-gpu: ## Stop SGLang FLUX server
	@wsl -d Ubuntu-24.04 -u root -- /bin/bash -c 'pkill -f sglang.launch_server 2>/dev/null' || true
	@echo "SGLang stopped"

down: ## Stop the backend server
	@pkill -f "uvicorn backend.app.main:app" 2>/dev/null || true
	@echo "Server stopped"

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
