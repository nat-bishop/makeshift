# Object System V2 — Stage 2: Godot + Cleanup

Stage 1 (complete): Backend produces V2 blueprints with substance profiles, derived traits, embeddings, combat profiles, and backward-compatible V1 tags/behaviors. The Godot client works but doesn't use the new data yet.

Stage 2 makes the Godot client consume the new data: substance-based physics, verb behavior system with embedding targeting, parameterized rules, new engine components (holdable, climbable, etc.), then removes all V1 code.

Full design rationale: `docs/design-object-system-v2.md` and `.claude/plans/golden-dreaming-codd.md`

---

## Checklist

### 1. Substance-Based Physics

Replace TagPhysicsMap with substance profiles from the blueprint.

- [ ] Create `godot/scripts/data/substance_physics.gd`
  - [ ] `resolve_physics(blueprint: Dictionary) -> Dictionary` — reads `substance_profile` from blueprint, returns {mass, gravity, friction, bounce, damping}
  - [ ] Apply state-derived physics: solid (gravity=1.0, damping=0.5), liquid (gravity=1.0, damping=2.0), gas (gravity=-0.2, damping=4.0), energy (gravity=0.0, damping=0.0)
  - [ ] Apply tag modifiers from blueprint tags: HEAVY (mass += 5.0), LIGHT (mass *= 0.15), BOUNCY (bounce=0.9), STICKY (friction=2.0), FLYING (gravity=0.0)
  - [ ] Fallback: if no `substance_profile` in blueprint, use existing TagPhysicsMap (V1 compat during transition)
- [ ] Update `godot/scripts/systems/physics_composer.gd`
  - [ ] Check for `substance_profile` key in blueprint first
  - [ ] If present: use `substance_physics.resolve_physics()`
  - [ ] If absent: use existing tag-based composition (V1 path)
- [ ] Update `godot/scenes/game_object/physics_applicator.gd`
  - [ ] Pass full blueprint dict to composer (not just tags)
- [ ] Update `godot/scenes/game_object/game_object.gd`
  - [ ] `init_from_blueprint()`: extract substance_profile, pass to physics applicator
  - [ ] `starting_durability`: read from blueprint (backend now computes this from substance)

**Test:** Create "metal sword" and "cloth flag" — verify metal feels heavier (mass 3.0 vs 0.3). Create "rubber ball" — verify it bounces (bounce 0.9). Debug overlay shows substance-derived values.

### 2. Verb Behavior System

Replace BehaviorExecutor with embedding-based verb targeting.

- [ ] Create `godot/scripts/systems/movement_utils.gd`
  - [ ] Port from `behavior_executor.gd`: `apply_movement_force()`, `apply_patrol()`, friction compensation, velocity clamping
  - [ ] These are shared between VerbBehaviorSystem and any future capabilities
- [ ] Create `godot/scripts/systems/verb_behavior_system.gd`
  - [ ] Reads `behaviors` (V2 format: verb + target) and `behavior_embeddings` from blueprint
  - [ ] Reads `identity_embedding` from each nearby game object
  - [ ] Stores pre-computed trait-state embeddings (hardcoded ~10 vectors, same values backend computed at startup — shipped as constants or loaded from a config file the backend generates)
  - [ ] Target scanning (every 0.3s):
    - For each behavior, for each nearby object in "game_objects" group:
      - `score = max(dot(target_embedding, object.identity_embedding), max(dot(target_embedding, trait_embedding[t]) for t in object.current_dynamic_traits))`
    - Pick highest score above threshold (0.5), break ties by distance
  - [ ] Verb execution:
    - `destroy`: move toward target using `movement_utils`, apply melee damage on contact (use element color from combat_profile). Damage amount from `combat_profile.melee_damage`
    - `eat`: move toward target, on contact: apply rapid damage to target, heal self 25% of target's max HP, destroy target
    - `investigate`: move toward target at 0.5× speed, stop at medium range (128px)
    - `follow`: move toward target, maintain close distance (64px)
    - `protect`: follow protected target, switch to destroy threats near it (two-state: FOLLOW ↔ ATTACK)
    - `flee`: move away from target at 1.5× speed
  - [ ] Verb priority: flee=1, protect=2, destroy=3, eat=4, follow=5, investigate=6. Only highest-priority active verb executes movement per frame.
  - [ ] Error handling: same pattern as BehaviorExecutor (5 consecutive errors disables behavior)
