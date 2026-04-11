# Design Documentation

Architecture and design docs for the Makeshift game engine.

## Documents

| Doc | What it covers |
|-----|----------------|
| [Architecture](architecture.md) | Core system design: collision rules (force), state propagation, creature behavior, caching strategy |
| [Engine Primitives](engine-primitives.md) | Everything the engine can execute: physics, force, 4 states, state propagation, essential-state destruction, affordances, creature behavior |
| [Creation Pipeline](creation-pipeline.md) | Call sequence from player input to spawned object: name gen, parallel questions, state properties, batching, call budgets |
| [LLM Design Patterns](llm-design-patterns.md) | Core patterns for decomposing problems into LLM calls: fan-out, sequential seeding, filter, constrained decoding |
| [Cache](cache.md) | Cache design: collision rules (persistent), behavior (session-local), lazy evaluation on miss |
| [Future Features](future-features.md) | Deferred ideas: compound sprites, object evolution, additional states/affordances |
| [Future Optimizations](future-optimizations.md) | Deferred optimizations: raw httpx + constrained decoding, stamina retry |

## Reading order

1. **LLM Design Patterns** — decomposition patterns and constraints
2. **Architecture** — system design (collision, propagation, behavior)
3. **Engine Primitives** — building blocks (what numbers the LLM outputs, what the engine does)
4. **Creation Pipeline** — end-to-end flow (batching, timing, budgets)
