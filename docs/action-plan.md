# Unified Action Plan

Cross-referenced from five analyses: [Gut Check](gut-check.md), [Design Review](design-review.md), [Architecture Comparison](architecture-comparison.md), [Balance Stress Test](balance-stress-test.md), [LLM Validation Audit](llm-validation-audit.md).

Items flagged by multiple documents are marked with the number of sources. Contradictions between documents are called out inline.

---

## DO NOW — Bugs and broken mechanics

These are things that are actively broken in the current build. Most are code-level fixes with bounded scope.

### 1. DOT timer stacking is unlimited (severity 8/10)

**Sources:** Balance Stress Test (Finding 1, Objects 2/4/6/7/10)

`effect_executor.gd:_apply_dot()` spawns a new Timer child on every call with no deduplication. A CORROSIVE weapon held against a target stacks to 90+ DOT DPS from a single source. Every IGNITE and CORRODE interaction in the game has this bug.

**Fix:** Before spawning a new DOT timer, check if the target already has one of the same type. If so, refresh duration instead of stacking. See Balance Stress Test Fix 1 for implementation.

**Files:** `godot/scripts/systems/effect_executor.gd`

### 2. Equipment tag stacking has no cap (severity 10/10)

**Sources:** Balance Stress Test (Finding 2, Object 9)

Three max-budget items give the player 8 effective tags, 170 DPS, floating mobility, and auto-targeting. The per-object budget of 10 is meaningless when the effective player tag budget is 30. This is the game's jetpack+rope — it trivializes all content.

**Fix:** Cap total transferred tags across all equipment slots to 4 (tunable). See Balance Stress Test Fix 2.

**Files:** `godot/scenes/player/player_equipment.gd`

### 3. Block/insulation rules are cosmetic (severity 7/10)

**Sources:** Balance Stress Test (Finding 3, Object 5), LLM Validation Audit (§1 — INSULATING+CONDUCTING gap)

The three "block" rules (`electric_insulating_block`, `insulating_heat_block`, `insulating_cold_block`) have the highest priority but zero mechanical effect. All matching rules fire regardless of priority — there is no preemption. A player who crafts a shield expecting defense gets damage + a reassuring "blocked!" message. This is a trust-breaking UX bug.

**Fix:** Add a rule preemption/channel system. Block rules suppress lower-priority damage rules in the same channel (electric, thermal, cold). See Balance Stress Test Fix 3.

**Files:** `godot/scripts/systems/collision_resolver.gd`, `backend/app/engine/rules_data.py`, `backend/app/models/rules.py`

### 4. Missing contradiction pairs

**Sources:** LLM Validation Audit (§1), Balance Stress Test (Object 5)

CONDUCTING + INSULATING are defined as conceptual opposites but aren't in the contradiction list. The LLM can generate objects with both, wasting budget and confusing players. REFLECTIVE + STICKY is also mechanically incoherent.

**Fix:** Add to `TAG_CONTRADICTIONS` in `tags.py`:
- `frozenset({Tag.CONDUCTING, Tag.INSULATING})` — most urgent
- `frozenset({Tag.REFLECTIVE, Tag.STICKY})`

**Files:** `backend/app/models/tags.py`

### 5. Force/mass creates absurd velocities (severity 7/10)

**Sources:** Balance Stress Test (Finding 4, Objects 6/7)

Force impulses (100–500) on GAS objects (mass 0.01) produce 50,000 px/s acceleration. Objects leave the playable area permanently. No velocity cap exists.

**Fix:** Cap resulting velocity from force application to ~800 px/s. See Balance Stress Test Fix 4.

**Files:** `godot/scripts/systems/effect_executor.gd`

### 6. Input normalization and temperature pinning

**Sources:** LLM Validation Audit (§3, §4C, §4D), Architecture Comparison (NEW RISKS §1)

"Fire Sword", "fire sword", "a fire sword" produce different LLM outputs. Default temperature adds sampling variance on top.

**Fix (two changes, both zero/low risk):**
- Normalize input: lowercase, strip articles, collapse whitespace. In `creator/agent.py` before `agent.run()`.
- Set `temperature: 0` in `model_settings`. Consistency > novelty for gameplay-determining tags.

**Files:** `backend/app/creator/agent.py`

---

## DO SOON — Design improvements, medium effort

These improve the player experience and system robustness but aren't blocking bugs.

### 7. System prompt: cultural consensus guidance

