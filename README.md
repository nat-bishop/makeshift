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

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system overview, object creation pipeline, image generation, rule engine, collision/cascade system, persistence, WebSocket protocol
- [Game Design](docs/GAME_DESIGN.md) — tag system, rule philosophy, object economy, equipment, durability, levels
- [CLAUDE.md](CLAUDE.md) — developer quick-reference (conventions, gotchas, API endpoints)
