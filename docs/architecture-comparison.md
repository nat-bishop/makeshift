# Architecture Comparison: Scribblenauts' Objectnaut vs. Makeshift

Design memo comparing the Objectnaut engine (5th Cell, 2009–2013) with our current architecture. Each section references actual files and functions in our repo and specific Scribblenauts patterns documented in the [compass research](compass_artifact_wf-daccc8ce-6234-4074-ac83-eaf097fd2a40_text_markdown.md).

---

## STEAL — Scribblenauts patterns we should adopt

### 1. Prototype-based source objects

**Scribblenauts pattern:** Every object inherited from a concrete **Source Object** — a prototype template that pre-filled most hidden properties. A checkbox toggled "inherit vs. override." This meant creating "zombie firefighter" was cheap: clone Zombie, override a few fields. The ~22,802 dictionary entries mapped to only ~4,000 unique visual objects because synonyms shared prototypes.

**Our gap:** Every object is generated from scratch. `creator/agent.py:create_object()` sends the full system prompt to Gemini for every request, with no concept of "this is basically a Sword but on fire." The LLM re-derives tags, visual descriptors, and names each time with no anchoring to known-good archetypes.

**Recommendation:** Build a **prototype library** — a curated set of ~50–100 `GameObjectBlueprint` records (defined in `models/blueprint.py`) covering common archetypes (sword, shield, potion, rock, torch, etc.). At creation time, `create_object()` should first attempt to match the player's description to a prototype via embedding similarity or keyword match, then ask the LLM to produce a *delta* from that prototype rather than generating from zero. This would:
- Reduce LLM token cost (smaller prompt, constrained output)
- Improve consistency (similar descriptions anchor to similar base stats)
- Mirror the Objectnaut workflow: "plop it in under a category, which already gives it a bunch of properties; from there we just tweak it"

The 15 seed objects already created per session (in `routers/sessions.py`) are a natural starting point for this library.

### 2. Identity-override field ("Objects React To It As If It's A")

**Scribblenauts pattern:** The **"Objects React To It As If It's A"** field decoupled an object's *name* from its *behavioral archetype*. A "zombie firefighter" had the name "zombie firefighter" but other AI entities treated it as a Zombie for interaction purposes. This was the single most powerful field in the Object Editor — it made multi-category membership work by giving each object a canonical behavioral identity.

**Our gap:** Our rule engine (`engine/resolver.py:RuleResolver.find_matching_rules()`) matches purely on tag sets. There's no concept of "this object *behaves like* a torch even though it's called 'enchanted candelabra.'" Two objects with identical tags interact identically, regardless of name or intent. This collapses meaningful distinctions — a "campfire" and a "flaming sword" with tags `[HEAT_SOURCE, HOT, SOLID]` are interchangeable to the rule engine.

**Recommendation:** Add an `archetype: str` field to `CreatorOutput` in `models/blueprint.py`. The LLM would assign a canonical archetype from a fixed vocabulary (e.g., "weapon," "light_source," "container," "creature," "barrier"). Rules in `engine/rules_data.py` could then include archetype-aware conditions alongside tag conditions, enabling rules like "creatures flee from weapons" without requiring a WEAPON tag that conflates behavior with physical property.

### 3. Trigger→action scripting for object lifecycle events

**Scribblenauts pattern:** The Scripting tab exposed a **trigger→action event model** with hard limits: max 3 actions per trigger, max 3-second wait. Triggers included "is created," "is destroyed," "gets eaten," "touches an object," "is used while equipped." Actions included adding/removing adjectives, creating objects, dealing damage, and playing animations. This gave designers a lightweight way to define *reactive behavior* without writing code.

**Our gap:** Our `EffectExecutor` (`godot/scripts/systems/effect_executor.gd`) handles effects only during collision resolution. There's no lifecycle hook system — objects can't react to being created, destroyed, equipped, or dropped. The 14 `EffectType` values in `engine/resolver.py` are collision-only. A torch can't "ignite when equipped" or "spawn smoke when destroyed" because those events aren't wired into the effect system.

