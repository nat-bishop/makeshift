# Makeshift Documentation

Reference documentation for the Makeshift game engine.

## How the system works

Start here to understand the architecture. Read in order for a complete picture, or jump to a specific doc when you need it.

| Doc | When to read it | What it covers |
|-----|-----------------|----------------|
| [LLM Design Patterns](llm-design-patterns.md) | First. Foundational patterns everything else builds on. | Decomposing problems into LLM calls: fan-out, sequential seeding, filter. Latency math, parallelism rules, model size tradeoffs. |
| [Architecture](architecture.md) | Second. The system design. | Unified behavior system (active + reactive objects), staged evaluation, state propagation, creation cache, implementation decisions. |
| [Engine Primitives](engine-primitives.md) | Reference. Come back when you need exact values. | Every number the LLM outputs and what the engine does with it: physics, durability tiers, 4 states + contradictions, affordances, behavior actions, utility scoring. |
| [Creation Pipeline](creation-pipeline.md) | When working on creation flow or call budgets. | End-to-end LLM call sequence from player input to spawned object. Call counts, wall times, scaling for 7/15/30-object scenes. |
| [Cache](cache.md) | When working on caching or spawn integration. | Creation cache (persistent, correctness) and behavior cache (scene-local, in-memory). Key normalization, model version coherence, edge cases. |

## Level and content design

| Doc | When to read it | What it covers |
|-----|-----------------|----------------|
| [Level Design](level-design.md) | When creating or modifying levels. | Design principles, BaseLevel API, seed object blueprint format, GameManager level registration. |
| [Animation Pipeline](animation-pipeline.md) | When implementing sprite animation. **Experimental — not yet in production.** | 2x2 spritesheet generation via Gemini, cell creator LLM, post-processing, Godot integration. |

## Deferred work

| Doc | When to read it | What it covers |
|-----|-----------------|----------------|
| [Future Features](future-features.md) | When considering new mechanics or revisiting deferred ideas. | Compound sprites, creature death remains, object evolution, additional states/affordances, triadic reasoning. |
| [Future Optimizations](future-optimizations.md) | When investigating performance or reliability on the local LLM path. | Raw httpx + constrained decoding, stamina retry library. |

## Background research

Design decisions were informed by these research documents. Not Makeshift-specific, but they explain why the system works the way it does.

| Doc | When to read it | What it covers |
|-----|-----------------|----------------|
| [LLM Behavior Systems](research/llm-behavior-systems.md) | When questioning a design decision or exploring alternatives. | Academic review: GROMIT, Voyager, Generative Agents, GOAP, behavior trees, constrained decoding. |
| [Scribblenauts Deep Dive](research/scribblenauts-deep-dive.md) | When thinking about content scaling, balancing, or dictionary-to-object pipelines. | Reverse-engineering of 5th Cell's Objectnaut engine: 22K objects, 9 behavior verbs, why hand-authoring dominated. |

## Historical

| Doc | When to read it | What it covers |
|-----|-----------------|----------------|
| [Benchmark Results](archive/benchmark_results.md) | Only if investigating local model performance history. | March 2026 benchmarks comparing Gemini Flash Lite vs Qwen3.5-35B configurations. Uses old system concepts. |

## Quick reference

- **Developer reference**: [CLAUDE.md](../CLAUDE.md) — commands, architecture routing, gotchas
- **Getting started**: [README.md](../README.md) — prerequisites, quick start, CLI tools
