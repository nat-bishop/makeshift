---
name: docs_drift_patterns
description: Common sources of drift and duplication across CLAUDE.md, docs/ARCHITECTURE.md, docs/GAME_DESIGN.md
type: project
---

## Where duplication tends to creep in

- CLAUDE.md Architecture section and ARCHITECTURE.md both describe subsystems. Pattern: CLAUDE.md holds a one-liner + pointer; ARCHITECTURE.md holds the full detail.
- GAME_DESIGN.md tends to describe design rationale while ARCHITECTURE.md covers implementation. Keep cost tables in GAME_DESIGN.md, keep numeric engine mappings in ARCHITECTURE.md.
- The Godot client table (autoloads) lives only in CLAUDE.md. Non-autoload systems (BehaviorExecutor, BehaviorMaps, EffectExecutor, PhysicsApplicator) are listed as "Key systems" in the same section rather than the table.

## Which files go stale

- CLAUDE.md Data Model Flow: needs updating whenever new computed fields are added to GameObjectBlueprint or new top-level fields appear in CreatorOutput.
- CLAUDE.md Gotchas: needs entries for any new model validator rules that have non-obvious constraints (e.g., ON_TAG_ADDED requires trigger_tag).
- ARCHITECTURE.md System Overview diagram: the ASCII diagram drifts when new client-side systems are added. Update both the diagram and the pipeline steps together.
- docs/ARCHITECTURE.md Session & Persistence: blueprint_json schema is implicit — note when new fields are added that don't require migration.
- ARCHITECTURE.md Object Creation Pipeline: deferred spawn / placement mode steps are easy to miss when adding new signals or UX states. Pipeline step count has grown to 10; check game.gd and event_bus.gd together when updating.
- ARCHITECTURE.md Image Generation Pipeline: cache key description and Flux model name drift independently from each other. Cache key is now a hash of the full prompt string (not individual VisualDescriptor fields) — easy to misremember. Model is `fal-ai/flux-pro/v1.1`, configured via `settings.image_model` in config.py.
- EventBus signal count: was documented as 4 in early versions; grew to 11 as placement, creation flow, and gameplay signals were added. ARCHITECTURE.md has the authoritative signal table; CLAUDE.md autoload table lists all signals by name. `player_died` was added with no docs update — check event_bus.gd directly when signal count matters.
- ARCHITECTURE.md WebSocket payload for `sprite_ready`: previously embedded base64 PNG (`sprite_png_base64, width, height`); now sends `sprite_url` only — Godot fetches the PNG via a separate HTTP request. This is a recurring shape of change (delivery mechanism changes without docs update).
- ARCHITECTURE.md Image pipeline step 5: previously described per-size LANCZOS resize to SIZE_PIXEL_MAP values (32-128px). Now saves at 512×512 (TEXTURE_RESOLUTION); client-side size_category determines world display size. Prompt style also changed from "pixel art" to "mixed media collage style paper cutout" — both the prompt text and the output size are drift-prone.

## Key structural decisions made during behavior system sync

- BehaviorMaps is a RefCounted static class, NOT an autoload — noted in ARCHITECTURE.md to avoid confusion.
- ON_USE trigger exists in the enum but is not yet implemented in BehaviorExecutor — not documented as a gotcha since the system just won't fire it; no misleading behavior.
- Phase 2 features (ALL_IN_RANGE target, ON_TAG_REMOVED, HEALTH_ABOVE/BELOW_HALF conditions) were intentionally omitted from all docs since they are not yet implemented.

**Why:** Stale "planned feature" docs actively mislead. If it's not in the code, it's not in the docs.
**How to apply:** When reviewing docs for completeness, cross-check enum values against BehaviorExecutor match statements to find unimplemented cases before documenting them.