**Recommendation:** Extend `GameObjectBlueprint` with an optional `lifecycle_hooks` field — a compact list of trigger→effect pairs drawn from the same `EffectType` enum we already have. The LLM would generate these at creation time. Triggers: `on_create`, `on_destroy`, `on_equip`, `on_unequip`, `on_idle` (timed). Effects: reuse existing effect types from `engine/resolver.py`. On the Godot side, `game_object.gd` already has `_on_body_entered` for collisions — adding `_on_equipped()` and `_on_destroyed()` hooks would be straightforward. Cap at 2–3 hooks per object to bound complexity, exactly as Scribblenauts did.

### 4. Material sub-categories as gameplay-relevant properties

**Scribblenauts pattern:** Material sub-categories — Metal, Plastic, Fabric, Stone, Wood, Glass, Paper — were first-class gameplay properties. Metal objects were heavy, fire-immune, and magnet-attractable. Wooden objects were flammable. Glass was breakable. These weren't just visual descriptors; they drove physics and interaction rules.

**Our gap:** `VisualDescriptor` (`models/blueprint.py`) has only `visual_description` (free text) and `size_category` — both visual-only, used in `images/pipeline.py:build_prompt()` to generate the sprite prompt. The actual gameplay behavior is driven entirely by tags. A "wooden shield" and a "metal shield" with identical tags behave identically in `CollisionResolver`.

**Recommendation:** Either promote material to a gameplay-relevant field with a material→tag mapping (e.g., "wood" auto-adds `FLAMMABLE`, "metal" auto-adds `CONDUCTING + HEAVY`, "glass" auto-adds `BREAKABLE + REFLECTIVE`), or — simpler — add a `check_material_tag_consistency` validator to `CreatorOutput` that uses `ModelRetry` (as the existing `check_contradictions` validator does in `models/blueprint.py`) to ensure the LLM assigns tags consistent with the stated material. The latter approach keeps the tag system as the single source of gameplay truth while reducing the chance of "metal flammable sword" hallucinations.

### 5. Multi-category membership for richer interaction targeting

**Scribblenauts pattern:** Objects belonged to multiple categories simultaneously. Apple was "Food" AND "Fruit" AND "Classroom." A lion's "Eat Food" rule matched anything tagged Food — including apples, hamburgers, and humans holding food. This multi-membership was the core mechanism driving emergent behavior.

**Our gap:** Our tag system is flat — 33 `Tag` values in `models/tags.py` with no hierarchy. Tags describe physical properties (SOLID, FLAMMABLE, SHARP) but not *identity categories* (Food, Weapon, Creature, Furniture). The rule engine in `engine/rules_data.py` can only express "SHARP + BREAKABLE → damage" — it cannot express "any Food near any Creature → Creature eats Food" because Food and Creature aren't in the tag vocabulary.

**Recommendation:** Introduce a small set of **semantic category tags** (5–10) alongside existing physical tags: CREATURE, FOOD, WEAPON, TOOL, FURNITURE, CONTAINER, CLOTHING, NATURAL. These would occupy a separate budget or be free (since they describe identity, not power). The LLM already infers these categories implicitly — making them explicit lets rules target them. This directly enables the behavior-verb patterns from Scribblenauts (Section 2 of the compass doc) without building a full AI behavior system.

### 6. "Spectacular Failure" as a design principle

**Scribblenauts pattern:** Liz England's GDC 2018 microtalk — "Designing for Spectacular Failure" — codified what the team learned: **the system should fail in entertaining ways rather than trying to prevent failure.** When a player glues steak to a lion and it eats itself, that's a bug, but it's a *fun* bug. The design goal is to make failures spectacular rather than boring or broken.

