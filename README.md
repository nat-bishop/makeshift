# Makeshift

"Scribblenauts meets Terraria" — a 2D physics sandbox where you type text descriptions to create game objects. An LLM generates tagged blueprints, a generative model produces pixel art sprites, and objects interact through a tag-based rule system with chain reactions.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [Godot 4.3](https://godotengine.org/) (for the client)
- API keys: [Google AI](https://ai.google.dev/) (Gemini — LLM + image generation); [fal.ai](https://fal.ai/) only if using cloud background removal

## Quick Start

```bash
# Configure environment
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY (FAL_KEY only needed for cloud bg removal)

# Install dependencies
make install

# Start all servers + launch game
make dev
```

You can also run servers without launching Godot:

```bash
# Typical workflow: start containers once, restart API freely
make gpu                           # start Docker GPU containers (detached, run once)
make api                           # start FastAPI dev server (foreground, Ctrl-C to restart)
make stop                          # stop everything
```

## Commands

| Command | Description |
|---------|-------------|
| `make gpu` | Start Docker GPU containers (detached) |
| `make api` | Start FastAPI dev server (foreground, auto-reload) |
| `make dev` | Start all servers + launch game |
| `make gpu-restart` | Restart Docker containers |
| `make gpu-logs` | Tail Docker container logs |
| `make stop` | Stop all servers and clean up |
| `make play` | Launch Godot game (servers must be running) |
| `make godot` | Open Godot editor |
| `make install` | Install all dependencies |
| `make test` | Run all tests |
| `make check` | Lint + typecheck + test |
| `make fix` | Lint with autofix |
| `make format` | Format code |
| `make help` | Show all available targets |

### CLI tools (no server needed)

```bash
make cli-create PROMPT="fire sword"   # run LLM creator, print JSON blueprint
make cli-image PROMPT="a red sword"   # generate raw image (no bg removal)
make cli-sprite PROMPT="fire sword"   # full pipeline: LLM → image → bg removal → crop
make cli-status                       # check health of configured services
```

### Evals

Evaluate creator agent output quality. Evals call a real LLM and cost money — they are separate from `make test`.

```bash
# Run evals and save results (50 cases, ~2-5 min)
cd backend && uv run python -m evals.run_eval

# Run a specific prompt variant
cd backend && uv run python -m evals.run_eval --variant v2

# Filter to specific cases
cd backend && uv run python -m evals.run_eval --cases "fire sword,rock"

# Compare two saved results (no LLM calls — instant)
cd backend && uv run python -m evals.run_comparison --a baseline --b v2

# Analyze a single saved result
cd backend && uv run python -m evals.run_comparison --a baseline

# Pytest runner (also saves results)
cd backend && uv run pytest evals/test_eval.py -v
```

**4 metrics** per case: Validity (deterministic rule checks), Relevance, Creativity, Coherence (LLM-as-judge via Gemini). Results saved as structured JSON to `backend/evals/results/` with pre-parsed tags/behaviors/size, retry counts, and aggregate stats. Comparison uses Wilcoxon signed-rank test for statistical significance. Distribution analysis shows tag/behavior/size frequencies across all objects.

Add prompt variants in `backend/evals/prompts.py`. Test cases in `backend/evals/dataset.py` (50 cases across 9 categories).

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system overview, object creation pipeline, image generation, rule engine, collision/cascade system, persistence, WebSocket protocol
- [Game Design](docs/GAME_DESIGN.md) — tag system, rule philosophy, object economy, equipment, durability, levels
- [CLAUDE.md](CLAUDE.md) — developer quick-reference (conventions, gotchas, API endpoints)