- [ ] Update `godot/scenes/game_object/game_object.gd`
  - [ ] If blueprint has `behavior_embeddings`: instantiate `VerbBehaviorSystem` as child
  - [ ] Else if blueprint has V1 `behaviors`: instantiate `BehaviorExecutor` as child (V1 fallback)
  - [ ] Store `identity_embedding` as a var on the node (for other objects to read during targeting scans)
  - [ ] Expose `get_identity_embedding() -> Array` method

**Test:** Create cop with `eat → "food, especially donuts"`, `destroy → "criminals"`, `flee → "ghosts"`. Place donut, robber, ghost in scene. Verify cop eats donut (moves toward, consumes), attacks robber (moves toward, damages), flees ghost (moves away). Create firefighter with `destroy → "fires and burning things"`. Place campfire. Set a tree on fire (via rule). Verify firefighter targets both.

### 3. Parameterized Rules

Use combat_profile values for differentiated damage.

- [ ] Update `godot/scripts/systems/effect_executor.gd`
  - [ ] When executing DAMAGE effects for parameterized rules, check source object for `combat_profile` dict
  - [ ] If `combat_profile` present and rule is parameterized: use pre-computed coefficient × target profile value
  - [ ] If absent: use hardcoded damage value (V1 fallback)
  - [ ] Rules to parameterize (source-side, pre-computed):
    - `sharp_living_cut`: use `combat_profile.melee_damage` instead of hardcoded 25
    - `sharp_breakable_damage`: use `combat_profile.melee_damage` instead of hardcoded 25
    - `heavy_breakable_crush`: use `combat_profile.crush_damage` instead of hardcoded 20
  - [ ] Rules to parameterize (both sides, coefficient × target):
    - `heat_flammable_ignite`: use `source.combat_profile.fire_dps_coefficient * target.substance_profile.burn_rate` instead of hardcoded 10
    - `electric_metallic_electrify`: use `30 * target.substance_profile.conductivity` instead of hardcoded 30
    - `wind_light_push`: use `45 * (0.3 / max(target.substance_profile.mass, 0.05))` instead of hardcoded 45
    - `reflective_heat_reflect`: use `10 * source.substance_profile.heat_output` instead of hardcoded 10
- [ ] Update `godot/scenes/game_object/game_object.gd`
  - [ ] Store `combat_profile` and `substance_profile` dicts from blueprint
  - [ ] Expose `get_combat_profile() -> Dictionary` and `get_substance_profile() -> Dictionary`

**Test:** Create "match" (fire substance, tiny) and "lava flow" (lava substance, large). Both ignite a wooden plank — match should deal ~8 dps (heat_output 1.5 × burn_rate 0.8 × base 10 / scaling), lava should deal ~24 dps. Create dagger (metal, small, sharp) and greatsword (metal, large, sharp+heavy) — dagger deals ~25 cut damage, greatsword deals ~60.

### 4. New Engine Components (incremental, each independent)

Add new tag values and Godot components as each is built. Each follows the pattern: add tag to enum → add to trait_deriver mapping → build Godot component → add to LLM system prompt.

- [ ] **HOLDABLE + THROWABLE** (~1 week)
  - [ ] Add HOLDABLE, THROWABLE to Tag enum
  - [ ] `godot/scripts/interactions/holdable.gd` — Component node. Player presses interact near holdable → object reparented to player, follows player position, physics disabled
  - [ ] `godot/scripts/interactions/throwable.gd` — Component node. While holding throwable, action key → re-enable physics, apply impulse in facing direction
  - [ ] Update `player.gd`: new `holding` state, interact input handling, hold/throw logic
  - [ ] Update `game_object.gd`: attach Holdable/Throwable components when tags present
- [ ] **CLIMBABLE** (~1 week)
  - [ ] Add CLIMBABLE to Tag enum
  - [ ] `godot/scripts/interactions/climbable.gd` — Component node. Area2D on the object. Player overlapping + pressing up → override gravity, allow vertical movement
  - [ ] Update `player.gd`: new `climbing` state, vertical movement while on climbable surface