**Our gap:** Our `check_contradictions` validator in `models/blueprint.py` hard-rejects 12 contradiction pairs via `ModelRetry`. Our cascade system (`collision_resolver.gd`, max depth 3, 96px radius) caps chain reactions. These are reasonable safety rails, but we have no philosophy for what happens when the system *does* produce something weird. The `interaction_feedback.gd` HUD element shows effect messages, but there's no system for making surprising interactions memorable or shareable.

**Recommendation:** This is a design-philosophy adoption, not a code change. When extending rules or effects, bias toward "interesting and visible" over "correct and invisible." Example: if a FROZEN + EXPLOSIVE object is created (not contradicted), let it detonate into ice shards rather than silently failing. The `EventBus.interaction_triggered` signal already broadcasts effect messages — lean into making those messages entertaining for edge cases.

---

## AVOID — Patterns our LLM approach makes obsolete or that were acknowledged mistakes

### 1. Six months of Wikipedia dictionary research

**Scribblenauts cost:** Five team members spent six months scouring Wikipedia, dictionaries, and encyclopedias to build the 22,802-word dictionary. Liz England was IP-banned from Google for excessive thesaurus use. The entire process was "hand authored 1 by 1 & lots of crunch."

**Why we skip it:** Our `creator/agent.py` replaces this entire pipeline. The LLM *is* the dictionary — it maps any player description to a structured `CreatorOutput` with tags, visual descriptors, and a name. The six-month research phase is compressed to a ~2-second API call. We should never attempt to pre-enumerate a dictionary of valid objects.

### 2. Hand-sorting adjectives into synonym groups

**Scribblenauts cost:** England downloaded ~80,000 adjectives from a public-domain dictionary and sorted them by hand into synonym groups and categories. Most were deleted. The final game shipped with ~10,000 adjectives. This was a purely subjective undertaking shaped by one person's biases.

**Why we skip it:** We don't have a discrete adjective system. Player descriptions are free-text, and the LLM interprets modifiers contextually. "Rusty sword" vs. "ancient sword" vs. "corroded blade" all flow through `create_object()` and produce different but contextually appropriate tag sets. There's no synonym table to maintain. The tradeoff is that we lose Scribblenauts' runtime adjective *application* (modifying objects after creation), but we were never going to ship 10,000 pre-authored adjective deltas.

### 3. Per-object exception authoring (the 80% problem)

**Scribblenauts cost:** England's core insight: "the hand-authoring phase dwarfed the systematic phase." The team spent ~80% of development time getting individual object properties right before a single level could function. The vegetarian ate hamburgers. The cop didn't go for the donut. The mongoose couldn't beat the cobra without becoming overpowered. Every fix was a hand-authored exception, and the exception space was infinite.

**Why we skip it:** Our LLM generates context-aware defaults. When a player creates a "vegetarian chef," the system prompt in `creator/agent.py` guides the LLM to assign culturally appropriate tags — it won't inherit a generic "human eats all food" rule because there is no inheritance. Each object is authored individually by the LLM with full context. The tradeoff is consistency (see NEW RISKS §1), but the per-object exception problem simply doesn't exist in our architecture.

### 4. Category-based AI that can't handle cultural exceptions

**Scribblenauts problem:** The nine behavior verbs targeted *categories*, not individuals. "All humans eat Food" was a single rule. This was elegant but brittle — the cop/donut problem, the vegetarian/hamburger problem, and the "if you glue steak to a lion, will it eat itself?" problem all stem from category-level rules that don't account for cultural context.

**Why we avoid it:** Our rule engine (`engine/resolver.py`) operates on tag sets, not object categories. Rules like `heat_flammable_ignite` in `rules_data.py` express physical interactions ("things with HEAT_SOURCE ignite things with FLAMMABLE"), not behavioral ones ("creatures eat food"). This is deliberately lower-level — we avoid the category-AI layer entirely. If we adopt semantic categories (STEAL §5), we should learn from Scribblenauts and keep category-targeted rules limited to physical/mechanical interactions, not cultural behaviors.