**Sources:** LLM Validation Audit (§2, §4F), Architecture Comparison (NEW RISKS §4)

The LLM generates encyclopedically accurate but culturally wrong tags — a feather gets SHARP (quill tip), a campfire gets TOOL (cooking), a balloon gets SOLID. The system prompt has two examples but no cultural-consensus principle.

**Fix:** Add a "Cultural Consensus Rule" section to the system prompt with 4–6 counter-examples and the heuristic: "what would a 10-year-old expect this object to do?" Add soft-warnings for debatable combos (FLAMMABLE+FROZEN, LIVING+GAS, EXPLOSIVE+INSULATING).

**Files:** `backend/app/creator/agent.py`

### 8. Semantic coherence validator

**Sources:** LLM Validation Audit (§4B), Architecture Comparison (NEW RISKS §4)

A fourth `@field_validator` on `CreatorOutput` catching the most common mismatches: TOOL requires SOLID or RIGID, WEARABLE requires SOLID or FLEXIBLE, LIVING discourages RIGID. Cheap dict-lookup, raises `ModelRetry` with specific guidance.

**Files:** `backend/app/models/blueprint.py`

### 9. Show tags on object creation ("the one thing I'd fix first")

**Sources:** Design Review (§"Where Players Will Be Confused", §"The One Thing I'd Fix First")

When an object is created, the panel just closes. No tag display, no cost, no reveal. The tag system is the primary mechanic and it's almost entirely hidden. Players don't know what they made or what it can do.

**Fix:** After creation, show a card with: name, tags (with colors/icons), size category, power cost. Make it feel like pulling something from a hat, not submitting a form.

**Files:** Godot UI scenes (creation panel)

### 10. Visible budget meter

**Sources:** Design Review (§"The budget is invisible pressure")

Players discover they're out of budget only when creation fails with an error. Budget scarcity should be a strategic resource, not a surprise paywall.

**Fix:** Show remaining creations on the HUD. "6 creations left" is a meaningful choice. "Budget exceeded" is frustration.

**Files:** Godot HUD scenes

### 11. Tag decay for cascade-added tags

**Sources:** Balance Stress Test (Finding 5, Objects 3/4/7/10)

Tags added by cascade (ELECTRIC, HEAT_SOURCE, HOT, TOXIC) persist forever. A level that experiences one cascade chain becomes permanently hazardous. No decay, no expiration, no cleanup.

**Fix:** Cascade `ADD_TAG` effects pass a duration (e.g., 10s ELECTRIC, 15s HOT, 8s TOXIC). Tag auto-removes after expiry. See Balance Stress Test Fix 5.

**Files:** `godot/scenes/game_object/game_object.gd`, `godot/scripts/systems/effect_executor.gd`

### 12. Material→tag consistency

**Sources:** Architecture Comparison (STEAL §4), LLM Validation Audit (§2 — glass vase example)

`material` on `VisualDescriptor` is visual-only. A "wooden shield" and "metal shield" with identical tags behave identically. A "glass vase" can get CONDUCTING when glass is an insulator.

**Fix (simpler of two options):** Add a `check_material_tag_consistency` validator that uses `ModelRetry` to ensure tags match the stated material. "wood" should imply FLAMMABLE, "metal" should imply CONDUCTING, "glass" should not have CONDUCTING. Keeps tags as single source of truth.

**Files:** `backend/app/models/blueprint.py`

### 13. Description-keyed result cache

**Sources:** LLM Validation Audit (§4E), Architecture Comparison (NEW RISKS §1)

Cache `CreatorOutput` by normalized description. First player to create "fire sword" defines it for everyone — same tags, same visuals. Turns the LLM into a progressive dictionary. Reduces non-determinism and cost simultaneously.

**Implementation:** In-memory dict for v1 (lost on restart). Upgrade path: persist to SQLite `object_templates` table.

**Files:** `backend/app/creator/agent.py` (or new `creator/cache.py`)

---

## DO EVENTUALLY — Architectural evolution

These are larger design changes that address the structural gaps between our game and the Scribblenauts reference. Each is a significant feature, not a patch.

### 14. Prototype library (highest-leverage single change)

**Sources:** Architecture Comparison (STEAL §1 — "single highest-leverage action"), LLM Validation Audit (§4E), Gut Check (§2 — implicit)

~50–100 curated `GameObjectBlueprint` archetypes (sword, shield, potion, torch...). At creation time, match the player's description to a prototype, then ask the LLM to produce a *delta*. Addresses: non-determinism (anchors common objects), cost (serve prototypes without LLM calls), hallucination (constrain to known-good base), latency (pre-generated sprites for common items).

