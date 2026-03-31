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
- ARCHITECTURE.md Image Generation Pipeline: image generator changed from Flux (fal.ai) to Gemini (`gemini_client.py`). Model is configured via `settings.image_model` (default `gemini-3.1-flash-image-preview`). Cache key is a hash of the full `build_prompt()` output string. `VisualDescriptor` was simplified from 9 fields to 2: `visual_description` (free text) and `size_category`. `generate_placeholder()`, `TAG_COLOR_MAP`, `placeholder_png_base64`, and `get_sprite_url()` were all removed — no placeholder is generated or sent. `rembg_model` setting was removed from config; local bg removal now uses `gpu_bg.make_gpu_remover()` directly.
- EventBus signal count: was documented as 4 in early versions; grew to 11 as placement, creation flow, and gameplay signals were added. ARCHITECTURE.md has the authoritative signal table; CLAUDE.md autoload table lists all signals by name. `player_died` was added with no docs update — check event_bus.gd directly when signal count matters.
- ARCHITECTURE.md WebSocket payload for `sprite_ready`: previously embedded base64 PNG (`sprite_png_base64, width, height`); now sends `sprite_url` only — Godot fetches the PNG via a separate HTTP request. This is a recurring shape of change (delivery mechanism changes without docs update).
- ARCHITECTURE.md Object Creation Pipeline step 7: `placeholder_png_base64` was fully removed from `CreateObjectResponse` — no placeholder generated, no base64 sent. On `sprite_failed`, placement proceeds without a texture (ghost has no sprite). Any mention of "placeholder" in pipeline steps or signal tables is stale.
- ARCHITECTURE.md Image pipeline step 5: previously described per-size LANCZOS resize to SIZE_PIXEL_MAP values (32-128px). Now saves at 512×512 (TEXTURE_RESOLUTION); client-side size_category determines world display size. Prompt style also changed from "pixel art" to "mixed media collage style paper cutout" — both the prompt text and the output size are drift-prone.

## Key structural decisions made during field system sync

- `trigger_mode` on `InteractionRule` is a backend data model field but its primary consumer is the Godot client (`TagField`, `CollisionResolver`). When new FIELD rules are added to `rules_data.py`, the only doc impact is the rule count in CLAUDE.md and GAME_DESIGN.md.
- `FieldConfig` is a static class (like `BehaviorMaps`), not an autoload — listed in CLAUDE.md "Key systems" paragraph.
- `TagField` is a per-object child node (like `BehaviorExecutor`), not an autoload — listed in "Key systems" paragraph. Both share the same lazy-instantiation pattern from `game_object.gd`.
- The physics table in ARCHITECTURE.md added an "Extra" column for STICKY's PinJoint2D behavior. If more tags get non-physics side effects, extend that column rather than adding prose.
- ARCHITECTURE.md Error fallback section for `BehaviorExecutor` said "3 errors" but code has `MAX_BEHAVIOR_ERRORS = 5`. Corrected. When checking error thresholds, read the const directly.

**Why:** Drift between error threshold docs and code (3 vs 5) is a quick mislead. Always verify numeric constants from the actual GDScript file.
**How to apply:** For any "disables after N errors" style gotcha, grep for the const before writing or reading the doc value.

## CLI tools and Makefile targets (added commit 60b304a)

- `make serve` does NOT exist — the correct target is `make dev-servers SERVICES=api`. CLAUDE.md had this wrong; now fixed.
- CLI tools (`cli-create`, `cli-image`, `cli-sprite`, `cli-status`) call `backend/app/cli.py` via `python -m app.cli`. Entry point registered as `makeshift` in pyproject.toml.
- `BG_REMOVAL_MODEL` env var was added (replaces the old `REMBG_MODEL`). Default: `briaai/RMBG-2.0`. Always check `.env.example` as the authoritative source for env var names and defaults.
- `LOCAL_IMAGE_MODEL` in CLAUDE.md drifted from `.env.example` (4B vs 9B). `.env.example` is the canonical default for env vars; CLAUDE.md/README should match it.

**Why:** Makefile targets are the ground truth for runnable commands. Any time commands change in the Makefile, CLAUDE.md Commands section and README.md Commands table both need updating.
**How to apply:** When syncing docs after commits that touch the Makefile or `.env.example`, always read both files directly and cross-check every command and env var listed in CLAUDE.md and README.md.

## Image pipeline multi-backend (commit 6e03ef7 onwards)

- ARCHITECTURE.md step 3 said "Gemini generate" but there are now three backends: `gemini`, `local` (SGLang FLUX), `fal`. Step 3 must be backend-agnostic.
- `services/sglang/README.md` tends to drift on model names (had 7B in table/config example, docker-compose uses 9B). Always verify model names from `docker-compose.yml`, not the README.

**How to apply:** When image pipeline or sglang services change, check `docker-compose.yml` and `.env.example` together with `services/sglang/README.md` for model name consistency.

## Key structural decisions made during behavior system sync