### 5. Static pairwise balance tuning

**Scribblenauts problem:** The mongoose-vs-cobra dilemma: "very difficult to fix without making the mongoose too OP." Any stat change that fixed one matchup created ripple effects across hundreds of others. Balance was attempted through hand-tuning individual stat values — Health (max 1,500), Weapon Damage (max 100) — with no formal point-budget system.

**Why we avoid it:** We have an explicit **tag power budget** (`OBJECT_TAG_BUDGET = 10` in `models/tags.py`) with per-tag costs (1–5). This is a formal constraint the LLM must satisfy, enforced by the `check_budget` validator in `models/blueprint.py`. We don't need to balance individual matchups because the budget caps the total "power" of any single object. A player can't create an invincible object because EXPLOSIVE alone costs 5, leaving only 5 points for other tags. This is the formal point-budget system Scribblenauts never had.

### 6. Localization as a parallel dictionary nightmare

**Scribblenauts cost:** 12 localizations required maintaining separate dictionaries with different systems for game text vs. object words. German words overflowed character limits. Version control across dozens of dictionary files was "a nightmare."

**Why we skip it:** Our objects are created from free-text descriptions. Localization would mean localizing the UI and system prompt in `creator/agent.py`, not maintaining parallel object dictionaries. The LLM handles multilingual input natively. This doesn't eliminate localization work, but it eliminates the dictionary-per-language problem entirely.

---

## NEW RISKS — Problems unique to us that Scribblenauts never faced

### 1. Non-determinism: same description, different objects

**The problem:** Scribblenauts' hand-authored database returned identical results every time. Our LLM may assign different tags, names, and visual descriptors to "fire sword" on different runs. `create_object()` in `creator/agent.py` has a `temperature=0` equivalent (via PydanticAI's deterministic settings), but LLM outputs are fundamentally stochastic. Two players creating "fire sword" in different sessions may get different objects with different capabilities.

**Where it bites:** The rule engine (`engine/resolver.py:find_matching_rules()`) produces different interaction outcomes for objects with different tag sets. If Player A's "fire sword" has `[HEAT_SOURCE, SHARP, SOLID, RIGID]` and Player B's has `[HOT, FLAMMABLE, SHARP, SOLID]`, they interact with the world differently. The `HEAT_SOURCE` version ignites flammable objects; the `HOT + FLAMMABLE` version gets ignited *by* heat sources. This is a gameplay-significant divergence from an identical input.

**Mitigation:** The prototype library (STEAL §1) would anchor common descriptions to consistent base stats. For the long tail, we should accept non-determinism as a feature ("your fire sword is unique") rather than fighting it — but log and monitor tag distributions to catch systematic drift.

### 2. Latency: object creation is not instant

**The problem:** In Scribblenauts, typing "jetpack" and pressing Enter spawned the object instantly — the 22,000-entry database was a local lookup. Our pipeline requires: LLM API call (~1–3s) → background Gemini image generation → WebSocket sprite delivery. The immediate response from `routers/objects.py` returns a blueprint, but the sprite arrives asynchronously. The client enters a materialize animation while waiting.

**Where it bites:** There's a perceptible delay between "I typed something" and "I have a usable object with a sprite," and a longer delay before the object *looks* like what I described. This breaks the Scribblenauts magic of instant materialization.

**Mitigation:** The materialize-animation-while-waiting approach is already the right approach. To improve perceived speed: (a) expand the prototype library with pre-generated sprites for common objects, (b) consider client-side sprite prediction or pre-fetching for likely descriptions, (c) lean into the delay as a game mechanic ("the object is materializing..."). Do not attempt to make the LLM call synchronous with gameplay — that path leads to unplayable latency spikes.

### 3. Cost ceiling: every object costs real money

