# V2 → V3 Migration

Design decisions and gaps that the V3 design docs don't address directly. Read this after the core design docs — it's the bridge between "what V3 is" and "how to get there from V2."

---

## Visual system

The V3 design specifies per-state visuals ([engine-primitives.md](engine-primitives.md)), but the full picture — what survives from V2, what's new, and how triggers change — isn't captured anywhere else.

### State visuals replace tag visuals

V2's `TagAnimations` class keys everything off tag strings. V3 replaces this with a state-keyed equivalent. The animation engine in `object_visual.gd` (sine-wave processors, particle management, shader application) stays — only the data tables change.

| V3 State | Particles | Shader | Anim | Light | What to reuse from V2 |
|----------|-----------|--------|------|-------|-----------------------|
| on_fire | Orange, upward | — | Flash (rapid) | Orange PointLight2D | HEAT_SOURCE particle config + flash timing |
| frozen | — | New ice shader | Color shift (blue) | — | FROZEN color_shift values |
| wet | Blue drips, downward | — | — | — | Nothing — WET had no V2 visual |
| electrified | Yellow sparks, burst | — | Flash (random interval) | — | ELECTRIC flash timing |
| poisoned | Green, upward | — | Color shift (green) | — | TOXIC particle config |
| corroded | Brown crumble, downward | — | Color shift (brown) | — | CORRODED color_shift values |
| molten | Orange, upward | Ripple (existing) | — | Orange glow | MOLTEN particle config + ripple shader |

New work: ice shader, wet/spark/crumble particles, PointLight2D management on state change.

### Physics-derived visuals (new pattern)

V2 triggers some animations from creation-time tags (FLYING, LIVING, BOUNCY). V3 has no creation-time tags. These visuals are still desirable — derive them from physics values instead.

| Visual | V2 trigger | V3 trigger | Threshold rationale |
|--------|-----------|------------|---------------------|
| Bobbing (vertical sine) | FLYING tag | `gravity < 25` | Balloon=5, smoke=15, ghost=30 all below. Normal=50 doesn't bob |
| Breathing (scale pulse) | LIVING tag | `autonomous == true` | All creatures breathe. LIVING was just auto-derived from CREATURE anyway |
| Bounce squash/stretch | BOUNCY tag + collision | `bounce > 60` | Tennis ball=70, super ball=99. Wood=20, clay=0 don't squash |

### Dropped V2 visuals

| Visual | V2 trigger | Why drop |
|--------|-----------|----------|
| Swaying (rotation sine) | WIND_SOURCE tag | Wind is a field effect, not a visual. No state equivalent |
| Alpha pulse | GLOWING tag | Internal-only V2 tag. No V3 equivalent |
| Jitter (position noise) | EXPLOSIVE, BRITTLE | Flavor. Tags don't exist in V3 |
| Gas shader | GAS tag | Not a V3 state. Could revisit as physics-derived (very low gravity?) |

### Unaffected visuals

Post-processing shaders, hit flash, floating damage numbers, materialize effect, damage overlay, player sprite animations, camera — all independent of the tag/state system.

---

## Environment bodies

V2 environment bodies are StaticBody2Ds with tags (ACIDIC, TOXIC, LIQUID). Interactions fire through the rule engine: `acidic + breakable → corrode`, `toxic + living → damage`. Tags are the entire interaction mechanism.

V3 has no tags. Environment bodies need a different approach.

### Option A: Named objects in the pairwise cache

Treat each env body as a named object ("acid pool", "lava pit", "electric fence"). Run the creation graph at level load to get physics. Evaluate pairwise interactions with all scene objects. Env bodies participate in the cache like any other object.

**Pro:** Unified system — no special cases. The LLM decides "acid pool hits wooden crate → damage 40, add corroded" naturally.
**Con:** Env bodies need creation cache entries + pairwise evaluations. Mitigated by pairwise screening (~75% of pairs filtered as uninteresting) and level pre-warming (ship seeded `cache.db` — see [cache.md](cache.md)).

### Option B: Direct state applicators

Env bodies skip the cache entirely. Each env body has a hardcoded state it applies on contact: acid pool → `corroded`, lava → `on_fire`, electric fence → `electrified`. Damage comes from the pairwise cache between the state and the contacted object (the state interaction already handles "corroded object near wooden crate → damage").

**Pro:** No pairwise evaluation needed for env bodies. Simpler.
**Con:** Loses nuance. A "mild acid" and "concentrated acid" would apply the same `corroded` state. Damage granularity comes only from the state interaction table, not the specific env body.

### Option C: Env bodies as pairwise cache entries, but hand-authored at level design time

Level designer specifies: "acid pool: anything touching takes damage 20/s, gains corroded." This is baked into the level data, not LLM-evaluated. Functionally like V2's rule-based approach but using the pairwise cache format.

**Pro:** Predictable. Levels are hand-tuned.
**Con:** Defeats the V3 thesis that the LLM handles interactions. Adding a new object to a level with env bodies means manually authoring interactions.

### Recommendation

**Option A** is the cleanest V3 answer. Env bodies are objects with names and physics, evaluated through the same pairwise cache as everything else. The level load cost is acceptable (env bodies are known at level design time and can be pre-cached). The LLM answering "acid pool hits wooden bridge → ?" is exactly what V3 is designed for.