- BehaviorMaps is a RefCounted static class, NOT an autoload — noted in ARCHITECTURE.md to avoid confusion.
- ON_USE trigger exists in the enum but is not yet implemented in BehaviorExecutor — not documented as a gotcha since the system just won't fire it; no misleading behavior.
- Phase 2 features (ALL_IN_RANGE target, ON_TAG_REMOVED, HEALTH_ABOVE/BELOW_HALF conditions) were intentionally omitted from all docs since they are not yet implemented.

**Why:** Stale "planned feature" docs actively mislead. If it's not in the code, it's not in the docs.
**How to apply:** When reviewing docs for completeness, cross-check enum values against BehaviorExecutor match statements to find unimplemented cases before documenting them.

## Tag/behavior system overhaul (2026-03-30)

- ARCHITECTURE.md rule count in the `RuleResolver` intro line must match the actual rule count in `rules_data.py`. After this overhaul: 50 rules (was 53). The "24 of N" FIELD annotation count is approximate — only update the total.
- ARCHITECTURE.md physics table drifts when tags are removed. SLIPPERY was removed but its row persisted. After any tag pruning, cross-check `tag_physics_map.gd` against the physics table.
- `FieldConfig.FIELD_TAGS` is the authoritative source for which tags are continuous vs periodic and at what range. ARCHITECTURE.md Field System table and GAME_DESIGN.md Field Modes section must match it. GLOWING was removed from FIELD_TAGS but persisted in both docs.
- `BehaviorTarget` enum: `NEAREST_OBJECT` was never a valid value. Docs and level blueprints that use it are stale. Valid targets: SELF, NEAREST_LIVING, NEAREST_PLAYER, CONTACT_BODY.
- LEVEL_DESIGN.md blueprint tags must use current tag names. After renames (CORROSIVE→ACIDIC, CONDUCTING→METALLIC) and pruning (SOLID, FLEXIBLE, SLIPPERY removed), ALL blueprint examples need updating — there are many instances across Levels 1-5 and Sandbox. `SOLID` was especially pervasive as it was included reflexively in almost all old blueprints.
- GAME_DESIGN.md "Pruned tags / Renamed" line had the old-name pairs backwards ("ACIDIC → ACIDIC, METALLIC → METALLIC"). Always write it as old→new.
- Behavior limit in ARCHITECTURE.md pipeline step 4 and behavior system section must match the LLM constraint: was "0-3 behaviors" (old list model), now "0-1 signature behavior" (string field).

**How to apply:** After any tag/rule system change, check: (1) rule count in resolver intro, (2) physics table rows vs `tag_physics_map.gd`, (3) FieldConfig table vs `field_config.gd`, (4) BehaviorTarget enum members vs `behaviors.py`, (5) all blueprint examples in LEVEL_DESIGN.md for old tag names.

## EnvironmentBody pattern (2026-03-29)

- New node types that are "almost like GameObject but not quite" belong in the CLAUDE.md Key systems paragraph (non-autoload systems) with a dense summary, and get a full section in ARCHITECTURE.md. The LEVEL_DESIGN.md checklist had prerequisite items that needed marking done.
- The solidity/filter duality (`solid=false` → no filter, `solid=true` → FIELD filter) is non-obvious and belongs as a CLAUDE.md gotcha, not just in ARCHITECTURE.md prose.
- EnvironmentBody intentionally does NOT use `TagField` — uses a rectangular Area2D inline because `TagField` is circular and undersized for large bodies. This is a design decision worth preserving so future devs don't "fix" it.

**How to apply:** When a new node type is added that partially overlaps an existing system (TagField, GameObject), document why it diverges rather than just describing what it does.

## Signal count drift (2026-03-29)

- EventBus signal count drifted again: went from 11 to 14 with addition of `player_damaged`, `player_healed`, `effect_applied`. CLAUDE.md autoload table listed the count explicitly ("11 signals") which becomes stale immediately. ARCHITECTURE.md signal table is the authoritative list; CLAUDE.md just names them.
- Physics table in ARCHITECTURE.md had an "Extra" column for STICKY side effects but no `damping` column — the column was missing entirely. When `PhysicsApplicator` gains a new property from `TagPhysicsMap`, the table in ARCHITECTURE.md needs a new column.
- Player physics constants are documented as gotchas in CLAUDE.md only (not ARCHITECTURE.md) — `EFFECTIVE_MASS` changed from 5.0 to 0.4 without any doc update. These values are in `player.gd` constants at top of file; always verify before citing them.
- `Backend` autoload `process_mode = PROCESS_MODE_ALWAYS` is the kind of silent fix that's easy to miss — no new class, no new signal, just a property assignment in `_ready()`. Worth a gotcha entry because forgetting it breaks sprite delivery during pause.
- DOT timer node lifecycle: `queue_free()` alone is insufficient to replace a named child node within the same frame — must `stop()` + `remove_child()` first. This is a Godot-specific pattern worth preserving as a gotcha.