**The problem:** Scribblenauts had no marginal cost per object — the dictionary was pre-authored and shipped on the cartridge. Our system charges $0.041 per object (tracked in `sessions/manager.py:track_cost_and_save_object()`), with a session budget of $1.00 (`budget_limit` in the sessions table). That's ~24 objects per session. Scribblenauts players could summon hundreds of objects per level.

**Where it bites:** The budget constraint in `routers/objects.py` returns HTTP 402 when the session budget is exhausted. Players who want to experiment broadly — Scribblenauts' core appeal — hit a hard wall. The 15 seed objects per session help, but 24 total objects is a fraction of what Scribblenauts allowed.

**Mitigation:** The prototype library (STEAL §1) could serve common objects without LLM calls, reserving the budget for novel creations. Sprite caching by prompt hash (`images/pipeline.py:_prompt_hash()`) already avoids redundant image generation for identical prompts. Consider a tiered system: prototype-based objects are free, LLM-generated objects cost budget. This aligns with Scribblenauts' own DS-era "Budget Meter" for simultaneous objects — but our constraint is economic, not hardware.

### 4. Hallucinated properties: plausible but mechanically incoherent objects

**The problem:** Scribblenauts' hand-authored objects were mechanically consistent by construction — a designer assigned each property intentionally. Our LLM may generate tag combinations that are technically valid (pass `check_contradictions` and `check_budget`) but mechanically nonsensical. A "lightweight anvil" with tags `[LIGHT, SOLID, RIGID]` passes all validators but violates player expectations. A "healing potion" might get `[LIQUID, TOXIC]` because the LLM conflates "potion" with "chemical."

**Where it bites:** The 12 contradiction pairs in `models/tags.py:TAG_CONTRADICTIONS` catch obvious physical impossibilities (FROZEN↔MOLTEN, HEAVY↔LIGHT) but not semantic incoherence. The system prompt in `creator/agent.py` provides guidance, but the LLM has no grounding in our specific game mechanics — it doesn't know that TOXIC means "applies DOT corrosion damage" in our `effect_executor.gd`, not "is a chemical substance."

**Mitigation:** Expand the validation layer in `models/blueprint.py` with **semantic validators** — not just contradiction pairs, but heuristic checks: if name contains "healing" or "potion," flag TOXIC/CORROSIVE tags for ModelRetry. The prototype library (STEAL §1) would also help here — anchoring to a known-good "potion" prototype prevents the LLM from hallucinating inappropriate tags. Long-term, consider a post-creation "common sense" validation pass.

### 5. Tag vocabulary ceiling: 33 tags vs. ~50 property fields

**The problem:** Scribblenauts' Object Editor exposed ~50 distinct property fields across 10 tabs, including nuanced properties like Buoyancy (float/sink/neutral), Jump Height (5-step enum), Movement Mode (walk/swim/fly/hover), Container Size, and Weapon Type (8 subtypes). Our tag system has 33 `Tag` values in `models/tags.py` that are primarily physical properties. We have no equivalent of movement modes, container behavior, weapon subtypes, or the rich equipment system (Can Wear Hats, Can Sit On Things, Can Pick Things Up).

**Where it bites:** Player descriptions like "a flying carpet," "a box that holds things," or "a gun that shoots fireballs" map poorly to our tag vocabulary. FLOATING is the closest to flight but doesn't distinguish hover from fly. There's no CONTAINER tag. TOOL doesn't distinguish melee from ranged. The LLM is forced to approximate rich concepts with a coarse tag set, and the rule engine in `engine/rules_data.py` can't express interactions that depend on properties we don't model.

**Mitigation:** This is a deliberate design tradeoff — 33 tags keep the system learnable and the budget math simple. Resist the temptation to grow to 50+ tags. Instead, address specific gaps through the archetype field (STEAL §2) and lifecycle hooks (STEAL §3). A "flying carpet" doesn't need a FLY tag if it has archetype "vehicle" and tags `[FLOATING, WEARABLE, FLEXIBLE]`. A "treasure chest" doesn't need a CONTAINER tag if it has a lifecycle hook `on_interact → spawn contained object`. Extend through composition, not vocabulary expansion.

