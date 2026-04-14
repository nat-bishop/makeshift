# Makeshift

"Scribblenauts meets Terraria" — a 2D physics sandbox where you type text descriptions to create game objects. An LLM generates physics blueprints via parallel 1-token calls, FLUX generates sprites locally, and objects interact through a unified behavior system with state propagation.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [Godot 4.6 **Mono/.NET**](https://godotengine.org/download/) (the .NET variant — the standard build won't compile the C# client)
- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)
- API keys: [Google AI](https://ai.google.dev/) (Gemini — LLM only); GPU server running FLUX (for sprite generation) and BiRefNet (for background removal) via Docker

## Quick Start

```bash
# Configure environment
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY

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

LLM quality gates — call a real LLM and cost money. Separate from `make test`.

```bash
make eval              # run all evals
make eval-creation     # creation pipeline quality
make eval-behavior     # behavior + screening quality
make eval-judge        # all evals + LLM judge for visual descriptions
```

Eval cases in `backend/evals/fixtures/eval_suite.yaml`. Results in `backend/evals/results/`.

## Documentation

- [Design Documentation](docs/index.md) — architecture, engine primitives, creation pipeline, caching, LLM design patterns
- [CLAUDE.md](CLAUDE.md) — developer quick-reference (conventions, gotchas, API endpoints)