The 15 seed objects are a natural starting point.

### 15. Archetype / identity-override field

**Sources:** Architecture Comparison (STEAL §2), Gut Check (§1 — "Objects React To It As If It's A")

Add `archetype: str` to `CreatorOutput` from a fixed vocabulary ("weapon", "creature", "light_source", "container"...). Decouples name from behavioral identity. Enables rules like "creatures flee weapons" without a WEAPON tag. The field Scribblenauts considered most powerful in their editor.

### 16. Autonomous object behavior / behavior verbs

**Sources:** Gut Check (§1 — central thesis), Design Review (§"Where Players Will Be Bored"), Architecture Comparison (STEAL §3, §5)

The game's biggest missing feature. Objects have no agency — a wolf and a sheep in the same level just sit there. Scribblenauts had 9 behavior verbs (destroy, eat, investigate, follow, protect, use, ride, steal, run away) that made the world alive.

**Approach:** Start with tick-based tag-seeking: HOSTILE seeks LIVING, BURNING seeks FLAMMABLE, ELECTRIC seeks CONDUCTIVE. Target categories, not individuals. Keep rules mechanical, not cultural (per Architecture Comparison AVOID §4).

> **Contradiction:** Architecture Comparison STEAL §5 recommends semantic category tags for behavior targeting, but Architecture Comparison AVOID §4 warns against category-based AI that can't handle cultural exceptions. **Resolution:** Use categories for *physical/mechanical* interactions only (predator→prey, fire→fuel), not cultural ones (cop→donut).

### 17. Modifier / adjective system

**Sources:** Gut Check (§3 — "the creative core of the game")

Players can't modify objects after creation. No "make it bigger", "set it on fire", "freeze it". Every creative act is a full LLM call. The deepest Scribblenauts engagement came from modifying and combining, not just summoning.

> **Tension with:** Architecture Comparison AVOID §2, which says we were "never going to ship 10,000 pre-authored adjective deltas." **Resolution:** Don't pre-author adjective deltas. Instead, define ~20 modifier verbs as tag transforms (e.g., "burning" = add HEAT_SOURCE + HOT, "frozen" = add FROZEN + COLD, "giant" = change size_category to LARGE). Player applies modifiers cheaply (no LLM call, low/no budget cost). The LLM already handles the initial creation; modifiers are deterministic post-creation transforms.

### 18. Numeric property layer (degree, not just kind)

**Sources:** Gut Check (§2), Architecture Comparison (NEW RISKS §5)

Tags are boolean. A "rusty dagger" and "enchanted greatsword" both get SHARP and deal the same 25 damage. No health, damage, speed, weight, or temperature as continuous values. The LLM generates rich descriptions that the game flattens to on/off switches.

> **Tension with:** Architecture Comparison NEW RISKS §5 ("resist the temptation to grow to 50+ tags") and the principle of keeping the system learnable. **Resolution:** Don't expand tags. Add a small set of numeric properties *alongside* tags: `damage_multiplier` (0.5–2.0), `durability`, `weight`, `speed`. The LLM fills these as part of `CreatorOutput`. Rules reference `damage * damage_multiplier` instead of fixed values. Keeps tag count at 33 but adds gradation.

### 19. Lifecycle hooks (trigger→action scripting)

**Sources:** Architecture Comparison (STEAL §3)

Objects can't react to being created, destroyed, equipped, or dropped. Scribblenauts had a trigger→action system (max 3 actions, max 3s wait). A torch can't "ignite when equipped" or "spawn smoke when destroyed."

**Fix:** Add optional `lifecycle_hooks` to `GameObjectBlueprint` — trigger→effect pairs from the existing `EffectType` enum. Triggers: `on_create`, `on_destroy`, `on_equip`, `on_unequip`. Cap at 2–3 hooks per object.

### 20. Sandbox / freeplay mode

**Sources:** Design Review (§"Where Players Will Be Bored" — "the biggest missing piece")

After 3 short levels, there's nothing to do. The tag system supports 55 rules and dozens of emergent combos. A freeplay area with no objective, generous budget, and room to experiment is where players would spend 80% of their time.

### 21. Visual state changes and juice

**Sources:** Design Review (Visual feedback C, Sound/juice D), Architecture Comparison (STEAL §6 — spectacular failure)