- [ ] **EDIBLE** (~3 days)
  - [ ] Add EDIBLE to Tag enum
  - [ ] `godot/scripts/interactions/edible.gd` — Component node. Player presses interact → object destroyed, player healed based on substance durability
  - [ ] Update `player.gd`: interact input triggers edible consumption
- [ ] **CONTAINING** (~1 week)
  - [ ] Add CONTAINING to Tag enum
  - [ ] `godot/scripts/interactions/container.gd` — Component node. Holds child objects. Release contents on damage or player interact. Bucket of water: glass container with water child.
- [ ] **Capabilities** (each ~3-5 days)
  - [ ] `heal_field` — Area2D that passively heals nearby LIVING objects. Port from existing campfire implied behavior.
  - [ ] `timed_explosion` — Timer + detonate. Port from existing EXPLOSIVE implied behavior.
  - [ ] `guard_area` — Area2D that attacks anything entering radius. Port from HOSTILE field behavior.
  - [ ] `attach_on_contact` — Create PinJoint2D between objects on collision. NEW.
  - [ ] `pull_holder` — Apply force pulling attached holder toward a target point. NEW. Requires attach_on_contact.
  - [ ] `emit_substance` — Periodically spawn small objects of a given substance. NEW.

### 5. Remove V1 Code

After verb behavior system and substance physics are stable.

- [ ] Remove `backend/app/models/behaviors.py` (V1 behavior DSL — parser, BehaviorSpec, triggers, actions, targets)
- [ ] Remove `backend/app/models/tag_behaviors.py` (V1 implied behaviors — replaced by implied_behaviors_v2)
- [ ] Remove V1 code paths in `backend/app/creator/agent.py` (old SYSTEM_PROMPT, old create_object function)
- [ ] Remove V1 `CreatorOutputSpec.signature` field and its validator
- [ ] Remove V1 `GameObjectBlueprint` model (keep only V2)
- [ ] Remove backward-compat V1 behavior conversion in blueprint builder
- [ ] Remove `godot/scripts/systems/behavior_executor.gd`
- [ ] Remove `godot/scripts/data/behavior_maps.gd`
- [ ] Remove `godot/scripts/data/tag_physics_map.gd`
- [ ] Remove V1 fallback paths in `physics_composer.gd` and `game_object.gd`
- [ ] Remove 15 tags from `LLM_VISIBLE_TAGS` (substance-absorbed + element-absorbed). Keep in Tag enum for internal rule matching.
- [ ] Update `TAG_CONTRADICTIONS` — remove pairs now prevented by substance/element structure
- [ ] Update `TAG_AUTO_CORRECTIONS` — remove entries for removed tags
- [ ] Update `TAG_DESCRIPTIONS` — only describe LLM-visible tags

### 6. Documentation + Eval Update

- [ ] Update `CLAUDE.md` — new architecture description, new LLM schema, substance profiles, behavior verbs, embedding system
- [ ] Update `docs/ARCHITECTURE.md` — object creation pipeline with V2 flow
- [ ] Update `docs/GAME_DESIGN.md` — substance system, element system, reduced tag set, behavior verbs
- [ ] Update eval suite — all 90 cases with V2 expected values (substance, element, reduced tags)
- [ ] Run full eval comparison: V2 substance accuracy, element accuracy, trait coverage, behavior quality
- [ ] Update `docs/LEVEL_DESIGN.md` if environment bodies need substance references

---

## Verification Criteria (Stage 2 done when)

- [ ] `make check` passes (lint + typecheck + test)
- [ ] Metal sword feels heavier than wooden stick in-game (debug overlay shows substance-derived mass)
- [ ] Cop/donut/robber/ghost targeting test passes (embedding-based verb behaviors work)
- [ ] Firefighter targets a tree that catches fire mid-scene (trait-state embedding augmentation works)
- [ ] Greatsword deals more damage than dagger (parameterized rules work)
- [ ] Campfire fire vs lava fire deal different damage to wood (combat_profile differentiation)
- [ ] At least 2 new engine components working (e.g., holdable + edible)
- [ ] No V1 behavior code remains (behaviors.py, behavior_executor.gd, behavior_maps.gd, tag_physics_map.gd deleted)
- [ ] All 3 existing levels still playable
- [ ] CLAUDE.md and docs updated