### 6. Sprite cache collision: prompt text as deduplication key

**The problem:** Our sprite cache keys on the full `build_prompt()` output (`images/pipeline.py:_prompt_hash()`), which means two objects with the same name + `visual_description` share a sprite — even if they have different tags and gameplay behavior. Scribblenauts had ~4,000 unique visual assets explicitly mapped to objects; we generate on demand and deduplicate aggressively.

**Where it bites:** A "fire sword" with a generic `visual_description` and another "fire sword" created later will hit the same cache entry regardless of different intended tags or aesthetics. Conversely, slight LLM variation in `visual_description` phrasing causes cache misses and redundant Gemini API calls for visually near-identical intended objects.

**Mitigation:** The LLM should be prompted to include gameplay-relevant visual cues in `visual_description` — a TOXIC sword should mention dripping green liquid to distinguish it from a HEAT_SOURCE sword with flames. This ties the visual description to tags, making cache hits more semantically meaningful. This is partially handled by the system prompt in `creator/agent.py` but could be more intentional.

### 7. No QA history: every LLM-generated object is untested

**The problem:** Scribblenauts shipped with a finite dictionary that QA could (partially) test. Despite Slaczka's admission that exhaustive testing was impossible, the team did test common interactions and patch known exploits across releases. Our objects have zero QA history — every LLM-created object is a novel entity entering the rule engine for the first time.

**Where it bites:** The 55 rules in `engine/rules_data.py` were authored assuming reasonable tag combinations. An LLM-generated object with an unusual tag set (e.g., `[EXPLOSIVE, CONDUCTING, BOUNCY, LIGHT]`) could trigger unexpected rule chains in `collision_resolver.gd`'s cascade system (depth 3, radius 96px). The cascade cap prevents infinite loops, but doesn't prevent a single object from triggering a screen-clearing chain reaction on first contact.

**Mitigation:** Add a **pre-flight simulation** step: before placing an LLM-generated object in the world, run its tag set through `RuleResolver.find_matching_rules()` against common environmental tags (SOLID+RIGID for terrain, HEAT_SOURCE for torches, LIVING for creatures) and flag objects that trigger 3+ rules or any cascade-eligible rule at priority ≥ 15. This doesn't prevent weird interactions — it surfaces them for the player ("Warning: this object is highly reactive") or for a future balance log.

---

## Summary

| Category | Count | Key theme |
|----------|-------|-----------|
| **STEAL** | 6 patterns | Scribblenauts solved the *structure* problem — prototype inheritance, identity overrides, lifecycle hooks, material-as-gameplay, multi-category membership, and spectacular failure. We should adopt the structural patterns even though we don't need the *content* pipeline. |
| **AVOID** | 6 patterns | The LLM eliminates Scribblenauts' *authoring bottleneck* — dictionary research, adjective curation, per-object exceptions, category-AI edge cases, pairwise balance tuning, and localization dictionaries. These were the 80% of development time we don't need to spend. |
| **NEW RISKS** | 7 risks | Our problems are *runtime* problems — non-determinism, latency, cost, hallucination, vocabulary limits, cache collisions, and zero QA history. Scribblenauts' problems were *authoring-time* problems. We've traded a six-month upfront cost for ongoing per-request risk. |

The single highest-leverage action across all three sections is **building the prototype library** (STEAL §1). It addresses non-determinism (NEW RISKS §1) by anchoring common objects, reduces cost (NEW RISKS §3) by serving prototypes without LLM calls, mitigates hallucination (NEW RISKS §4) by constraining the LLM to deltas from known-good archetypes, and directly implements the pattern that made Objectnaut efficient enough to ship 22,000 objects on a 4 MB handheld.