Objects don't visually change when affected. A burning plank looks the same as a normal plank. No fire particles, no frost effects, no screen shake, no audio. The systems create spectacular failures but the presentation whispers them.

### 22. Semantic category tags

**Sources:** Architecture Comparison (STEAL §5)

5–10 identity-category tags (CREATURE, FOOD, WEAPON, TOOL, FURNITURE, CONTAINER, CLOTHING, NATURAL) alongside existing physical tags. These describe what something *is*, not what it *does*. Enables behavior rules like "CREATURE near FOOD → eat." Free or separate budget since they describe identity, not power.

> **Note:** Only valuable after behavior verbs (item 16) are implemented. Without autonomous behavior, category tags have no rules to target.

---

## Contradictions between documents

### A. Tag vocabulary size

- Architecture Comparison STEAL §5 recommends adding 5–10 semantic category tags.
- Architecture Comparison NEW RISKS §5 says "resist the temptation to grow to 50+ tags."
- Gut Check §2 wants a numeric property layer underneath tags.

**Verdict:** These are reconcilable. Add a *small* set of semantic categories (free, identity-only). Add numeric *properties* alongside tags (separate system). Don't expand the physical tag vocabulary beyond 33.

### B. Category-based rules

- Gut Check §1 wants HOSTILE seeks LIVING, BURNING seeks FLAMMABLE (category-targeting behavior).
- Architecture Comparison AVOID §4 warns against category-based AI that can't handle cultural exceptions (cop/donut).

**Verdict:** Physical/mechanical category rules are safe. Cultural behavior rules are not. "Predators chase prey" = OK. "Cops prefer donuts" = don't.

### C. Adjective/modifier system

- Gut Check §3 strongly advocates for modifiers as the creative core.
- Architecture Comparison AVOID §2 notes we were "never going to ship 10,000 pre-authored adjective deltas."

**Verdict:** Not a real contradiction. Gut Check wants ~20 modifier *verbs* as deterministic tag transforms, not 10,000 hand-authored deltas. The authoring cost Architecture Comparison warns about doesn't apply.

### D. Object budget adequacy

- Balance Stress Test: "No single legal object is game-breaking" — the 10-point budget works for individual objects.
- Design Review: Budget creates invisible frustration; ~24 creations isn't enough.
- Architecture Comparison AVOID §5: Credits tag budget as solving Scribblenauts' balance problem.
- Balance Stress Test: But equipment stacking makes the budget meaningless (effective = 30).

**Verdict:** The per-object budget is well-designed. The problems are: (a) no system-level cap on equipment stacking (Fix 2), and (b) the budget is invisible to players (Fix 10). The budget amount ($1.00/~24 objects) is a business constraint, not a design flaw — address with the prototype library serving common objects for free.

### E. Non-determinism: bug or feature?

- LLM Validation Audit §3: Detailed concern about inconsistency across sessions.
- Architecture Comparison NEW RISKS §1: "Accept non-determinism as a feature ('your fire sword is unique')."
- LLM Validation Audit §4D: Pin temperature to 0.

**Verdict:** Reduce variance where cheap (normalization, temperature, caching) but don't fight it architecturally. Two players getting slightly different fire swords is fine. Two players getting *mechanically opposite* fire swords (HEAT_SOURCE vs HOT+FLAMMABLE) is not. The cache (item 13) solves the worst cases.

---

## Cross-reference: what each document uniquely contributes

| Document | Unique contribution | Overlap with others |
|----------|-------------------|-------------------|
| **Gut Check** | Behavior verbs, modifier system, numeric properties | Objects-as-props shared with Design Review, Architecture Comparison |
| **Design Review** | Creation UX, budget visibility, level design critique, sandbox mode, visual juice | Visual feedback shared with Architecture Comparison STEAL §6 |
| **Architecture Comparison** | Prototype library, archetype field, lifecycle hooks, material-as-gameplay, category tags | Non-determinism shared with LLM Validation; spectacular failure shared with Design Review |
| **Balance Stress Test** | DOT stacking, equipment tag cap, force/mass, tag decay, rule preemption | Block rules shared with LLM Validation (INSULATING gap) |
| **LLM Validation Audit** | Contradiction gaps, semantic validator, input normalization, temperature, result cache, cultural consensus prompt | Non-determinism shared with Architecture Comparison |

The highest-confidence items are those flagged independently by 2+ documents with consistent diagnosis and compatible proposed fixes. Items 3, 4, 6, 7, 8, 12, 13, 14, and 16 all have multi-document support.
