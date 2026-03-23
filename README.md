# Makeshift

"Scribblenauts meets Terraria" — a 2D physics sandbox where you type text descriptions to create game objects. An LLM generates tagged blueprints, a generative model produces pixel art sprites, and objects interact through a tag-based rule system with chain reactions.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [Godot 4.3](https://godotengine.org/) (for the client)
- API keys: [Google AI](https://ai.google.dev/) (Gemini) + [fal.ai](https://fal.ai/) (Flux image generation)

## Quick Start

```bash
# Configure environment
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY and FAL_KEY

# Install dependencies
uv sync

# Run backend server (from repo root)
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Then open the Godot client:

```bash
godot --path godot/
# Press F5 in the editor to play
```

## Commands

| Command | Description |
|---------|-------------|
| `uv sync` | Install all dependencies (including dev) |
| `uv sync --no-dev` | Install production dependencies only |
| `uv run pytest` | Run all tests |
| `uv run pytest -k "test_name"` | Run a single test by name |
| `uv run ruff check backend/` | Lint |
| `uv run ruff check backend/ --fix` | Lint with autofix |
| `uv run ruff format backend/` | Format |
| `uv run mypy backend/` | Type checking |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system overview, object creation pipeline, image generation, rule engine, collision/cascade system, persistence, WebSocket protocol
- [Game Design](docs/GAME_DESIGN.md) — tag system, rule philosophy, object economy, equipment, durability, levels
- [CLAUDE.md](CLAUDE.md) — developer quick-reference (conventions, gotchas, API endpoints)