This means `EnvironmentBody` stops being a special node type with tags. It becomes a `GameObject` variant that's indestructible, has no sprite gen (uses level-defined ColorRect), and is pre-registered in the creation + pairwise caches.

---

## Level design

V2 levels are designed around tag names and rule IDs. Every solution path references specific tags ("create something RIGID without BREAKABLE") and specific rules ("acidic_breakable_corrode fires: 15 dmg/s"). This is deeply V2-specific.

### What changes

In V3, players don't need to know tag names — they think about materials and properties, and the LLM evaluates whether their creation survives. "Create a stone bridge" works not because stone has RIGID tag, but because the LLM evaluates "acid pool hits stone bridge → damage 5" (stone is resistant to acid, the LLM knows this).

This is actually **better for gameplay**. V2 required players to think in tags ("I need RIGID, not BREAKABLE"). V3 lets players think in real-world terms ("acid eats wood but not stone"). The LLM handles the translation.

### What stays

The level design principles from `docs/LEVEL_DESIGN.md` are version-agnostic:
- Every level requires creating objects
- The puzzle requires material/property awareness (was "tag awareness")
- Seed objects demonstrate mechanics
- Multiple solution paths
- Progressive complexity: environmental → autonomous → chain reactions
- Antagonistic objects differentiate from Scribblenauts

### What needs rewriting

- Seed object blueprints (V2 format with `tags: ["RIGID", "FLAMMABLE"]` → V3 format with physics values)
- Environment object definitions (tags → named objects in pairwise cache)
- Solution path explanations (tag-based reasoning → material-based reasoning)
- "Rules exercised" tables → "Pairwise interactions demonstrated"
- Edge case analysis (BREAKABLE priority, METALLIC corrosion rates → LLM-evaluated equivalents)

The level designs themselves (acid moat, sentry, etc.) are good puzzles worth keeping. The rewrite is format conversion, not puzzle redesign.

---

## Eval system

V2 evals test substance/tag accuracy against expected values. 7 deterministic metrics + 3 LLM judges, all V2-specific:

| V2 metric | What it tests | V3 status |
|-----------|--------------|-----------|
| Validity | Schema validity (CreatorOutput parses) | Rewrite for V3 blueprint schema |
| Substance Accuracy | Correct substance for prompt | **Delete** — no substances |
| Element Accuracy | Correct element for prompt | **Delete** — no elements |
| Category Accuracy | Correct categories for prompt | **Delete** — no categories |
| Tag Recall | Expected tags present | **Delete** — no creation-time tags |
| Interaction Surface | Enough tags for interesting interactions | Rethink — maybe "does pairwise cache produce interesting outcomes" |
| Has Signature | Visual description quality | Keep, minor rubric update |
| Faithfulness (judge) | Design matches player intent | Rewrite rubric (remove substance/tag references) |
| Delight (judge) | Would player want to experiment | Rewrite rubric (remove substance/tag references) |
| Visual Clarity (judge) | Can image model produce good sprite | Keep, remove substance/tag consistency check |

### V3 eval dimensions

New metrics to consider:

- **Physics reasonableness** — is mass/friction/bounce/gravity sensible? "Fire sword" mass=2kg, not 50000kg. Calibration examples in the prompt should handle this, but eval verifies
- **Physics consistency** — does creation cache work? Same name → same physics across runs
- **Affordance accuracy** — horse=mount, sword=carry, wall=nothing
- **Autonomous accuracy** — zombie=yes, sword=no
- **Pairwise quality** — fire sword + wooden shield → high damage + on_fire? Eval could use extracted V2 rules_data.py interaction pairs as ground truth
- **Creature behavior quality** — zombie + donut → approach + eat? firefighter + fire → approach + remove on_fire?

### Reference data to extract from V2 before deleting

**From `engine/rules_data.py`** — 56 rules encode expected interaction outcomes. Convert to eval fixtures:
```
fire/heat + wood/flammable → damage + on_fire
acid + glass/breakable → high damage + corroded
heavy + glass/breakable → crush damage
electric + wet → amplified damage
cold + liquid → frozen
```
These are the ground truth for pairwise cache quality testing.

**From `models/substances.py`** — SUBSTANCE_PROFILES provide reference physics values:
```
metal: mass=8, friction=0.4, state=solid
wood: mass=2, friction=0.6, state=solid
water: mass=1, friction=0.1, state=liquid
fire: mass=0.1, friction=0.0, state=energy
```
Useful for calibrating physics reasonableness checks.

---

## Docs to archive

Move to `docs/archive/` — these describe V2 systems now documented in `docs/v3-design/`:

| Doc | Why archive |
|-----|------------|
| `docs/ARCHITECTURE.md` | Entire doc is V2 (PydanticAI agent, substance profiles, rule engine, tag matching) |
| `docs/GAME_DESIGN.md` | Tag system, substance system, 56 rules, behavior verbs — all V2 |
| `docs/object-system-v2.md` | V2 by name |
| `docs/action-plan.md` | V2 roadmap |

Keep as-is: `scribblenauts-deep-dive.md`, `llm-behavior-systems.md`, `ANIMATION_PIPELINE.md`, `LEVEL_DESIGN.md` (version-agnostic or applicable with updates).

### CLAUDE.md

Don't rewrite until V3 code exists. Add a note at the top: "V2 architecture below. See docs/v3-design/ for V3 design." CLAUDE.md should describe running code, not planned code.
