# V3 Design: Question-Based Object System

V2 with fewer enums, LLM-generated physics, and auto-populated interaction rules. The LLM replaces substance profiles, tag derivation, and 56 hand-authored rules with a graph of tiny cached questions. The engine keeps affordances, per-pair creature behavior, closed states, and cascade control — each earns its place by saving LLM calls or providing mechanical guarantees.

## Documents

| Doc | What it covers |
|-----|----------------|
| [Architecture](architecture.md) | Core system design: two interaction systems (passive vs intentional), pairwise cache, per-pair creature behavior, what's removed from V2 and why |
| [Engine Primitives](engine-primitives.md) | Everything the engine can execute: physics, outcomes, 7 states, affordances, creature behavior, fields |
| [Creation Pipeline](creation-pipeline.md) | Exact call sequence from player input to spawned object, batching, call budgets, scaling characteristics |
| [LLM Design Patterns](llm-design-patterns.md) | Core patterns for decomposing problems into LLM calls: fan-out, sequential seeding, filter, decomposition principle. The foundation everything else is built on |
| [Cache](cache.md) | Unified cache design: types, key normalization, separate DB, edge cases |
| [Future Features](future-features.md) | Ideas deferred from core: compound object sprites, creature death remains, object evolution, additional states and affordances |
| [Future Optimizations](future-optimizations.md) | Implementation optimizations evaluated but deferred: raw httpx + constrained decoding, stamina retry |

## Reading order

1. **LLM Design Patterns** — understand the constraints and decomposition patterns (the foundation)
2. **Architecture** — understand the design (two interaction systems, pairwise cache)
3. **Engine Primitives** — understand the building blocks (what numbers the LLM outputs, what the engine does with them)
4. **Creation Pipeline** — understand the flow (batching, timing, hardware)

## What V3 removes from V2

- 16 substances + profiles → LLM-generated physics numbers
- 7 elements + traits → part of object description
- 7 categories → affordances + autonomous flag
- 31 tags (10 LLM-visible + 21 internal) → 7 interaction-only states
- 56 hand-authored rules → LLM-populated pairwise cache
- Tag derivation pipeline → not needed
- Seek/avoid lists + semantic target matching → per-pair creature behavior (staged evaluation)
- 6 behavior verbs → per-pair on-arrival actions (more expressive, per-relationship)
- Combat profiles → pairwise cache damage values

## What V3 keeps from V2

- Closed state vocabulary (smaller: 7 vs 31)
- State contradiction table (smaller: 4 pairs vs 16)
- Cascade control (depth 3, dedup, no recursive triggers)
- Collision detection + Area2D fields
- Image pipeline (sprite gen, bg removal, caching)
- WebSocket delivery, session persistence
