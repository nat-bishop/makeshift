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

If you're using cloud services (Gemini) instead of local GPU servers, start only what you need:

```bash
make dev SERVICES=api              # backend only (cloud LLM + cloud images)
make dev SERVICES="api gpu"        # backend + local image server
make dev SERVICES="api llm"        # backend + local LLM
```

You can also run servers without launching Godot:

```bash
make dev-servers                   # all servers
make dev-servers SERVICES=api      # just the backend
```

## Commands

| Command | Description |
|---------|-------------|
| `make dev` | Start all servers + launch game |
| `make dev-servers` | Start all servers (no game) |
| `make play` | Launch Godot game (servers must be running) |
| `make godot` | Open Godot editor |
| `make install` | Install all dependencies |
| `make test` | Run all tests |
| `make check` | Lint + typecheck + test |
| `make fix` | Lint with autofix |
| `make format` | Format code |
| `make help` | Show all available targets |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system overview, object creation pipeline, image generation, rule engine, collision/cascade system, persistence, WebSocket protocol
- [Game Design](docs/GAME_DESIGN.md) — tag system, rule philosophy, object economy, equipment, durability, levels
- [CLAUDE.md](CLAUDE.md) — developer quick-reference (conventions, gotchas, API endpoints)
